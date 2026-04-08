# Design — Advanced Browser Agent (browser-use)

**Date :** 2026-04-07
**Projet :** Jarvis / Ada
**Statut :** Approuvé

---

## Contexte

Ada dispose déjà de `web_agent.py` : un loop Playwright custom + Gemini vision pour la recherche web rapide. Ce design ajoute un second agent, `advanced_browser_agent.py`, capable de missions web complexes (authentification, formulaires multi-pages, navigation persistante sur des comptes) en déléguant le loop agentic à la librairie `browser-use`.

Les deux agents coexistent et sont complémentaires :
- `run_web_agent` → recherche rapide, scraping, résumé de page
- `advanced_web_navigation` → missions complexes, comptes connectés, interactions multi-étapes

---

## Décisions d'architecture

| Question | Décision | Raison |
|---|---|---|
| Framework LLM | `langchain-google-genai` (LangChain thin wrapper) | `browser-use` ne supporte pas l'API Gemini directement |
| Règle "pas de LangChain" | Exception acceptée | LangChain utilisé uniquement comme adaptateur LLM (2 lignes), pas comme framework agent |
| Headless | Auto-détection : `BROWSER_HEADLESS=false` ET `DISPLAY` présent | Zero config sur VPS, visible en local sans toucher à rien |
| Cookies | Playwright `storage_state` → `projects/browser_session/cookies.json` | Persistance native Playwright, compatible browser-use |
| Feedback frontend | Socket `browser_frame` existant, format `{"image": b64, "log": str}` | Réutilise l'infra existante, pas de nouveau event socket |
| Bridge Telegram | Inclus (non exclu contrairement à `run_web_agent`) | L'utilisateur veut confier des missions web par Telegram |

---

## Fichiers à créer / modifier

| Fichier | Action | Description |
|---|---|---|
| `backend/advanced_browser_agent.py` | Créer | Classe `AdvancedBrowserAgent` |
| `backend/mcp_tools_declarations.py` | Modifier | Ajouter déclaration `advanced_web_navigation` |
| `backend/ada.py` | Modifier | Import + dispatch audio loop + `_execute_text_tool` |
| `backend/external_bridge.py` | Modifier | Import + dispatch `_execute_tool` |
| `.env.example` | Modifier | Ajouter `BROWSER_HEADLESS` |
| `requirements.txt` | Modifier | Ajouter `browser-use`, `langchain-google-genai` |

---

## Spec détaillée — `advanced_browser_agent.py`

### Classe

```python
class AdvancedBrowserAgent:
    def __init__(self):
        self._llm = ChatGoogleGenerativeAI(
            model="gemini-2.5-flash",
            google_api_key=os.getenv("GEMINI_API_KEY"),
        )
        self._session_path = JARVIS_ROOT / "projects" / "browser_session"
        self._cookies_file = self._session_path / "cookies.json"

    async def run(self, mission: str, step_callback=None) -> str: ...
```

### Détection headless

```python
def _is_headless() -> bool:
    if os.getenv("BROWSER_HEADLESS", "true").lower() == "false":
        # DISPLAY absent (VPS) → is None = True → headless
        # DISPLAY présent (Mac) → is None = False → navigateur visible
        return os.environ.get("DISPLAY") is None
    return True
```

Logique :
- `BROWSER_HEADLESS=true` (défaut) → toujours headless
- `BROWSER_HEADLESS=false` + `DISPLAY` présent → headless=False (navigateur visible)
- `BROWSER_HEADLESS=false` + pas de `DISPLAY` (VPS) → headless=True silencieux + log warning

### Cookies persistants

- Répertoire : `JARVIS_ROOT/projects/browser_session/` (créé si absent)
- Avant chaque run : charger `cookies.json` si existant → `BrowserContextConfig(storage_state=...)`
- Après chaque run : sauvegarder le state → `cookies.json`
- Format : Playwright `storage_state` natif (cookies + localStorage)

### Callback step → frontend

`browser-use` expose un système de hooks par step (API à confirmer sur la version installée — `on_step_start`, `register_action`, ou subclassing du `Controller`). Le callback injecté envoie :
```python
{"image": screenshot_b64, "log": f"→ {action_description}"}
```
Via `step_callback(data)` — identique au format `on_web_data` utilisé par `web_agent.py`.

Quand `step_callback` est None (bridge Telegram) : aucun envoi socket, uniquement logs console.

### Retour

Toujours `str`. En cas d'erreur : `f"Erreur navigation avancée : {e}"`.

---

## Spec détaillée — Déclaration outil

```python
advanced_web_navigation = {
    "name": "advanced_web_navigation",
    "description": (
        "Navigue sur le web de manière complexe (clics, formulaires, "
        "navigation multi-pages, connexion aux comptes) pour accomplir "
        "des missions métier ou personnelles."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "mission": {
                "type": "STRING",
                "description": "Description complète de la mission web à accomplir"
            }
        },
        "required": ["mission"]
    }
}
```

Ajouté dans `MCP_TOOLS` (section navigation/web).

---

## Spec détaillée — Wiring ada.py

### 1. Audio loop (tool call voix) — NON_BLOCKING

```python
elif fc.name == "advanced_web_navigation":
    asyncio.create_task(self.handle_advanced_browser_request(fc.args.get("mission", "")))
    result_text = "Navigation avancée démarrée. Je te tiendrai informé."
```

Méthode `handle_advanced_browser_request` :
```python
async def handle_advanced_browser_request(self, mission: str):
    async def update_frontend(data):
        if self.on_web_data:
            self.on_web_data(data)
    result = await self.advanced_browser_agent.run(mission, step_callback=update_frontend)
    await self.session.send(input=f"Mission web terminée : {result}", end_of_turn=True)
```

### 2. `_execute_text_tool` (contexte texte)

```python
elif name == "advanced_web_navigation":
    try:
        return await self.advanced_browser_agent.run(args.get("mission", ""))
    except Exception as e:
        return f"Navigation avancée erreur : {e}"
```

---

## Spec détaillée — Wiring external_bridge.py

`advanced_web_navigation` **n'est pas dans `_EXCLUDED_FROM_BRIDGE`**.

Dans `_execute_tool` :
```python
elif name == "advanced_web_navigation":
    try:
        return await self._advanced_browser.run(args.get("mission", ""))
    except Exception as e:
        return f"Navigation avancée erreur : {e}"
```

Init dans `_init_agents` :
```python
try:
    from advanced_browser_agent import AdvancedBrowserAgent
    self._advanced_browser = AdvancedBrowserAgent()
except Exception as e:
    warnings.warn(f"[TextAgent] AdvancedBrowserAgent: {e}")
    self._advanced_browser = None
```

---

## Dépendances

```
browser-use>=0.1.0
langchain-google-genai>=2.0.0
```

`playwright` est déjà installé (utilisé par `web_agent.py`).

---

## Variables d'environnement

```bash
# Navigateur visible en développement (défaut: true = headless)
BROWSER_HEADLESS=false
```

`GEMINI_API_KEY` déjà présente.

---

## Ce qui ne change pas

- `web_agent.py` et `run_web_agent` : inchangés, coexistent
- Event socket `browser_frame` : réutilisé tel quel
- Pattern asyncio pur : respecté (`async def run`, exceptions catchées, retour `str`)
- Backup git : non applicable (pas d'écriture de code par cet agent)
