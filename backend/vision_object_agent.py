"""Agent asyncio orchestrant la couche vision objet (YOLO).

Trois rôles :
  1. Mode PULL — tools Gemini one-shot (detect_objects / query / count)
  2. Mode PUSH — boucles caméra + écran qui propagent au brain SNN
  3. Singleton inter-modules — partagé entre ada.py (voix) et external_bridge.py (texte)
"""
from __future__ import annotations

import asyncio
import logging
import os
import time
from collections import deque
from datetime import datetime, timedelta, timezone
from typing import Any, Awaitable, Callable

import numpy as np

from vision_deduplicator import (
    DedupConfig,
    EventType,
    ObjectEvent,
    _DetectionDeduplicator,
)
from vision_storage import _VisionStorage
from yolo_detector import YoloDetector

_LOG = logging.getLogger("vision_object")

HIGH_PRIORITY_CLASSES_EN: set[str] = {
    "Person", "Cat", "Dog", "Fire", "Knife", "Gun", "Pistol",
}
HIGH_RISK_CLASSES_EN: set[str] = {"Fire", "Knife", "Gun", "Pistol"}
DEFAULT_DB_PATH = "backend/memory/vision_timeline.db"


def _classify_risk(event: ObjectEvent) -> str:
    if event.detection.class_name in HIGH_RISK_CLASSES_EN:
        return "high"
    if event.detection.class_name in {"Person", "Cat", "Dog"} and event.event_type == EventType.APPEARED:
        return "low"
    return "none"


def _classify_attention(event: ObjectEvent) -> float:
    if event.detection.class_name in HIGH_RISK_CLASSES_EN:
        return 0.9
    if event.detection.class_name in HIGH_PRIORITY_CLASSES_EN:
        return 0.5
    if event.event_type == EventType.MOVED:
        return 0.3
    return 0.1


def _classify_movement(event: ObjectEvent) -> float:
    return 0.6 if event.event_type == EventType.MOVED else 0.2


def _hint_for(event: ObjectEvent) -> str:
    return f"{event.detection.class_fr} {event.event_type.value} sur {event.source}"


