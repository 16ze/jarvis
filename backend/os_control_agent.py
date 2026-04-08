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
        print("[OsControl] ⚠️  Impossible de détecter la résolution logique — fallback 1440x900")
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
                key = parts[-1].replace('"', '\\"')
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
            print(f"[OsControl] Résultat : {result_str}")
            history.append(f"{action}: {reason} → {result_str}")

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
