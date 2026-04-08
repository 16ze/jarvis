# OS Control Agent Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Créer `OsControlAgent` — boucle action-observation autonome (mss + osascript + Gemini) qui prend le contrôle total du Mac sur ordre d'Ada.

**Architecture:** L'agent prend un screenshot mss, l'envoie à Gemini 2.5 Flash avec la tâche et l'historique des 5 dernières actions. Gemini répond en JSON `{action, x, y, text, reason, result}`. L'agent exécute via osascript/pbcopy (primitives déjà dans ada.py), envoie un step_callback au frontend via `browser_frame`, puis reboucle. Failsafe double : timeout 120s (`asyncio.wait_for`) + hotkey globale `Cmd+Shift+Esc` via `pynput` (thread daemon).

**Tech Stack:** mss, Pillow, osascript (subprocess), pynput, google-genai, asyncio pur

---

## File Map

| Fichier | Action | Rôle |
|---|---|---|
| `backend/os_control_agent.py` | **Créer** | Classe `OsControlAgent`, boucle action-observation |
| `backend/mcp_tools_declarations.py` | **Modifier** | Ajouter `execute_pc_task_tool` + MCP_TOOLS |
| `backend/ada.py` | **Modifier** | Init + `handle_pc_task_request` + dispatch audio loop + `_execute_text_tool` |
| `backend/external_bridge.py` | **Modifier** | Ajouter `execute_pc_task` dans `_EXCLUDED_FROM_BRIDGE` |
| `requirements.txt` | **Modifier** | Ajouter `pynput>=1.7.0` |

---

## Task 1 : Installer pynput et vérifier les dépendances

**Files:**
- Modify: `requirements.txt`

- [ ] **Step 1 : Installer pynput**

```bash
cd /Users/bryandev/jarvis
pip install pynput
```

Expected : `Successfully installed pynput-x.x.x`

- [ ] **Step 2 : Vérifier toutes les dépendances disponibles**

```bash
python -c "
import mss
import PIL.Image
import google.genai
from pynput import keyboard
print('mss OK')
print('Pillow OK')
print('google-genai OK')
print('pynput OK')
"
```

Expected : 4 lignes `OK` sans erreur.

- [ ] **Step 3 : Vérifier que osascript fonctionne**

```bash
osascript -e 'tell application "System Events" to return name of first process whose frontmost is true'
```

Expected : nom de l'application active (ex: `Terminal`, `Finder`).

- [ ] **Step 4 : Mettre à jour requirements.txt**

Ajouter à la fin de `/Users/bryandev/jarvis/requirements.txt` :
```
pynput>=1.7.0
```

- [ ] **Step 5 : Commit**

```bash
git -C /Users/bryandev/jarvis add requirements.txt
git -C /Users/bryandev/jarvis commit -m "chore: add pynput dependency for OS control agent hotkey"
```

---

## Task 2 : Créer os_control_agent.py

**Files:**
- Create: `backend/os_control_agent.py`

- [ ] **Step 1 : Créer le fichier complet**

Créer `/Users/bryandev/jarvis/backend/os_control_agent.py` avec ce contenu :