class VisionObjectAgent:
    """Singleton orchestrant les détections YOLO."""

    _singleton: "VisionObjectAgent | None" = None

    @classmethod
    def get_or_create_singleton(
        cls,
        memory_manager: Any | None = None,
        face_frame_source: Any | None = None,
        on_object_event: Callable[[dict], Awaitable[None]] | None = None,
        db_path: str | None = None,
    ) -> "VisionObjectAgent":
        if cls._singleton is None:
            cls._singleton = VisionObjectAgent(
                face_frame_source=face_frame_source,
                memory_manager=memory_manager,
                on_object_event=on_object_event,
                db_path=db_path or DEFAULT_DB_PATH,
            )
        else:
            if face_frame_source is not None and cls._singleton._face_source is None:
                cls._singleton._face_source = face_frame_source
            if on_object_event is not None and cls._singleton._on_event is None:
                cls._singleton._on_event = on_object_event
        return cls._singleton

    @classmethod
    def peek_singleton(cls) -> "VisionObjectAgent | None":
        return cls._singleton

    def __init__(
        self,
        face_frame_source: Any | None,
        memory_manager: Any | None,
        on_object_event: Callable[[dict], Awaitable[None]] | None = None,
        db_path: str = DEFAULT_DB_PATH,
        brain_throttle_sec: float | None = None,
        max_events_per_sec: int | None = None,
    ) -> None:
        self._face_source = face_frame_source
        self._memory = memory_manager
        self._on_event = on_object_event

        self._detector = YoloDetector(
            model_path=os.getenv("VISION_OBJECT_MODEL", "yolov8m-oiv7.pt"),
            device=os.getenv("VISION_OBJECT_DEVICE", "mps"),
            confidence_min=float(os.getenv("VISION_OBJECT_CONFIDENCE", "0.45")),
        )
        self._dedup = _DetectionDeduplicator(DedupConfig())
        self._storage = _VisionStorage(db_path=db_path, memory_manager=memory_manager)

        self._brain_throttle_sec = (
            brain_throttle_sec if brain_throttle_sec is not None
            else float(os.getenv("VISION_OBJECT_BRAIN_THROTTLE_SEC", "1.0"))
        )
        self._max_events_per_sec = (
            max_events_per_sec if max_events_per_sec is not None
            else int(os.getenv("VISION_OBJECT_MAX_EVENTS_PER_SEC", "10"))
        )

        self._last_brain_push_by_class: dict[str, float] = {}
        self._recent_push_ts: deque[float] = deque(maxlen=self._max_events_per_sec)

        self._camera_task: asyncio.Task | None = None
        self._cleanup_task: asyncio.Task | None = None
        self._stopping = False

    # ─────── Mode PULL ───────

    async def detect_on_demand(
        self, source: str = "camera", filter_class: str | None = None, max_results: int = 10,
    ) -> str:
        """One-shot : capture frame → YOLO → réponse FR. Bypass la dédup."""
        try:
            frame = await self._capture_frame(source)
            if frame is None:
                return f"Erreur: pas de frame disponible pour la source '{source}' (caméra ou écran indisponible)."

            detections = await asyncio.to_thread(self._detector.detect, frame)

            if filter_class:
                fc = filter_class.lower()
                detections = [d for d in detections if fc in d.class_fr.lower()]

            if not detections:
                if filter_class:
                    return f"Je ne vois pas de {filter_class} sur la {source}."
                return f"Je ne détecte rien sur la {source}."

            detections = detections[:max_results]
            lines = []
            for d in detections:
                pos = self._bbox_to_position_fr(d.bbox)
                lines.append(f"- {d.class_fr} {pos} (confiance {d.confidence:.2f})")
            header = f"J'identifie {len(detections)} objet(s) sur la {source} :"
            return header + "\n" + "\n".join(lines)

        except Exception as exc:
            _LOG.warning("[VISION_OBJ] detect_on_demand failed: %s", exc)
            return f"Erreur détection: {exc}"

    async def query_history(
        self, object_query: str, since: str | None = None, max_results: int = 5,
    ) -> str:
        try:
            since_ts = self._parse_since(since)
            rows = self._storage.query_by_class(
                class_fr=object_query, since_ts=since_ts, max_results=max_results,
            )
            if not rows:
                return f"Aucune trace de '{object_query}' depuis la période demandée."
            lines = [
                f"- {r['timestamp_iso']} sur {r['source']} (confiance {r['confidence']:.2f})"
                for r in rows
            ]
            return f"J'ai vu '{object_query}' {len(rows)} fois :\n" + "\n".join(lines)
        except Exception as exc:
            return f"Erreur recherche: {exc}"

    async def count_seen(self, object_class: str, period: str = "today") -> str:
        try:
            since_ts, until_ts = self._parse_period(period)
            count = self._storage.count_distinct(
                class_fr=object_class, since_ts=since_ts, until_ts=until_ts,
            )
            return f"J'ai vu {count} fois '{object_class}' sur la période '{period}'."
        except Exception as exc:
            return f"Erreur comptage: {exc}"

    # ─────── Mode PUSH ───────

    async def detect_on_frame_bytes(self, frame_bytes: bytes, source: str) -> None:
        """Greffon utilisé par screen_watcher (fire-and-forget)."""
        try:
            import cv2
            arr = np.frombuffer(frame_bytes, dtype=np.uint8)
            frame_bgr = cv2.imdecode(arr, cv2.IMREAD_COLOR)
            if frame_bgr is None:
                return
            await self._process_frame(frame_bgr, source)
        except Exception as exc:
            _LOG.warning("[VISION_OBJ] detect_on_frame_bytes failed: %s", exc)

    async def _process_frame(self, frame_bgr: np.ndarray, source: str) -> None:
        detections = await asyncio.to_thread(self._detector.detect, frame_bgr)
        events = self._dedup.diff(detections, source=source, timestamp=time.time())
        if not events:
            return
        await asyncio.to_thread(self._storage.persist, events)
        for evt in events:
            await self._propagate_to_brain(evt)

    async def _propagate_to_brain(self, event: ObjectEvent) -> None:
        if self._on_event is None:
            return

        now = time.time()
        is_high_priority = event.detection.class_name in HIGH_PRIORITY_CLASSES_EN

        if not is_high_priority and len(self._recent_push_ts) == self._max_events_per_sec:
            oldest = self._recent_push_ts[0]
            if now - oldest < 1.0:
                return

        if not is_high_priority:
            last = self._last_brain_push_by_class.get(event.detection.class_fr, 0.0)
            if now - last < self._brain_throttle_sec:
                return

        self._last_brain_push_by_class[event.detection.class_fr] = now
        self._recent_push_ts.append(now)

        stimulus = {
            "source": "vision_object",
            "description": f"{event.detection.class_fr} {event.event_type.value}",
            "object_class": event.detection.class_fr,
            "event_type": event.event_type.value,
            "movement": _classify_movement(event),
            "risk": _classify_risk(event),
            "attention_need": _classify_attention(event),
            "valence": 0.0,
            "spontaneous_hint": _hint_for(event),
        }
        try:
            await self._on_event(stimulus)
        except Exception as exc:
            _LOG.warning("[VISION_OBJ] Brain callback failed: %s", exc)

    # ─────── Helpers ───────

    async def _capture_frame(self, source: str) -> np.ndarray | None:
        if source == "camera":
            if self._face_source is None:
                return None
            return self._face_source.get_last_frame()
        if source == "screen":
            try:
                import mss
                import cv2
                with mss.mss() as sct:
                    img = np.array(sct.grab(sct.monitors[1]))
                    return cv2.cvtColor(img, cv2.COLOR_BGRA2BGR)
            except Exception as exc:
                _LOG.warning("[VISION_OBJ] Screen capture failed: %s", exc)
                return None
        return None

    @staticmethod
    def _bbox_to_position_fr(bbox: tuple[float, float, float, float]) -> str:
        xc, yc, _, _ = bbox
        horiz = "à gauche" if xc < 0.33 else ("à droite" if xc > 0.66 else "au centre")
        vert = "en haut" if yc < 0.33 else ("en bas" if yc > 0.66 else "")
        return f"{vert} {horiz}".strip()

    @staticmethod
    def _parse_since(since: str | None) -> float:
        if not since:
            return time.time() - 86400.0
        s = since.lower().strip()
        now = time.time()
        if s in {"hier", "yesterday"}:
            return now - 2 * 86400.0
        if s in {"cette semaine", "this_week", "this week"}:
            return now - 7 * 86400.0
        if s in {"dernier mois", "last_month"}:
            return now - 30 * 86400.0
        try:
            return datetime.fromisoformat(since.replace("Z", "+00:00")).timestamp()
        except Exception:
            return now - 86400.0

    @staticmethod
    def _parse_period(period: str) -> tuple[float, float]:
        now = time.time()
        p = (period or "today").lower().strip()
        if p == "today":
            start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
            return start.timestamp(), now
        if p == "yesterday":
            today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
            yesterday_start = today_start - timedelta(days=1)
            return yesterday_start.timestamp(), today_start.timestamp()
        if p == "this_week":
            return now - 7 * 86400.0, now
        if p == "last_24h":
            return now - 86400.0, now
        if p == "last_hour":
            return now - 3600.0, now
        return now - 86400.0, now

    # ─────── Lifecycle ───────

    async def start(self) -> None:
        _LOG.info("[VISION_OBJ] Agent started (singleton)")
        if os.getenv("VISION_OBJECT_CAMERA_LOOP", "true").lower() == "true":
            fps = int(os.getenv("VISION_OBJECT_FPS", "10"))
            await self.start_camera_loop(fps=fps)
        await self.start_cleanup_loop()

    async def start_cleanup_loop(
        self, interval_sec: float = 86400.0, retention_days: int | None = None,
    ) -> None:
        if self._cleanup_task is not None and not self._cleanup_task.done():
            return
        retention = (
            retention_days if retention_days is not None
            else int(os.getenv("VISION_OBJECT_RETENTION_DAYS", "30"))
        )
        self._stopping = False
        self._cleanup_task = asyncio.create_task(
            self._run_cleanup_loop(interval_sec=interval_sec, retention_days=retention)
        )
        _LOG.info("[VISION_OBJ] Cleanup loop started (interval=%.0fs, retention=%dd)", interval_sec, retention)

    async def _run_cleanup_loop(self, interval_sec: float, retention_days: int) -> None:
        while not self._stopping:
            try:
                deleted = await asyncio.to_thread(
                    self._storage.cleanup_older_than, retention_days
                )
                _LOG.info(
                    "[VISION_OBJ] Nightly cleanup: %d events purged (retention=%dd)",
                    deleted, retention_days,
                )
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                _LOG.warning("[VISION_OBJ] Cleanup failed: %s", exc)
            await asyncio.sleep(interval_sec)

    async def start_camera_loop(self, fps: int = 10) -> None:
        """Démarre la boucle continue sur la caméra (partagée avec MediaPipe)."""
        if self._camera_task is not None and not self._camera_task.done():
            return
        period = 1.0 / max(1, fps)
        self._stopping = False
        self._camera_task = asyncio.create_task(self._run_camera_loop(period))
        _LOG.info("[VISION_OBJ] Camera loop started (period=%.3fs, fps=%d)", period, fps)

    async def _run_camera_loop(self, period: float) -> None:
        while not self._stopping:
            tick_start = time.monotonic()
            try:
                frame = None
                if self._face_source is not None:
                    frame = self._face_source.get_last_frame()
                if frame is None:
                    await asyncio.sleep(period)
                    continue
                await self._process_frame(frame, source="camera")
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                _LOG.warning("[VISION_OBJ] Camera loop tick failed: %s", exc)
            elapsed = time.monotonic() - tick_start
            sleep_for = max(0.0, period - elapsed)
            await asyncio.sleep(sleep_for)

    async def stop(self) -> None:
        self._stopping = True
        for task in (self._camera_task, self._cleanup_task):
            if task and not task.done():
                task.cancel()
                try:
                    await task
                except (asyncio.CancelledError, Exception):
                    pass
        _LOG.info("[VISION_OBJ] Agent stopped")
