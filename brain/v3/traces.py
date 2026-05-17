"""Ring buffer thread-safe pour observer en live les décisions du brain v3."""
from __future__ import annotations

import threading
import time
from collections import deque
from datetime import datetime

from brain.v3.types import ReactionDecision, Stimulus


class ShortTermMemory:
    """Buffer FIFO borné dans le temps. Utilisé par l'endpoint /brain/v3/traces."""

    def __init__(self, window_sec: float = 60.0, max_items: int = 500) -> None:
        self._window = max(0.01, float(window_sec))
        self._max_items = int(max_items)
        self._items: deque[tuple[float, dict]] = deque(maxlen=max_items)
        self._lock = threading.Lock()

    def append(self, stimulus: Stimulus, decision: ReactionDecision) -> None:
        now = time.monotonic()
        entry = (
            now,
            {
                "ts": datetime.now().strftime("%H:%M:%S"),
                "stimulus": stimulus.canonical_id,
                "channel": stimulus.channel,
                "saliency": round(decision.saliency, 3),
                "action": decision.action,
                "reason": decision.reason,
                "cost": round(decision.cost, 3),
            },
        )
        with self._lock:
            self._items.append(entry)
            self._evict_old(now)

    def recent(self, n: int = 50) -> list[dict]:
        """Retourne les n entrées les plus récentes (récent en premier)."""
        now = time.monotonic()
        with self._lock:
            self._evict_old(now)
            payload = [d for _ts, d in self._items]
        return list(reversed(payload))[:n]

    def _evict_old(self, now: float) -> None:
        cutoff = now - self._window
        while self._items and self._items[0][0] < cutoff:
            self._items.popleft()
