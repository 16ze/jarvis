"""Fixtures partagées des tests v3."""
from __future__ import annotations


class MockLimbic:
    """Stub minimaliste imitant CerveauEmotif.get_snapshot()."""

    def __init__(self, snapshot: dict | None = None) -> None:
        self._snap = snapshot or {
            "cortisol": 0.10, "dopamine": 0.28, "oxytocine": 0.30,
            "serotonine": 0.42, "self_confidence": 0.60, "mental_load": 0.15,
            "mood": "Neutre", "momentum": 0.0, "last_stimulus": "init",
        }

    def get_snapshot(self) -> dict:
        return dict(self._snap)

    def set(self, **kwargs) -> None:
        self._snap.update(kwargs)
