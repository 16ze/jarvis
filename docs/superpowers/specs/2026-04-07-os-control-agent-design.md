# Design — OS Control Agent (Full Computer Use)

**Date :** 2026-04-07
**Projet :** Jarvis / Ada
**Statut :** Approuvé

---

## Contexte

Ada dispose déjà de `control_computer` : un outil d'action atomique (un clic, une frappe, un screenshot) que Gemini Live orchestre pas à pas via la conversation vocale. Ce design ajoute `os_control_agent.py` — une boucle action-observation autonome qui prend une mission complète en langage naturel et l'exécute sans intervention humaine jusqu'à completion.

| | `control_computer` | `execute_pc_task` |
|---|---|---|
| Orchestration | Gemini Live (voix) | Agent autonome |
| Granularité | Action atomique | Mission complète |
| Loop | Non | Oui (max 30 steps) |
| Failsafe | Manuel | Timeout 120s + hotkey |

---

## Décisions d'architecture

| Question | Décision | Raison |
|---|---|---|
| Librairie exécution | `osascript` + `mss` existants | Prouvés en prod, pas de permissions extra, pas de conflit |
| `pyautogui` | Non utilisé | Problèmes de permissions macOS, redondant avec osascript |
| Failsafe | Timeout 120s + hotkey `Cmd+Shift+Esc` | Double protection obligatoire pour contrôle total du Mac |
| Hotkey listener | `pynput` (thread background) | Seule lib capable de capturer des hotkeys globales en Python macOS |
| Feedback frontend | Socket `browser_frame` existant | Réutilise l'infra web_agent/advanced_browser_agent |
| Bridge Telegram | Exclu (`_EXCLUDED_FROM_BRIDGE`) | Trop risqué de contrôler le Mac à distance sans être devant l'écran |
| `control_computer` | Inchangé, coexiste | Toujours utile pour actions atomiques dans la conversation vocale |

---

## Fichiers à créer / modifier

| Fichier | Action | Description |
|---|---|---|
| `backend/os_control_agent.py` | Créer | Classe `OsControlAgent`, boucle action-observation |
| `backend/mcp_tools_declarations.py` | Modifier | Ajouter `execute_pc_task_tool` + ajout MCP_TOOLS |
| `backend/ada.py` | Modifier | Init + `handle_pc_task_request` + dispatch audio loop + `_execute_text_tool` |
| `backend/external_bridge.py` | Modifier | Ajouter `execute_pc_task` dans `_EXCLUDED_FROM_BRIDGE` |
| `requirements.txt` | Modifier | Ajouter `pynput` |

---

## Spec détaillée — `os_control_agent.py`

### Classe

```python
class OsControlAgent:
    def __init__(self):
        # Vérifie GEMINI_API_KEY
        # Prépare le client Gemini

    async def run(self, task: str, step_callback=None) -> str:
        # Lance le thread hotkey killer
        # asyncio.wait_for(self._loop(task, step_callback), timeout=120.0)
        # Retourne toujours str

    async def _loop(self, task: str, step_callback) -> str:
        # Boucle action-observation, max 30 steps
        # Chaque step : screenshot → Gemini → parse JSON → exécute → callback

    async def _screenshot(self) -> tuple[bytes, str]:
        # mss.grab(monitors[1]) → JPEG 65% → (raw_bytes, base64)

    async def _execute_action(self, action_json: dict) -> str:
        # Dispatch sur action : click/double_click/right_click/type/hotkey/scroll/wait
        # Réutilise les mêmes primitives que control_computer dans ada.py
        # Retourne str résultat
```

### Prompt système Gemini

```
Tu contrôles un Mac. À chaque étape tu reçois :
1. Un screenshot de l'écran actuel
2. La tâche à accomplir
3. L'historique des 5 dernières actions

Réponds UNIQUEMENT avec un JSON valide (pas de markdown, pas d'explication) :
{
  "action": "click|double_click|right_click|type|hotkey|scroll|wait|finish",
  "x": <0-1000, normalisé>,
  "y": <0-1000, normalisé>,
  "text": "<texte à taper ou combinaison de touches>",
  "delta": <pixels scroll, défaut 3>,
  "reason": "<description lisible de l'action pour l'utilisateur>",
  "result": "<résumé final, uniquement pour finish>"
}

Règles :
- Utilise "wait" si l'écran charge (attend 1 seconde)
- Utilise "finish" quand la tâche est terminée ou impossible
- "reason" est affiché en temps réel à l'utilisateur — sois clair et en français
- Les coordonnées sont normalisées de 0 à 1000 (0,0 = haut-gauche, 1000,1000 = bas-droite)
- Inclus toujours "reason" même pour les actions simples
```

