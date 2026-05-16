"""
ScreenWatcher — Vision continue de l'écran en arrière-plan.

Fonctionnement :
  - Capture l'écran à intervalle configurable via screencapture (macOS native)
  - Analyse chaque frame en événement visuel structuré
  - Garde un buffer circulaire des 10 dernières descriptions
  - Répond INSTANTANÉMENT à "describe_screen" depuis le buffer
  - Peut notifier le brain pour humeur/spontanéité
"""

import asyncio
import os
import re
import subprocess
import time
from collections import deque
from collections.abc import Awaitable, Callable
from typing import Optional
from dotenv import load_dotenv

load_dotenv()

from visual_scene_observer import analyze_visual_scene

INTERVAL_SEC = float(os.getenv("SCREEN_WATCHER_INTERVAL_SEC", "15"))
BUFFER_SIZE = 10
MAX_BACKOFF_SEC = float(os.getenv("SCREEN_WATCHER_MAX_BACKOFF_SEC", "300"))

_tmp_file = "/tmp/ada_screen_watcher.jpg"


def _env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _capture_screen() -> Optional[bytes]:
    """Capture l'écran via screencapture macOS. Retourne les bytes JPEG ou None."""
    try:
        result = subprocess.run(
            ["screencapture", "-x", "-t", "jpg", _tmp_file],
            capture_output=True,
            timeout=5,
        )
        if result.returncode == 0 and os.path.exists(_tmp_file):
            with open(_tmp_file, "rb") as f:
                return f.read()
    except Exception as e:
        print(f"[ScreenWatcher] Capture error: {e}")
    return None


def _retry_delay_from_error(exc: Exception) -> float | None:
    match = re.search(r"retryDelay['\"]?:\s*['\"]?(\d+(?:\.\d+)?)(ms|s)?", str(exc))
    if not match:
        return None
    delay = float(match.group(1))
    return delay / 1000.0 if match.group(2) == "ms" else delay


class ScreenWatcher:
    def __init__(
        self,
        on_scene_event: Callable[[dict], Awaitable[None]] | None = None,
    ):
        self._running = False
        self._enabled = _env_bool("SCREEN_WATCHER_ENABLED", False)
        self._task: Optional[asyncio.Task] = None
        self._buffer: deque[str] = deque(maxlen=BUFFER_SIZE)
        self._last_frame: Optional[bytes] = None
        self._lock = asyncio.Lock()
        self._last_analysis: Optional[str] = None
        self._last_analysis_time: float = 0
        self._initialized = False
        self._analysis_in_flight = False
        self._cooldown_until = 0.0
        self._error_count = 0
        self._on_scene_event = on_scene_event

    async def start(self):
        """Démarre la capture d'écran en arrière-plan."""
        self._initialized = True
        if not self._enabled:
            print("[ScreenWatcher] Désactivé — SCREEN_WATCHER_ENABLED=false")
            return
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._capture_loop())
        print(f"[ScreenWatcher] Démarré — capture toutes les {INTERVAL_SEC:g} secondes")

    async def stop(self):
        """Arrête la capture."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        print("[ScreenWatcher] Arrêté")

    async def describe(self) -> str:
        """Retourne instantanément la description de l'écran actuel."""
        if not self._initialized:
            return "Vision continue non encore initialisée."

        if not self._enabled:
            return "Vision continue désactivée pour préserver le quota Gemini."

        if self._last_analysis and (time.time() - self._last_analysis_time) < 5:
            return self._last_analysis

        if self._buffer:
            return self._buffer[-1]

        if self._last_analysis:
            return self._last_analysis

        return "Je n'ai pas encore capturé d'image de l'écran."

    async def _capture_loop(self):
        """Boucle de capture — tourne en arrière-plan."""
        while self._running:
            try:
                jpeg_bytes = await asyncio.to_thread(_capture_screen)

                if jpeg_bytes:
                    async with self._lock:
                        self._last_frame = jpeg_bytes

                    now = time.time()
                    if not self._analysis_in_flight and now >= self._cooldown_until:
                        self._analysis_in_flight = True
                        asyncio.create_task(self._analyze_frame(jpeg_bytes))

            except Exception as e:
                print(f"[ScreenWatcher] Erreur capture : {e}")

            await asyncio.sleep(INTERVAL_SEC)

    async def _analyze_frame(self, frame_bytes: bytes):
        """Analyse un frame et met à jour le buffer."""
        try:
            event = await analyze_visual_scene(frame_bytes, source="screen")
            desc = event.get("description") or "Écran visible."

            async with self._lock:
                self._buffer.append(desc)
                self._last_analysis = desc
                self._last_analysis_time = time.time()
                self._error_count = 0

            if self._on_scene_event:
                await self._on_scene_event(event)

        except Exception as e:
            self._error_count += 1
            retry_delay = _retry_delay_from_error(e)
            fallback_delay = min(MAX_BACKOFF_SEC, 30 * (2 ** min(self._error_count - 1, 4)))
            delay = max(retry_delay or 0.0, fallback_delay)
            self._cooldown_until = time.time() + delay
            print(
                "[ScreenWatcher] Analyse suspendue "
                f"{delay:.0f}s après erreur Gemini: {type(e).__name__}"
            )
        finally:
            self._analysis_in_flight = False

    @property
    def is_running(self) -> bool:
        return self._running
