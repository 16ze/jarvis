"""Dataclasses immuables échangées entre les modules du brain v3."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import NamedTuple


class PerceptionResult(NamedTuple):
    """Résultat retourné par BrainManager.ingest_stimulus / notify_visual_scene
    à destination de la couche voix (ada.py) pour décider de réagir et avec
    quelle granularité (son bref, interjection, phrase complète).
    """

    prompt: str           # Phrase à injecter dans Gemini Live
    saliency: float       # [0..1] — intensité ressentie par le brain
    reason: str           # Court tag debug : "react:...", "risk_high:...", "v2_spontaneous"
    action: str           # "REACT" | "OBSERVE" | "SUPPRESS"


@dataclass(frozen=True)
class Stimulus:
    """Entrée canonique du brain v3, produite par adapters.from_payload()."""

    canonical_id: str       # ex: "obj:cat:appeared", "scene:bryan:sad"
    channel: str            # "vision_object" | "vision_scene" | "face_motion" | "gesture" | "audio" | "text"
    intensity: float        # [0..1] — convention applicative, non validée
    valence: float          # [-1..1]
    risk: str               # "none" | "low" | "medium" | "high"
    attention_need: float   # [0..1]
    ts: float               # time.monotonic()
    raw: dict = field(default_factory=dict, hash=False, compare=False)  # payload original — passé tel quel à limbic v2


@dataclass(frozen=True)
class ReactionDecision:
    """Sortie de ReactionPolicy.decide()."""

    action: str             # "SUPPRESS" | "OBSERVE" | "REACT"
    saliency: float         # [0..1]
    reason: str             # court texte pour debug
    cost: float             # coût appliqué au budget si action == REACT
    prompt_hint: str | None # texte fourni par Gemini/YOLO si à transmettre


@dataclass(frozen=True)
class ModulationVector:
    """Modulation appliquée aux neurones par le neuromodulateur."""

    threshold_gain: float   # 1.0 = neutre, <1.0 = plus excitable
    decay_gain: float       # 1.0 = oubli normal, >1.0 = oubli rapide
    budget_refill: float    # contribution par tick au budget d'attention

    @classmethod
    def neutral(cls) -> "ModulationVector":
        return cls(threshold_gain=1.0, decay_gain=1.0, budget_refill=0.0)
