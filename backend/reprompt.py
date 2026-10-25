"""
reprompt.py — Couche de reformulation d'intention (« reprompting »).

Avant que le LLM ne traite une demande TEXTE de Bryan, on la reformule en une
instruction claire, complète et sans ambiguïté — comme le font les IA
génératives modernes. Conçu pour ne jamais trahir l'intention :
  - fast-path : ignore le trivial / trop court (renvoie le texte tel quel) ;
  - fallback systématique sur le texte ORIGINAL en cas d'erreur ou de sortie
    douteuse (vide, trop longue).

Ne s'applique qu'au texte. Le mode voix (Gemini Live, audio direct) n'est pas
concerné : il n'y a pas de texte à reformuler avant le modèle.
"""

import asyncio
import os

_ENABLED = os.getenv("JARVIS_REPROMPT", "false").lower() in ("1", "true", "yes", "on")
_MODEL = os.getenv("JARVIS_REPROMPT_MODEL", "gemini-2.5-flash")
_MIN_LEN = int(os.getenv("JARVIS_REPROMPT_MIN_LEN", "12"))
_GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")

_SYSTEM = (
    "Tu reformules la demande de l'utilisateur (Bryan) en UNE instruction claire, "
    "complète et sans ambiguïté pour un assistant IA, en français.\n"
    "RÈGLES STRICTES :\n"
    "- Conserve EXACTEMENT l'intention, la langue et les détails (noms, chiffres, "
    "cibles, textes exacts). N'invente RIEN, n'ajoute aucune donnée que "
    "l'utilisateur n'a pas fournie.\n"
    "- Explicite seulement l'implicite évident (l'app/la cible, l'action attendue) "
    "sans changer le sens.\n"
    "- Si la demande est déjà claire, une simple question, ou une salutation, "
    "renvoie-la telle quelle.\n"
    "- Réponds UNIQUEMENT par l'instruction reformulée — aucun commentaire, aucune "
    "explication, aucune guillemet superflue."
)

_client = None


def _get_client():
    global _client
    if _client is None and _GEMINI_API_KEY:
        from google import genai
        _client = genai.Client(api_key=_GEMINI_API_KEY)
    return _client


async def enhance(text: str) -> str:
    """Retourne une version clarifiée du texte. Fallback = texte original."""
    if not _ENABLED or not text or len(text.strip()) < _MIN_LEN:
        return text
    try:
        client = _get_client()
        if client is None:
            return text
        from google.genai import types
        resp = await asyncio.to_thread(
            client.models.generate_content,
            model=_MODEL,
            contents=text.strip(),
            config=types.GenerateContentConfig(
                system_instruction=_SYSTEM,
                temperature=0.0,
            ),
        )
        out = (resp.text or "").strip()
        # Garde-fous : non vide et longueur raisonnable, sinon on garde l'original.
        if out and len(out) <= max(400, len(text) * 4):
            return out
    except Exception as e:
        print(f"[REPROMPT] fallback ({e})")
    return text
