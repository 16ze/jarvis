"""
llm_router.py — Cerveau hybride d'Ada.

Le raisonnement / la planification / le codage passent par Claude (modèles
Anthropic) quand c'est dispo — c'est ce qui donne « l'intelligence comme Claude »
— avec repli automatique sur Gemini. La VOIX reste sur Gemini Live (gérée dans
ada.py, NON concernée ici : Claude n'a pas d'audio natif).

Config (.env) :
  JARVIS_BRAIN = hybrid (défaut) | claude | gemini
    - hybrid : Claude si ANTHROPIC_API_KEY + SDK présents, sinon Gemini
    - claude : force Claude (lève une erreur claire si indispo)
    - gemini : force Gemini
  ANTHROPIC_API_KEY, JARVIS_CLAUDE_MODEL (défaut claude-sonnet-4-5)
  GEMINI_API_KEY,    JARVIS_GEMINI_TEXT_MODEL (défaut gemini-2.5-flash)
"""

import asyncio
import os

BRAIN = os.getenv("JARVIS_BRAIN", "hybrid").lower()
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
CLAUDE_MODEL = os.getenv("JARVIS_CLAUDE_MODEL", "claude-sonnet-4-5")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL = os.getenv("JARVIS_GEMINI_TEXT_MODEL", "gemini-2.5-flash")

_anthropic_client = None
_gemini_client = None


def claude_available() -> bool:
    if BRAIN == "gemini" or not ANTHROPIC_API_KEY:
        return False
    try:
        import anthropic  # noqa: F401
        return True
    except Exception:
        return False


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


def _think_gemini_sync(system: str, prompt: str, temperature: float) -> str:
    from google.genai import types
    client = _get_gemini()
    resp = client.models.generate_content(
        model=GEMINI_MODEL,
        contents=prompt,
        config=types.GenerateContentConfig(system_instruction=system, temperature=temperature),
    )
    return (resp.text or "").strip()


async def think(system: str, prompt: str, max_tokens: int = 4096, temperature: float = 0.1) -> str:
    """Raisonnement texte via le cerveau hybride. Retourne le texte brut."""
    if claude_available():
        try:
            return await asyncio.to_thread(_think_claude_sync, system, prompt, max_tokens, temperature)
        except Exception as e:
            print(f"[LLM] Claude échec ({e}) → repli Gemini")
            if BRAIN == "claude":
                raise
    if not GEMINI_API_KEY:
        raise RuntimeError("Aucun moteur disponible : ni Claude (clé/SDK) ni GEMINI_API_KEY.")
    return await asyncio.to_thread(_think_gemini_sync, system, prompt, temperature)


def active_engine() -> str:
    return "claude" if claude_available() else "gemini"
