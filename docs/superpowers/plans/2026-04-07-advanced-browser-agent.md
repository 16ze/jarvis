# Advanced Browser Agent Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Créer `AdvancedBrowserAgent` (browser-use + LangChain) avec cookies persistants, headless auto, feedback socket, câblé dans ada.py et external_bridge.py.

**Architecture:** `browser-use` gère le loop agentic complet (planning, actions, retry). `langchain-google-genai` adapte Gemini 2.5 Flash pour browser-use. Les cookies Playwright sont sauvegardés dans `projects/browser_session/cookies.json` pour maintenir les sessions LinkedIn/Gmail/etc. Le feedback frontend réutilise le socket `browser_frame` existant.

**Tech Stack:** browser-use ≥0.1.0, langchain-google-genai ≥2.0.0, playwright (déjà installé), asyncio pur

---

## File Map

| Fichier | Action | Rôle |
|---|---|---|
| `backend/advanced_browser_agent.py` | **Créer** | Classe `AdvancedBrowserAgent` |
| `backend/mcp_tools_declarations.py` | **Modifier** | Déclaration `advanced_web_navigation` + ajout MCP_TOOLS |
| `backend/ada.py` | **Modifier** | Import, init, `handle_advanced_browser_request`, dispatch audio loop + `_execute_text_tool` |
| `backend/external_bridge.py` | **Modifier** | Import, init dans `_init_agents`, dispatch dans `_execute_tool` |
| `requirements.txt` | **Modifier** | Ajouter browser-use, langchain-google-genai |
| `.env.example` | **Modifier** | Ajouter `BROWSER_HEADLESS` |

---

## Task 1 : Installer les dépendances

**Files:**
- Modify: `requirements.txt`

- [ ] **Step 1 : Installer les packages**

```bash
cd /Users/bryandev/jarvis
pip install browser-use langchain-google-genai
playwright install chromium
```

Expected output : `Successfully installed browser-use-x.x.x langchain-google-genai-x.x.x`

- [ ] **Step 2 : Vérifier les imports critiques**

```bash
python -c "
from browser_use import Agent, Browser, BrowserConfig
from langchain_google_genai import ChatGoogleGenerativeAI
print('browser-use version:', __import__('browser_use').__version__)
print('OK')
"
```

Expected : `OK` sans erreur.

- [ ] **Step 3 : Vérifier l'API BrowserContextConfig**

```bash
python -c "
from browser_use.browser.context import BrowserContextConfig
import inspect
print(inspect.signature(BrowserContextConfig.__init__))
"
```

Noter si `storage_state` est dans la signature. Si absent, noter qu'on utilisera le contexte Playwright interne.

- [ ] **Step 4 : Mettre à jour requirements.txt**

Ajouter ces deux lignes dans `requirements.txt` :
```
browser-use>=0.1.0
langchain-google-genai>=2.0.0
```

- [ ] **Step 5 : Commit**

```bash
git add requirements.txt
git commit -m "chore: add browser-use and langchain-google-genai dependencies"
```

---

## Task 2 : Créer advanced_browser_agent.py

**Files:**
- Create: `backend/advanced_browser_agent.py`

- [ ] **Step 1 : Créer le fichier**

Créer `backend/advanced_browser_agent.py` avec ce contenu complet :

```python
"""
advanced_browser_agent.py — Agent de navigation web avancée (browser-use + Gemini)

Capacités vs web_agent.py :
- Loop agentic délégué à browser-use (planning, retry, multi-pages)
- Cookies persistants (sessions LinkedIn, Gmail, etc.)
- Headless auto : visible en local si BROWSER_HEADLESS=false + DISPLAY présent
- Feedback frontend via callback step
"""

import asyncio
import json
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
        self._log_handler: Optional[logging.Handler] = None

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
        loop = asyncio.get_event_loop()

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
        from browser_use import Agent, Browser, BrowserConfig

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

        try:
            llm = self._get_llm()
            browser_config = BrowserConfig(headless=headless)

            # Charger les cookies si disponibles
            storage_state = str(COOKIES_FILE) if COOKIES_FILE.exists() else None

            # Tenter BrowserContextConfig avec storage_state (API varie selon la version)
            try:
                from browser_use.browser.context import BrowserContextConfig
                import inspect
                sig = inspect.signature(BrowserContextConfig.__init__)
                if "storage_state" in sig.parameters:
                    ctx_config = BrowserContextConfig(storage_state=storage_state)
                    browser = Browser(config=browser_config)
                    context = await browser.new_context(config=ctx_config)
                else:
                    # storage_state non supporté dans cette version → browser simple
                    browser = Browser(config=browser_config)
                    context = await browser.new_context()
                    if storage_state:
                        print("[AdvancedBrowser] storage_state non supporté dans cette version — cookies ignorés.")

                agent = Agent(task=mission, llm=llm, browser_context=context)

            except (ImportError, TypeError):
                # Fallback : browser simple sans contexte custom
                browser = Browser(config=browser_config)
                agent = Agent(task=mission, llm=llm, browser=browser)
                context = None

            # Exécuter la mission
            result = await agent.run(max_steps=50)
            final = result.final_result() if hasattr(result, "final_result") else str(result)
            final = final or "Mission terminée."

            # Sauvegarder les cookies après la session
            if context is not None:
                try:
                    # Accéder au contexte Playwright interne
                    pw_ctx = None
                    if hasattr(context, "session") and hasattr(context.session, "context"):
                        pw_ctx = context.session.context
                    elif hasattr(context, "_context"):
                        pw_ctx = context._context
                    elif hasattr(context, "playwright_context"):
                        pw_ctx = context.playwright_context

                    if pw_ctx is not None:
                        state = await pw_ctx.storage_state()
                        COOKIES_FILE.write_text(
                            json.dumps(state, ensure_ascii=False, indent=2),
                            encoding="utf-8"
                        )
                        print(f"[AdvancedBrowser] Cookies sauvegardés → {COOKIES_FILE}")
                    else:
                        print("[AdvancedBrowser] Impossible d'accéder au contexte Playwright pour les cookies.")
                except Exception as e:
                    print(f"[AdvancedBrowser] Cookie save warning : {e}")

            try:
                await browser.close()
            except Exception:
                pass

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
```