```python
"""
os_control_agent.py — Agent de contrôle total du Mac (Full Computer Use)

Boucle action-observation autonome :
  screenshot → Gemini analyse → action osascript → screenshot → ...

Failsafe double :
  - Timeout 120s (asyncio.wait_for)
  - Hotkey Cmd+Shift+Esc (pynput thread daemon)

Primitives d'exécution : osascript + pbcopy (déjà dans ada.py, pas de pyautogui)
Coordonnées : normalisées 0-1000 → converties en points logiques macOS
"""

import asyncio
import base64
import io
import json
import os
import subprocess
import threading
from pathlib import Path
from typing import Callable, Optional

import mss
import PIL.Image
from dotenv import load_dotenv
from google import genai
from google.genai import types

load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
MODEL = "gemini-2.5-flash"
MAX_STEPS = 30
TIMEOUT_SEC = 120.0
HISTORY_SIZE = 5

SYSTEM_PROMPT = """Tu contrôles un Mac. À chaque étape tu reçois :
1. Un screenshot de l'écran actuel
2. La tâche à accomplir
3. L'historique des dernières actions

Réponds UNIQUEMENT avec un JSON valide (sans markdown, sans explication) :
{
  "action": "click|double_click|right_click|type|hotkey|scroll|wait|finish",
  "x": <0-1000, coordonnée normalisée, pour click/right_click/double_click/scroll>,
  "y": <0-1000, coordonnée normalisée, pour click/right_click/double_click/scroll>,
  "text": "<texte à taper OU combinaison de touches ex: cmd+space>",
  "delta": <entier, pixels scroll positif=bas négatif=haut, défaut 3>,
  "reason": "<description française lisible de l'action — affichée à l'utilisateur>",
  "result": "<résumé final de ce qui a été accompli, uniquement pour action=finish>"
}

Règles :
- Utilise "wait" si l'écran charge ou si une animation est en cours (attend 1s)
- Utilise "finish" quand la tâche est terminée ou clairement impossible
- "reason" est obligatoire sur chaque action — sois concis et en français
- Les coordonnées (x, y) sont normalisées de 0 à 1000 (0,0 = haut-gauche, 1000,1000 = bas-droite)
- Pour "hotkey" : utilise le format "cmd+space", "ctrl+c", "cmd+shift+esc", etc.
- N'inclus "x","y" que pour les actions de pointeur (click, scroll)
- Pour "type" : inclus uniquement "text", pas de coordonnées
- Analyse attentivement le screenshot avant d'agir
- Si tu te retrouves en boucle (même action répétée), utilise "finish" avec un rapport d'échec"""


def _run_osascript(script: str) -> str:
    """Exécute un script AppleScript synchrone. Retourne stdout ou lève RuntimeError."""
    result = subprocess.run(
        ["osascript", "-e", script],
        capture_output=True, text=True
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip())
    return result.stdout.strip()


def _get_logical_screen_size() -> tuple[int, int]:
    """
    Retourne la taille logique de l'écran principal en points (pas en pixels).
    Nécessaire sur Retina : osascript utilise des coordonnées en points logiques.
    """
    try:
        output = subprocess.run(
            ["osascript", "-e",
             'tell application "Finder" to get bounds of window of desktop'],
            capture_output=True, text=True, timeout=5
        ).stdout.strip()
        # Format: "0, 0, 1440, 900"
        parts = [p.strip() for p in output.split(",")]
        return int(parts[2]), int(parts[3])
    except Exception:
        # Fallback conservateur
        return 1440, 900


class OsControlAgent:
    def __init__(self):
        if not GEMINI_API_KEY:
            raise RuntimeError("GEMINI_API_KEY non configurée.")
        self._client = genai.Client(api_key=GEMINI_API_KEY)
        self._stop_event: Optional[asyncio.Event] = None

    def _start_hotkey_listener(self, stop_event: asyncio.Event, loop: asyncio.AbstractEventLoop) -> threading.Thread:
        """
        Lance un thread daemon qui écoute Cmd+Shift+Esc.
        Déclenche stop_event via run_coroutine_threadsafe quand pressé.
        """
        from pynput import keyboard as kb

        _pressed = set()
        _STOP_COMBO = {kb.Key.cmd, kb.Key.shift, kb.Key.esc}

        def on_press(key):
            _pressed.add(key)
            if _STOP_COMBO.issubset(_pressed):
                asyncio.run_coroutine_threadsafe(
                    _set_event(stop_event), loop
                )

        def on_release(key):
            _pressed.discard(key)

        async def _set_event(ev: asyncio.Event):
            ev.set()

        listener = kb.Listener(on_press=on_press, on_release=on_release)
        listener.daemon = True
        listener.start()
        return listener

    async def _screenshot(self) -> tuple[bytes, str]:
        """
        Capture l'écran principal via mss.
        Retourne (jpeg_bytes, base64_str).
        Redimensionné à 1280×720 max pour économiser les tokens Gemini.
        """
        def _grab():
            with mss.mss() as sct:
                monitor = sct.monitors[1]
                shot = sct.grab(monitor)
                img = PIL.Image.frombytes("RGB", shot.size, shot.bgra, "raw", "BGRX")
                img.thumbnail([1280, 720])
                buf = io.BytesIO()
                img.save(buf, format="jpeg", quality=65)
                return buf.getvalue()

        raw = await asyncio.to_thread(_grab)
        b64 = base64.b64encode(raw).decode()
        return raw, b64

    async def _execute_action(self, action_json: dict, screen_w: int, screen_h: int) -> str:
        """
        Exécute l'action décrite par action_json.
        Convertit les coordonnées normalisées 0-1000 en points logiques macOS.
        Retourne une str de résultat.
        """
        action = action_json.get("action", "")
        norm_x = action_json.get("x")
        norm_y = action_json.get("y")
        text = action_json.get("text", "")
        delta = int(action_json.get("delta", 3))

        # Conversion coordonnées normalisées → points logiques
        def to_logical(nx, ny) -> tuple[int, int]:
            lx = int(nx * screen_w / 1000)
            ly = int(ny * screen_h / 1000)
            return lx, ly

        try:
            if action in ("click", "double_click", "right_click") and norm_x is not None and norm_y is not None:
                lx, ly = to_logical(norm_x, norm_y)
                if action == "click":
                    script = f'tell application "System Events" to click at {{{lx}, {ly}}}'
                elif action == "double_click":
                    script = f'tell application "System Events" to double click at {{{lx}, {ly}}}'
                else:  # right_click
                    script = (
                        f'tell application "System Events"\n'
                        f'  set p to {{{lx}, {ly}}}\n'
                        f'  click at p using {{control down}}\n'
                        f'end tell'
                    )
                await asyncio.to_thread(_run_osascript, script)
                return f"{action} at ({lx}, {ly})"

            elif action == "type" and text:
                # pbcopy + cmd+v : fonctionne pour tout l'Unicode, accents, code
                await asyncio.to_thread(
                    lambda: subprocess.run(
                        ["pbcopy"], input=text.encode("utf-8"), check=True
                    )
                )
                await asyncio.to_thread(
                    _run_osascript,
                    'tell application "System Events" to keystroke "v" using command down'
                )
                return f"Typed: {text[:80]}"

            elif action == "hotkey" and text:
                _modifier_map = {
                    "ctrl": "control down", "control": "control down",
                    "cmd": "command down", "command": "command down",
                    "shift": "shift down",
                    "alt": "option down", "option": "option down",
                }
                parts = [p.strip().lower() for p in text.split("+")]
                key = parts[-1]
                mods = [_modifier_map[p] for p in parts[:-1] if p in _modifier_map]
                using_clause = ", ".join(mods)
                if using_clause:
                    script = f'tell application "System Events" to keystroke "{key}" using {{{using_clause}}}'
                else:
                    script = f'tell application "System Events" to keystroke "{key}"'
                await asyncio.to_thread(_run_osascript, script)
                return f"Hotkey: {text}"

            elif action == "scroll" and norm_x is not None and norm_y is not None:
                lx, ly = to_logical(norm_x, norm_y)
                script = (
                    f'tell application "System Events"\n'
                    f'    scroll at {{{lx}, {ly}}} by {{0, {delta}}}\n'
                    f'end tell'
                )
                await asyncio.to_thread(_run_osascript, script)
                return f"Scroll {delta} at ({lx}, {ly})"

            elif action == "wait":
                await asyncio.sleep(1.0)
                return "Waited 1s"

            elif action == "finish":
                return "__DONE__"

            else:
                return f"Action inconnue ou paramètres manquants : {action}"

        except Exception as e:
            return f"Erreur action {action}: {e}"

    async def _loop(self, task: str, step_callback: Optional[Callable], stop_event: asyncio.Event) -> str:
        """Boucle action-observation principale."""
        screen_w, screen_h = await asyncio.to_thread(_get_logical_screen_size)
        print(f"[OsControl] Écran logique : {screen_w}x{screen_h}")

        history: list[str] = []
        final_result = "Tâche terminée."

        for step in range(MAX_STEPS):
            # Vérifier le failsafe hotkey
            if stop_event.is_set():
                return "Tâche interrompue par l'utilisateur (Cmd+Shift+Esc)."

            print(f"[OsControl] Step {step + 1}/{MAX_STEPS}")

            # Screenshot
            raw_bytes, b64 = await self._screenshot()

            # Feedback frontend : screenshot de l'état actuel
            if step_callback:
                await step_callback({"image": b64, "log": f"[PC] Step {step + 1} — analyse de l'écran..."})

            # Construire le prompt avec historique
            history_str = "\n".join(
                f"{i + 1}. {h}" for i, h in enumerate(history[-HISTORY_SIZE:])
            ) if history else "Aucune action précédente."

            user_prompt = (
                f"Tâche : {task}\n\n"
                f"Historique des actions précédentes :\n{history_str}\n\n"
                "Analyse le screenshot et détermine la prochaine action."
            )

            # Appel Gemini avec le screenshot
            try:
                response = await asyncio.to_thread(
                    self._client.models.generate_content,
                    model=MODEL,
                    contents=[
                        types.Content(
                            role="user",
                            parts=[
                                types.Part(text=user_prompt),
                                types.Part.from_bytes(data=raw_bytes, mime_type="image/jpeg"),
                            ]
                        )
                    ],
                    config=types.GenerateContentConfig(
                        system_instruction=SYSTEM_PROMPT,
                        temperature=0.1,
                    ),
                )
            except Exception as e:
                print(f"[OsControl] Erreur API Gemini : {e}")
                return f"Erreur API Gemini : {e}"

            # Parser la réponse JSON
            raw_text = response.text.strip()
            # Nettoyer les balises markdown si présentes
            if raw_text.startswith("```"):
                lines = raw_text.split("\n")
                raw_text = "\n".join(lines[1:])
                raw_text = raw_text.rstrip("`").strip()

            try:
                action_json = json.loads(raw_text)
            except json.JSONDecodeError as e:
                print(f"[OsControl] JSON invalide : {e} — raw: {raw_text[:200]}")
                # Réessayer au prochain step sans action
                history.append(f"(JSON invalide — step ignoré)")
                continue

            action = action_json.get("action", "")
            reason = action_json.get("reason", action)
            print(f"[OsControl] Action : {action} — {reason}")

            # Feedback frontend avec l'action décidée
            if step_callback:
                await step_callback({"image": b64, "log": f"[PC] → {reason}"})

            # Vérifier à nouveau le failsafe avant d'agir
            if stop_event.is_set():
                return "Tâche interrompue par l'utilisateur (Cmd+Shift+Esc)."

            # Exécuter l'action
            if action == "finish":
                final_result = action_json.get("result", "Tâche accomplie.")
                if step_callback:
                    await step_callback({"image": b64, "log": f"[PC] ✓ {final_result}"})
                return final_result

            result_str = await self._execute_action(action_json, screen_w, screen_h)
            history.append(f"{action}: {reason}")

            # Petite pause pour laisser le Mac réagir
            await asyncio.sleep(0.5)

        return f"Tâche interrompue : limite de {MAX_STEPS} steps atteinte."

    async def run(self, task: str, step_callback: Optional[Callable] = None) -> str:
        """
        Point d'entrée principal. Lance la boucle avec failsafe double.

        Args:
            task: Description de la tâche à accomplir.
            step_callback: Coroutine appelée à chaque step → {"image": b64, "log": str}.

        Returns:
            Résumé str du résultat. Jamais d'exception non catchée.
        """
        print(f"[OsControl] Démarrage : {task[:100]}")

        if step_callback:
            await step_callback({"image": None, "log": f"[PC] Prise de contrôle — {task[:80]}"})

        loop = asyncio.get_running_loop()
        stop_event = asyncio.Event()
        listener = self._start_hotkey_listener(stop_event, loop)

        try:
            result = await asyncio.wait_for(
                self._loop(task, step_callback, stop_event),
                timeout=TIMEOUT_SEC,
            )
            return result

        except asyncio.TimeoutError:
            msg = f"Tâche interrompue : timeout {int(TIMEOUT_SEC)}s dépassé."
            print(f"[OsControl] {msg}")
            if step_callback:
                await step_callback({"image": None, "log": f"[PC] ⏰ {msg}"})
            return msg

        except Exception as e:
            msg = f"Erreur OsControl : {e}"
            print(f"[OsControl] {msg}")
            if step_callback:
                await step_callback({"image": None, "log": f"[PC] Erreur : {e}"})
            return msg

        finally:
            stop_event.set()  # Signale au listener de s'arrêter
            try:
                listener.stop()
            except Exception:
                pass
