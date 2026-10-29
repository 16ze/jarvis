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
import random
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

# ── Robustesse : retries / backoff / timeouts (asyncio pur, aucune dépendance) ─
# 3 tentatives, backoff exponentiel 0.5s → 1s → 2s (+ petit jitter aléatoire).
LLM_MAX_RETRIES = max(1, int(os.getenv("JARVIS_LLM_MAX_RETRIES", "3")))
LLM_BACKOFF_BASE = float(os.getenv("JARVIS_LLM_BACKOFF_BASE", "0.5"))
# Délai max par appel à un moteur (asyncio.wait_for). Ne jamais rester bloqué.
LLM_TIMEOUT = float(os.getenv("JARVIS_LLM_TIMEOUT", "120"))

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


# ── Robustesse : logging, classification d'erreurs, retries ──────────────────

def _log(msg: str) -> None:
    """Log cohérent avec le reste du projet (préfixe [LLM], toujours visible)."""
    print(f"[LLM] {msg}")


def _sanitize(text: str, limit: int = 200) -> str:
    """Nettoie un message d'erreur : masque les clés API et tronque.
    Les clés ne doivent JAMAIS apparaître en clair dans les logs/messages."""
    if not text:
        return ""
    for secret in (ANTHROPIC_API_KEY, GEMINI_API_KEY):
        if secret:
            text = text.replace(secret, "***")
    text = " ".join(text.split())
    return text[:limit]


# Messages FR par catégorie d'erreur (clairs et distincts selon la cause).
_CATEGORY_FR = {
    "auth": "clé API manquante ou invalide",
    "quota": "quota ou crédits épuisés (crédits de prépaiement épuisés)",
    "rate_limit": "limite de débit atteinte (trop de requêtes)",
    "server": "moteur temporairement indisponible (erreur serveur)",
    "timeout": "délai de réponse dépassé",
    "connection": "problème réseau",
    "model_unavailable": "modèle configuré indisponible",
    "bad_request": "requête invalide",
    "empty": "réponse vide du moteur",
    "unknown": "erreur inattendue",
}

# Catégories transitoires → on retente (backoff). Les autres → repli immédiat.
_RETRYABLE = {"rate_limit", "server", "timeout", "connection"}


class _EngineError(Exception):
    """Échec d'un moteur après retries, portant la catégorie et l'erreur d'origine."""

    def __init__(self, engine: str, category: str, original):
        self.engine = engine
        self.category = category
        self.original = original
        super().__init__(f"{engine}: {category}")


def _classify(exc: Exception) -> str:
    """Classe une exception moteur en catégorie exploitable.
    Jamais de retry sur auth (401/403), bad_request (400), quota ou modèle absent."""
    if isinstance(exc, (asyncio.TimeoutError, TimeoutError, subprocess.TimeoutExpired)):
        return "timeout"
    if isinstance(exc, ConnectionError):
        return "connection"

    status = None
    for attr in ("status_code", "code", "http_status"):
        v = getattr(exc, attr, None)
        if isinstance(v, int):
            status = v
            break

    low = (str(getattr(exc, "message", "") or "") + " " + str(exc)).lower()

    # Quota/crédits d'abord (non transitoire : retenter n'y changerait rien).
    if any(k in low for k in (
        "prepayment credits", "credits depleted", "credit balance",
        "insufficient", "quota", "billing", "payment required",
    )):
        return "quota"
    if status in (401, 403) or any(k in low for k in (
        "authentication", "unauthorized", "permission denied",
        "invalid api key", "invalid x-api-key", "forbidden",
    )):
        return "auth"
    if status == 429 or "rate limit" in low or "too many requests" in low or "429" in low:
        return "rate_limit"
    if (status is not None and 500 <= status < 600) or any(k in low for k in (
        "internal server error", "overloaded", "service unavailable",
        "bad gateway", "gateway timeout", " 500", " 502", " 503", " 504",
    )):
        return "server"
    if any(k in low for k in (
        "model not found", "model_not_found", "unknown model",
        "does not exist", "model is not available",
    )):
        return "model_unavailable"
    if status == 400 or "invalid request" in low or "invalid_request" in low:
        return "bad_request"
    if "timed out" in low or "timeout" in low:
        return "timeout"
    if any(k in low for k in (
        "connection", "network", "temporarily unreachable",
        "connection reset", "connection aborted",
    )):
        return "connection"
    return "unknown"


