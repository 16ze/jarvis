"""
llm_router.py — Cerveau hybride d'Ada.

Le raisonnement / la planification / le codage passent par Claude — c'est ce qui
donne « l'intelligence comme Claude » — avec repli automatique sur Gemini. La VOIX
reste sur Gemini Live (gérée dans ada.py, NON concernée ici).

Trois façons d'avoir le cerveau Claude :
  - API Anthropic (ANTHROPIC_API_KEY) : rapide, mais payant au token.
  - Claude Code CLI (`claude -p`) : utilise TON ABONNEMENT Claude → GRATUIT, plus
    privé, aucune clé API. (idée volée à PIO). Nécessite Claude Code installé.
  - (sinon) Gemini.

Config (.env) :
  JARVIS_BRAIN = hybrid (défaut) | claude | claudecli | gemini
    - hybrid    : API Claude si clé, sinon Claude Code CLI si dispo, sinon Gemini
    - claude    : force l'API Anthropic
    - claudecli : force le cerveau via Claude Code CLI (gratuit, abonnement)
    - gemini    : force Gemini
  ANTHROPIC_API_KEY, JARVIS_CLAUDE_MODEL (défaut claude-sonnet-4-5)
  JARVIS_CLAUDECLI_BIN (défaut "claude"), JARVIS_CLAUDECLI_MODEL (optionnel),
  JARVIS_CLAUDECLI_TIMEOUT (défaut 120)
  GEMINI_API_KEY, JARVIS_GEMINI_TEXT_MODEL (défaut gemini-2.5-flash)
"""

import asyncio
import os
import shutil
import subprocess

BRAIN = os.getenv("JARVIS_BRAIN", "hybrid").lower()
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
CLAUDE_MODEL = os.getenv("JARVIS_CLAUDE_MODEL", "claude-sonnet-4-5")
CLAUDECLI_BIN = os.getenv("JARVIS_CLAUDECLI_BIN", "claude")
CLAUDECLI_MODEL = os.getenv("JARVIS_CLAUDECLI_MODEL", "")
CLAUDECLI_TIMEOUT = float(os.getenv("JARVIS_CLAUDECLI_TIMEOUT", "120"))
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL = os.getenv("JARVIS_GEMINI_TEXT_MODEL", "gemini-2.5-flash")

_anthropic_client = None
_gemini_client = None


# ── Disponibilité des moteurs ────────────────────────────────────────────────

def claude_available() -> bool:
    if BRAIN in ("gemini", "claudecli") or not ANTHROPIC_API_KEY:
        return False
    try:
        import anthropic  # noqa: F401
        return True
    except Exception:
        return False


def claudecli_available() -> bool:
    if BRAIN == "gemini":
        return False
    try:
        return shutil.which(CLAUDECLI_BIN) is not None
    except Exception:
        return False


# ── Clients ──────────────────────────────────────────────────────────────────

def _get_anthropic():
    global _anthropic_client
    if _anthropic_client is None:
        import anthropic
        _anthropic_client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    return _anthropic_client


def _get_gemini():
    global _gemini_client
    if _gemini_client is None:
        from google import genai
        _gemini_client = genai.Client(api_key=GEMINI_API_KEY)
    return _gemini_client


# ── Implémentations synchrones (exécutées dans un thread) ────────────────────

def _think_claude_sync(system: str, prompt: str, max_tokens: int, temperature: float) -> str:
    client = _get_anthropic()
    resp = client.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=max_tokens,
        temperature=temperature,
        system=system,
        messages=[{"role": "user", "content": prompt}],
    )
    parts = [b.text for b in resp.content if getattr(b, "type", None) == "text"]
    return "".join(parts).strip()


def _think_claudecli_sync(system: str, prompt: str) -> str:
    """Cerveau via Claude Code CLI (`claude -p`) — abonnement, pas de clé API.
    Le prompt est passé par stdin ; on demande une sortie texte brute. Les tâches
    de raisonnement (think_deeply, planner, dev_agent) renvoient du texte/JSON que
    NOTRE code exécute — Claude Code n'agit donc pas sur la machine ici."""
    full = f"{system}\n\n---\n\n{prompt}" if system else prompt
    cmd = [CLAUDECLI_BIN, "-p", "--output-format", "text"]
    if CLAUDECLI_MODEL:
        cmd += ["--model", CLAUDECLI_MODEL]
    proc = subprocess.run(
        cmd, input=full, capture_output=True, text=True, timeout=CLAUDECLI_TIMEOUT
    )
    if proc.returncode != 0:
        raise RuntimeError(f"claude CLI exit {proc.returncode}: {(proc.stderr or '')[:200]}")
    out = (proc.stdout or "").strip()
    if not out:
        raise RuntimeError("claude CLI : sortie vide")
    return out


def _think_gemini_sync(system: str, prompt: str, temperature: float) -> str:
    from google.genai import types
    client = _get_gemini()
    resp = client.models.generate_content(
        model=GEMINI_MODEL,
        contents=prompt,
        config=types.GenerateContentConfig(system_instruction=system, temperature=temperature),
    )
    return (resp.text or "").strip()


# ── Ordre des moteurs + routage ──────────────────────────────────────────────

def _engine_order() -> list:
    if BRAIN == "gemini":
        return ["gemini"]
    if BRAIN == "claude":
        return ["claude"] + (["gemini"] if GEMINI_API_KEY else [])
    if BRAIN == "claudecli":
        return ["claudecli"] + (["gemini"] if GEMINI_API_KEY else [])
    # hybrid : API Claude si clé, sinon Claude Code CLI (gratuit), sinon Gemini
    order = []
    if claude_available():
        order.append("claude")
    elif claudecli_available():
        order.append("claudecli")
    if GEMINI_API_KEY:
        order.append("gemini")
    return order or ["gemini"]


async def think(system: str, prompt: str, max_tokens: int = 4096, temperature: float = 0.1) -> str:
    """Raisonnement texte via le cerveau hybride. Retourne le texte brut.
    Essaie les moteurs dans l'ordre et bascule au suivant en cas d'échec."""
    last_err = None
    for eng in _engine_order():
        try:
            if eng == "claude":
                return await asyncio.to_thread(_think_claude_sync, system, prompt, max_tokens, temperature)
            if eng == "claudecli":
                return await asyncio.to_thread(_think_claudecli_sync, system, prompt)
            if eng == "gemini":
                return await asyncio.to_thread(_think_gemini_sync, system, prompt, temperature)
        except Exception as e:
            last_err = e
            print(f"[LLM] moteur '{eng}' a échoué ({e}) → suivant")
    raise RuntimeError(f"Aucun moteur n'a répondu. Dernière erreur : {last_err}")


def active_engine() -> str:
    order = _engine_order()
    return order[0] if order else "none"
