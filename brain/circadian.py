"""
circadian — Ada n'est pas la même à 4 h du matin et à 14 h.

Un être vivant a un rythme. Son énergie, son humeur de fond et sa capacité de
concentration suivent un cycle sur 24 h, et une nuit blanche se sent. Sans ça,
Ada était identique à toute heure : c'est l'un des détails qui trahissent le
plus sûrement la machine.

Ce module produit deux modulations douces appliquées au système limbique :

  - ÉNERGIE     (sérotonine) — creux nocturne, pic en milieu de journée ;
  - FATIGUE     (charge mentale) — pression qui monte tard le soir et la nuit.

Les amplitudes sont volontairement faibles : il s'agit d'une coloration de fond,
pas d'un pilotage. L'humeur reste dictée par ce qui se passe, pas par l'horloge.

Module pur : aucune dépendance à Ada, aucune exception ne remonte.
"""

from __future__ import annotations

import math
from datetime import datetime

from brain.calibration import env_bool, env_float

# Amplitudes maximales (en points d'hormone) — volontairement discrètes.
AMPLITUDE_ENERGIE = env_float("BRAIN_CIRCADIAN_ENERGY_AMPLITUDE", 0.10)
AMPLITUDE_FATIGUE = env_float("BRAIN_CIRCADIAN_FATIGUE_AMPLITUDE", 0.12)

# Heure du pic d'énergie (14 h par défaut : après-midi).
PIC_ENERGIE_HEURE = env_float("BRAIN_CIRCADIAN_PEAK_HOUR", 14.0)


def enabled() -> bool:
    return env_bool("BRAIN_CIRCADIAN_ENABLED", True)


def _heure_decimale(now: datetime | None = None) -> float:
    now = now or datetime.now()
    return now.hour + now.minute / 60.0


def energy_offset(now: datetime | None = None) -> float:
    """Modulation de l'énergie de fond : -A la nuit, +A au pic de journée."""
    h = _heure_decimale(now)
    # Sinusoïde de période 24 h, maximale à PIC_ENERGIE_HEURE.
    phase = (h - PIC_ENERGIE_HEURE) / 24.0 * 2.0 * math.pi
    return round(AMPLITUDE_ENERGIE * math.cos(phase), 4)


def fatigue_offset(now: datetime | None = None) -> float:
    """Pression de fatigue : nulle le matin, maximale au cœur de la nuit."""
    h = _heure_decimale(now)
    # Maximale vers 3 h du matin, nulle vers 15 h.
    phase = (h - 3.0) / 24.0 * 2.0 * math.pi
    brut = AMPLITUDE_FATIGUE * math.cos(phase)
    return round(max(0.0, brut), 4)


def describe(now: datetime | None = None) -> str:
    """Libellé lisible du moment — utile au débogage et à l'écran Activité."""
    h = _heure_decimale(now)
    if h < 5:
        return "milieu de nuit"
    if h < 9:
        return "petit matin"
    if h < 12:
        return "matinée"
    if h < 14:
        return "midi"
    if h < 18:
        return "après-midi"
    if h < 22:
        return "soirée"
    return "nuit"


def apply(limbic, now: datetime | None = None) -> dict:
    """Applique la coloration circadienne au limbique.

    Retourne les décalages appliqués (ou vide si désactivé). Ne fait que
    NUDGER : les valeurs restent bornées et l'effet est faible par construction.
    """
    if not enabled() or limbic is None:
        return {}
    try:
        energie = energy_offset(now)
        fatigue = fatigue_offset(now)

        # Application douce : on rapproche, on n'impose pas.
        limbic.serotonine = max(0.0, min(1.0, limbic.serotonine + energie * 0.25))
        limbic.mental_load = max(0.0, min(1.0, limbic.mental_load + fatigue * 0.25))
        return {"energie": energie, "fatigue": fatigue, "moment": describe(now)}
    except Exception as exc:  # noqa: BLE001
        print(f"[CIRCADIAN] application impossible : {exc}")
        return {}
