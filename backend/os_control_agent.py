"""
os_control_agent.py — Contrôle Mac avec comportement humain

Architecture Plan → Execute → Verify :
  1. Fast-path  : navigation pure, shell direct  (0 appel API)
  2. Plan       : 1 appel API → séquence complète d'actions
  3. Execute    : rafale d'actions sans latence API entre elles
  4. Verify     : 1 appel API → vérification visuelle
  5. Correct    : si raté, plan correctif (max 2 tentatives)

Un humain senior ne demande pas "quelle est ma prochaine action ?" après chaque clic.
Il visualise toute la séquence et l'exécute d'un coup.
"""

import asyncio
import base64
import io
import json
import os
import re
import subprocess
import urllib.parse
from typing import Callable, Optional

import mss
import PIL.Image
from dotenv import load_dotenv
from google import genai
from google.genai import types

load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
MODEL = "gemini-2.5-flash"
TIMEOUT_SEC = 90.0

_SPECIAL_KEY_CODES = {
    "return": 36, "enter": 36,
    "escape": 53, "esc": 53,
    "tab": 48, "space": 49,
    "delete": 51, "backspace": 51,
    "up": 126, "down": 125, "left": 123, "right": 124,
    "home": 115, "end": 119, "pageup": 116, "pagedown": 121,
    "f1": 122, "f2": 120, "f3": 99, "f4": 118,
    "f5": 96, "f6": 97, "f7": 98, "f8": 100,
}

_SHELL_PREFIXES = ("open ", "osascript ", "say ", "screencapture", "killall ", "defaults ")

# Tâches qui nécessitent une interaction UI — jamais interceptées par le fast-path
_INTERACTION_KEYWORDS = re.compile(
    r"messagerie|messages?(?!\s+(?:vocal|audio))|discussion|chat|inbox|"
    r"clique?|appuie?|presse?|sélectionne?|touche(?:\s+le\s+bouton)?|"
    r"profil|paramètre|réglage|setting|notifications?|"
    r"explorer|reels?|story|stories|"
    r"like|j'aime|commente?|partage?|"
    r"cherche\s+dans|barre\s+de\s+(?:recherche|navigation)|"
    r"onglet|menu\s+(?:de)?|bouton|icône|"
    r"fil\s+d'actualité|feed|accueil(?!\s+(?:de\s+safari|du\s+navigateur|de\s+chrome))|"
    r"envoie?|écri[st]|tape|saisi[st]|rédige|"
    r"déconnecte?|connexion|login|logout|inscription",
    re.IGNORECASE
)

# ─── Prompts ──────────────────────────────────────────────────────────────────