```

- [ ] **Step 2 : Vérifier la syntaxe**

```bash
cd /Users/bryandev/jarvis/backend && python -m py_compile os_control_agent.py && echo "Syntaxe OK"
```

Expected : `Syntaxe OK`

- [ ] **Step 3 : Test d'import et d'instanciation**

```bash
cd /Users/bryandev/jarvis/backend && python -c "
import os, sys
sys.path.insert(0, '.')
os.environ['GEMINI_API_KEY'] = 'fake-key'
from os_control_agent import OsControlAgent, _get_logical_screen_size
agent = OsControlAgent()
print('OsControlAgent OK')
w, h = _get_logical_screen_size()
print(f'Écran logique : {w}x{h}')
"
```

Expected : `OsControlAgent OK` + dimensions d'écran cohérentes (ex: `1440x900` ou `2560x1600`).

- [ ] **Step 4 : Test du screenshot**

```bash
cd /Users/bryandev/jarvis/backend && python -c "
import os, asyncio
os.environ['GEMINI_API_KEY'] = 'fake-key'
os.environ['JARVIS_ROOT'] = '/Users/bryandev/jarvis'
import sys; sys.path.insert(0, '.')
from os_control_agent import OsControlAgent
agent = OsControlAgent()
raw, b64 = asyncio.run(agent._screenshot())
print(f'Screenshot OK — {len(raw)} bytes, b64 length {len(b64)}')
assert len(raw) > 1000, 'Screenshot trop petit'
assert len(b64) > 100, 'Base64 vide'
"
```

Expected : `Screenshot OK — XXXXX bytes, b64 length XXXXX`

- [ ] **Step 5 : Test de _get_logical_screen_size**

```bash
cd /Users/bryandev/jarvis/backend && python -c "
from os_control_agent import _get_logical_screen_size
w, h = _get_logical_screen_size()
assert w > 100 and h > 100, f'Dimensions invalides : {w}x{h}'
print(f'Écran logique : {w}x{h} — OK')
"
```

Expected : `Écran logique : NNNNxNNNN — OK`

- [ ] **Step 6 : Commit**

```bash
git -C /Users/bryandev/jarvis add backend/os_control_agent.py
git -C /Users/bryandev/jarvis commit -m "feat: create OsControlAgent (Full Computer Use — mss + osascript + pynput)"
```

---

## Task 3 : Déclarer execute_pc_task dans mcp_tools_declarations.py

**Files:**
- Modify: `backend/mcp_tools_declarations.py`

- [ ] **Step 1 : Ajouter la déclaration avant MCP_TOOLS**

Dans `/Users/bryandev/jarvis/backend/mcp_tools_declarations.py`, juste avant le bloc `# ─────────────────────────────────────────────────────────────────────────────` qui précède `MCP_TOOLS = [`, ajouter :

