"""
Module de contrôle ordinateur (macOS).
Expose handle(action, args) pour typer, cliquer, scroller et envoyer des raccourcis clavier.
Utilise osascript (AppleScript) et pynput pour le scroll.
"""

import asyncio
import subprocess
from typing import Any


# ── Touches spéciales → key code AppleScript ──────────────────────────────────
_SPECIAL_KEYS: dict[str, int] = {
    "return": 36, "enter": 36,
    "escape": 53, "esc": 53,
    "tab": 48,
    "space": 49,
    "backspace": 51, "delete": 51,
    "up": 126, "down": 125,
    "left": 123, "right": 124,
    "f1": 122, "f2": 120, "f3": 99, "f4": 118,
    "f5": 96,  "f6": 97, "f7": 98, "f8": 100,
    "f9": 101, "f10": 109, "f11": 103, "f12": 111,
    "page_up": 116, "pageup": 116,
    "page_down": 121, "pagedown": 121,
    "home": 115, "end": 119,
}

# ── Modificateurs → clause AppleScript ────────────────────────────────────────
_MODIFIER_MAP: dict[str, str] = {
    "ctrl": "control down", "control": "control down",
    "cmd": "command down", "command": "command down",
    "shift": "shift down",
    "alt": "option down", "option": "option down",
}


def _run_osascript(script: str) -> str:
    """Exécute un script AppleScript de façon synchrone, lève RuntimeError si échec."""
    result = subprocess.run(
        ["osascript", "-e", script],
        capture_output=True, text=True
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip())
    return result.stdout.strip()


async def handle(action: str, args: dict[str, Any]) -> str:
    """
    Exécute une action de contrôle ordinateur macOS.

    Actions supportées :
    - screenshot   : retourne un message d'indisponibilité en mode texte
    - type         : tape du texte via presse-papiers + Cmd+V
    - hotkey       : envoie un raccourci clavier (ex : "cmd+shift+s")
    - click        : clic simple aux coordonnées (x, y)
    - double_click : double-clic aux coordonnées (x, y)
    - right_click  : clic droit aux coordonnées (x, y)
    - scroll       : scroll à (x, y) avec delta
    """
    try:
        if action == "screenshot":
            return "Screenshot non disponible en mode texte."

        text_val: str = args.get("text", "")
        x = args.get("x")
        y = args.get("y")

        if action == "type" and text_val:
            # Copier dans le presse-papiers puis coller (gère tous les caractères Unicode)
            await asyncio.to_thread(
                lambda: subprocess.run(["pbcopy"], input=text_val.encode("utf-8"), check=True)
            )
            await asyncio.to_thread(
                _run_osascript,
                'tell application "System Events" to keystroke "v" using command down'
            )
            return f"Tapé : {text_val[:80]}"

        elif action == "hotkey" and text_val:
            parts = [p.strip().lower() for p in text_val.split("+")]
            key = parts[-1]
            mods = [_MODIFIER_MAP[p] for p in parts[:-1] if p in _MODIFIER_MAP]
            clause = ", ".join(mods)

            if key in _SPECIAL_KEYS:
                kc = _SPECIAL_KEYS[key]
                script = (
                    f'tell application "System Events" to key code {kc} using {{{clause}}}'
                    if clause else
                    f'tell application "System Events" to key code {kc}'
                )
            else:
                script = (
                    f'tell application "System Events" to keystroke "{key}" using {{{clause}}}'
                    if clause else
                    f'tell application "System Events" to keystroke "{key}"'
                )
            await asyncio.to_thread(_run_osascript, script)
            return f"Raccourci : {text_val}"

        elif action in ("click", "right_click", "double_click") and x is not None and y is not None:
            ix, iy = int(x), int(y)
            if action == "click":
                script = f'tell application "System Events" to click at {{{ix}, {iy}}}'
            elif action == "right_click":
                script = (
                    f'tell application "System Events"\n'
                    f'  set p to {{{ix}, {iy}}}\n'
                    f'  click at p using {{control down}}\n'
                    f'end tell'
                )
            else:  # double_click
                script = f'tell application "System Events" to double click at {{{ix}, {iy}}}'
            await asyncio.to_thread(_run_osascript, script)
            return f"{action} at ({ix}, {iy})"

        elif action == "scroll" and x is not None and y is not None:
            ix = int(x)
            iy = int(y)
            idelta = int(args.get("delta", 3))

            def _do_scroll(lx: int, ly: int, d: int) -> None:
                from pynput import mouse as _pmouse
                import time as _t
                m = _pmouse.Controller()
                m.position = (lx, ly)
                _t.sleep(0.08)
                m.scroll(0, -d)  # pynput : négatif = bas, positif = haut

            await asyncio.to_thread(_do_scroll, ix, iy, idelta)
            return f"Scroll {idelta} at ({ix}, {iy})"

        return f"Action inconnue ou paramètres manquants : action={action}"

    except Exception as e:
        return f"Erreur control_computer [{action}] : {e}"
