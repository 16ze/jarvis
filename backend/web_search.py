"""
web_search — recherche web unifiée pour Ada, en cascade et robuste.

Ordre de priorité :
  1. Brave Search  (BRAVE_SEARCH_API_KEY)     — meilleure qualité.
  2. Google CSE    (GOOGLE_SEARCH_API_KEY + GOOGLE_SEARCH_ENGINE_ID).
  3. DuckDuckGo    (sans clé)                  — toujours disponible.

Objectif : la recherche web fonctionne DÈS L'INSTALLATION (via DuckDuckGo),
et gagne en qualité si une clé Brave/Google est fournie.

Retourne toujours une `str` prête à être renvoyée au modèle — jamais d'exception.
"""

from __future__ import annotations

import html
import os
import re

import httpx

_UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
       "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36")


def _format(results: list[dict], source: str, query: str) -> str:
    if not results:
        return f"Aucun résultat web pour « {query} »."
    lines = [f"Résultats web pour « {query} » (via {source}) :"]
    for i, r in enumerate(results, 1):
        title = r.get("title") or r.get("url") or "(sans titre)"
        url = r.get("url") or ""
        snippet = (r.get("snippet") or "").strip()
        lines.append(f"{i}. {title}\n   {url}" + (f"\n   {snippet}" if snippet else ""))
    return "\n".join(lines)


async def _brave(query: str, n: int) -> list[dict] | None:
    key = os.getenv("BRAVE_SEARCH_API_KEY", "")
    if not key:
        return None
    try:
        async with httpx.AsyncClient(timeout=12) as c:
            resp = await c.get(
                "https://api.search.brave.com/res/v1/web/search",
                params={"q": query, "count": max(1, min(n, 20)), "country": "FR",
                        "search_lang": "fr", "safesearch": "moderate"},
                headers={"Accept": "application/json", "X-Subscription-Token": key},
            )
            resp.raise_for_status()
            items = (resp.json().get("web", {}) or {}).get("results", []) or []
            return [
                {"title": it.get("title", ""), "url": it.get("url", ""),
                 "snippet": it.get("description", "")}
                for it in items[:n] if it.get("url")
            ]
    except Exception as exc:  # noqa: BLE001
        print(f"[web_search] Brave a échoué : {exc}")
        return None


async def _google(query: str, n: int) -> list[dict] | None:
    key = os.getenv("GOOGLE_SEARCH_API_KEY", "")
    cx = os.getenv("GOOGLE_SEARCH_ENGINE_ID", "") or os.getenv("GOOGLE_CSE_ID", "")
    if not (key and cx):
        return None
    try:
        async with httpx.AsyncClient(timeout=12) as c:
            resp = await c.get(
                "https://www.googleapis.com/customsearch/v1",
                params={"key": key, "cx": cx, "q": query, "num": max(1, min(n, 10)),
                        "hl": "fr"},
            )
            resp.raise_for_status()
            items = resp.json().get("items", []) or []
            return [
                {"title": it.get("title", ""), "url": it.get("link", ""),
                 "snippet": it.get("snippet", "")}
                for it in items[:n] if it.get("link")
            ]
    except Exception as exc:  # noqa: BLE001
        print(f"[web_search] Google a échoué : {exc}")
        return None


_DDG_BLOCK = re.compile(
    r'<a[^>]*class="result__a"[^>]*href="(?P<url>[^"]+)"[^>]*>(?P<title>.*?)</a>'
    r'(?:.*?<a[^>]*class="result__snippet"[^>]*>(?P<snippet>.*?)</a>)?',
    re.IGNORECASE | re.DOTALL,
)


def _strip_tags(text: str) -> str:
    return html.unescape(re.sub(r"<[^>]+>", "", text or "")).strip()


def _ddg_clean_url(url: str) -> str:
    # DDG HTML enrobe parfois l'URL dans un redirect uddg=
    m = re.search(r"uddg=([^&]+)", url)
    if m:
        from urllib.parse import unquote
        return unquote(m.group(1))
    return url


async def _duckduckgo(query: str, n: int) -> list[dict] | None:
    try:
        async with httpx.AsyncClient(timeout=12, follow_redirects=True) as c:
            resp = await c.post(
                "https://html.duckduckgo.com/html/",
                data={"q": query, "kl": "fr-fr"},
                headers={"User-Agent": _UA, "Accept": "text/html"},
            )
            resp.raise_for_status()
            out = []
            for m in _DDG_BLOCK.finditer(resp.text):
                url = _ddg_clean_url(m.group("url"))
                title = _strip_tags(m.group("title"))
                snippet = _strip_tags(m.group("snippet") or "")
                if url.startswith("http") and title:
                    out.append({"title": title, "url": url, "snippet": snippet})
                if len(out) >= n:
                    break
            return out
    except Exception as exc:  # noqa: BLE001
        print(f"[web_search] DuckDuckGo a échoué : {exc}")
        return None


async def web_search(query: str, max_results: int = 6) -> str:
    """Recherche web en cascade. Retourne une chaîne formatée pour le modèle."""
    query = (query or "").strip()
    if not query:
        return "Requête de recherche vide."

    for name, fn in (("Brave", _brave), ("Google", _google), ("DuckDuckGo", _duckduckgo)):
        results = await fn(query, max_results)
        if results:
            return _format(results, name, query)

    return (f"Aucun résultat pour « {query} ». Les moteurs web n'ont rien renvoyé "
            "(vérifie la connexion, ou configure BRAVE_SEARCH_API_KEY pour de "
            "meilleurs résultats).")