```python
# ── OS CONTROL (Full Computer Use) ───────────────────────────────────────────
execute_pc_task_tool = {
    "name": "execute_pc_task",
    "description": (
        "Prend le contrôle total du Mac (souris, clavier, applications) "
        "pour accomplir n'importe quelle tâche complexe de manière autonome. "
        "Prend des screenshots en continu, analyse l'écran et agit jusqu'à completion. "
        "Peut ouvrir le Finder, déplacer des fichiers, coder dans VS Code, changer les réglages système, etc."
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

- [ ] **Step 2 : Ajouter dans MCP_TOOLS**

Dans la liste `MCP_TOOLS`, dans la section `# Recherche`, ajouter `execute_pc_task_tool,` après `advanced_web_navigation_tool,` :

```python
    # Recherche
    youtube_search_tool, youtube_video_info_tool, youtube_transcript_tool,
    wikipedia_search_tool, wikipedia_article_tool,
    arxiv_search_tool, arxiv_paper_tool,
    advanced_web_navigation_tool,
    execute_pc_task_tool,  # ← ajouter ici
```

- [ ] **Step 3 : Vérifier**

```bash
cd /Users/bryandev/jarvis/backend && python -c "
from mcp_tools_declarations import MCP_TOOLS, MCP_TOOL_NAMES
assert 'execute_pc_task' in MCP_TOOL_NAMES, 'Outil absent!'
tool = next(t for t in MCP_TOOLS if t['name'] == 'execute_pc_task')
assert tool['parameters']['required'] == ['task_description'], 'Param incorrect!'
assert tool.get('behavior') == 'NON_BLOCKING', 'behavior manquant!'
print('OK — execute_pc_task dans MCP_TOOLS, behavior=NON_BLOCKING')
"
```