### Failsafe double

**Timeout :**
```python
try:
    return await asyncio.wait_for(self._loop(task, cb), timeout=120.0)
except asyncio.TimeoutError:
    return "Tâche interrompue : timeout 120s dépassé."
```

**Hotkey `Cmd+Shift+Esc` :**
```python
# Thread daemon pynput
# Déclenche asyncio.Event → _loop vérifie l'event à chaque itération
# Stop propre avec message "Tâche interrompue par l'utilisateur (Cmd+Shift+Esc)"
```

Le listener pynput est démarré au début de `run()` et arrêté dans un `finally`.

### Historique des actions

Les 5 dernières actions sont injectées dans le prompt à chaque step :
```
Historique des actions précédentes :
1. click (450, 230) — Ouverture du Finder
2. double_click (320, 180) — Double-clic sur Documents
...
```
Cela évite les boucles infinies (Gemini sait ce qu'il a déjà fait).

### Step callback

Format identique à `web_agent` et `advanced_browser_agent` :
```python
{"image": screenshot_b64, "log": f"→ {reason}"}
```
Envoyé via `on_web_data` → socket `browser_frame`.

---

## Spec détaillée — Déclaration outil

```python
execute_pc_task_tool = {
    "name": "execute_pc_task",
    "description": (
        "Prend le contrôle total du Mac (souris, clavier, applications) "
        "pour accomplir n'importe quelle tâche complexe. Prend des screenshots "
        "en continu et agit de façon autonome jusqu'à completion."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "task_description": {
                "type": "STRING",
                "description": "Description complète de la tâche à accomplir sur le Mac."
            }
        },
        "required": ["task_description"]
    },
    "behavior": "NON_BLOCKING"
}
```

Ajouté dans `MCP_TOOLS` (section navigation/web, après `advanced_web_navigation_tool`).

---

## Spec détaillée — Wiring ada.py

### Init (dans le constructeur AudioLoop)

Après `self.advanced_browser_agent = AdvancedBrowserAgent()` :
```python
try:
    from os_control_agent import OsControlAgent
    self.os_control_agent = OsControlAgent()
except Exception as e:
    warnings.warn(f"[ADA] OsControlAgent init: {e}")
    self.os_control_agent = None
```

### Méthode `handle_pc_task_request`

```python
async def handle_pc_task_request(self, task: str):
    # 1. Annonce vocale via session.send()
    # 2. Ouvre browser_frame sur frontend
    # 3. Lance os_control_agent.run(task, step_callback)
    # 4. Retourne résultat à Gemini via session.send()
```

L'annonce vocale : `"Je prends le contrôle de votre Mac pour : {task[:80]}"` envoyée à Gemini qui la lit à voix haute avant de lancer la tâche.

### Dispatch audio loop (NON_BLOCKING)

```python
elif fc.name == "execute_pc_task":
    task = fc.args.get("task_description", "")
    asyncio.create_task(self.handle_pc_task_request(task))
    function_responses.append(types.FunctionResponse(
        id=fc.id, name=fc.name,
        response={"result": "Prise de contrôle du Mac démarrée."}
    ))
```

### Dispatch `_execute_text_tool`

```python
elif name == "execute_pc_task":
    if not self.os_control_agent:
        return "OsControlAgent non disponible."
    try:
        return await self.os_control_agent.run(args.get("task_description", ""))
    except Exception as e:
        return f"PC task erreur : {e}"
```

---

## Spec détaillée — Wiring external_bridge.py

`execute_pc_task` est ajouté à `_EXCLUDED_FROM_BRIDGE` :
```python
_EXCLUDED_FROM_BRIDGE = {
    "generate_cad", "iterate_cad", "generate_cad_prototype",
    "control_computer",
    "discover_printers", "print_stl", "get_print_status",
    "run_web_agent",
    "execute_pc_task",   # ← contrôle Mac à distance trop risqué
    "ada_sleep", "ada_wake",
}
```

Pas de dispatch `_execute_tool` nécessaire — exclu du bridge.

---

## Dépendances

```
pynput>=1.7.0
```

`mss`, `Pillow`, `google-genai` déjà installés.

---

## Ce qui ne change pas

- `control_computer` et `web_agent.py` : inchangés, coexistent
- Socket `browser_frame` : réutilisé tel quel
- Pattern asyncio pur respecté