_PLAN_SYSTEM = """You are an expert Mac operator with perfect visual perception and UI knowledge.
You see a real screenshot of the Mac screen. Generate a COMPLETE action plan to accomplish the task.

THINK LIKE A SENIOR HUMAN:
- Analyze the entire current screen state
- Identify exactly what UI elements are present and where
- Plan ALL steps needed upfront — never plan just one step
- Be precise about coordinates: mentally zoom into elements, use their CENTER
- For text input: always click the field FIRST to focus it, then type
- For sending messages: click input field → type text → hotkey "return"
- For navigation within apps: identify the exact nav element, click it precisely

COORDINATE SYSTEM: 0-1000 scale (0,0 = top-left, 1000,1000 = bottom-right)
Example: element visually at 1/3 from left, 3/4 from top → x=333, y=750

COMMON PATTERNS:
  Send message   : click on chat input (bottom of chat) → type text → hotkey "return"
  Click link     : identify exact position → click
  Fill field     : click field → hotkey "cmd+a" (select all) → type new value
  Open URL       : run_shell "open -a 'Safari' 'https://...'"
  Instagram DM   : the chat input is typically at the bottom center of the screen

OUTPUT: ONLY a valid JSON array (no markdown, no explanation):
[
  {"action": "ACTION", "x": N, "y": N, "text": "...", "reason": "brief description"},
  ...
]

ACTIONS:
  click         : {"action":"click","x":0-1000,"y":0-1000,"reason":"..."}
  double_click  : {"action":"double_click","x":0-1000,"y":0-1000,"reason":"..."}
  right_click   : {"action":"right_click","x":0-1000,"y":0-1000,"reason":"..."}
  type          : {"action":"type","text":"text to type","reason":"..."}
  hotkey        : {"action":"hotkey","text":"return|escape|cmd+l|cmd+a|cmd+v|tab","reason":"..."}
  scroll        : {"action":"scroll","x":0-1000,"y":500,"delta":3,"reason":"..."}  (positive=down)
  run_shell     : {"action":"run_shell","text":"shell command","reason":"..."}
  wait          : {"action":"wait","duration":1.0,"reason":"waiting for page load"}
  get_ui_elements: {"action":"get_ui_elements","reason":"list accessible UI elements"}

RULES:
- Include ALL steps, not just the first one
- After opening an app or navigating, add a wait step (duration: 1.5)
- After clicking a text field, type immediately (no wait needed)
- For hotkey "return" or "escape": use exactly those strings (handled as key codes internally)
- If the task requires scrolling to find something, include scroll steps
- Maximum 12 actions in one plan — if more needed, prioritize the most direct path

ABSOLUTE PROHIBITIONS — these will be blocked at execution level and cause task failure:
- NEVER use hotkey "cmd+space" or "command+space" — Spotlight is FORBIDDEN
- NEVER open Spotlight for any reason — use run_shell with "open -a AppName" instead
- To open any app: run_shell with "open -a 'AppName'" (not Spotlight, not clicking the Dock)
- To search the web: run_shell with "open -a 'Safari' 'https://google.com/search?q=...'"
- Spotlight will be intercepted and blocked — your plan will fail if you use it
"""

_VERIFY_SYSTEM = """You are verifying if a Mac task was successfully completed.
Look at the current screenshot carefully.

Return ONLY valid JSON (no markdown):
{
  "success": true or false,
  "confidence": 0-100,
  "evidence": "what you see that confirms success or failure",
  "remaining": "if not done, what still needs to happen (empty string if done)"
}

Be honest. If the screen doesn't clearly show the task was completed, say false.
"""

_CORRECT_SYSTEM = """You are an expert Mac operator correcting a failed attempt.
You see the current screen state and know what was attempted and why it failed.
Generate a CORRECTIVE action plan to complete the task.

Focus on what went wrong and take a different approach.
Return ONLY a valid JSON array of actions (same format as before).
"""


