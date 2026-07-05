"""Agent de recherche sauvegardée dans un workspace ADA."""

from __future__ import annotations

import re
import os
from datetime import datetime, timezone

from google import genai

from brave_search_agent import BraveSearchAgent, BraveSearchResult
from research_agent import ResearchAgent
from workspace_event_bus import WorkspaceEventBus
from workspace_manager import WorkspaceManager

SUB_MODEL = os.getenv("ADA_SUB_MODEL", "gemini-2.5-flash")


class WorkspaceResearchAgent:
    def __init__(
        self,
        workspace_manager: WorkspaceManager,
        research_agent: ResearchAgent | None = None,
        event_bus: WorkspaceEventBus | None = None,
        search_agent: BraveSearchAgent | None = None,
    ):
        self.workspace_manager = workspace_manager
        self.research_agent = research_agent or ResearchAgent()
        self.event_bus = event_bus or WorkspaceEventBus()
        self.search_agent = search_agent or BraveSearchAgent()
        self._client = genai.Client()
        self._last_search_error = ""

    async def run(
        self,
        query: str,
        depth: str = "standard",
        workspace: str | None = None,
        save_sources: bool = True,
        synthesize: bool = True,
    ) -> str:
        if not query.strip():
            return "Erreur : requête de recherche vide."

        if workspace:
            self.workspace_manager.create_workspace(workspace)

        active = self.workspace_manager.get_active_workspace()["activeWorkspace"]
        await self.event_bus.emit_status(f"Recherche workspace lancée : {query}", "info")
        await self.event_bus.emit_activity(
            {
                "type": "research_started",
                "query": query,
                "depth": depth,
                "synthesize": synthesize,
            }
        )

        search_results = await self._search_web(query, depth)
        structured_results: list[dict] = []
        if search_results:
            await self.event_bus.emit_activity(
                {
                    "type": "search_results_collected",
                    "engine": "brave",
                    "query": query,
                    "count": len(search_results),
                }
            )
            for result in search_results:
                saved_id: str | None = None
                if save_sources:
                    saved_id = self.workspace_manager.add_source(
                        url=result.url,
                        title=result.title,
                        summary=result.snippet,
                    )
                structured_results.append(
                    {
                        "title": result.title,
                        "url": result.url,
                        "snippet": result.snippet,
                        "source": result.source,
                        "savedItemId": saved_id,
                    }
                )
            if synthesize:
                markdown = await self._synthesize_search_results(query, search_results, depth)
            else:
                markdown = BraveSearchAgent.to_markdown(query, search_results)
        else:
            if synthesize:
                await self.event_bus.emit_status(
                    "Brave Search indisponible ou sans résultat, fallback vers l'agent recherche existant.",
                    "warning",
                )
                markdown = await self.research_agent.run(query)
            else:
                reason = f" Détail : {self._last_search_error}" if self._last_search_error else ""
                markdown = f"Brave Search indisponible ou sans résultat.{reason}"
        filename = f"{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}-research.md"
        artifact_id = self.workspace_manager.add_artifact(filename, markdown, "artifact")

        if save_sources and not search_results:
            for url in self._extract_urls(markdown)[:12]:
                self.workspace_manager.add_source(url=url, title=url, summary=f"Source mentionnée dans la recherche : {query}")

        state = self.workspace_manager.get_active_workspace()
        await self.event_bus.emit_activity({"type": "research_completed", "query": query, "artifactId": artifact_id})
        await self.event_bus.emit_research_result(
            active,
            markdown,
            query=query,
            depth=depth,
            synthesized=synthesize,
            results=structured_results,
        )
        await self.event_bus.emit_state(state)
        return markdown

    async def _search_web(self, query: str, depth: str) -> list[BraveSearchResult]:
        # Brave accepte count jusqu'à 20 — on monte un peu pour "deep".
        limit_by_depth = {"quick": 5, "standard": 8, "deep": 15}
        self._last_search_error = ""
        try:
            return await self.search_agent.search(
                query=query,
                limit=limit_by_depth.get(depth, 8),
            )
        except Exception as exc:
            self._last_search_error = str(exc)
            await self.event_bus.emit_activity(
                {
                    "type": "search_unavailable",
                    "engine": "brave",
                    "query": query,
                    "message": str(exc),
                }
            )
            return []

    async def _synthesize_search_results(
        self,
        query: str,
        results: list[BraveSearchResult],
        depth: str,
    ) -> str:
        raw_results = BraveSearchAgent.to_markdown(query, results)
        response = await self._client.aio.models.generate_content(
            model=SUB_MODEL,
            contents=(
                "Tu es AdaSearch, un moteur de recherche dans ADA. "
                "À partir des résultats Brave Search ci-dessous, produis une synthèse utile en français.\n\n"
                f"Requête : {query}\n"
                f"Profondeur : {depth}\n\n"
                f"{raw_results}\n\n"
                "Format attendu :\n"
                "1. Résumé direct\n"
                "2. Points clés vérifiables\n"
                "3. Sources recommandées avec liens markdown\n"
                "4. Prochaines recherches utiles\n\n"
                "Ne prétends pas avoir lu une page complète si seul le snippet est disponible."
            ),
        )
        return response.text

    @staticmethod
    def _extract_urls(markdown: str) -> list[str]:
        seen: set[str] = set()
        urls: list[str] = []
        for match in re.findall(r"https?://[^\s)>\]]+", markdown):
            clean = match.rstrip(".,;:")
            if clean not in seen:
                seen.add(clean)
                urls.append(clean)
        return urls
