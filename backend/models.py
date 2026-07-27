"""
models — registre central des modèles utilisés par Ada.

L'audit initial relevait le problème : les modèles étaient codés en dur à une
douzaine d'endroits, avec des versions incohérentes et obsolètes
(`gemini-2.0-flash-lite` pour trois agents, un `gemini-3-pro-preview` qui
renvoyait 404 et cassait silencieusement la génération CAO).

Ici, on raisonne par RÔLE plutôt que par nom de modèle. Monter de version se
fait à un seul endroit.

Les valeurs par défaut ont été vérifiées en génération réelle sur la clé du
projet — pas seulement listées comme disponibles : `gemini-3-pro-preview` et
`gemini-2.5-pro` apparaissent dans le catalogue mais renvoient 404 à l'usage.
"""

from __future__ import annotations

import os

# ── Rôles ─────────────────────────────────────────────────────────────────────
# REASONING : profondeur maximale — questions de fond, planification délicate.
#             Latence acceptable car hors du chemin vocal.
# FAST      : bon compromis qualité/latence — agents, évaluation, rêverie.
# VISION    : analyse d'écran et d'images.
# CHEAP     : tâches très simples et fréquentes.

REASONING = os.getenv("ADA_MODEL_REASONING", "gemini-3.1-pro-preview")
FAST = os.getenv("ADA_MODEL_FAST", "gemini-3.6-flash")
VISION = os.getenv("ADA_MODEL_VISION", "gemini-3.6-flash")
CHEAP = os.getenv("ADA_MODEL_CHEAP", "gemini-2.5-flash")

# Repli si un modèle récent devient indisponible : toujours un modèle éprouvé.
FALLBACK = os.getenv("ADA_MODEL_FALLBACK", "gemini-2.5-flash")

ROLES = {
    "reasoning": REASONING,
    "fast": FAST,
    "vision": VISION,
    "cheap": CHEAP,
    "fallback": FALLBACK,
}


def get(role: str = "fast") -> str:
    """Modèle correspondant à un rôle. Rôle inconnu → repli sûr."""
    return ROLES.get((role or "").strip().lower(), FALLBACK)


def describe() -> str:
    """Résumé lisible — utile au diagnostic de démarrage."""
    return " | ".join(f"{role}: {nom}" for role, nom in ROLES.items() if role != "fallback")
