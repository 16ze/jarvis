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
MAX_STEPS = 50
TIMEOUT_SEC = 180.0
HISTORY_SIZE = 6

SYSTEM_PROMPT = """Tu contrôles un Mac pour Bryan. À chaque étape tu reçois un screenshot + la tâche + l'historique.

Réponds UNIQUEMENT avec un JSON valide (sans markdown, sans explication) :
{
  "action": "click|double_click|right_click|type|hotkey|scroll|wait|finish",
  "x": <0-1000, coordonnée normalisée, pour click/double_click/right_click/scroll SEULEMENT>,
  "y": <0-1000, coordonnée normalisée, pour click/double_click/right_click/scroll SEULEMENT>,
  "text": "<texte pour type|hotkey>",
  "delta": <entier scroll, positif=bas négatif=haut, défaut 3>,
  "reason": "<action en français, obligatoire>",
  "result": "<résumé uniquement pour action=finish>"
}

══════════════════════════════════════════════════════
STRATÉGIES PRIORITAIRES macOS (dans cet ordre strict)
══════════════════════════════════════════════════════

▸ OUVRIR UNE APPLICATION :
  1. PRÉFÉRER le terminal si déjà lancé : type "open -a \"NomApp\"\n"
  2. SINON Spotlight : hotkey "cmd+space" → wait → type "NomApp" → wait → type "return"
  3. JAMAIS cliquer au hasard sur le bureau pour chercher une app
  4. JAMAIS faire cmd+space si Spotlight est déjà ouvert

▸ FERMER UNE FENÊTRE : hotkey "cmd+w" ou cliquer ✕ rouge (haut gauche)
▸ QUITTER UNE APP : hotkey "cmd+q"
▸ COPIER/COLLER : hotkey "cmd+c" / hotkey "cmd+v"
▸ CHANGER D'APP : hotkey "cmd+tab" (puis tab pour naviguer)
▸ PRENDRE UNE ZONE DE L'ÉCRAN : hotkey "cmd+shift+4"
▸ NOUVELLE FENÊTRE NAVIGATEUR : hotkey "cmd+n"
▸ NOUVEL ONGLET : hotkey "cmd+t"
▸ BARRE D'ADRESSE NAVIGATEUR : hotkey "cmd+l" → type URL → type "return"

══════════════════════════════════════════════════════
RÈGLES DE PRÉCISION — NE JAMAIS ENFREINDRE
══════════════════════════════════════════════════════

1. ANALYSE D'ABORD : lis tout le screenshot avant d'agir. Identifie l'élément exact.
2. UN SEUL OBJECTIF PAR STEP : ne combine jamais 2 intentions en 1 action.
3. RACCOURCIS AVANT CLICS : si un raccourci clavier accomplit la tâche → l'utiliser.
4. COORDONNÉES : centre exact de l'élément, pas approximatif. Zoom mentalement.
5. WAIT obligatoire : après hotkey, après click sur menu, après ouverture app → wait 1 fois.
6. BOUCLE DÉTECTÉE (même action ×2) → finish avec échec explicite, ne pas continuer.
7. JAMAIS cliquer sans avoir identifié l'élément visuellement sur le screenshot.
8. DOCK (bas de l'écran) : les icônes sont à y≈970, réparties horizontalement. Identifier par icône.

══════════════════════════════════════════════════════
FORMAT STRICT
══════════════════════════════════════════════════════
- "x" et "y" : UNIQUEMENT pour click/double_click/right_click/scroll. JAMAIS pour type/hotkey/wait/finish.
- "text" : UNIQUEMENT pour type et hotkey.
- Les coordonnées sont 0-1000 (0,0 = haut-gauche, 1000,1000 = bas-droite).
- Hotkey format : "cmd+space", "cmd+q", "cmd+shift+4", "return", "escape".
"""


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
        print("[OsControl] ⚠️  Impossible de détecter la résolution logique — fallback 1440x900")
        return 1440, 900


