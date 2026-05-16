"""
MediaPipeAdapter — pont READ-ONLY entre la détection visage et le brain.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable

from brain.limbic import CerveauEmotif
from brain.network import ReseauAttention


class MediaPipeAdapter:
    def __init__(
        self,
        getter: Callable[[], tuple[float, float, float]],
        reseau: ReseauAttention,
        limbic: CerveauEmotif,
        *,
        poll_hz: float = 2.0,
    ) -> None:
        self._getter = getter
        self._reseau = reseau
        self._limbic = limbic
        self._poll_hz = max(0.1, float(poll_hz))
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._loop,
            name="BrainMediaPipeAdapter",
            daemon=True,
        )
        self._thread.start()

    def arret_propre(self) -> None:
        self._stop.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=1.0)

    def _loop(self) -> None:
        delay = 1.0 / self._poll_hz
        while not self._stop.is_set():
            try:
                presence, mouvement, confiance = self._getter()
                presence_bool = bool(presence)
                presence_float = 1.0 if presence_bool else 0.0
                mouvement = max(0.0, min(1.0, float(mouvement)))
                confiance = max(0.0, min(1.0, float(confiance)))
                self._reseau.tick_visual(presence_float * confiance, mouvement)
                self._limbic.update(
                    delta_mouvement=mouvement,
                    presence=presence_bool,
                    confiance_detection=confiance,
                )
            except Exception as exc:
                print(f"[BRAIN_ERROR] MediaPipeAdapter: {exc}")
            self._stop.wait(delay)
