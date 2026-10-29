"""
monitoring.py — Monitoring léger et centralisé des erreurs d'Ada.

Objectif : qu'AUCUNE erreur n'arrive « en silence ». Dépendance ZÉRO
(logging standard uniquement), aucun framework lourd — conforme à la règle
asyncio pur du projet. Tous les helpers sont « safe » : ils ne lèvent jamais
eux-mêmes (sauf le re-raise volontaire de @guard).

Utilisation :
    from monitoring import log_exception, guard, get_error_stats

    try:
        ...
    except Exception as exc:
        log_exception("telegram.send", exc)   # journalise + compteur
        raise

    @guard("printer.status")                  # sync OU async
    async def get_status(): ...

    get_error_stats()                          # dict interrogeable (/health/errors)

Masquage des secrets : log_exception masque automatiquement toute valeur de
variable d'environnement ressemblant à une clé/token/secret avant de journaliser
ou de stocker le message — les credentials n'apparaissent jamais en clair.
"""

import asyncio
import functools
import logging
import os
import threading
from collections import Counter
from datetime import datetime, timezone

# ── Logger dédié, non intrusif ───────────────────────────────────────────────
_LOG = logging.getLogger("ada.monitoring")
if not _LOG.handlers:
    _handler = logging.StreamHandler()
    _handler.setFormatter(
        logging.Formatter("[MONITOR] %(asctime)s %(levelname)s %(message)s")
    )
    _LOG.addHandler(_handler)
    _LOG.setLevel(logging.INFO)
    _LOG.propagate = False

# ── Compteur d'erreurs en mémoire, thread-safe ───────────────────────────────
_LOCK = threading.Lock()
_ERROR_COUNTS: Counter = Counter()
_TOTAL = 0
_LAST_ERRORS: list = []       # ring buffer des N dernières erreurs
_MAX_LAST = 50

_SECRET_SUFFIXES = ("_KEY", "_TOKEN", "_SECRET", "_PASSWORD", "_PASS")


def _mask_secrets(text) -> str:
    """Masque toute valeur de secret connue (clés/tokens) présente dans `text`.

    On parcourt l'environnement et on remplace la valeur de toute variable dont
    le nom ressemble à un secret. Ne lève jamais."""
    if not text:
        return ""
    try:
        s = str(text)
        for name, value in os.environ.items():
            if not value or len(value) < 6:
                continue
            up = name.upper()
            if up.endswith(_SECRET_SUFFIXES) or "API_KEY" in up or "APIKEY" in up:
                s = s.replace(value, "***")
        return s
    except Exception:
        return str(text)


def log_exception(context: str, exc: BaseException, *, level: int = logging.ERROR) -> None:
    """Journalise une exception ET incrémente le compteur. Ne lève jamais.

    `context` : étiquette courte de l'endroit fautif, ex. "telegram.send".
    Le message est nettoyé des secrets et tronqué avant stockage/log."""
    global _TOTAL
    try:
        category = type(exc).__name__
        msg = _mask_secrets(str(exc))[:300]
        with _LOCK:
            _TOTAL += 1
            _ERROR_COUNTS[f"{context}:{category}"] += 1
            _LAST_ERRORS.append({
                "ts": datetime.now(timezone.utc).isoformat(),
                "context": context,
                "type": category,
                "message": msg,
            })
            if len(_LAST_ERRORS) > _MAX_LAST:
                del _LAST_ERRORS[:-_MAX_LAST]
        _LOG.log(level, "%s → %s: %s", context, category, msg)
    except Exception:
        # Le monitoring ne doit JAMAIS casser l'appelant.
        pass


def get_error_stats() -> dict:
    """Instantané interrogeable des erreurs observées depuis le démarrage.

    {total, by_context: {"<ctx>:<Type>": n}, recent: [ {ts, context, type, message} ]}"""
    with _LOCK:
        return {
            "total": _TOTAL,
            "by_context": dict(_ERROR_COUNTS),
            "recent": list(_LAST_ERRORS),
        }


def reset_error_stats() -> None:
    """Réinitialise les compteurs (utile en test, ou pour un reset manuel)."""
    global _TOTAL
    with _LOCK:
        _TOTAL = 0
        _ERROR_COUNTS.clear()
        _LAST_ERRORS.clear()


def guard(context: str, *, reraise: bool = True, default=None):
    """Décorateur sync + async : logge toute exception puis la ré-émet proprement
    (ou renvoie `default` si reraise=False). Aucune erreur ne passe en silence.

    Exemple :
        @guard("printer.status", reraise=False, default="indisponible")
        def get_status(): ...
    """
    def decorator(func):
        if asyncio.iscoroutinefunction(func):
            @functools.wraps(func)
            async def awrapper(*args, **kwargs):
                try:
                    return await func(*args, **kwargs)
                except Exception as exc:
                    log_exception(context, exc)
                    if reraise:
                        raise
                    return default
            return awrapper

        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except Exception as exc:
                log_exception(context, exc)
                if reraise:
                    raise
                return default
        return wrapper

    return decorator
