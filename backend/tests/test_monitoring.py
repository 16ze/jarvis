"""Tests du module de monitoring léger (monitoring.py).

Objectif : vérifier qu'aucune erreur ne passe en silence, que le compteur est
interrogeable, que @guard marche en sync ET async, et que les secrets sont
masqués. Aucune dépendance réseau / clé API.
"""
import asyncio
import logging

import pytest

import monitoring
from monitoring import guard, get_error_stats, log_exception, reset_error_stats


@pytest.fixture(autouse=True)
def _clean_stats():
    """Repart d'un compteur vierge avant et après chaque test."""
    reset_error_stats()
    yield
    reset_error_stats()


def test_log_exception_increments_and_records():
    stats_before = get_error_stats()
    assert stats_before["total"] == 0

    log_exception("telegram.send", ValueError("boom"))

    stats = get_error_stats()
    assert stats["total"] == 1
    assert stats["by_context"]["telegram.send:ValueError"] == 1
    assert stats["recent"][-1]["context"] == "telegram.send"
    assert stats["recent"][-1]["type"] == "ValueError"
    assert "boom" in stats["recent"][-1]["message"]


def test_log_exception_counts_per_context_and_type():
    log_exception("a.one", ValueError("x"))
    log_exception("a.one", ValueError("y"))
    log_exception("b.two", KeyError("z"))

    stats = get_error_stats()
    assert stats["total"] == 3
    assert stats["by_context"]["a.one:ValueError"] == 2
    assert stats["by_context"]["b.two:KeyError"] == 1


def test_log_exception_never_raises():
    class Nasty(Exception):
        def __str__(self):
            raise RuntimeError("str() explosed")

    # Ne doit rien lever même si str(exc) explose.
    log_exception("weird.ctx", Nasty())
    # Compteur toujours cohérent / interrogeable.
    assert isinstance(get_error_stats()["total"], int)


def test_ring_buffer_is_bounded():
    for i in range(monitoring._MAX_LAST + 25):
        log_exception("loop.ctx", ValueError(str(i)))
    stats = get_error_stats()
    assert stats["total"] == monitoring._MAX_LAST + 25
    # Le ring buffer "recent" est borné.
    assert len(stats["recent"]) == monitoring._MAX_LAST


def test_secret_is_masked_in_recorded_message(monkeypatch):
    monkeypatch.setenv("SOME_API_KEY", "sk-supersecret-abcdef")
    log_exception("auth.ctx", RuntimeError("echec avec sk-supersecret-abcdef dans l'URL"))
    stats = get_error_stats()
    recorded = stats["recent"][-1]["message"]
    assert "sk-supersecret-abcdef" not in recorded
    assert "***" in recorded


def test_guard_sync_logs_and_reraises():
    @guard("sync.job")
    def boom():
        raise ValueError("sync fail")

    with pytest.raises(ValueError):
        boom()

    stats = get_error_stats()
    assert stats["by_context"]["sync.job:ValueError"] == 1


def test_guard_sync_success_passthrough():
    @guard("sync.ok")
    def add(a, b):
        return a + b

    assert add(2, 3) == 5
    assert get_error_stats()["total"] == 0


def test_guard_sync_no_reraise_returns_default():
    @guard("sync.soft", reraise=False, default="fallback")
    def boom():
        raise RuntimeError("nope")

    assert boom() == "fallback"
    assert get_error_stats()["total"] == 1


@pytest.mark.asyncio
async def test_guard_async_logs_and_reraises():
    @guard("async.job")
    async def boom():
        await asyncio.sleep(0)
        raise KeyError("async fail")

    with pytest.raises(KeyError):
        await boom()

    stats = get_error_stats()
    assert stats["by_context"]["async.job:KeyError"] == 1


@pytest.mark.asyncio
async def test_guard_async_success_passthrough():
    @guard("async.ok")
    async def mul(a, b):
        await asyncio.sleep(0)
        return a * b

    assert await mul(4, 5) == 20
    assert get_error_stats()["total"] == 0


@pytest.mark.asyncio
async def test_guard_async_no_reraise_returns_default():
    @guard("async.soft", reraise=False, default=42)
    async def boom():
        await asyncio.sleep(0)
        raise RuntimeError("nope")

    assert await boom() == 42
    assert get_error_stats()["total"] == 1


def test_log_level_is_respected():
    """Vérifie que le niveau passé est bien celui émis par le logger dédié.

    Le logger ada.monitoring a propagate=False : on attache donc un handler
    de capture directement dessus plutôt que de compter sur caplog (root)."""
    records: list[logging.LogRecord] = []

    class _Capture(logging.Handler):
        def emit(self, record):
            records.append(record)

    handler = _Capture()
    monitoring._LOG.addHandler(handler)
    try:
        log_exception("lvl.ctx", ValueError("warn please"), level=logging.WARNING)
    finally:
        monitoring._LOG.removeHandler(handler)

    matching = [r for r in records if "lvl.ctx" in r.getMessage()]
    assert matching, "le message journalisé n'a pas été capturé"
    assert matching[-1].levelno == logging.WARNING
