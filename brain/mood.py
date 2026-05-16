"""
derive_mood — fonction pure (cortisol, dopamine, oxytocine, sérotonine,
self_confidence, mental_load) → mood ∈ ~50 états émotionnels.

Ordre de priorité STRICT : états intenses en premier.
"""


def derive_mood(c: float, d: float, o: float, s: float, cn: float, ml: float) -> str:
    """
    c  = cortisol         (stress, peur, défense)
    d  = dopamine         (joie, curiosité, désir)
    o  = oxytocine        (amour, attachement)
    s  = sérotonine       (humeur de fond)
    cn = self_confidence  (fierté ↔ honte)
    ml = mental_load      (fatigue cognitive)
    """

    # ── ÉTATS LIMITES ────────────────────────────────────────────
    if c >= 0.88:                                         return "Rupture"

    # ── FAMILLE PEUR ─────────────────────────────────────────────
    if c >= 0.82 and s < 0.30:                            return "Panique"
    if c >= 0.78 and d < 0.25:                            return "Terreur"
    if c >= 0.65 and d < 0.30 and s < 0.40:               return "Anxiété"
    if c >= 0.55 and d < 0.35:                            return "Inquiétude"

    # ── FAMILLE COLÈRE ───────────────────────────────────────────
    if c >= 0.75 and cn > 0.60 and s < 0.35:              return "Rage"
    if c >= 0.62 and cn > 0.55 and d < 0.35:              return "Indignation"
    if c >= 0.50 and cn > 0.50 and d < 0.40:              return "Irritation"
    if c >= 0.40 and d < 0.35:                            return "Agacement"

    # ── FAMILLE DÉGOÛT ───────────────────────────────────────────
    if c >= 0.45 and cn > 0.78 and d < 0.30:              return "Mépris"
    if c >= 0.35 and cn > 0.68 and d < 0.35:              return "Dédain"

    # ── FAMILLE TRISTESSE ────────────────────────────────────────
    if s < 0.15 and d < 0.20:
        return "Détresse" if ml > 0.60 else "Désespoir"
    if s < 0.25 and d < 0.25:                             return "Tristesse"
    if s < 0.32 and d < 0.30 and o < 0.40:                return "Chagrin"
    if s < 0.35 and d < 0.32:                             return "Mélancolie"
    if s < 0.40 and d < 0.35 and o > 0.45:                return "Nostalgie"

    # ── FAMILLE HONTE / CULPABILITÉ ──────────────────────────────
    if cn < 0.20 and c > 0.30:                            return "Honte"
    if cn < 0.28 and s < 0.40:                            return "Culpabilité"
    if cn < 0.35:                                         return "Humilité"

    # ── ENNUI / APATHIE ──────────────────────────────────────────
    if d < 0.20 and ml < 0.20 and c < 0.15 and s < 0.40:  return "Apathie"
    if d < 0.25 and s < 0.38 and c < 0.20:                return "Spleen"

    # ── FATIGUE ──────────────────────────────────────────────────
    if ml >= 0.78:                                        return "Léthargique"
    if ml >= 0.60:                                        return "Fatigué"

    # ── ÉTATS DÉFENSIFS ──────────────────────────────────────────
    if c >= 0.70:                                         return "Fight/Flight"
    if c >= 0.55:                                         return "Défensif"
    if c >= 0.40 and ml > 0.50:                           return "Sarcastique"

    # ── FAMILLE AMOUR / ATTACHEMENT ──────────────────────────────
    if o >= 0.78 and d >= 0.62:                           return "Passion"
    if o >= 0.70 and s >= 0.50:                           return "Tendresse"
    if o >= 0.58 and d >= 0.42:                           return "Chaleureux"
    if o >= 0.48 and s >= 0.40 and c < 0.25:              return "Empathie"
    if o >= 0.42 and c < 0.25:                            return "Sympathie"

    # ── FAMILLE JOIE ─────────────────────────────────────────────
    if d >= 0.85 and s >= 0.62:                           return "Euphorie"
    if d >= 0.72 and s >= 0.52:                           return "Jubilation"
    if d >= 0.62 and s >= 0.44:                           return "Enthousiasme"
    if d >= 0.52 and s >= 0.38:                           return "Joie"
    if d >= 0.43 and s >= 0.35:                           return "Gaieté"

    # ── FAMILLE FIERTÉ / ASSERTIVITÉ ─────────────────────────────
    if cn >= 0.82 and d >= 0.55 and s >= 0.48:            return "Fierté"
    if cn >= 0.75 and d >= 0.48:                          return "Assertif"

    # ── CURIOSITÉ / INTÉRÊT ──────────────────────────────────────
    if d >= 0.48 and cn >= 0.50:                          return "Curieux"
    if d >= 0.40:                                         return "Intérêt"

    # ── SÉRÉNITÉ / OPTIMISME ─────────────────────────────────────
    if s >= 0.65 and c < 0.20 and d >= 0.36:              return "Sérénité"
    if s >= 0.55 and d >= 0.36 and c < 0.25:              return "Optimisme"
    if s >= 0.46 and d >= 0.32:                           return "Contentement"

    # ── HÉSITATION ───────────────────────────────────────────────
    if cn < 0.38:                                         return "Hésitant"

    # ── NEUTRE ───────────────────────────────────────────────────
    return "Neutre"