def _run_osascript(script: str) -> str:
    r = subprocess.run(["osascript", "-e", script], capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(r.stderr.strip())
    return r.stdout.strip()


def _get_screen_size() -> tuple[int, int]:
    try:
        out = subprocess.run(
            ["osascript", "-e", 'tell application "Finder" to get bounds of window of desktop'],
            capture_output=True, text=True, timeout=5
        ).stdout.strip()
        parts = [p.strip() for p in out.split(",")]
        return int(parts[2]), int(parts[3])
    except Exception:
        return 1440, 900


def _is_interaction_task(task: str) -> bool:
    return bool(_INTERACTION_KEYWORDS.search(task))


def _parse_json_response(text: str) -> any:
    """Parse JSON from model response, stripping markdown if present."""
    text = text.strip()
    text = re.sub(r'^```(?:json)?\s*', '', text)
    text = re.sub(r'\s*```$', '', text).strip()
    return json.loads(text)


class OsControlAgent:
    def __init__(self):
        if not GEMINI_API_KEY:
            raise RuntimeError("GEMINI_API_KEY non configurée.")
        self._client = genai.Client(api_key=GEMINI_API_KEY)
        self._global_stop = asyncio.Event()
        self._lock = asyncio.Lock()
        self._current_task = ""
        self._sw, self._sh = 1440, 900  # mis à jour au premier run

    def stop(self):
        self._global_stop.set()
        print(f"[OsControl] STOP — {self._current_task[:50]}")

    def _reset(self):
        self._global_stop.clear()

    # ── Screenshot ─────────────────────────────────────────────────────────────

    async def _screenshot(self) -> tuple[bytes, str]:
        """Screenshot 1280×800 JPEG 85% — qualité suffisante pour l'analyse UI."""
        def _grab():
            with mss.mss() as sct:
                shot = sct.grab(sct.monitors[1])
                img = PIL.Image.frombytes("RGB", shot.size, shot.bgra, "raw", "BGRX")
                img.thumbnail([1280, 800])
                buf = io.BytesIO()
                img.save(buf, format="jpeg", quality=85)
                return buf.getvalue()
        raw = await asyncio.to_thread(_grab)
        return raw, base64.b64encode(raw).decode()

    # ── Gemini calls ───────────────────────────────────────────────────────────

    async def _call_gemini(self, system: str, user_text: str, screenshot_bytes: bytes) -> str:
        """Appel Gemini avec screenshot. Retourne le texte brut de la réponse."""
        resp = await asyncio.to_thread(
            self._client.models.generate_content,
            model=MODEL,
            contents=[types.Content(role="user", parts=[
                types.Part(text=user_text),
                types.Part.from_bytes(data=screenshot_bytes, mime_type="image/jpeg"),
            ])],
            config=types.GenerateContentConfig(
                system_instruction=system,
                temperature=0.1,
            ),
        )
        return resp.text

    async def _plan(self, task: str, screenshot: bytes) -> list[dict]:
        """Génère un plan complet d'actions pour accomplir la tâche."""
        prompt = (
            f"Task to accomplish: {task}\n\n"
            "Analyze the screenshot carefully. "
            "Generate the COMPLETE action sequence needed. "
            "Be precise about coordinates — identify element centers visually. "
            "Include ALL steps including focus clicks before typing."
        )
        raw = await self._call_gemini(_PLAN_SYSTEM, prompt, screenshot)
        try:
            plan = _parse_json_response(raw)
            if not isinstance(plan, list):
                raise ValueError("Expected JSON array")
            print(f"[OsControl] Plan généré: {len(plan)} actions")
            for i, a in enumerate(plan):
                print(f"  {i+1}. {a.get('action')} — {a.get('reason','')}")
            return plan
        except Exception as e:
            print(f"[OsControl] Erreur parse plan: {e}\nRaw: {raw[:300]}")
            return []

    async def _verify(self, task: str, screenshot: bytes) -> dict:
        """Vérifie si la tâche a été accomplie."""
        prompt = (
            f"Task that was attempted: {task}\n\n"
            "Look at the current screen. Was the task successfully completed? "
            "Look for clear visual evidence."
        )
        raw = await self._call_gemini(_VERIFY_SYSTEM, prompt, screenshot)
        try:
            result = _parse_json_response(raw)
            print(f"[OsControl] Vérification: success={result.get('success')} "
                  f"({result.get('confidence')}%) — {result.get('evidence','')[:80]}")
            return result
        except Exception as e:
            print(f"[OsControl] Erreur parse verify: {e}")
            return {"success": False, "confidence": 0, "evidence": str(e), "remaining": ""}

    async def _correct(self, task: str, error: str, screenshot: bytes) -> list[dict]:
        """Génère un plan correctif après un échec."""
        prompt = (
            f"Task: {task}\n\n"
            f"Previous attempt failed. Evidence: {error}\n\n"
            "Analyze the current screenshot. "
            "Generate a CORRECTIVE action plan using a different approach. "
            "Identify precisely what needs to be done now."
        )
        raw = await self._call_gemini(_CORRECT_SYSTEM, prompt, screenshot)
        try:
            plan = _parse_json_response(raw)
            if not isinstance(plan, list):
                raise ValueError("Expected JSON array")
            print(f"[OsControl] Plan correctif: {len(plan)} actions")
            return plan
        except Exception as e:
            print(f"[OsControl] Erreur parse correct: {e}")
            return []

    # ── Accessibilité ──────────────────────────────────────────────────────────

    async def _get_front_app(self) -> str:
        try:
            return await asyncio.to_thread(
                _run_osascript,
                'tell application "System Events" to get name of first application process whose frontmost is true'
            )
        except Exception:
            return "Unknown"

    async def _get_ui_elements(self) -> str:
        try:
            app = await self._get_front_app()
            script = f'''
tell application "System Events"
    tell process "{app}"
        set res to ""
        try
            repeat with btn in every button of window 1
                try
                    set d to description of btn
                    if d is not "" then set res to res & "BTN:" & d & "\\n"
                end try
                try
                    set t to title of btn
                    if t is not "" then set res to res & "BTN_T:" & t & "\\n"
                end try
            end repeat
        end try
        try
            repeat with btn in every button of toolbar 1 of window 1
                try
                    set d to description of btn
                    if d is not "" then set res to res & "TB:" & d & "\\n"
                end try
            end repeat
        end try
        return res
    end tell
end tell'''
            r = await asyncio.to_thread(_run_osascript, script)
            return f"UI ({app}):\n{r}" if r.strip() else f"Aucun élément UI accessible dans {app}."
        except Exception as e:
            return f"get_ui_elements erreur: {e}"

    async def _click_element_by_name(self, name: str) -> str:
        try:
            app = await self._get_front_app()
            script = f'''
tell application "System Events"
    tell process "{app}"
        try
            click (first button whose description contains "{name}") of window 1
            return "ok"
        end try
        try
            click (first button whose title contains "{name}") of window 1
            return "ok"
        end try
        try
            click (first button whose description contains "{name}") of toolbar 1 of window 1
            return "ok"
        end try
        try
            click (first link whose description contains "{name}") of window 1
            return "ok"
        end try
        return "not_found"
    end tell
end tell'''
            r = await asyncio.to_thread(_run_osascript, script)
            return f"click_element '{name}': {r}"
        except Exception as e:
            return f"click_element erreur: {e}"

    # ── Exécution d'une action ─────────────────────────────────────────────────

    # Combinaisons de touches ABSOLUMENT interdites — jamais exécutées quoi que Gemini dise
    # Note: vérification par composants (pas set-membership) pour survivre aux variantes Unicode
    _SPOTLIGHT_MODIFIERS = {"cmd", "command", "ctrl", "control"}
    _SPOTLIGHT_KEY = "space"

    # Commandes shell interdites dans run_shell
    _FORBIDDEN_SHELL_PATTERNS = re.compile(
        r"open\s+-a\s+['\"]?spotlight['\"]?|"
        r"osascript.*spotlight|"
        r"mdfind(?!\s+-0)",  # mdfind seul = recherche Spotlight
        re.IGNORECASE
    )

    async def _exec_action(self, a: dict) -> str:
        """Exécute une action atomique. Retourne description du résultat."""
        action = a.get("action", "")
        nx, ny = a.get("x"), a.get("y")
        text = a.get("text", "")
        delta = int(a.get("delta", 3))
        duration = float(a.get("duration", 1.0))

        # ── GARDE DE SÉCURITÉ — actions interdites bloquées avant tout ──────
        if action == "hotkey":
            # Split sur tout séparateur possible (+, espace, _, -)
            parts = set(re.split(r'[\s_\-+]+', text.strip().lower()))
            if self._SPOTLIGHT_KEY in parts and parts & self._SPOTLIGHT_MODIFIERS:
                msg = f"[BLOQUÉ] hotkey '{text}' interdit (Spotlight). Utiliser run_shell 'open -a AppName'."
                print(f"[OsControl] ⛔ {msg}")
                return msg

        if action == "run_shell" and self._FORBIDDEN_SHELL_PATTERNS.search(text):
            msg = f"[BLOQUÉ] commande shell interdite: {text[:60]}"
            print(f"[OsControl] ⛔ {msg}")
            return msg

        sw, sh = self._sw, self._sh

        def lp(nx, ny):
            return int(nx * sw / 1000), int(ny * sh / 1000)

        # Alias Gemini non-standards
        if action == "press_key":
            action = "hotkey"  # press_key = hotkey
        if action == "key_press":
            action = "hotkey"

        try:
            if action in ("click", "double_click", "right_click") and nx is not None:
                lx, ly = lp(nx, ny)
                if action == "click":
                    s = f'tell application "System Events" to click at {{{lx}, {ly}}}'
                elif action == "double_click":
                    s = f'tell application "System Events" to double click at {{{lx}, {ly}}}'
                else:
                    s = (f'tell application "System Events"\n'
                         f'  click at {{{lx}, {ly}}} using {{control down}}\n'
                         f'end tell')
                await asyncio.to_thread(_run_osascript, s)
                await asyncio.sleep(0.3)
                return f"{action}({lx},{ly})"

            elif action == "click_element":
                r = await self._click_element_by_name(text)
                await asyncio.sleep(0.3)
                return r

            elif action == "get_ui_elements":
                return await self._get_ui_elements()

            elif action == "type" and text:
                await asyncio.to_thread(
                    lambda: subprocess.run(["pbcopy"], input=text.encode("utf-8"), check=True)
                )
                await asyncio.to_thread(
                    _run_osascript,
                    'tell application "System Events" to keystroke "v" using command down'
                )
                await asyncio.sleep(0.2)
                return f"typed: {text[:50]}"

            elif action == "hotkey" and text:
                _mods = {
                    "ctrl": "control down", "control": "control down",
                    "cmd": "command down", "command": "command down",
                    "shift": "shift down", "alt": "option down", "option": "option down",
                }
                parts = [p.strip().lower() for p in text.split("+")]
                key = parts[-1].replace('"', '\\"')
                mods = [_mods[p] for p in parts[:-1] if p in _mods]
                using = ", ".join(mods)
                if key in _SPECIAL_KEY_CODES:
                    code = _SPECIAL_KEY_CODES[key]
                    s = (f'tell application "System Events" to key code {code} using {{{using}}}'
                         if using else
                         f'tell application "System Events" to key code {code}')
                elif using:
                    s = f'tell application "System Events" to keystroke "{key}" using {{{using}}}'
                else:
                    s = f'tell application "System Events" to keystroke "{key}"'
                await asyncio.to_thread(_run_osascript, s)
                await asyncio.sleep(0.3)
                return f"hotkey: {text}"

            elif action == "scroll" and nx is not None:
                lx, ly = lp(nx, ny)
                s = (f'tell application "System Events"\n'
                     f'  scroll at {{{lx}, {ly}}} by {{0, {delta}}}\n'
                     f'end tell')
                await asyncio.to_thread(_run_osascript, s)
                await asyncio.sleep(0.4)
                return f"scroll {delta} at ({lx},{ly})"

            elif action == "run_shell" and text:
                r = await asyncio.to_thread(
                    subprocess.run, text, shell=True,
                    capture_output=True, text=True, timeout=30
                )
                out = (r.stdout or "").strip()
                err = (r.stderr or "").strip()
                await asyncio.sleep(1.5)  # laisser l'app/page se charger
                return f"shell: {out or 'ok'}" + (f" | {err}" if err else "")

            elif action == "wait":
                await asyncio.sleep(max(0.5, min(duration, 5.0)))
                return f"waited {duration}s"

            if action in ("click", "double_click", "right_click"):
                # Gemini a envoyé click sans coordonnées — prendre le centre de l'écran
                return f"[SKIP] {action} sans coordonnées ignoré"
            return f"action inconnue: {action}"

        except Exception as e:
            return f"erreur {action}: {e}"

    async def _execute_plan(self, plan: list[dict], cb: Optional[Callable], stop: asyncio.Event) -> bool:
        """Exécute un plan en rafale. Retourne False si interrompu."""
        for i, action in enumerate(plan):
            if stop.is_set() or self._global_stop.is_set():
                return False
            act = action.get("action", "")
            reason = action.get("reason", act)
            # Log de pré-exécution
            print(f"[OsControl] Action {i+1}/{len(plan)}: {act} — {reason}")
            if cb:
                await cb({"image": None, "log": f"[PC] {reason}"})
            result = await self._exec_action(action)
            print(f"[OsControl]   → {result}")
            # Si l'action a été bloquée, notifier et continuer (pas d'arrêt)
            if result.startswith("[BLOQUÉ]") and cb:
                await cb({"image": None, "log": f"[PC] ⛔ {result}"})
        return True

    # ── Fast-path ──────────────────────────────────────────────────────────────

    async def _fast_path(self, task: str, cb: Optional[Callable]) -> Optional[str]:
        """Navigation pure et commandes shell directes. None → vision loop."""
        t = task.strip()
        tl = t.lower()

        # Les interactions UI passent toujours en vision loop
        if _is_interaction_task(t):
            print("[OsControl] Interaction détectée → vision loop")
            return None

        # Commande shell directe
        if any(tl.startswith(p) for p in _SHELL_PREFIXES):
            if cb:
                await cb({"image": None, "log": f"[PC] {t[:80]}"})
            r = await asyncio.to_thread(subprocess.run, t, shell=True,
                                        capture_output=True, text=True, timeout=30)
            return (r.stdout or "ok").strip()

        # ── Ouverture d'app directe (AVANT website nav pour éviter l'ambiguïté "ouvre X") ──
        # Sites connus → Safari. Apps connues → open -a. Sinon → vision loop.
        WEB_SITES = {
            "instagram": "https://www.instagram.com",
            "youtube": "https://www.youtube.com",
            "twitter": "https://www.x.com",
            "facebook": "https://www.facebook.com",
            "gmail": "https://mail.google.com",
            "google": "https://www.google.com",
            "github": "https://www.github.com",
            "notion": "https://www.notion.so",
            "linkedin": "https://www.linkedin.com",
        }
        # Apps desktop connues → open -a (pas Safari, pas vision loop)
        KNOWN_APPS = {
            "spotify": "Spotify",
            "finder": "Finder",
            "terminal": "Terminal",
            "safari": "Safari",
            "chrome": "Google Chrome",
            "firefox": "Firefox",
            "vscode": "Visual Studio Code",
            "code": "Visual Studio Code",
            "xcode": "Xcode",
            "figma": "Figma",
            "slack": "Slack",
            "zoom": "zoom.us",
            "discord": "Discord",
            "telegram": "Telegram",
            "whatsapp": "WhatsApp",
            "notes": "Notes",
            "calendar": "Calendar",
            "calendrier": "Calendar",
            "messages": "Messages",
            "mail": "Mail",
            "photos": "Photos",
            "musique": "Music",
            "music": "Music",
            "appstore": "App Store",
            "app store": "App Store",
        }

        app_m = re.search(
            r"^(?:ouvre?|lance?|démarre?|open|start|launch|active?)\s+"
            r"(?:l'?app(?:lication)?\s+)?[«\"']?([a-zA-Z0-9À-ÿ\s\.\-]+?)[«\"']?\s*$",
            t, re.IGNORECASE
        )
        if app_m:
            target_raw = app_m.group(1).strip().strip("'\"«»")
            target_lower = target_raw.lower()

            # Site web connu → Safari
            if target_lower in WEB_SITES:
                url = WEB_SITES[target_lower]
                subprocess.run(["open", "-a", "Safari", url], capture_output=True, timeout=10)
                return f"Safari ouvert sur {url}."

            # App desktop connue → open -a avec nom exact
            if target_lower in KNOWN_APPS:
                app_name = KNOWN_APPS[target_lower]
                r = subprocess.run(["open", "-a", app_name], capture_output=True, text=True, timeout=10)
                if r.returncode == 0:
                    return f"{app_name} ouvert."

            # App quelconque → tenter open -a avec le nom brut
            r = subprocess.run(["open", "-a", target_raw], capture_output=True, text=True, timeout=10)
            if r.returncode == 0:
                return f"{target_raw} ouvert."

            # Fallback AppleScript activate
            try:
                _run_osascript(f'tell application "{target_raw}" to activate')
                return f"{target_raw} activé."
            except Exception:
                pass  # → vision loop

        # ── Recherche web ──────────────────────────────────────────────────────
        SEARCHES = [
            (r"(?:cherche?|recherche?|search|trouve?)\s+(.+?)\s+(?:sur|on|dans)\s+youtube",
             "YouTube", "https://www.youtube.com/results?search_query={}"),
            (r"(?:cherche?|recherche?|search|trouve?)\s+(.+?)\s+(?:sur|on)\s+google",
             "Google", "https://www.google.com/search?q={}"),
            (r"(?:cherche?|recherche?|search|trouve?)\s+(.+?)\s+(?:sur|on)\s+(?:twitter|x\.com)",
             "Twitter", "https://x.com/search?q={}"),
        ]
        for pat, engine, tmpl in SEARCHES:
            m = re.search(pat, tl, re.IGNORECASE)
            if m:
                q = m.group(1).strip().rstrip(".")
                url = tmpl.format(urllib.parse.quote(q))
                if cb:
                    await cb({"image": None, "log": f"[PC] Recherche {engine}: {q}"})
                subprocess.run(["open", "-a", "Safari", url], capture_output=True, timeout=10)
                return f"Recherche '{q}' sur {engine}."

        # ── Navigation directe vers URL ou site connu ──────────────────────────
        nav = re.search(
            r"^(?:va(?:s)?\s+(?:sur|à)|navigue?\s+(?:vers|sur)|va\s+sur|ouvre?\s+le\s+site)\s+(.+)$",
            tl.strip()
        )
        if nav:
            target = nav.group(1).strip().rstrip(".")
            url_m = re.search(r"(https?://\S+)", target)
            if url_m:
                subprocess.run(["open", "-a", "Safari", url_m.group(1)], capture_output=True, timeout=10)
                return f"Safari ouvert sur {url_m.group(1)}."
            for kw, url in WEB_SITES.items():
                if re.fullmatch(re.escape(kw) + r'\s*', target, re.IGNORECASE):
                    subprocess.run(["open", "-a", "Safari", url], capture_output=True, timeout=10)
                    return f"Safari ouvert sur {url}."
            return None  # Navigation avec sous-action → vision loop

        # Volume
        if re.search(r"(mute|coupe?\s+le\s+son|silence|sourdine)", tl):
            _run_osascript("set volume output muted true")
            return "Son coupé."
        vs = re.search(r"(?:volume|son)\s+(?:à|a|=)?\s*(\d+)", tl)
        if vs:
            _run_osascript(f"set volume output volume {min(100, max(0, int(vs.group(1))))}")
            return f"Volume {vs.group(1)}%."
        if re.search(r"(baisse|diminue|réduis)\s+(?:le\s+)?(?:volume|son)", tl):
            _run_osascript("set cur to output volume of (get volume settings)\n"
                           "set volume output volume (cur - 15)")
            return "Volume baissé."
        if re.search(r"(monte|augmente|hausse)\s+(?:le\s+)?(?:volume|son)", tl):
            _run_osascript("set cur to output volume of (get volume settings)\n"
                           "set volume output volume (cur + 15)")
            return "Volume monté."

        return None  # → vision loop

    # ── Point d'entrée principal ───────────────────────────────────────────────

    async def run(self, task: str, step_callback: Optional[Callable] = None) -> str:
        # Stop toute tâche précédente en cours
        if self._lock.locked():
            print("[OsControl] Tâche précédente active → stop")
            self._global_stop.set()
            await asyncio.sleep(0.3)

        async with self._lock:
            self._reset()
            self._current_task = task
            self._sw, self._sh = await asyncio.to_thread(_get_screen_size)
            print(f"[OsControl] ▶ {task[:80]} (écran {self._sw}×{self._sh})")

            if step_callback:
                await step_callback({"image": None, "log": f"[PC] {task[:80]}"})

            # 1. Fast-path
            try:
                fp = await self._fast_path(task, step_callback)
                if fp is not None:
                    return fp
            except Exception as e:
                print(f"[OsControl] Fast-path erreur: {e}")

            # Setup stop event
            local_stop = asyncio.Event()

            async def _watch():
                while not self._global_stop.is_set():
                    await asyncio.sleep(0.05)
                local_stop.set()

            watcher = asyncio.create_task(_watch())
            listener = self._start_hotkey_listener(local_stop)

            try:
                result = await asyncio.wait_for(
                    self._plan_execute_verify(task, step_callback, local_stop),
                    timeout=TIMEOUT_SEC,
                )
                return result
            except asyncio.TimeoutError:
                return f"Timeout {int(TIMEOUT_SEC)}s."
            except Exception as e:
                return f"Erreur: {e}"
            finally:
                local_stop.set()
                watcher.cancel()
                try:
                    if listener:
                        listener.stop()
                except Exception:
                    pass

    async def _plan_execute_verify(
        self, task: str, cb: Optional[Callable], stop: asyncio.Event
    ) -> str:
        """
        Boucle Plan → Execute → Verify avec max 3 tentatives.
        C'est le cœur du comportement "humain senior".
        """
        attempt = 0
        last_error = ""

        while attempt < 3:
            if stop.is_set() or self._global_stop.is_set():
                return "Tâche interrompue."

            # Screenshot initial
            raw, b64 = await self._screenshot()
            if cb:
                await cb({"image": b64, "log": f"[PC] Analyse de l'écran... (tentative {attempt+1})"})

            # Générer le plan
            if attempt == 0:
                plan = await self._plan(task, raw)
            else:
                # Plan correctif avec contexte de l'échec
                plan = await self._correct(task, last_error, raw)

            if not plan:
                return "Impossible de générer un plan d'action."

            if stop.is_set() or self._global_stop.is_set():
                return "Tâche interrompue."

            # Exécuter le plan en rafale
            if cb:
                await cb({"image": b64, "log": f"[PC] Exécution: {len(plan)} actions..."})

            completed = await self._execute_plan(plan, cb, stop)
            if not completed:
                return "Tâche interrompue."

            # Laisser l'UI se stabiliser
            await asyncio.sleep(0.8)

            if stop.is_set() or self._global_stop.is_set():
                return "Tâche interrompue."

            # Screenshot post-exécution + vérification
            raw2, b64_2 = await self._screenshot()
            if cb:
                await cb({"image": b64_2, "log": "[PC] Vérification..."})

            verification = await self._verify(task, raw2)

            if verification.get("success", False):
                evidence = verification.get("evidence", "")
                return f"✓ {evidence}"

            # Échec → préparer la correction
            last_error = verification.get("evidence", "") + " | " + verification.get("remaining", "")
            print(f"[OsControl] Tentative {attempt+1} échouée: {last_error}")
            if cb:
                await cb({"image": b64_2, "log": f"[PC] Pas encore fait — correction ({attempt+2}/3)"})

            attempt += 1

        return f"Tâche non complétée après 3 tentatives. Dernier état: {last_error}"

    def _start_hotkey_listener(self, stop_event: asyncio.Event):
        try:
            from pynput import keyboard as kb
            _pressed = set()
            _COMBO = {kb.Key.cmd, kb.Key.shift, kb.Key.esc}
            loop = asyncio.get_event_loop()

            async def _set(ev): ev.set()

            def on_press(key):
                _pressed.add(key)
                if _COMBO.issubset(_pressed):
                    asyncio.run_coroutine_threadsafe(_set(stop_event), loop)

            def on_release(key): _pressed.discard(key)

            l = kb.Listener(on_press=on_press, on_release=on_release)
            l.daemon = True
            l.start()
            return l
        except Exception as e:
            print(f"[OsControl] Hotkey listener: {e}")
            return None
