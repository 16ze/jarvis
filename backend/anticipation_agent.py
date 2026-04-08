"""
AnticipationAgent — Sub-agent de prédiction proactive des besoins.

Flow :
  1. Collect : récupère mémoire Ada + historique chat récent + heure actuelle
  2. Predict : Gemini analyse les patterns et retourne des suggestions JSON

Usage depuis ada.py :
    result = await self.anticipation_agent.run()
    # ou avec contexte additionnel :
    result = await self.anticipation_agent.run("Bryan part en voyage demain")
"""

import asyncio
import json
import os
import re
from datetime import datetime

from google import genai

SUB_MODEL = "gemini-2.0-flash-lite"
_client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

_PRIORITY_EMOJI = {"haute": "🔴", "moyenne": "🟡", "basse": "🟢"}


class AnticipationAgent:
    def __init__(self, memory=None, project_manager=None):
        self._memory = memory
        self._project_manager = project_manager

    # ─── PUBLIC ──────────────────────────────────────────────────────────────

    async def run(self, context: str = "") -> str:
        """Analyse le contexte et retourne des suggestions proactives formatées."""
        full_context = await self._collect_context(context)
        return await self._predict(full_context)

    # ─── PRIVATE ─────────────────────────────────────────────────────────────

    async def _collect_context(self, extra: str) -> str:
        """Rassemble le contexte disponible : heure, mémoire, historique, extra."""
        parts: list[str] = []

        # Heure actuelle
        now = datetime.now().strftime("%A %d %B %Y à %H:%M")
        parts.append(f"Date et heure : {now}")

        # Mémoire persistante Ada
        if self._memory:
            try:
                startup_ctx = await asyncio.to_thread(self._memory.get_startup_context)
                if startup_ctx:
                    parts.append(f"Mémoire Ada :\n{startup_ctx[:2000]}")
            except Exception:
                pass

        # Historique récent des conversations
        if self._project_manager:
            try:
                history = await asyncio.to_thread(
                    self._project_manager.get_recent_chat_history, 20
                )
                if history:
                    lines = [
                        f"[{e.get('sender', '?')}]: {e.get('text', '')}"
                        for e in history
                    ]
                    parts.append("Historique récent :\n" + "\n".join(lines))
            except Exception:
                pass

        if extra:
            parts.append(f"Contexte additionnel : {extra}")

        return "\n\n".join(parts)

    async def _predict(self, full_context: str) -> str:
        """Passe Gemini : analyse et retourne des suggestions proactives."""
        response = await _client.aio.models.generate_content(
            model=SUB_MODEL,
            contents=(
                "Tu es l'agent d'anticipation d'Ada, assistante personnelle de Bryan "
                "(fondateur Kairo Digital — objectif : 4 500€/mois avant été 2026).\n\n"
                "Analyse ce contexte et prédit les besoins imminents de Bryan "
                "pour les prochaines heures.\n\n"
                f"{full_context}\n\n"
                "Produis une liste de suggestions proactives en JSON :\n"
                '{"suggestions": ['
                '{"priorite": "haute|moyenne|basse", '
                '"categorie": "communication|travail|santé|finance|rappel", '
                '"message": "...", "action_recommandee": "..."}], '
                '"resume": "..."}\n\n'
                "Focus sur ce qui est actionnable MAINTENANT. Maximum 5 suggestions. "
                "Réponds UNIQUEMENT avec le JSON."
            ),
        )
        return self._format(response.text)

    def _format(self, raw: str) -> str:
        """Transforme le JSON Gemini en texte lisible."""
        try:
            m = re.search(r"\{.*\}", raw, re.DOTALL)
            data = json.loads(m.group())
            suggestions = data.get("suggestions", [])
            resume = data.get("resume", "")

            lines = [f"**Anticipations Ada** — {resume}\n"]
            for s in suggestions:
                emoji = _PRIORITY_EMOJI.get(s.get("priorite", ""), "⚪")
                cat = s.get("categorie", "")
                msg = s.get("message", "")
                action = s.get("action_recommandee", "")
                lines.append(f"{emoji} [{cat}] {msg}")
                if action:
                    lines.append(f"   → {action}")
            return "\n".join(lines)
        except Exception:
            return raw
