"""Tests de llm_router.think — robustesse du cerveau hybride.

Aucune vraie clé API ni réseau : on monkeypatch l'ordre des moteurs et les
implémentations synchrones de chaque moteur (_think_claude_sync, etc.).
Le backoff est ramené à 0 pour que les tests de retry soient instantanés.
"""
import pytest

import llm_router


class _HTTPError(Exception):
    """Exception factice portant un status_code, comme les SDK HTTP."""

    def __init__(self, message, status_code=None):
        super().__init__(message)
        self.status_code = status_code


@pytest.fixture(autouse=True)
def _fast_backoff(monkeypatch):
    """Supprime toute attente réelle entre les tentatives."""
    monkeypatch.setattr(llm_router, "LLM_BACKOFF_BASE", 0.0)
    monkeypatch.setattr(llm_router, "LLM_MAX_RETRIES", 3)


def _force_order(monkeypatch, engines):
    monkeypatch.setattr(llm_router, "_engine_order", lambda: list(engines))


# ── Cas nominal ──────────────────────────────────────────────────────────────

async def test_think_returns_str_on_success(monkeypatch):
    _force_order(monkeypatch, ["claude"])
    monkeypatch.setattr(
        llm_router, "_think_claude_sync",
        lambda system, prompt, max_tokens, temperature: "réponse claire",
    )
    out = await llm_router.think("sys", "prompt")
    assert isinstance(out, str)
    assert out == "réponse claire"


# ── Retries sur erreur transitoire ─────────────────────────────────────────────

async def test_retry_on_transient_then_success(monkeypatch):
    _force_order(monkeypatch, ["claude"])
    calls = {"n": 0}

    def flaky(system, prompt, max_tokens, temperature):
        calls["n"] += 1
        if calls["n"] == 1:
            raise _HTTPError("503 Service Unavailable", status_code=503)
        return "ok après retry"

    monkeypatch.setattr(llm_router, "_think_claude_sync", flaky)
    out = await llm_router.think("sys", "prompt")
    assert out == "ok après retry"
    assert calls["n"] == 2  # a retenté une fois puis réussi


# ── Pas de retry sur auth / quota ──────────────────────────────────────────────

async def test_no_retry_on_auth_error(monkeypatch):
    _force_order(monkeypatch, ["claude"])
    calls = {"n": 0}

    def auth_fail(system, prompt, max_tokens, temperature):
        calls["n"] += 1
        raise _HTTPError("invalid api key", status_code=401)

    monkeypatch.setattr(llm_router, "_think_claude_sync", auth_fail)
    out = await llm_router.think("sys", "prompt")
    assert calls["n"] == 1  # aucune reprise sur une erreur d'auth
    assert isinstance(out, str)
    assert "clé API" in out  # message FR catégorie "auth"


async def test_no_retry_on_quota_error(monkeypatch):
    _force_order(monkeypatch, ["claude"])
    calls = {"n": 0}

    def quota_fail(system, prompt, max_tokens, temperature):
        calls["n"] += 1
        raise RuntimeError("Your credit balance is too low")

    monkeypatch.setattr(llm_router, "_think_claude_sync", quota_fail)
    out = await llm_router.think("sys", "prompt")
    assert calls["n"] == 1
    assert "quota ou crédits" in out


# ── Échec total : message FR propre, jamais d'exception ────────────────────────

async def test_total_failure_returns_french_message(monkeypatch):
    _force_order(monkeypatch, ["claude", "gemini"])

    def claude_fail(system, prompt, max_tokens, temperature):
        raise _HTTPError("500 internal server error", status_code=500)

    def gemini_fail(system, prompt, temperature):
        raise _HTTPError("503 service unavailable", status_code=503)

    monkeypatch.setattr(llm_router, "_think_claude_sync", claude_fail)
    monkeypatch.setattr(llm_router, "_think_gemini_sync", gemini_fail)

    out = await llm_router.think("sys", "prompt")
    assert isinstance(out, str)
    assert out.startswith("⚠️")
    assert "claude" in out and "gemini" in out


async def test_fallback_to_next_engine(monkeypatch):
    _force_order(monkeypatch, ["claude", "gemini"])

    def claude_fail(system, prompt, max_tokens, temperature):
        raise _HTTPError("401 unauthorized", status_code=401)

    monkeypatch.setattr(llm_router, "_think_claude_sync", claude_fail)
    monkeypatch.setattr(
        llm_router, "_think_gemini_sync",
        lambda system, prompt, temperature: "sauvé par gemini",
    )
    out = await llm_router.think("sys", "prompt")
    assert out == "sauvé par gemini"


async def test_empty_response_falls_through(monkeypatch):
    _force_order(monkeypatch, ["claude", "gemini"])
    monkeypatch.setattr(
        llm_router, "_think_claude_sync",
        lambda system, prompt, max_tokens, temperature: "   ",
    )
    monkeypatch.setattr(
        llm_router, "_think_gemini_sync",
        lambda system, prompt, temperature: "contenu gemini",
    )
    out = await llm_router.think("sys", "prompt")
    assert out == "contenu gemini"


# ── Masquage des clés dans les messages / logs ─────────────────────────────────

def test_sanitize_masks_api_keys(monkeypatch):
    monkeypatch.setattr(llm_router, "ANTHROPIC_API_KEY", "sk-ant-SECRET123")
    monkeypatch.setattr(llm_router, "GEMINI_API_KEY", "gm-SECRET456")
    cleaned = llm_router._sanitize("erreur avec sk-ant-SECRET123 et gm-SECRET456 ici")
    assert "sk-ant-SECRET123" not in cleaned
    assert "gm-SECRET456" not in cleaned
    assert "***" in cleaned


async def test_failure_message_does_not_leak_key(monkeypatch):
    monkeypatch.setattr(llm_router, "ANTHROPIC_API_KEY", "sk-ant-LEAK789")
    _force_order(monkeypatch, ["claude"])

    def leaky(system, prompt, max_tokens, temperature):
        raise _HTTPError("invalid api key sk-ant-LEAK789", status_code=401)

    monkeypatch.setattr(llm_router, "_think_claude_sync", leaky)
    out = await llm_router.think("sys", "prompt")
    assert "sk-ant-LEAK789" not in out


# ── Classification d'erreurs (unitaire, synchrone) ─────────────────────────────

@pytest.mark.parametrize("exc, expected", [
    (_HTTPError("boom", status_code=401), "auth"),
    (_HTTPError("boom", status_code=429), "rate_limit"),
    (_HTTPError("boom", status_code=500), "server"),
    (_HTTPError("boom", status_code=400), "bad_request"),
    (RuntimeError("Your credit balance is too low"), "quota"),
    (RuntimeError("model not found"), "model_unavailable"),
    (TimeoutError("timed out"), "timeout"),
    (ConnectionError("connection reset"), "connection"),
])
def test_classify_categories(exc, expected):
    assert llm_router._classify(exc) == expected


def test_retryable_set_excludes_auth_and_quota():
    assert "auth" not in llm_router._RETRYABLE
    assert "quota" not in llm_router._RETRYABLE
    assert "server" in llm_router._RETRYABLE
    assert "rate_limit" in llm_router._RETRYABLE