class OsControlAgent:
    def __init__(self):
        if not GEMINI_API_KEY:
            raise RuntimeError("GEMINI_API_KEY non configurée.")
        self._client = genai.Client(api_key=GEMINI_API_KEY)
        self._stop_event: Optional[asyncio.Event] = None
        self._current_stop_event: Optional[asyncio.Event] = None  # stop_pc_task

    async def stop(self) -> str:
        """Interrompt la tâche en cours (appelé par stop_pc_task)."""
        if self._current_stop_event and not self._current_stop_event.is_set():
            self._current_stop_event.set()
            return "Tâche PC interrompue."
        return "Aucune tâche PC en cours."

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
                # Touches spéciales via key code (keystroke "return" taperait "return" comme texte !)
                _SPECIAL_KEYS = {
                    "return": 36, "enter": 36,
                    "escape": 53, "esc": 53,
                    "tab": 48, "space": 49,
                    "backspace": 51, "delete": 51,
                    "up": 126, "down": 125, "left": 123, "right": 124,
                    "f1": 122, "f2": 120, "f3": 99, "f4": 118,
                    "f5": 96, "f6": 97, "f7": 98, "f8": 100,
                    "f9": 101, "f10": 109, "f11": 103, "f12": 111,
                    "page_up": 116, "pageup": 116,
                    "page_down": 121, "pagedown": 121,
                    "home": 115, "end": 119,
                }
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
                if key in _SPECIAL_KEYS:
                    kc = _SPECIAL_KEYS[key]
                    script = (
                        f'tell application "System Events" to key code {kc} using {{{using_clause}}}'
                        if using_clause else
                        f'tell application "System Events" to key code {kc}'
                    )
                else:
                    escaped_key = key.replace('"', '\\"')
                    script = (
                        f'tell application "System Events" to keystroke "{escaped_key}" using {{{using_clause}}}'
                        if using_clause else
                        f'tell application "System Events" to keystroke "{escaped_key}"'
                    )
                await asyncio.to_thread(_run_osascript, script)
                return f"Hotkey: {text}"

            elif action == "scroll" and norm_x is not None and norm_y is not None:
                lx, ly = to_logical(norm_x, norm_y)
                # pynput pour le scroll (AppleScript scroll est non standard)
                # delta>0 = scroll bas, delta<0 = scroll haut
                def _do_scroll(px, py, d):
                    from pynput import mouse as _pmouse
                    m = _pmouse.Controller()
                    m.position = (px, py)
                    import time as _t; _t.sleep(0.08)
                    m.scroll(0, -d)  # pynput: négatif = bas, positif = haut
                await asyncio.to_thread(_do_scroll, lx, ly, delta)
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
            print(f"[OsControl] Résultat : {result_str}")
            history.append(f"{action}: {reason} → {result_str}")

            # Petite pause pour laisser le Mac réagir
            await asyncio.sleep(0.5)

        return f"Tâche interrompue : limite de {MAX_STEPS} steps atteinte."

    # ── Fast-path : actions simples sans vision loop ──────────────────────────
    _OPEN_PATTERNS = [
        r"(?:ouvre?|lance?|démarre?|open|start|launch)\s+(?:l'?app(?:lication)?\s+)?[«\"']?([a-zA-Z0-9À-ÿ\s\.\-]+?)[«\"']?\s*$",
    ]

    async def _try_fast_path(self, task: str, step_callback: Optional[Callable]) -> Optional[str]:
        """
        Tente d'exécuter les tâches simples directement via osascript/subprocess.
        Retourne le résultat si géré, None sinon (→ vision loop).
        """
        import re
        task_lower = task.lower().strip()

        # ── Ouvrir une application ──────────────────────────────────────────
        for pattern in self._OPEN_PATTERNS:
            m = re.search(pattern, task.strip(), re.IGNORECASE)
            if m:
                app_name = m.group(1).strip().strip("'\"«»")
                if step_callback:
                    await step_callback({"image": None, "log": f"[PC] Ouverture de {app_name} via open -a"})
                try:
                    result = await asyncio.to_thread(
                        subprocess.run,
                        ["open", "-a", app_name],
                        capture_output=True, text=True, timeout=10
                    )
                    if result.returncode == 0:
                        return f"{app_name} ouvert."
                    # Fallback : essayer avec osascript activate
                    try:
                        await asyncio.to_thread(
                            _run_osascript,
                            f'tell application "{app_name}" to activate'
                        )
                        return f"{app_name} activé."
                    except Exception:
                        pass
                    # Fallback Spotlight si open -a échoue
                    if step_callback:
                        await step_callback({"image": None, "log": f"[PC] open -a échoué → Spotlight"})
                    return None  # Laisser la vision loop gérer via Spotlight
                except Exception as e:
                    if step_callback:
                        await step_callback({"image": None, "log": f"[PC] Erreur fast-path : {e}"})
                    return None

        # ── Raccourcis système directs ──────────────────────────────────────
        DIRECT_HOTKEYS = {
            r"(prends?|capture|screenshot)\s+(?:un |l')?écran": "cmd+shift+3",
            r"(verrouille|lock)\s+(?:l'|le )?écran": "cmd+ctrl+q",
            r"(volume|son)\s+(mute|muet|silence)": "F10",
        }
        for pattern, hotkey in DIRECT_HOTKEYS.items():
            if re.search(pattern, task_lower):
                parts = hotkey.split("+")
                key = parts[-1]
                mods_map = {
                    "cmd": "command down", "ctrl": "control down",
                    "shift": "shift down", "opt": "option down",
                }
                mods = [mods_map[p] for p in parts[:-1] if p in mods_map]
                using = ", ".join(mods)
                script = (
                    f'tell application "System Events" to keystroke "{key}" using {{{using}}}'
                    if using else
                    f'tell application "System Events" to key code {key}'
                )
                try:
                    await asyncio.to_thread(_run_osascript, script)
                    return f"Raccourci {hotkey} exécuté."
                except Exception:
                    return None

        return None  # Pas de fast-path → vision loop

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

        # Tenter le fast-path avant la vision loop
        try:
            fast_result = await self._try_fast_path(task, step_callback)
            if fast_result is not None:
                print(f"[OsControl] Fast-path → {fast_result}")
                return fast_result
        except Exception as e:
            print(f"[OsControl] Fast-path erreur : {e}")

        loop = asyncio.get_running_loop()
        stop_event = asyncio.Event()
        self._current_stop_event = stop_event  # exposé pour stop_pc_task
        listener = None

        try:
            try:
                listener = self._start_hotkey_listener(stop_event, loop)
            except Exception as e:
                print(f"[OsControl] ⚠️  Failsafe hotkey désactivé (pynput indisponible : {e})")

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
            stop_event.set()
            self._current_stop_event = None
            try:
                if listener:
                    listener.stop()
            except Exception:
                pass