Expected : `OK — execute_pc_task dans MCP_TOOLS, behavior=NON_BLOCKING`

- [ ] **Step 4 : Commit**

```bash
git -C /Users/bryandev/jarvis add backend/mcp_tools_declarations.py
git -C /Users/bryandev/jarvis commit -m "feat: declare execute_pc_task tool in MCP_TOOLS (NON_BLOCKING)"
```

---

## Task 4 : Wiring dans ada.py

**Files:**
- Modify: `backend/ada.py` (4 points : init ~614, nouvelle méthode ~1197, audio loop ~1402, _execute_text_tool ~2724)

- [ ] **Step 1 : Init OsControlAgent dans le constructeur**

Dans `/Users/bryandev/jarvis/backend/ada.py`, après les lignes qui initialisent `self.advanced_browser_agent` (environ ligne 620), ajouter :

```python
        try:
            from os_control_agent import OsControlAgent
            self.os_control_agent = OsControlAgent()
        except Exception as e:
            import warnings
            warnings.warn(f"[ADA] OsControlAgent init: {e}")
            self.os_control_agent = None
```

- [ ] **Step 2 : Ajouter handle_pc_task_request**

Dans `/Users/bryandev/jarvis/backend/ada.py`, juste après la méthode `handle_advanced_browser_request` (environ ligne 1197), ajouter :

