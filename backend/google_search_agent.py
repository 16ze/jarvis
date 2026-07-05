"""GoogleSearchAgent — recherche Google via Programmable Search JSON API."""

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
class GoogleSearchResult:
    title: str
    url: str
    snippet: str
    source: str = "google"

    def to_dict(self) -> dict:
        return asdict(self)


class GoogleSearchAgent:
    """Client minimal pour Google Programmable Search."""

    API_URL = "https://www.googleapis.com/customsearch/v1"

    def __init__(self, api_key: str | None = None, search_engine_id: str | None = None):
        self.api_key = api_key or os.getenv("GOOGLE_SEARCH_API_KEY", "")
        self.search_engine_id = (
            search_engine_id
            or os.getenv("GOOGLE_SEARCH_ENGINE_ID", "")
            or os.getenv("GOOGLE_CSE_ID", "")
        )

    @property
    def configured(self) -> bool:
        return bool(self.api_key and self.search_engine_id)

    async def search(self, query: str, limit: int = 8, language: str = "fr") -> list[GoogleSearchResult]:
        if not self.configured:
            raise RuntimeError(
                "Google Search non configuré : définir GOOGLE_SEARCH_API_KEY et GOOGLE_SEARCH_ENGINE_ID."
            )

        safe_limit = max(1, min(int(limit), 10))
        params = {
            "key": self.api_key,
            "cx": self.search_engine_id,
            "q": query,
            "num": safe_limit,
            "hl": language,
            "lr": f"lang_{language}",
            "safe": "off",
        }
        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.get(self.API_URL, params=params)
            if response.status_code >= 400:
                message = f"Erreur Google Search HTTP {response.status_code}"
                try:
                    error = response.json().get("error", {})
                    message = error.get("message") or message
                except Exception:
                    pass
                raise RuntimeError(message)
            data = response.json()

        results = []
        for item in data.get("items", []):
            title = item.get("title", "").strip()
            url = item.get("link", "").strip()
            snippet = item.get("snippet", "").strip()
            if title and url:
                results.append(GoogleSearchResult(title=title, url=url, snippet=snippet))
        return results

    @staticmethod
    def to_markdown(query: str, results: list[GoogleSearchResult]) -> str:
        if not results:
            return f"Aucun résultat Google trouvé pour : {query}"
        lines = [f"## Résultats Google pour : {query}"]
        for index, result in enumerate(results, start=1):
            lines.append(
                f"{index}. [{result.title}]({result.url})\n"
                f"   - {result.snippet or 'Aucun extrait disponible.'}"
            )
        return "\n".join(lines)
