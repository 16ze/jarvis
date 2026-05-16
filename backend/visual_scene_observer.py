"""
Visual scene observer — convertit une frame en événement structuré pour le brain.

Le SNN/brain ne reçoit pas les pixels bruts. Il reçoit un stimulus sémantique
court, stable et borné, puis décide de l'impact émotionnel et de la spontanéité.
"""

from __future__ import annotations

import json
import os
import re
from typing import Any

from dotenv import load_dotenv
from google import genai
from google.genai import types

load_dotenv()

MODEL = os.getenv("VISUAL_SCENE_MODEL", "gemini-2.5-flash")

_client = None

_SCENE_PROMPT = """Analyse cette scène visuelle pour Ada.
Réponds UNIQUEMENT avec un JSON valide, sans markdown.

Schéma :
{
  "description": "phrase courte en français",
  "source": "screen|camera|unknown",
  "person": "Bryan|Rose|inconnu|personne|unknown",
  "human_emotion": "neutral|happy|sad|angry|tired|stressed|intimate|unknown",
  "movement": 0.0,
  "risk": "none|low|medium|high",
  "attention_need": 0.0,
  "affection": 0.0,
  "valence": 0.0,
  "spontaneous_hint": "phrase courte qu'Ada pourrait dire si elle doit réagir"
}

Règles :
- movement, attention_need, affection sont entre 0 et 1.
- valence est entre -1 et 1.
- risk=high seulement si danger concret, urgence, intrusion, blessure, feu, chute, ou détresse visible.
- Ne déclenche pas de spontanéité pour une scène banale.
- Si tu n'es pas sûr, mets unknown/none et des scores faibles."""


def _get_client():
    global _client
    if _client is None:
        _client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
    return _client


def _coerce_float(value: Any, default: float = 0.0) -> float:
    try:
        return max(-1.0, min(1.0, float(value)))
    except (TypeError, ValueError):
        return default


def _extract_json(text: str) -> dict:
    raw = (text or "").strip()
    if not raw:
        return {}
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", raw, flags=re.S)
        if not match:
            return {}
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            return {}


def normalize_scene_event(data: dict, *, source: str) -> dict:
    risk = str(data.get("risk") or "none").lower()
    if risk not in {"none", "low", "medium", "high"}:
        risk = "none"

    emotion = str(data.get("human_emotion") or "unknown").lower()
    if emotion not in {
        "neutral",
        "happy",
        "sad",
        "angry",
        "tired",
        "stressed",
        "intimate",
        "unknown",
    }:
        emotion = "unknown"

    return {
        "description": str(data.get("description") or "Scène visible.").strip()[:300],
        "source": source,
        "person": str(data.get("person") or "unknown").strip()[:40],
        "human_emotion": emotion,
        "movement": max(0.0, _coerce_float(data.get("movement"), 0.0)),
        "risk": risk,
        "attention_need": max(0.0, _coerce_float(data.get("attention_need"), 0.0)),
        "affection": max(0.0, _coerce_float(data.get("affection"), 0.0)),
        "valence": _coerce_float(data.get("valence"), 0.0),
        "spontaneous_hint": str(data.get("spontaneous_hint") or "").strip()[:220],
    }


async def analyze_visual_scene(frame_bytes: bytes, *, source: str) -> dict:
    client = _get_client()
    response = await client.aio.models.generate_content(
        model=MODEL,
        contents=[
            types.Content(
                parts=[
                    types.Part.from_bytes(data=frame_bytes, mime_type="image/jpeg")
                ]
            ),
            _SCENE_PROMPT.replace('"screen|camera|unknown"', f'"{source}"'),
        ],
    )
    data = _extract_json(response.text or "")
    return normalize_scene_event(data, source=source)
