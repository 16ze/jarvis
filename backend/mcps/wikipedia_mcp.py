import re


class WikipediaMCP:
    def __init__(self):
        self._wikis = {}

    def _get_wiki(self, lang: str = "fr"):
        if lang not in self._wikis:
            import wikipediaapi
            self._wikis[lang] = wikipediaapi.Wikipedia(
                language=lang,
                user_agent="Jarvis/1.0 (assistant IA personnel)",
            )
        return self._wikis[lang]

    def search(self, query: str, limit: int = 5) -> str:
        try:
            import wikipediaapi
            # wikipediaapi ne fournit pas de recherche native — on utilise l'API MediaWiki via httpx
            import httpx
            params = {
                "action": "query",
                "list": "search",
                "srsearch": query,
                "srlimit": limit,
                "format": "json",
            }
            response = httpx.get("https://fr.wikipedia.org/w/api.php", params=params, timeout=10)
            response.raise_for_status()
            data = response.json()
            results = data.get("query", {}).get("search", [])
            if not results:
                return f"Aucun article Wikipedia trouvé pour '{query}'."
            lines = [f"Résultats Wikipedia pour '{query}':"]
            for r in results:
                title = r.get("title", "?")
                snippet = re.sub(r"<[^>]+>", "", r.get("snippet", ""))
                lines.append(f"  {title}: {snippet}...")
            return "\n".join(lines)
        except Exception as e:
            return f"Erreur Wikipedia: {str(e)}"

    def get_article(self, title: str, lang: str = "fr") -> str:
        try:
            wiki = self._get_wiki(lang)
            page = wiki.page(title)
            if not page.exists():
                return f"Article Wikipedia introuvable: '{title}' (lang: {lang})"
            summary = page.summary[:500] if page.summary else "(pas de résumé)"
            content = page.text[:2000] if page.text else "(pas de contenu)"
            url = page.fullurl
            sections = list(page.sections)
            section_titles = [s.title for s in sections[:8]]
            lines = [
                f"Article: {page.title}",
                f"URL: {url}",
                f"Résumé:\n{summary}",
                f"\nSections: {', '.join(section_titles) if section_titles else 'N/A'}",
                f"\nContenu (2000 premiers caractères):\n{content}",
            ]
            if len(page.text) > 2000:
                lines.append(f"... [{len(page.text) - 2000} caractères supplémentaires disponibles]")
            return "\n".join(lines)
        except Exception as e:
            return f"Erreur Wikipedia: {str(e)}"

    def get_summary(self, title: str, lang: str = "fr") -> str:
        try:
            wiki = self._get_wiki(lang)
            page = wiki.page(title)
            if not page.exists():
                return f"Article Wikipedia introuvable: '{title}' (lang: {lang})"
            summary = page.summary
            if not summary:
                return f"Aucun résumé disponible pour '{title}'."
            return f"{page.title} ({lang}):\n{summary}"
        except Exception as e:
            return f"Erreur Wikipedia: {str(e)}"
