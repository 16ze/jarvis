"""Helpers de calibration pilotés par variables d'environnement."""

from __future__ import annotations

import os


def env_float(name: str, default: float) -> float:
    value = os.getenv(name)
    if value is None:
        return float(default)
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def env_int(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None:
        return int(default)
    try:
        return int(value)
    except (TypeError, ValueError):
        return int(default)


def env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}
