"""
ResearchAgent — Sub-agent de recherche autonome.

Flow :
  1. Plan   : Gemini liste les angles et sources à couvrir
  2. Gather : appels parallèles WikipediaMCP / ArxivMCP / YouTubeMCP
  3. Synth  : Gemini synthétise en rapport markdown structuré

Usage depuis ada.py :
    result = await self.research_agent.run("les dernières avancées en computer vision")
"""

import asyncio
import json
import os
import re

from google import genai

from mcps.wikipedia_mcp import WikipediaMCP
from mcps.arxiv_mcp import ArxivMCP
from mcps.youtube_mcp import YouTubeMCP

SUB_MODEL = "gemini-2.0-flash-lite"
_client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))


class ResearchAgent:
    def __init__(
        self,
        wikipedia: WikipediaMCP | None = None,
        arxiv: ArxivMCP | None = None,
        youtube: YouTubeMCP | None = None,
    ):
        self.wikipedia = wikipedia or WikipediaMCP()
        self.arxiv = arxiv or ArxivMCP()
        self.youtube = youtube or YouTubeMCP()

    # ─── PUBLIC ──────────────────────────────────────────────────────────────

    async def run(self, query: str) -> str:
        """Recherche complète sur `query`. Retourne un rapport markdown."""
        angles = await self._plan(query)
        raw_data = await self._gather(query, angles)
        return await self._synthesize(query, raw_data)

    # ─── PRIVATE ─────────────────────────────────────────────────────────────

    async def _plan(self, query: str) -> list[dict]:
        """Passe 1 : Gemini décompose la requête en angles + sources."""
        response = await _client.aio.models.generate_content(
            model=SUB_MODEL,
            contents=(
                "Tu es un agent de recherche. Pour la requête suivante, liste en JSON "
                "les 3 à 5 angles de recherche à couvrir et les sources les plus pertinentes "
                "(wikipedia, arxiv, youtube).\n\n"
                f"Requête : {query}\n\n"
                "Réponds UNIQUEMENT avec un JSON valide :\n"
                '{"angles": [{"angle": "...", "sources": ["wikipedia"], "search_query": "..."}]}'
            ),
        )
        try:
            m = re.search(r"\{.*\}", response.text, re.DOTALL)
            plan = json.loads(m.group())
            return plan.get("angles", [])
        except Exception:
            return [{"angle": query, "sources": ["wikipedia", "arxiv"], "search_query": query}]

    async def _gather(self, query: str, angles: list[dict]) -> str:
        """Passe 2 : collecte toutes les sources en parallèle."""
        sections = await asyncio.gather(*[self._gather_angle(query, a) for a in angles])
        return "\n\n---\n\n".join(sections)

    async def _gather_angle(self, fallback_query: str, angle_data: dict) -> str:
        sq = angle_data.get("search_query") or fallback_query
        sources = angle_data.get("sources", [])

        calls = []
        if "wikipedia" in sources:
            calls.append(asyncio.to_thread(self.wikipedia.search, sq, 3))
        if "arxiv" in sources:
            calls.append(asyncio.to_thread(self.arxiv.search, sq, 3))
        if "youtube" in sources:
            calls.append(asyncio.to_thread(self.youtube.search_videos, sq, 3))

        gathered = await asyncio.gather(*calls, return_exceptions=True)
        parts = [str(g) for g in gathered if not isinstance(g, Exception)]
        return f"### {angle_data.get('angle', sq)}\n" + "\n\n".join(parts)

    async def _synthesize(self, query: str, raw_data: str) -> str:
        """Passe 3 : Gemini produit le rapport final."""
        response = await _client.aio.models.generate_content(
            model=SUB_MODEL,
            contents=(
                f"Tu es un expert en synthèse d'information. Voici les données brutes "
                f"collectées sur le sujet \"{query}\".\n\n"
                f"{raw_data}\n\n"
                "Produis un rapport structuré en markdown avec :\n"
                "- Un résumé exécutif (3-5 phrases)\n"
                "- Les points clés par angle\n"
                "- Les sources et références notables\n"
                "- Une conclusion avec recommandations si pertinent\n\n"
                "Rapport en français, clair et concis."
            ),
        )
        return response.text