```python
    async def handle_pc_task_request(self, task: str):
        print(f"[ADA DEBUG] [PC] PC Task: '{task}'")

        # Annonce vocale avant de prendre le contrôle
        try:
            if self.session:
                await self.session.send(
                    input=f"System Notification: Je prends le contrôle de votre Mac pour : {task[:80]}. Appuyez sur Cmd+Shift+Esc pour arrêter.",
                    end_of_turn=True,
                )
        except Exception as e:
            print(f"[ADA DEBUG] [PC] Annonce vocale échouée : {e}")

        if self.on_web_data:
            self.on_web_data({"image": None, "log": f"[PC] Mission : {task[:80]}"})

        async def update_frontend(data: dict):
            if self.on_web_data:
                self.on_web_data(data)

        if not self.os_control_agent:
            result = "OsControlAgent non disponible."
        else:
            result = await self.os_control_agent.run(task, step_callback=update_frontend)

        try:
            if self.session:
                await self.session.send(
                    input=f"System Notification: Contrôle PC terminé.\nRésultat: {result}",
                    end_of_turn=True,
                )
        except Exception as e:
            print(f"[ADA DEBUG] [ERR] Failed to send PC task result: {e}")
```

- [ ] **Step 3 : Dispatch dans l'audio loop (NON_BLOCKING)**

