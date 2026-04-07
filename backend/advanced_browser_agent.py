"""
advanced_browser_agent.py — Agent de navigation web avancée (browser-use v0.12.6 + Gemini)

Capacités vs web_agent.py :
- Loop agentic délégué à browser-use (planning, retry, multi-pages)
- Cookies persistants (sessions LinkedIn, Gmail, etc.)
- Headless auto : visible en local si BROWSER_HEADLESS=false + DISPLAY présent
- Feedback frontend via callback step (log intercepteur browser-use)

NOTE ARCHITECTURE : Ce fichier utilise langchain-google-genai comme adaptateur LLM.
browser-use v0.12.6 requiert obligatoirement un LLM LangChain (BaseChatModel) — il n'existe
pas d'interface Gemini native dans cette version. C'est la seule exception acceptée au
principe "pas de LangChain" du projet.
"""

import asyncio
import logging
import os
from pathlib import Path
from typing import Callable, Optional

from dotenv import load_dotenv

load_dotenv()

JARVIS_ROOT = Path(os.getenv("JARVIS_ROOT", "/Users/bryandev/jarvis")).resolve()
SESSION_DIR = JARVIS_ROOT / "projects" / "browser_session"
COOKIES_FILE = SESSION_DIR / "cookies.json"
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")


def _is_headless() -> bool:
    """
    Détermine le mode headless :
    - BROWSER_HEADLESS=true (défaut) → toujours headless
    - BROWSER_HEADLESS=false + DISPLAY présent (Mac dev) → navigateur visible
    - BROWSER_HEADLESS=false + pas de DISPLAY (VPS) → headless silencieux
    """
    if os.getenv("BROWSER_HEADLESS", "true").lower() == "false":
        # DISPLAY absent (VPS) → is None = True → headless
        # DISPLAY présent (Mac) → is None = False → visible
        return os.environ.get("DISPLAY") is None
    return True


class AdvancedBrowserAgent:
    def __init__(self):
        if not GEMINI_API_KEY:
            raise RuntimeError("GEMINI_API_KEY non configurée.")
        SESSION_DIR.mkdir(parents=True, exist_ok=True)

    def _get_llm(self):
        from langchain_google_genai import ChatGoogleGenerativeAI
        return ChatGoogleGenerativeAI(
            model="gemini-2.5-flash",
            google_api_key=GEMINI_API_KEY,
            temperature=0.3,
        )

    def _setup_log_interceptor(self, step_callback: Callable) -> logging.Handler:
        """
        Intercepte les logs browser-use pour envoyer les actions en cours au frontend.
        browser-use log ses actions avec des emojis → on filtre sur ces patterns.
        """
        loop = asyncio.get_running_loop()

        class _BrowserUseHandler(logging.Handler):
            _KEYWORDS = ("Action:", "Executing", "Navigate", "Click", "Type",
                         "Scroll", "Step", "🌐", "🖱", "⌨", "📍", "✅", "❌")

            def emit(self_, record: logging.LogRecord) -> None:
                msg = record.getMessage()
                if any(kw in msg for kw in self_._KEYWORDS):
                    clean = msg[:150].replace("\n", " ")
                    try:
                        asyncio.run_coroutine_threadsafe(
                            step_callback({"image": None, "log": f"[BROWSER] {clean}"}),
                            loop,
                        )
                    except Exception:
                        pass

        handler = _BrowserUseHandler()
        handler.setLevel(logging.INFO)
        logging.getLogger("browser_use").addHandler(handler)
        return handler

    def _remove_log_interceptor(self, handler: logging.Handler) -> None:
        logging.getLogger("browser_use").removeHandler(handler)

    async def run(self, mission: str, step_callback: Optional[Callable] = None) -> str:
        """
        Exécute une mission web complexe.

        Args:
            mission: Description en langage naturel de la mission à accomplir.
            step_callback: Coroutine appelée à chaque étape → {"image": b64|None, "log": str}.
                           None quand appelé depuis le bridge Telegram.

        Returns:
            Résumé textuel du résultat. Jamais d'exception non catchée.
        """
        from browser_use import Agent, Browser

        headless = _is_headless()

        if not headless:
            print("[AdvancedBrowser] Mode visible activé (BROWSER_HEADLESS=false + DISPLAY présent).")
        elif os.getenv("BROWSER_HEADLESS", "true").lower() == "false":
            print("[AdvancedBrowser] BROWSER_HEADLESS=false mais DISPLAY absent — fallback headless.")

        if step_callback:
            await step_callback({"image": None, "log": f"[BROWSER] Mission démarrée : {mission[:100]}"})

        log_handler = None
        if step_callback:
            log_handler = self._setup_log_interceptor(step_callback)

        browser = None
        try:
            llm = self._get_llm()

            # browser-use v0.12.6 : Browser == BrowserSession (Pydantic model).
            # headless et storage_state sont des champs de BrowserProfile.
            from browser_use import BrowserProfile
            storage_state = str(COOKIES_FILE) if COOKIES_FILE.exists() else None
            profile = BrowserProfile(headless=headless, storage_state=storage_state)

            browser = Browser(browser_profile=profile)

            agent = Agent(task=mission, llm=llm, browser=browser)

            # Exécuter la mission
            result = await agent.run(max_steps=50)
            final = result.final_result() if hasattr(result, "final_result") else str(result)
            final = final or "Mission terminée."

            # Sauvegarder les cookies après la session.
            # browser-use v0.12.6 : BrowserSession expose export_storage_state(output_path)
            # qui extrait les cookies via CDP et les écrit directement au format Playwright.
            try:
                await browser.export_storage_state(output_path=COOKIES_FILE)
                print(f"[AdvancedBrowser] Cookies sauvegardés → {COOKIES_FILE}")
            except Exception as e:
                print(f"[AdvancedBrowser] Cookie save warning : {e}")

            if step_callback:
                await step_callback({"image": None, "log": f"[BROWSER] ✓ {final[:120]}"})

            return final

        except Exception as e:
            print(f"[AdvancedBrowser] Erreur : {e}")
            if step_callback:
                await step_callback({"image": None, "log": f"[BROWSER] Erreur : {e}"})
            return f"Erreur navigation avancée : {e}"

        finally:
            if log_handler:
                self._remove_log_interceptor(log_handler)
            if browser is not None:
                try:
                    await browser.close()
                except Exception:
                    pass
