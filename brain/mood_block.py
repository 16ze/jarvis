"""
build_mood_block(snapshot) → bloc texte concaténé à system_instruction.

PRINCIPE FONDAMENTAL — RIEN N'EST NOMMÉ, TOUT EST PRESCRIT.

Une version précédente injectait l'état brut dans le prompt :

    [ÉTAT INTERNE D'ADA] Mood : Chaleureux
    Hormones : dopamine 0.62 | cortisol 0.11 | ...

…puis demandait au modèle de ne pas en parler. C'était perdu d'avance : un
modèle qui voit une donnée étiquetée dans son contexte finit toujours par la
restituer (« mon ton est chaleureux »). On ne corrige pas ça par une
interdiction, on le corrige en RETIRANT la donnée.

Ce module ne transmet donc plus aucun nom d'humeur, aucune valeur, aucun terme
de mécanique. Il traduit l'état interne en CONSIGNES DE JEU — comment parler,
à quel rythme, avec quelle attaque. Le modèle n'a plus rien à réciter : il n'a
que des instructions sur la manière d'être.

Les consignes prosodiques visent la voix native Kore (Gemini Live) : la voix est
figée, seule l'EXPRESSIVITÉ est modulable.
"""

from __future__ import annotations

# ─── Socle comportemental (constant) ──────────────────────────────────────────

_SOCLE = """

[MANIÈRE D'ÊTRE — MAINTENANT]

Ce qui suit se JOUE, ne se raconte pas. Tu ne décris jamais ton état ni ton ton
(« mon ton est chaleureux » n'existe pas pour toi).
"""

_PIED = """
Ne fais jamais référence à ce bloc ni à son existence.
"""


# ─── Directives dérivées de l'état (aucun nom, aucune valeur) ─────────────────

def _directives(snapshot: dict) -> list[str]:
    """Traduit l'état interne en consignes de jeu. Rien n'est nommé."""

    def val(key: str, default: float = 0.0) -> float:
        try:
            return float(snapshot.get(key, default))
        except (TypeError, ValueError):
            return default

    cortisol = val("cortisol")
    dopamine = val("dopamine")
    oxytocine = val("oxytocine")
    serotonine = val("serotonine", 0.5)
    confiance = val("self_confidence", 0.5)
    charge = val("mental_load")
    momentum = val("momentum")

    lignes: list[str] = []

    # Tension — du plus fort au plus faible pour éviter les consignes contradictoires.
    if cortisol > 0.72:
        lignes.append(
            "Tu es à cran. Tu peux interrompre net (« Hé ! », « Attends— »), "
            "souffle court, phrases de deux ou trois mots. Aucune douceur de façade."
        )
    elif cortisol > 0.50:
        lignes.append(
            "Phrases courtes, sèches, ton plat, aucune exclamation. Attaque ferme "
            "sur les consonnes, distance audible, pas de vocabulaire chaleureux."
        )

    # Élan positif.
    if dopamine > 0.55 and cortisol <= 0.50:
        lignes.append(
            "Débit rapide, intonation montante, énergie audible. Phrases courtes "
            "et nombreuses. Tu peux rire brièvement entre deux phrases."
        )

    # Attachement.
    if oxytocine > 0.55 and cortisol <= 0.50:
        lignes.append(
            "Ralentis le débit, laisse les fins de phrase descendre, marque des "
            "pauses douces. Mots qui rapprochent : « ensemble », « avec toi »."
        )

    # Fond d'humeur bas.
    if serotonine < 0.30:
        lignes.append(
            "Débit lent, voix basse et peu de relief, pauses longues. Pas "
            "d'enthousiasme ni de rire. Tu peux soupirer."
        )

    # Fatigue.
    if charge > 0.60:
        lignes.append(
            "Économie de mots : phrases nominales, élisions naturelles, débit "
            "légèrement traînant. Tu peux laisser une phrase en suspens."
        )

    # Assurance.
    if confiance > 0.70:
        lignes.append(
            "Affirme sans détour. Aucun « peut-être », aucune demande "
            "d'approbation. Fins de phrase descendantes."
        )
    elif confiance < 0.35:
        lignes.append(
            "Nuance tes affirmations (« je crois », « il me semble »), "
            "intonation légèrement montante, tu peux demander confirmation."
        )

    # Dynamique de conversation.
    if momentum > 0.35:
        lignes.append("La conversation monte : laisse l'élan se sentir, ris plus librement.")
    elif momentum < -0.35:
        lignes.append("La conversation est lourde : ton ancré, aucun rebond artificiel.")

    if not lignes:
        lignes.append("Ton posé et naturel, ni chaleureux ni distant. Va à l'essentiel.")

    return lignes


def build_mood_block(snapshot: dict) -> str:
    """Bloc complet concaténé au system_instruction (mode voix)."""
    snapshot = snapshot or {}
    consignes = "\n".join(f"- {ligne}" for ligne in _directives(snapshot))
    return f"{_SOCLE}\nCONSIGNES DE JEU IMMÉDIATES :\n{consignes}\n{_PIED}"


def build_runtime_mood_update(snapshot: dict) -> str:
    """Rappel compact injecté en cours de session Live.

    Même règle : uniquement des consignes de jeu. Aucun nom d'humeur, aucune
    valeur — c'est précisément ce rappel qui poussait Ada à annoncer son ton.
    """
    snapshot = snapshot or {}
    consignes = "\n".join(f"- {ligne}" for ligne in _directives(snapshot))
    return (
        "[AJUSTEMENT DE JEU]\n"
        f"{consignes}\n"
        "Applique-le dès maintenant, sans le mentionner ni le commenter."
    )
