"""Pont hormones v2 -> ModulationVector v3.

derive() lit un snapshot du limbic v2 (cortisol, dopamine, mental_load) et
produit un vecteur de modulation qui sera consommé par les neurones v3 :
- threshold_gain  : multiplie le seuil effectif (cortisol haut -> baisse)
- decay_gain      : module la vitesse d'oubli (fatigue -> oubli rapide)
- budget_refill   : contribution par tick au budget d'attention (dopamine)
"""
from __future__ import annotations

from brain.calibration import env_float
from brain.v3.types import ModulationVector


def derive(snapshot: dict) -> ModulationVector:
    cortisol = float(snapshot.get("cortisol", 0.10))
    dopamine = float(snapshot.get("dopamine", 0.28))
    mental_load = float(snapshot.get("mental_load", 0.15))

    cortisol_gain = env_float("BRAIN_V3_CORTISOL_THRESHOLD_GAIN", 0.40)
    fatigue_gain = env_float("BRAIN_V3_FATIGUE_DECAY_GAIN", 0.50)
    refill_gain = env_float("BRAIN_V3_DOPAMINE_REFILL_GAIN", 0.0008)

    threshold_gain = 1.0 - cortisol_gain * (cortisol - 0.30)
    threshold_gain = max(0.6, min(1.4, threshold_gain))

    decay_gain = 1.0 + fatigue_gain * max(0.0, mental_load - 0.60)

    budget_refill = refill_gain * dopamine - (refill_gain * 0.375) * mental_load

    return ModulationVector(
        threshold_gain=round(threshold_gain, 4),
        decay_gain=round(decay_gain, 4),
        budget_refill=round(budget_refill, 6),
    )
