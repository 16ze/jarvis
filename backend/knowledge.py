"""
knowledge — la voie de réflexion d'Ada, pour les questions qui demandent du fond.

Deux raisons faisaient qu'Ada « ne savait presque rien » :

1. Le modèle de la voix (`gemini-*-native-audio`) est optimisé pour la
   conversation temps réel : latence minimale, aucun temps de réflexion. Il
   excelle à parler, beaucoup moins à raisonner ou à expliquer une procédure.
2. Sa consigne la poussait à chercher un OUTIL pour toute demande. Face à
   « comment on fait X ? », elle cherchait quoi exécuter au lieu de répondre.

Ce module ouvre la seconde voie : les questions de savoir sont traitées par un
modèle texte, AVEC un budget de réflexion réel. Ada relaie ensuite la réponse
avec ses mots.

C'est le même principe que la double voie émotionnelle (`appraisal`) : la voix
reste instantanée, la profondeur arrive par un chemin dédié.
"""

from __future__ import annotations

import asyncio
import os

MODEL = os.getenv("KNOWLEDGE_MODEL", "gemini-2.5-flash")
TIMEOUT_SEC = float(os.getenv("KNOWLEDGE_TIMEOUT_SEC", "30"))
# Budget de réflexion : c'est lui qui fait la différence sur les questions de fond.
THINKING_BUDGET = int(os.getenv("KNOWLEDGE_THINKING_BUDGET", "2048"))

_SYSTEM = """Tu es le fond de réflexion d'Ada, l'assistante de Bryan.

Bryan pose une question à Ada ; c'est toi qui réfléchis, et Ada relaiera ta
réponse à voix haute. Écris donc une réponse DITE, pas un article :

- va droit au but, sans préambule ni « bien sûr » ;
- structure par étapes numérotées seulement si c'est une procédure ;
- reste concret : commandes exactes, noms de menus, valeurs précises ;
- si plusieurs approches existent, donne la meilleure et dis pourquoi en une
  phrase, sans lister toutes les alternatives ;
- pas de markdown, pas de titres, pas de gras : ce texte sera prononcé ;
- longueur : le minimum qui répond vraiment. Trois phrases si ça suffit.

Si la question demande une information postérieure à tes connaissances (prix
actuel, actualité, version récente), dis-le en une phrase au lieu d'inventer :
Ada saura alors lancer une recherche web.

Langue : français."""


class KnowledgeEngine:
    """Répond aux questions de fond via un modèle texte avec réflexion."""

    def __init__(self, client=None):
        self._client = client

    @property
    def enabled(self) -> bool:
        raw = os.getenv("KNOWLEDGE_ENABLED")
        return True if raw is None else raw.strip().lower() in {"1", "true", "yes", "on"}

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
            print(f"[KNOWLEDGE] client indisponible : {exc}")
            return None

    async def ask(self, question: str, contexte: str = "") -> str:
        question = (question or "").strip()
        if not question:
            return "Aucune question fournie."
        if not self.enabled:
            return ""

        client = self._get_client()
        if client is None:
            return "Je n'ai pas accès à mon moteur de réflexion (clé Gemini absente)."

        prompt = question if not contexte else f"{question}\n\nContexte : {contexte}"

        try:
            from google.genai import types

            config = types.GenerateContentConfig(
                system_instruction=_SYSTEM,
                temperature=0.4,
                max_output_tokens=1400,
            )
            # Le budget de réflexion n'est pas supporté par tous les modèles :
            # on l'active si possible, sans jamais bloquer la réponse.
            try:
                config.thinking_config = types.ThinkingConfig(
                    thinking_budget=THINKING_BUDGET
                )
            except Exception:
                pass

            response = await asyncio.wait_for(
                client.aio.models.generate_content(
                    model=MODEL, contents=prompt, config=config
                ),
                timeout=TIMEOUT_SEC,
            )
            texte = (response.text or "").strip()
            return texte or "Je n'ai pas réussi à formuler de réponse utile."
        except asyncio.TimeoutError:
            return "Ma réflexion a pris trop de temps — reformule ou demande plus court."
        except Exception as exc:  # noqa: BLE001
            print(f"[KNOWLEDGE] échec : {exc}")
            return f"Je n'ai pas pu réfléchir à ça : {exc}"


_ENGINE: KnowledgeEngine | None = None


def get_engine() -> KnowledgeEngine:
    global _ENGINE
    if _ENGINE is None:
        _ENGINE = KnowledgeEngine()
    return _ENGINE


async def think(question: str, contexte: str = "") -> str:
    return await get_engine().ask(question, contexte)
