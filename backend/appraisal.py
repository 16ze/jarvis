"""
appraisal — la voie lente de l'émotion d'Ada.

Le système limbique juge d'abord par comptage de mots (`limbic.analyser_texte`).
C'est rapide, mais aveugle : « je ne suis **pas** en colère » est compté comme
de la colère, « super, encore un bug… » comme un compliment.

Ce module apporte la seconde voie : une évaluation structurée par le LLM, selon
la théorie de l'évaluation cognitive (*appraisal theory*). Elle ne dit pas
seulement *combien* c'est chargé, mais **de quoi** il s'agit :

    valence   -1..1   négatif ↔ positif
    arousal    0..1   calme ↔ activé
    dominance  0..1   subi ↔ maîtrisé
    cause             ce qui, dans le message, provoque ce ressenti
    target            vers quoi l'émotion est dirigée
    certainty  0..1   confiance de l'évaluation

Architecture à double voie (LeDoux) : la voie rapide réagit immédiatement, la
voie lente arrive après et **corrige l'écart** — jamais elle ne recompte. C'est
ce qui permet de garder une réponse vocale instantanée tout en gagnant la
finesse du LLM : Ada réagit d'abord, puis nuance, exactement comme un humain qui
comprend une seconde plus tard que c'était de l'ironie.

Défensif : si le LLM est indisponible, lent ou illisible, seule la voie rapide
s'applique — le comportement actuel est conservé tel quel.
"""

from __future__ import annotations

import asyncio
import json
import os

import models
import re
from dataclasses import dataclass

_MODEL = os.getenv("APPRAISAL_MODEL", models.get("fast"))
_TIMEOUT_SEC = float(os.getenv("APPRAISAL_TIMEOUT_SEC", "6"))
_MIN_CHARS = int(os.getenv("APPRAISAL_MIN_CHARS", "8"))

_SYSTEM = """Tu évalues la charge émotionnelle d'un message adressé à Ada par Bryan.

Tu n'es pas Ada : tu es son appareil d'évaluation. Tu analyses, tu ne réponds pas.

Sois attentif à ce qu'un comptage de mots raterait :
- la NÉGATION (« je ne suis pas en colère » n'est pas de la colère) ;
- l'IRONIE et le sarcasme (« super, encore un bug… » est négatif) ;
- l'humour et la taquinerie affectueuse (une pique tendre n'est pas une attaque) ;
- l'intensité réelle : une critique technique factuelle n'est pas une insulte.

Réponds UNIQUEMENT par un JSON valide, sans markdown :
{
  "valence": -1.0 à 1.0,
  "arousal": 0.0 à 1.0,
  "dominance": 0.0 à 1.0,
  "cause": "ce qui provoque ce ressenti, 3-8 mots, en français",
  "target": "bryan" | "soi" | "situation" | "tiers",
  "certainty": 0.0 à 1.0
}

"cause" sera lu par Ada comme la raison de son état : formule-la du point de vue
de son ressenti (ex. « une critique sèche sur son travail », « une taquinerie
affectueuse »), jamais comme une analyse technique."""


@dataclass
class Appraisal:
    valence: float
    arousal: float
    dominance: float
    cause: str
    target: str
    certainty: float

    @property
    def is_meaningful(self) -> bool:
        return self.certainty >= 0.25


def _clamp(v, lo=0.0, hi=1.0) -> float:
    try:
        return max(lo, min(hi, float(v)))
    except (TypeError, ValueError):
        return lo


def parse(raw: str) -> Appraisal | None:
    """Transforme la réponse du modèle en Appraisal. None si illisible."""
    if not raw:
        return None
    cleaned = re.sub(r"^```(?:json)?\s*", "", raw.strip())
    cleaned = re.sub(r"\s*```$", "", cleaned).strip()
    try:
        data = json.loads(cleaned)
    except (json.JSONDecodeError, ValueError):
        return None
    if not isinstance(data, dict):
        return None

    target = str(data.get("target", "situation")).strip().lower()
    if target not in {"bryan", "soi", "situation", "tiers"}:
        target = "situation"

    return Appraisal(
        valence=_clamp(data.get("valence", 0.0), -1.0, 1.0),
        arousal=_clamp(data.get("arousal", 0.0)),
        dominance=_clamp(data.get("dominance", 0.5)),
        cause=str(data.get("cause", "")).strip()[:120],
        target=target,
        certainty=_clamp(data.get("certainty", 0.0)),
    )