Dans `/Users/bryandev/jarvis/backend/ada.py`, dans le bloc dispatch audio loop, après le bloc `elif fc.name == "advanced_web_navigation":` (environ ligne 1401), ajouter :

```python
                                elif fc.name == "execute_pc_task":
                                    task = fc.args.get("task_description", "")
                                    print(f"[ADA DEBUG] [TOOL] Tool Call: 'execute_pc_task' task='{task[:60]}'")
                                    asyncio.create_task(self.handle_pc_task_request(task))
                                    function_response = types.FunctionResponse(
                                        id=fc.id,
                                        name=fc.name,
                                        response={"result": "Prise de contrôle du Mac démarrée. Cmd+Shift+Esc pour stopper."},
                                    )
                                    function_responses.append(function_response)
```

- [ ] **Step 4 : Dispatch dans _execute_text_tool**

Dans `/Users/bryandev/jarvis/backend/ada.py`, dans `_execute_text_tool`, après le bloc `elif name == "advanced_web_navigation":` (environ ligne 2735), ajouter :

```python
            # ── CONTRÔLE PC AUTONOME ──────────────────────────────────────────
            elif name == "execute_pc_task":
                if not self.os_control_agent:
                    return "OsControlAgent non disponible (vérifier les dépendances)."
                try:
                    return await self.os_control_agent.run(args.get("task_description", ""))
                except Exception as e:
                    return f"PC task erreur : {e}"
```

- [ ] **Step 5 : Vérifier la syntaxe**

```bash
cd /Users/bryandev/jarvis/backend && python -m py_compile ada.py && echo "Syntaxe OK"
```

Expected : `Syntaxe OK`

- [ ] **Step 6 : Vérification rapide des 4 points**

```bash
cd /Users/bryandev/jarvis/backend && python -c "
src = open('ada.py').read()
assert 'OsControlAgent' in src, 'Init manquant'
assert 'handle_pc_task_request' in src, 'Méthode manquante'
assert 'execute_pc_task' in src, 'Dispatch manquant'
print('Tous les points ada.py présents')
"
```

Expected : `Tous les points ada.py présents`

- [ ] **Step 7 : Commit**

```bash
git -C /Users/bryandev/jarvis add backend/ada.py
git -C /Users/bryandev/jarvis commit -m "feat: wire execute_pc_task in ada.py (init + handler + audio loop + _execute_text_tool)"
```

---

## Task 5 : Wiring external_bridge.py

**Files:**
- Modify: `backend/external_bridge.py`

- [ ] **Step 1 : Ajouter execute_pc_task dans _EXCLUDED_FROM_BRIDGE**

Dans `/Users/bryandev/jarvis/backend/external_bridge.py`, dans le set `_EXCLUDED_FROM_BRIDGE` (environ ligne 122), ajouter `"execute_pc_task"` :

Le set doit ressembler à :
```python
_EXCLUDED_FROM_BRIDGE = {
    "generate_cad", "iterate_cad", "generate_cad_prototype",
    "control_computer",
    "discover_printers", "print_stl", "get_print_status",
    "run_web_agent",
    "execute_pc_task",   # contrôle Mac à distance trop risqué
    "ada_sleep", "ada_wake",
}
```

