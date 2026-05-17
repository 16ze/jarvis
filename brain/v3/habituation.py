"""Habituation par identifiant canonique avec LRU et decay temporel.

HabituationTracker maintient une familiarite courte par stimulus canonique.
Chaque empreinte renforce le compteur, puis la familiarite decroit de facon
exponentielle selon une demi-vie configurable. La taille est bornee par une
eviction LRU basee sur le dernier acces d'imprint.
"""
from __future__ import annotations

import threading
import time


class HabituationTracker:
    """Tracker thread-safe de familiarite habituelle par identifiant."""

    def __init__(self, halflife_sec: float = 120.0, max_keys: int = 256) -> None:
        self._halflife = max(0.01, float(halflife_sec))
        self._max_keys = max(1, int(max_keys))
        self._counts: dict[str, float] = {}
        self._last_ts: dict[str, float] = {}
        self._lock = threading.Lock()

    def familiarity(self, canonical_id: str) -> float:
        """Retourne une familiarite normalisee entre 0.0 et 1.0."""
        with self._lock:
            if canonical_id not in self._counts:
                return 0.0

            now = time.monotonic()
            elapsed = now - self._last_ts[canonical_id]
            decayed = self._counts[canonical_id] * (0.5 ** (elapsed / self._halflife))
            return min(1.0, decayed / 10.0)

    def imprint(self, canonical_id: str) -> None:
        """Renforce la trace d'un identifiant canonique."""
        with self._lock:
            now = time.monotonic()
            if canonical_id in self._counts:
                elapsed = now - self._last_ts[canonical_id]
                count = self._counts[canonical_id] * (0.5 ** (elapsed / self._halflife))
                self._counts[canonical_id] = count + 1.0
            else:
                if len(self._counts) >= self._max_keys:
                    oldest = min(self._last_ts, key=self._last_ts.get)
                    del self._counts[oldest]
                    del self._last_ts[oldest]
                self._counts[canonical_id] = 1.0

            self._last_ts[canonical_id] = now

    def size(self) -> int:
        """Retourne le nombre d'identifiants suivis."""
        with self._lock:
            return len(self._counts)