class AppraisalEngine:
    """Évalue un message via le LLM. Ne lève jamais."""

    def __init__(self, client=None):
        self._client = client  # injectable pour les tests

    @property
    def enabled(self) -> bool:
        raw = os.getenv("APPRAISAL_ENABLED")
        if raw is None:
            return True
        return raw.strip().lower() in {"1", "true", "yes", "on"}

    def _get_client(self):
        """Initialisation paresseuse — aucun effet de bord à l'import."""
        if self._client is not None:
            return self._client
        key = os.getenv("GEMINI_API_KEY", "")
        if not key:
            return None
        try:
            from google import genai

            self._client = genai.Client(api_key=key)
            return self._client
        except Exception as exc:  # noqa: BLE001
            print(f"[APPRAISAL] client indisponible : {exc}")
            return None

    async def evaluate(self, text: str, contexte: str = "") -> Appraisal | None:
        """Évalue un message. None si indisponible, trop court ou illisible."""
        text = (text or "").strip()
        if not self.enabled or len(text) < _MIN_CHARS:
            return None

        client = self._get_client()
        if client is None:
            return None

        prompt = f"Message de Bryan :\n« {text[:800]} »"
        if contexte:
            prompt += f"\n\nContexte (état d'Ada) : {contexte}"

        try:
            from google.genai import types

            response = await asyncio.wait_for(
                client.aio.models.generate_content(
                    model=_MODEL,
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        system_instruction=_SYSTEM,
                        temperature=0.2,       # évaluation = tâche stable
                        max_output_tokens=200,
                    ),
                ),
                timeout=_TIMEOUT_SEC,
            )
            return parse(response.text or "")
        except asyncio.TimeoutError:
            print("[APPRAISAL] délai dépassé — seule la voie rapide s'applique")
            return None
        except Exception as exc:  # noqa: BLE001
            print(f"[APPRAISAL] évaluation impossible : {exc}")
            return None


_ENGINE: AppraisalEngine | None = None


def get_engine() -> AppraisalEngine:
    global _ENGINE
    if _ENGINE is None:
        _ENGINE = AppraisalEngine()
    return _ENGINE


async def appraise_and_apply(text: str, brain=None) -> float:
    """Évalue puis applique la correction au limbique. Retourne la correction.

    C'est le point d'entrée à lancer en tâche de fond après avoir notifié la
    voie rapide : Ada a déjà réagi, cette correction affine son ressenti.
    """
    try:
        if brain is None:
            from brain.brain_manager import get_brain

            brain = get_brain()
        if not getattr(brain, "enabled", False):
            return 0.0

        snap = brain.get_affect_snapshot() or {}
        contexte = f"humeur actuelle {snap.get('mood', 'neutre')}" if snap else ""

        appraisal = await get_engine().evaluate(text, contexte)
        if appraisal is None or not appraisal.is_meaningful:
            return 0.0

        correction = brain.limbic.reevaluer(appraisal)
        if correction:
            print(
                f"[APPRAISAL] correction {correction:+.2f} "
                f"(valence {appraisal.valence:+.2f}) — {appraisal.cause}"
            )

        # Boucle fermée : si Ada s'est exprimée spontanément juste avant, cette
        # réaction dit comment elle a été reçue. C'est le meilleur signal
        # d'apprentissage social disponible (valence finement évaluée).
        # L'évaluation fine renseigne aussi sur l'état de Bryan lui-même.
        try:
            brain.notify_user_appraisal(appraisal.valence, appraisal.arousal)
        except Exception:
            pass

        try:
            credite = brain.notify_reaction(appraisal.valence)
            if credite:
                print(
                    f"[SOCIAL] accueil de « {credite} » mis à jour "
                    f"(retour {appraisal.valence:+.2f})"
                )
        except Exception:
            pass

        return correction
    except Exception as exc:  # noqa: BLE001
        print(f"[APPRAISAL] application impossible : {exc}")
        return 0.0
