"""Normalisation des payloads bruts vers les Stimulus du brain v3."""
from __future__ import annotations

import time

from brain.v3.types import Stimulus


_VALID_RISKS = {"none", "low", "medium", "high"}


def _clamp(value: float, lo: float, hi: float) -> float:
    try:
        coerced = float(value)
    except (TypeError, ValueError):
        return lo
    return max(lo, min(hi, coerced))


def _coerce_str(value: object, default: str = "unknown") -> str:
    if value is None:
        return default
    coerced = str(value).strip().lower()
    return coerced or default


def _valence_bucket(value: float) -> str:
    valence = _clamp(value, -1.0, 1.0)
    if valence > 0.25:
        return "positive"
    if valence < -0.25:
        return "negative"
    return "neutral"


def canonical_id_for(channel: str, payload: dict) -> str:
    channel = _coerce_str(channel)

    if channel == "vision_object":
        object_class = _coerce_str(payload.get("object_class"))
        event_type = _coerce_str(payload.get("event_type"))
        return f"obj:{object_class}:{event_type}"

    if channel == "vision_scene":
        person = _coerce_str(payload.get("person"))
        human_emotion = _coerce_str(payload.get("human_emotion"))
        return f"scene:{person}:{human_emotion}"

    if channel == "face_motion":
        return "face:present" if bool(payload.get("presence_bool")) else "face:absent"

    if channel == "audio":
        intensity_bucket = _coerce_str(payload.get("intensity_bucket"), default="normal")
        return f"audio:{intensity_bucket}"

    if channel == "text":
        return f"text:{_valence_bucket(payload.get('valence', 0.0))}"

    return f"{channel}:unknown"


def from_payload(payload: dict, channel: str) -> Stimulus:
    channel = _coerce_str(channel)

    risk = _coerce_str(payload.get("risk"), default="none")
    if risk not in _VALID_RISKS:
        risk = "none"

    attention_need = _clamp(payload.get("attention_need", 0.0), 0.0, 1.0)
    valence = _clamp(payload.get("valence", 0.0), -1.0, 1.0)

    if channel == "vision_object":
        intensity_value = payload.get("movement", 0.0)
    elif channel == "vision_scene":
        movement = _clamp(payload.get("movement", 0.0), 0.0, 1.0)
        intensity_value = max(movement, attention_need)
    elif channel == "face_motion":
        intensity_value = payload.get("mouvement", payload.get("movement", 0.0))
    elif channel == "audio":
        intensity_value = payload.get("energie", payload.get("intensity", 0.0))
    elif channel == "text":
        intensity_value = abs(valence)
    else:
        intensity_value = payload.get("intensity", 0.0)

    intensity = _clamp(intensity_value, 0.0, 1.0)

    return Stimulus(
        canonical_id=canonical_id_for(channel, payload),
        channel=channel,
        intensity=intensity,
        valence=valence,
        risk=risk,
        attention_need=attention_need,
        ts=time.monotonic(),
        raw=payload,
    )
