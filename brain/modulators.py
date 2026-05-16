"""
Mapping mood → params Gemini (temperature, thinking_budget).

⚠️  Kore est figée côté Ada. Ce module NE TOUCHE JAMAIS voice_name.
La modulation émotionnelle passe par :
  1. Le contenu du mood_block injecté dans system_instruction
  2. La temperature (variabilité de génération)
  3. Le thinking_budget (latence de réflexion)
"""

from typing import Optional


# Profils par "famille mood" : (temperature_target, thinking_budget)
_MOOD_PROFILES: dict[str, tuple[float, int]] = {
    # Tendresse / amour
    "Tendresse":    (0.75, 0),
    "Empathie":     (0.75, 0),
    "Passion":      (0.75, 0),
    "Chaleureux":   (0.75, 0),
    "Sympathie":    (0.75, 0),

    # Joie
    "Euphorie":     (0.90, 0),
    "Jubilation":   (0.90, 0),
    "Enthousiasme": (0.90, 0),
    "Joie":         (0.90, 0),
    "Gaieté":       (0.90, 0),

    # Curiosité
    "Curieux":      (0.85, 0),
    "Intérêt":      (0.85, 0),

    # Sérénité / neutre
    "Sérénité":     (0.70, 0),
    "Optimisme":    (0.70, 0),
    "Contentement": (0.70, 0),
    "Neutre":       (0.70, 0),

    # Tristesse modérée (un peu de réflexion)
    "Mélancolie":   (0.60, 400),
    "Nostalgie":    (0.60, 400),
    "Tristesse":    (0.60, 400),
    "Chagrin":      (0.60, 400),

    # Tristesse profonde (réflexion plus longue)
    "Détresse":     (0.50, 600),
    "Désespoir":    (0.50, 600),

    # Fatigue / apathie
    "Léthargique":  (0.55, 0),
    "Fatigué":      (0.55, 0),
    "Apathie":      (0.55, 0),
    "Spleen":       (0.55, 0),

    # Défense modérée
    "Inquiétude":   (0.45, 0),
    "Anxiété":      (0.45, 0),
    "Défensif":     (0.45, 0),
    "Sarcastique":  (0.45, 0),
    "Agacement":    (0.45, 0),

    # Combat / rage
    "Fight/Flight": (0.40, 0),
    "Rage":         (0.40, 0),
    "Indignation":  (0.40, 0),
    "Irritation":   (0.40, 0),
    "Panique":      (0.40, 0),
    "Terreur":      (0.40, 0),

    # État limite
    "Rupture":      (0.30, 0),

    # Hésitation / honte (réflexion avant parole)
    "Hésitant":     (0.60, 600),
    "Honte":        (0.60, 600),
    "Culpabilité":  (0.60, 600),
    "Humilité":     (0.60, 600),

    # Mépris / dédain
    "Mépris":       (0.50, 200),
    "Dédain":       (0.50, 200),

    # Fierté
    "Fierté":       (0.80, 0),
    "Assertif":     (0.80, 0),
}

_DEFAULT_PROFILE: tuple[float, int] = (0.70, 0)


def get_gemini_params(
    mood: str,
    hormones: dict | None = None,
    previous_temp: Optional[float] = None,
) -> dict:
    """
    Retourne {'temperature': float, 'thinking_budget': int}.

    JAMAIS de voice_name — Kore est figée côté Ada.

    Smoothing : si previous_temp est fourni, la temperature finale est
    `0.7 * previous + 0.3 * target` pour éviter les sauts brusques entre
    deux appels consécutifs.
    """
    target_temp, thinking = _MOOD_PROFILES.get(mood, _DEFAULT_PROFILE)

    if previous_temp is not None:
        final_temp = 0.7 * previous_temp + 0.3 * target_temp
    else:
        final_temp = target_temp

    # Clamp défensif au cas où une valeur exotique remonterait
    final_temp = max(0.0, min(1.0, final_temp))

    return {
        "temperature": round(final_temp, 4),
        "thinking_budget": int(thinking),
    }
