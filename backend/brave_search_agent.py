"""BraveSearchAgent — recherche web via Brave Search API.

Pourquoi Brave plutôt que Google Custom Search :
- Pas de Custom Search Engine ID à créer
- Pas de billing account GCP requis pour le free tier (2000 req/mois)
- Index web indépendant (crawler Brave Search)
- Une seule variable d'env : BRAVE_SEARCH_API_KEY

Garde la MÊME interface publique que GoogleSearchAgent (search/to_markdown/configured)
pour rester drop-in compatible avec workspace_research_agent.
"""

from __future__ import annotations

import os
from dataclasses import asdict, dataclass
from pathlib import Path

import httpx
from dotenv import load_dotenv


BACKEND_DIR = Path(__file__).resolve().parent
load_dotenv(BACKEND_DIR / ".env")
load_dotenv(BACKEND_DIR.parent / ".env")


@dataclass
class BraveSearchResult:
    title: str
    url: str
    snippet: str
    source: str = "brave"

    def to_dict(self) -> dict:
        return asdict(self)


class BraveSearchAgent:
    """Client minimal pour Brave Search API (Web Search endpoint)."""

    API_URL = "https://api.search.brave.com/res/v1/web/search"

    def __init__(self, api_key: str | None = None):
        self.api_key = api_key or os.getenv("BRAVE_SEARCH_API_KEY", "")

    @property
    def configured(self) -> bool:
        return bool(self.api_key)

    async def search(
        self,
        query: str,
        limit: int = 8,
        language: str = "fr",
        country: str = "FR",
    ) -> list[BraveSearchResult]:
        if not self.configured:
            raise RuntimeError(
                "Brave Search non configuré : définir BRAVE_SEARCH_API_KEY dans .env."
            )

        # Brave accepte count entre 1 et 20.
        safe_limit = max(1, min(int(limit), 20))
        params = {
            "q": query,
            "count": safe_limit,
            "search_lang": language,
            "country": country,
            "safesearch": "moderate",
        }
        headers = {
            "Accept": "application/json",
            "Accept-Encoding": "gzip",
            "X-Subscription-Token": self.api_key,
        }

        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.get(self.API_URL, params=params, headers=headers)
            if response.status_code >= 400:
                # Brave renvoie soit un JSON {meta, error}, soit du texte selon le cas.
                message = f"Erreur Brave Search HTTP {response.status_code}"
                try:
                    payload = response.json()
                    err = (payload.get("error") or {}) if isinstance(payload, dict) else {}
                    message = err.get("detail") or err.get("message") or payload.get("message") or message
                except Exception:
                    body = response.text.strip()
                    if body:
                        message = f"{message}: {body[:200]}"
                raise RuntimeError(message)
            data = response.json()

        results: list[BraveSearchResult] = []
        web_block = data.get("web") or {}
        for item in web_block.get("results", []):
            title = (item.get("title") or "").strip()
            url = (item.get("url") or "").strip()
            # Brave nomme le snippet `description`.
            snippet = (item.get("description") or "").strip()
            if title and url:
                results.append(BraveSearchResult(title=title, url=url, snippet=snippet))
        return results

    @staticmethod
    def to_markdown(query: str, results: list[BraveSearchResult]) -> str:
        if not results:
            return f"Aucun résultat Brave trouvé pour : {query}"
        lines = [f"## Résultats Brave pour : {query}"]
        for index, result in enumerate(results, start=1):
            lines.append(
                f"{index}. [{result.title}]({result.url})\n"
                f"   - {result.snippet or 'Aucun extrait disponible.'}"
            )
        return "\n".join(lines)