- [ ] **Step 2 : Vérifier la syntaxe**

```bash
cd /Users/bryandev/jarvis/backend
python -m py_compile advanced_browser_agent.py && echo "OK"
```

Expected : `OK`

- [ ] **Step 3 : Test d'import**

```bash
python -c "from advanced_browser_agent import AdvancedBrowserAgent; print('Import OK')"
```

Expected : `Import OK` (RuntimeError si GEMINI_API_KEY manquante, c'est normal).

- [ ] **Step 4 : Test d'import avec clé**

```bash
python -c "
import os
os.environ['GEMINI_API_KEY'] = 'test'
os.environ['JARVIS_ROOT'] = '/Users/bryandev/jarvis'
from advanced_browser_agent import AdvancedBrowserAgent, _is_headless
agent = AdvancedBrowserAgent()
print('headless:', _is_headless())
print('session_dir:', agent.__class__.__name__, 'OK')
"
```

Expected : `headless: True` (ou False si BROWSER_HEADLESS=false + DISPLAY) + `AdvancedBrowserAgent OK`

- [ ] **Step 5 : Commit**

```bash
git add backend/advanced_browser_agent.py
git commit -m "feat: create AdvancedBrowserAgent (browser-use + cookies + headless auto)"
```

---

## Task 3 : Déclarer le tool dans mcp_tools_declarations.py

**Files:**
- Modify: `backend/mcp_tools_declarations.py:1400-1452`

- [ ] **Step 1 : Ajouter la déclaration avant MCP_TOOLS**

Dans `backend/mcp_tools_declarations.py`, juste avant la ligne `# ─────────────────────────────────────────────────────────────────────────────` qui précède `MCP_TOOLS = [`, ajouter :

```python
# ── ADVANCED BROWSER ──────────────────────────────────────────────────────────
advanced_web_navigation_tool = {
    "name": "advanced_web_navigation",
    "description": (
        "Navigue sur le web de manière complexe (clics, formulaires, "
        "navigation multi-pages, connexion aux comptes) pour accomplir "
        "des missions métier ou personnelles. Utilise les sessions "
        "existantes (LinkedIn, Gmail, etc.) si disponibles."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "mission": {
                "type": "STRING",
                "description": "Description complète de la mission web à accomplir en langage naturel."
            }
        },
        "required": ["mission"]
    }
}
```

- [ ] **Step 2 : Ajouter dans MCP_TOOLS**

Dans la liste `MCP_TOOLS`, ajouter `advanced_web_navigation_tool` dans la section `# Recherche` (après `arxiv_paper_tool`) :

```python
    # Recherche
    youtube_search_tool, youtube_video_info_tool, youtube_transcript_tool,
    wikipedia_search_tool, wikipedia_article_tool,
    arxiv_search_tool, arxiv_paper_tool,
    advanced_web_navigation_tool,  # ← ajouter ici
```

- [ ] **Step 3 : Vérifier**

```bash
cd /Users/bryandev/jarvis/backend
python -c "
from mcp_tools_declarations import MCP_TOOLS, MCP_TOOL_NAMES
assert 'advanced_web_navigation' in MCP_TOOL_NAMES, 'Outil absent !'
tool = next(t for t in MCP_TOOLS if t['name'] == 'advanced_web_navigation')
assert 'mission' in tool['parameters']['properties'], 'Param mission absent !'
print('OK — advanced_web_navigation dans MCP_TOOLS')
"
```

Expected : `OK — advanced_web_navigation dans MCP_TOOLS`

- [ ] **Step 4 : Commit**

```bash
git add backend/mcp_tools_declarations.py
git commit -m "feat: declare advanced_web_navigation tool in MCP_TOOLS"
```

---

## Task 4 : Wiring dans ada.py

**Files:**
- Modify: `backend/ada.py` (3 points : import+init ~line 611, audio loop ~line 1352, _execute_text_tool ~line 2674)

- [ ] **Step 1 : Ajouter import + init dans _init_agents (audio loop)**

Dans `backend/ada.py`, après la ligne `self.web_agent = WebAgent()` (environ ligne 611), ajouter :

```python
        try:
            from advanced_browser_agent import AdvancedBrowserAgent
            self.advanced_browser_agent = AdvancedBrowserAgent()
        except Exception as e:
            import warnings
            warnings.warn(f"[ADA] AdvancedBrowserAgent init: {e}")
            self.advanced_browser_agent = None
```

- [ ] **Step 2 : Ajouter handle_advanced_browser_request**

Dans `backend/ada.py`, juste après la méthode `handle_web_agent_request` (environ ligne 1158), ajouter :

```python
    async def handle_advanced_browser_request(self, mission: str):
        print(f"[ADA DEBUG] [BROWSER+] Advanced Browser Mission: '{mission}'")

        if self.on_web_data:
            self.on_web_data({"image": None, "log": f"[BROWSER+] Mission: {mission[:80]}"})

        async def update_frontend(data: dict):
            if self.on_web_data:
                self.on_web_data(data)

        if not self.advanced_browser_agent:
            result = "AdvancedBrowserAgent non disponible."
        else:
            try:
                result = await self.advanced_browser_agent.run(
                    mission, step_callback=update_frontend
                )
            except Exception as e:
                print(f"[ADA DEBUG] [ERR] AdvancedBrowser crashed: {e}")
                if self.on_web_data:
                    self.on_web_data({"image": None, "log": f"[BROWSER+] Erreur : {e}"})
                result = f"Navigation avancée échouée : {e}"

        try:
            if self.session:
                await self.session.send(
                    input=f"System Notification: Navigation avancée terminée.\nRésultat: {result}",
                    end_of_turn=True,
                )
        except Exception as e:
            print(f"[ADA DEBUG] [ERR] Failed to send advanced browser result: {e}")
```

- [ ] **Step 3 : Dispatcher dans l'audio loop (NON_BLOCKING)**

Dans `backend/ada.py`, dans le bloc de dispatch des tool calls de l'audio loop (environ ligne 1352, après le bloc `elif fc.name == "run_web_agent":`), ajouter :

```python
                                elif fc.name == "advanced_web_navigation":
                                    mission = fc.args.get("mission", "")
                                    print(f"[ADA DEBUG] [TOOL] Tool Call: 'advanced_web_navigation' mission='{mission[:60]}'")
                                    asyncio.create_task(self.handle_advanced_browser_request(mission))
                                    function_response = types.FunctionResponse(
                                        id=fc.id,
                                        name=fc.name,
                                        response={"result": "Navigation avancée démarrée. Je te tiendrai informé."},
                                    )
                                    function_responses.append(function_response)
```

- [ ] **Step 4 : Dispatcher dans _execute_text_tool**

Dans `backend/ada.py`, dans `_execute_text_tool`, après le bloc `elif name == "run_web_agent":` (environ ligne 2674), ajouter :

```python
            # ── NAVIGATION AVANCÉE ────────────────────────────────────────────
            elif name == "advanced_web_navigation":
                if not self.advanced_browser_agent:
                    return "AdvancedBrowserAgent non disponible (vérifier les dépendances)."
                try:
                    return await self.advanced_browser_agent.run(args.get("mission", ""))
                except Exception as e:
                    return f"Navigation avancée erreur : {e}"
```

- [ ] **Step 5 : Vérifier la syntaxe de ada.py**

```bash
cd /Users/bryandev/jarvis/backend
python -m py_compile ada.py && echo "OK"
```

Expected : `OK`

- [ ] **Step 6 : Commit**

```bash
git add backend/ada.py
git commit -m "feat: wire advanced_web_navigation in ada.py (audio loop + _execute_text_tool)"
```

---

## Task 5 : Wiring dans external_bridge.py

**Files:**
- Modify: `backend/external_bridge.py` (2 points : _init_agents ~line 254, _execute_tool ~line 770)

- [ ] **Step 1 : Ajouter init dans _init_agents**

Dans `backend/external_bridge.py`, à la fin de `_init_agents` (après le dernier bloc `try/except` existant, environ ligne 290), ajouter :

```python
        try:
            from advanced_browser_agent import AdvancedBrowserAgent
            self._advanced_browser = AdvancedBrowserAgent()
        except Exception as e:
            warnings.warn(f"[TextAgent] AdvancedBrowserAgent: {e}")
            self._advanced_browser = None
```

- [ ] **Step 2 : Ajouter dispatch dans _execute_tool**

Dans `backend/external_bridge.py`, dans la méthode `_execute_tool`, après le bloc `elif name == "run_task" and self._task:` (environ ligne 774), ajouter :

```python
        elif name == "advanced_web_navigation":
            if not self._advanced_browser:
                return "AdvancedBrowserAgent non disponible (vérifier les dépendances)."
            try:
                return await self._advanced_browser.run(args.get("mission", ""))
            except Exception as e:
                return f"Navigation avancée erreur : {e}"
```

- [ ] **Step 3 : Vérifier que l'outil n'est PAS dans _EXCLUDED_FROM_BRIDGE**

```bash
grep "advanced_web_navigation" /Users/bryandev/jarvis/backend/external_bridge.py
```

Expected : une seule occurrence (le dispatch), **pas** dans `_EXCLUDED_FROM_BRIDGE`.

- [ ] **Step 4 : Vérifier la syntaxe**

```bash
cd /Users/bryandev/jarvis/backend
python -m py_compile external_bridge.py && echo "OK"
```

Expected : `OK`

- [ ] **Step 5 : Commit**

```bash
git add backend/external_bridge.py
git commit -m "feat: wire advanced_web_navigation in external_bridge.py (Telegram enabled)"
```

---

## Task 6 : Mettre à jour .env.example

**Files:**
- Modify: `.env.example`

- [ ] **Step 1 : Ajouter la variable**

Dans `.env.example`, dans la section `# Navigateur / Browser` (créer si absente), ajouter :

```bash
# Navigateur visible en développement (false = visible si DISPLAY disponible, true = headless)
BROWSER_HEADLESS=true
```

- [ ] **Step 2 : Commit**

```bash
git add .env.example
git commit -m "chore: add BROWSER_HEADLESS env var to .env.example"
```

---

## Task 7 : Test d'intégration

- [ ] **Step 1 : Test unitaire headless detection**

```bash
cd /Users/bryandev/jarvis/backend
python -c "
import os
os.environ['GEMINI_API_KEY'] = 'fake'
os.environ['JARVIS_ROOT'] = '/Users/bryandev/jarvis'

from advanced_browser_agent import _is_headless

# Test 1 : défaut = headless
assert _is_headless() == True, 'Défaut devrait être headless'

# Test 2 : BROWSER_HEADLESS=false + pas de DISPLAY → headless
os.environ['BROWSER_HEADLESS'] = 'false'
if 'DISPLAY' in os.environ:
    del os.environ['DISPLAY']
assert _is_headless() == True, 'Sans DISPLAY devrait être headless'

# Test 3 : BROWSER_HEADLESS=false + DISPLAY → visible
os.environ['DISPLAY'] = ':0'
assert _is_headless() == False, 'Avec DISPLAY devrait être visible'

print('Tous les tests headless passent.')
"
```

Expected : `Tous les tests headless passent.`

- [ ] **Step 2 : Test de mission réelle (optionnel, requiert GEMINI_API_KEY valide)**

```bash
cd /Users/bryandev/jarvis/backend
python -c "
import asyncio, os
os.environ['JARVIS_ROOT'] = '/Users/bryandev/jarvis'
from advanced_browser_agent import AdvancedBrowserAgent

async def main():
    agent = AdvancedBrowserAgent()
    result = await agent.run('Va sur wikipedia.org et dis-moi quel est l\'article du jour.')
    print('Résultat:', result[:200])

asyncio.run(main())
"
```

Expected : résumé de l'article Wikipedia du jour.

- [ ] **Step 3 : Vérifier la création du répertoire cookies**

```bash
ls /Users/bryandev/jarvis/projects/browser_session/
```

Expected : dossier créé (possiblement `cookies.json` après le test step 2).

- [ ] **Step 4 : Vérifier l'import complet du serveur**

```bash
cd /Users/bryandev/jarvis/backend
python -c "
import sys
sys.path.insert(0, '.')
# Simuler imports partiels pour vérifier qu'aucun conflit
import mcp_tools_declarations as m
assert 'advanced_web_navigation' in m.MCP_TOOL_NAMES
print('mcp_tools_declarations OK')
import advanced_browser_agent
print('advanced_browser_agent OK')
"
```

Expected : deux lignes `OK`.

- [ ] **Step 5 : Commit final**

```bash
git add -A
git commit -m "feat: advanced_web_navigation — browser-use + cookies + headless auto + wiring complet"
```
