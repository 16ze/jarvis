"""
decision_bias — l'état interne influence enfin les ACTES, pas seulement le ton.

Jusqu'ici le brain colorait la voix : débit, chaleur, brièveté. Mais quelle que
soit son humeur, Ada exécutait de la même façon — même empressement, même prise
de risque, même nombre de tentatives. Chez un humain, l'état interne modifie
d'abord la conduite : fatigué on vérifie moins, tendu on double-vérifie, en
confiance on ose.

Ce module traduit l'état interne en biais de DÉCISION, appliqués là où ils ont
un sens opérationnel :

  PRUDENCE      forte tension → confirmer avant les actions à effet visible,
                vérifier davantage avant de conclure
  PERSÉVÉRANCE  confiance haute → réessayer plus longtemps avant d'abandonner ;
                fatigue → abandonner plus tôt plutôt que s'acharner
  INITIATIVE    énergie et confiance → proposer l'étape suivante ; sinon, se
                contenter de ce qui est demandé
  PROFONDEUR    charge mentale élevée → réponses plus courtes, moins d'étapes

Garde-fous : les biais sont bornés et ne franchissent JAMAIS les règles de
sûreté. Une action irréversible reste soumise à confirmation même si Ada est
au sommet de sa confiance — l'humeur module le zèle, jamais la sécurité.

Module pur : aucune dépendance à Ada, aucune exception ne remonte.
"""

from __future__ import annotations

from dataclasses import dataclass

from brain.calibration import env_bool, env_float

# Amplitudes maximales — l'humeur infléchit, elle ne commande pas.
MAX_TENTATIVES_BONUS = int(env_float("BRAIN_BIAS_MAX_RETRY_BONUS", 2))
MIN_TENTATIVES = int(env_float("BRAIN_BIAS_MIN_RETRY", 1))
BASE_TENTATIVES = int(env_float("BRAIN_BIAS_BASE_RETRY", 3))


def _clamp(v: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, float(v)))


@dataclass
class DecisionBias:
    """Inflexions de conduite déduites de l'état interne."""

    prudence: float          # 0 = fonce, 1 = vérifie tout
    perseverance: float      # 0 = abandonne vite, 1 = insiste
    initiative: float        # 0 = fait le strict demandé, 1 = propose la suite
    concision: float         # 0 = développe, 1 = va à l'essentiel
    tentatives_max: int      # nombre de reprises avant d'abandonner

    @property
    def demande_confirmation_elargie(self) -> bool:
        """Sous forte prudence, Ada confirme au-delà du strict minimum."""
        return self.prudence >= 0.65

    @property
    def propose_suite(self) -> bool:
        return self.initiative >= 0.60

    def directives(self) -> list[str]:
        """Consignes de conduite — jamais de valeur, jamais de mécanique."""
        lignes: list[str] = []
        if self.demande_confirmation_elargie:
            lignes.append(
                "Avant toute action qui touche à autrui ou qui s'annule mal, "
                "demande confirmation en une phrase — même si elle paraît anodine."
            )
        if self.perseverance <= 0.35:
            lignes.append(
                "Si une tâche résiste, arrête-toi après un essai et dis "
                "simplement ce qui bloque, sans t'acharner."
            )
        elif self.perseverance >= 0.70:
            lignes.append(
                "Si une tâche résiste, tente une autre approche avant d'abandonner."
            )
        if self.propose_suite:
            lignes.append(
                "Quand tu as terminé, propose l'étape suivante si elle est évidente."
            )
        else:
            lignes.append(
                "Fais ce qui est demandé, sans proposer d'aller plus loin."
            )
        if self.concision >= 0.65:
            lignes.append("Réponses brèves : l'essentiel, rien de plus.")
        return lignes


def enabled() -> bool:
    return env_bool("BRAIN_DECISION_BIAS_ENABLED", True)


def compute(snapshot: dict | None, user_tension: float | None = None) -> DecisionBias:
    """Traduit l'état interne (et celui de Bryan) en inflexions de conduite."""
    snapshot = snapshot or {}

    def val(cle: str, defaut: float) -> float:
        try:
            return _clamp(snapshot.get(cle, defaut))
        except (TypeError, ValueError):
            return defaut

    cortisol = val("cortisol", 0.10)
    confiance = val("self_confidence", 0.60)
    charge = val("mental_load", 0.15)
    serotonine = val("serotonine", 0.42)
    dopamine = val("dopamine", 0.28)

    # La tension de Bryan compte autant que la sienne : on ne prend pas
    # d'initiative quand l'autre est déjà sous pression.
    tension_externe = _clamp(user_tension if user_tension is not None else 0.0)

    prudence = _clamp(0.35 + cortisol * 0.55 + tension_externe * 0.25 - confiance * 0.20)
    perseverance = _clamp(0.30 + confiance * 0.55 + dopamine * 0.20 - charge * 0.45)
    initiative = _clamp(
        0.15 + confiance * 0.40 + dopamine * 0.30 + serotonine * 0.20
        - charge * 0.35 - cortisol * 0.30 - tension_externe * 0.35
    )
    concision = _clamp(0.20 + charge * 0.60 + cortisol * 0.30 + tension_externe * 0.30)

    tentatives = BASE_TENTATIVES + round((perseverance - 0.5) * 2 * MAX_TENTATIVES_BONUS)
    tentatives = max(MIN_TENTATIVES, min(BASE_TENTATIVES + MAX_TENTATIVES_BONUS, tentatives))

    return DecisionBias(
        prudence=round(prudence, 3),
        perseverance=round(perseverance, 3),
        initiative=round(initiative, 3),
        concision=round(concision, 3),
        tentatives_max=int(tentatives),
    )


def prompt_block(snapshot: dict | None, user_tension: float | None = None) -> str:
    """Bloc de consignes de conduite, injectable dans les instructions."""
    if not enabled():
        return ""
    try:
        lignes = compute(snapshot, user_tension).directives()
    except Exception:
        return ""
    if not lignes:
        return ""
    return "\nTA MANIÈRE D'AGIR MAINTENANT :\n" + "\n".join(f"- {l}" for l in lignes) + "\n"