async def _run_engine(engine: str, func, args: tuple, timeout: float) -> str:
    """Exécute un moteur (func sync dans un thread) avec timeout explicite et
    retries à backoff exponentiel sur erreurs transitoires uniquement.
    Lève `_EngineError` si le moteur échoue après toutes les tentatives."""
    last_exc = None
    last_cat = "unknown"
    for attempt in range(1, LLM_MAX_RETRIES + 1):
        try:
            return await asyncio.wait_for(asyncio.to_thread(func, *args), timeout=timeout)
        except Exception as e:  # noqa: BLE001 — on classe puis on décide
            last_exc = e
            last_cat = _classify(e)
            if last_cat not in _RETRYABLE or attempt >= LLM_MAX_RETRIES:
                raise _EngineError(engine, last_cat, e) from e
            delay = LLM_BACKOFF_BASE * (2 ** (attempt - 1)) + random.uniform(0, LLM_BACKOFF_BASE / 2)
            _log(
                f"moteur '{engine}' erreur transitoire ({last_cat}) — "
                f"tentative {attempt}/{LLM_MAX_RETRIES}, nouvel essai dans {delay:.1f}s"
            )
            await asyncio.sleep(delay)
    raise _EngineError(engine, last_cat, last_exc)


def _format_failure(errors: list) -> str:
    """Construit un message d'erreur FR clair et exploitable quand tous les
    moteurs ont échoué — retourné proprement, sans exception qui remonte."""
    if not errors:
        return (
            "⚠️ Aucun moteur LLM n'est disponible. "
            "Vérifie la configuration (JARVIS_BRAIN, clés API)."
        )
    lines = []
    for ee in errors:
        fr = _CATEGORY_FR.get(ee.category, "erreur inattendue")
        detail = _sanitize(str(ee.original)) if ee.original is not None else ""
        lines.append(f"- {ee.engine} : {fr}" + (f" ({detail})" if detail else ""))
    return (
        "⚠️ Aucun moteur LLM n'a pu répondre après plusieurs tentatives.\n"
        + "\n".join(lines)
        + "\nVérifie les clés API, les crédits et le modèle configuré."
    )


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

    Essaie les moteurs dans l'ordre et bascule au suivant en cas d'échec.
    Chaque appel est protégé par un timeout explicite et par des retries à
    backoff exponentiel sur erreurs transitoires (timeout, 429, 5xx, réseau).
    Si TOUS les moteurs échouent, retourne un message d'erreur FR clair et
    exploitable — jamais d'exception qui remonterait et crasherait l'appelant."""
    errors = []
    for eng in _engine_order():
        if eng == "claude":
            func, args = _think_claude_sync, (system, prompt, max_tokens, temperature)
            timeout = LLM_TIMEOUT
        elif eng == "claudecli":
            # Le subprocess a son propre timeout (CLAUDECLI_TIMEOUT) ; on laisse
            # un peu de marge au wait_for pour qu'il déclenche en dernier recours.
            func, args = _think_claudecli_sync, (system, prompt)
            timeout = max(LLM_TIMEOUT, CLAUDECLI_TIMEOUT + 10)
        elif eng == "gemini":
            func, args = _think_gemini_sync, (system, prompt, temperature)
            timeout = LLM_TIMEOUT
        else:
            continue

        try:
            result = await _run_engine(eng, func, args, timeout)
        except _EngineError as ee:
            errors.append(ee)
            detail = _sanitize(str(ee.original)) if ee.original is not None else ""
            _log(
                f"moteur '{eng}' a échoué définitivement ({ee.category}"
                + (f" : {detail}" if detail else "")
                + ") → moteur suivant"
            )
            continue

        if result and result.strip():
            if errors:
                _log(f"moteur '{eng}' a répondu après repli")
            return result
        errors.append(_EngineError(eng, "empty", None))
        _log(f"moteur '{eng}' a renvoyé une réponse vide → moteur suivant")

    return _format_failure(errors)


def active_engine() -> str:
    order = _engine_order()
    return order[0] if order else "none"