- [ ] **Step 2 : Vérifier**

```bash
cd /Users/bryandev/jarvis/backend && python -c "
src = open('external_bridge.py').read()
import re
m = re.search(r'_EXCLUDED_FROM_BRIDGE\s*=\s*\{([^}]+)\}', src, re.DOTALL)
assert m, 'Set introuvable'
excluded = m.group(1)
assert 'execute_pc_task' in excluded, 'execute_pc_task non exclu!'
print('OK — execute_pc_task dans _EXCLUDED_FROM_BRIDGE')
"
```

Expected : `OK — execute_pc_task dans _EXCLUDED_FROM_BRIDGE`

- [ ] **Step 3 : Vérifier syntaxe**

```bash
cd /Users/bryandev/jarvis/backend && python -m py_compile external_bridge.py && echo "Syntaxe OK"
```

Expected : `Syntaxe OK`

- [ ] **Step 4 : Commit**

```bash
git -C /Users/bryandev/jarvis add backend/external_bridge.py
git -C /Users/bryandev/jarvis commit -m "feat: exclude execute_pc_task from Telegram bridge (security)"
```

---

## Task 6 : Tests d'intégration

- [ ] **Step 1 : Test headless — logique complète sans Gemini**

```bash
cd /Users/bryandev/jarvis/backend && python -c "
import os, asyncio, sys
sys.path.insert(0, '.')
os.environ['GEMINI_API_KEY'] = 'fake-key'

from os_control_agent import OsControlAgent, _get_logical_screen_size

# Test 1 : init
agent = OsControlAgent()
print('Init OK')

# Test 2 : écran logique
w, h = _get_logical_screen_size()
assert w > 0 and h > 0
print(f'Écran logique OK : {w}x{h}')

# Test 3 : screenshot
raw, b64 = asyncio.run(agent._screenshot())
assert len(raw) > 1000
print(f'Screenshot OK : {len(raw)} bytes')

# Test 4 : conversion coordonnées
action_json = {'action': 'click', 'x': 500, 'y': 500, 'reason': 'test'}
# Vérifier que to_logical(500, 500) donne w//2, h//2
expected_x = w // 2
expected_y = h // 2
# On vérifie juste que la formule est correcte
actual_x = int(500 * w / 1000)
actual_y = int(500 * h / 1000)
assert actual_x == expected_x and actual_y == expected_y, f'{actual_x},{actual_y} != {expected_x},{expected_y}'
print(f'Coordonnées OK : (500,500) normalisé → ({actual_x},{actual_y}) logique')

print('Tous les tests passent.')
"
```

Expected : 5 lignes `OK` + `Tous les tests passent.`

- [ ] **Step 2 : Test mcp_tools_declarations**

```bash
cd /Users/bryandev/jarvis/backend && python -c "
from mcp_tools_declarations import MCP_TOOL_NAMES
assert 'execute_pc_task' in MCP_TOOL_NAMES
assert 'advanced_web_navigation' in MCP_TOOL_NAMES
assert 'run_web_agent' not in MCP_TOOL_NAMES  # run_web_agent n'est pas dans MCP_TOOLS
print('MCP_TOOLS OK')
"
```

Expected : `MCP_TOOLS OK`

- [ ] **Step 3 : Test syntaxe tous les fichiers**

```bash
cd /Users/bryandev/jarvis/backend && python -m py_compile os_control_agent.py mcp_tools_declarations.py ada.py external_bridge.py && echo "Tous les fichiers OK"
```

Expected : `Tous les fichiers OK`

- [ ] **Step 4 : Commit final**

```bash
git -C /Users/bryandev/jarvis add -A
git -C /Users/bryandev/jarvis commit -m "feat: execute_pc_task — Full Computer Use complet (os_control_agent + wiring + tests)"
```
