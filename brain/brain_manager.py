"""
Singleton façade du brain biomimétique.

Ada ne consulte que ce module. Toutes les méthodes publiques sont défensives :
aucune exception ne doit remonter vers Ada.
"""

from __future__ import annotations

import os
import time
from collections.abc import Callable
from threading import Lock

from brain.limbic import CerveauEmotif
from brain.modulators import get_gemini_params as _params_for_mood
from brain.mood_block import build_mood_block, build_runtime_mood_update
from brain.network import EtatEveil, ReseauAttention
from brain.sensors_adapter import MediaPipeAdapter


def _env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


class BrainManager:
    def __init__(self) -> None:
        self.reseau = ReseauAttention()
        self.limbic = CerveauEmotif()
        self._adapter: MediaPipeAdapter | None = None
        self._lock = Lock()
        self._last_temperature: float | None = None
        self._degraded_until = 0.0
        self._v3 = None
        if _env_bool("BRAIN_V3_ENABLED", False):
            try:
                from brain.v3.v3_manager import V3Manager
                self._v3 = V3Manager(limbic_ref=self.limbic)
            except Exception as exc:
                print(f"[BRAIN_V3] init failed, falling back to v2: {exc}")
                self._v3 = None

    @property
    def enabled(self) -> bool:
        return _env_bool("BRAIN_ENABLED", False)

    @property
    def observe_only(self) -> bool:
        return self.enabled and _env_bool("BRAIN_OBSERVE_ONLY", True) and not self.modulate_all

    @property
    def modulate_all(self) -> bool:
        return self.enabled and _env_bool("BRAIN_MODULATE_ALL", False)

    def start(
        self,
        mediapipe_getter: Callable[[], tuple[float, float, float]] | None = None,
        *,
        poll_hz: float = 2.0,
    ) -> None:
        self._safe(
            "start",
            lambda: self._start_impl(mediapipe_getter, poll_hz=poll_hz),
            fallback=None,
        )

    def stop(self) -> None:
        self._safe("stop", self._stop_impl, fallback=None)

    def get_mood_block(self) -> str | None:
        if not self.enabled or self.observe_only or not self.modulate_all or self._is_degraded():
            return None
        return self._safe(
            "get_mood_block",
            self._internal_compute_block,
            fallback=None,
        )

    def get_runtime_mood_update(self) -> str | None:
        if not self.enabled or self.observe_only or not self.modulate_all or self._is_degraded():
            return None
        return self._safe(
            "get_runtime_mood_update",
            lambda: build_runtime_mood_update(self.limbic.get_snapshot()),
            fallback=None,
        )

    def get_gemini_params(
        self,
        default_temperature: float = 0.7,
        default_thinking_budget: int = 0,
    ) -> dict:
        defaults = {
            "temperature": default_temperature,
            "thinking_budget": default_thinking_budget,
        }
        if not self.enabled or self.observe_only or not self.modulate_all or self._is_degraded():
            return defaults

        def compute() -> dict:
            snap = self.limbic.get_snapshot()
            params = _params_for_mood(
                snap["mood"],
                snap,
                previous_temp=self._last_temperature,
            )
            self._last_temperature = params["temperature"]
            return params

        return self._safe("get_gemini_params", compute, fallback=defaults)

    def notify_user_message(self, text: str, audio_features: dict | None = None) -> None:
        if not self.enabled or self._is_degraded():
            return

        def notify() -> None:
            before = self.limbic.get_snapshot()
            self.limbic.analyser_texte(text)
            after = self.limbic.get_snapshot()
            self.reseau.tick_text(abs(after["momentum"]))
            if audio_features:
                self.limbic.analyser_intonation(
                    float(audio_features.get("energie", 0.0)),
                    float(audio_features.get("zcr", 0.0)),
                    float(audio_features.get("duree", 0.0)),
                )
            if after != before:
                self.limbic.penser(after["last_stimulus"])

        self._safe("notify_user_message", notify, fallback=None)
        if self._v3 is not None and self._v3.enabled:
            try:
                self._v3.observe(
                    {"text": text, "valence": 0.0, "audio": audio_features or {}},
                    channel="text",
                )
            except Exception as exc:
                print(f"[BRAIN_V3] notify_user_message observe failed: {exc}")

    def notify_llm_response(self) -> None:
        if not self.enabled or self._is_degraded():
            return
        self._safe("notify_llm_response", self.limbic.consommer_charge, fallback=None)

    def notify_visual_scene(self, event: dict) -> str | None:
        if not self.enabled or self._is_degraded():
            return None
        return self._safe(
            "notify_visual_scene",
            lambda: self._dispatch_stimulus(event, channel="vision_scene"),
            fallback=None,
        )

    def ingest_stimulus(self, stimulus: dict) -> str | None:
        """Pont YOLO/screen_watcher -> brain."""
        if not self.enabled or self._is_degraded():
            return None
        return self._safe(
            "ingest_stimulus",
            lambda: self._dispatch_stimulus(
                stimulus,
                channel=stimulus.get("source", "vision_object"),
            ),
            fallback=None,
        )

    def consume_spontaneous_impulse(self) -> str | None:
        if not self.enabled or self._is_degraded():
            return None
        return self._safe(
            "consume_spontaneous_impulse",
            self.limbic.verifier_action_spontanee,
            fallback=None,
        )

    def get_debug_state(self) -> dict:
        defaults = {
            "enabled": self.enabled,
            "observe_only": self.observe_only,
            "modulate_all": self.modulate_all,
            "degraded": self._is_degraded(),
        }
        return self._safe(
            "get_debug_state",
            lambda: {
                **defaults,
                "network_state": self.reseau.etat.value,
                "snapshot": self.limbic.get_snapshot(),
            },
            fallback=defaults,
        )

    def _existing_visual_scene_logic(self, event: dict) -> str | None:
        """Logique v2 originelle de notify_visual_scene."""
        movement = float(event.get("movement", 0.0) or 0.0)
        attention = float(event.get("attention_need", 0.0) or 0.0)
        risk = str(event.get("risk") or "none").lower()
        person = str(event.get("person") or "").lower()
        presence = 1.0 if person not in {"", "personne", "unknown"} else 0.0
        self.reseau.tick_visual(
            presence=presence,
            mouvement=max(movement, attention),
        )
        self.limbic.analyser_scene_visuelle(event)
        should_emit = risk == "high" or self.reseau.etat == EtatEveil.EVEIL
        if not should_emit:
            return None
        return self.limbic.verifier_action_spontanee()

    def _dispatch_stimulus(self, payload: dict, channel: str) -> str | None:
        """Route un stimulus visuel via v3 si activé, puis v2 dans tous les cas."""
        decision = None
        if self._v3 is not None and self._v3.enabled:
            decision = self._v3.process(payload, channel=channel)
            if self._v3.shadow_mode:
                decision = None

        v2_prompt: str | None = None
        if channel == "vision_scene":
            v2_prompt = self._existing_visual_scene_logic(payload)
        elif channel == "vision_object":
            try:
                self.limbic.analyser_scene_visuelle(payload)
            except Exception:
                pass

        if decision is not None and decision.action != "REACT":
            return None
        if decision is not None and decision.action == "REACT" and decision.prompt_hint:
            return decision.prompt_hint
        return v2_prompt

    def _start_impl(
        self,
        mediapipe_getter: Callable[[], tuple[float, float, float]] | None,
        *,
        poll_hz: float,
    ) -> None:
        if not self.enabled or mediapipe_getter is None:
            return
        with self._lock:
            if self._adapter is None:
                self._adapter = MediaPipeAdapter(
                    mediapipe_getter,
                    self.reseau,
                    self.limbic,
                    poll_hz=poll_hz,
                )
            self._adapter.start()

    def _stop_impl(self) -> None:
        with self._lock:
            if self._adapter is not None:
                self._adapter.arret_propre()
                self._adapter = None
            if self._v3 is not None:
                self._v3.stop()

    def _internal_compute_block(self) -> str:
        return build_mood_block(self.limbic.penser("system_instruction"))

    def _is_degraded(self) -> bool:
        return time.monotonic() < self._degraded_until

    def _safe(self, label: str, fn, *, fallback):
        start = time.perf_counter()
        try:
            result = fn()
            elapsed_ms = (time.perf_counter() - start) * 1000.0
            if elapsed_ms > 5.0:
                self._degraded_until = time.monotonic()
                print(f"[BRAIN_ERROR] {label} slow path: {elapsed_ms:.2f}ms")
            return result
        except Exception as exc:
            self._degraded_until = time.monotonic()
            print(f"[BRAIN_ERROR] {label}: {type(exc).__name__}: {exc}")
            return fallback


_BRAIN: BrainManager | None = None
_BRAIN_LOCK = Lock()


def get_brain() -> BrainManager:
    global _BRAIN
    if _BRAIN is None:
        with _BRAIN_LOCK:
            if _BRAIN is None:
                _BRAIN = BrainManager()
    return _BRAIN
