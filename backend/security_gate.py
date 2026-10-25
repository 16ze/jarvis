"""
security_gate.py — Point de passage unique des actions sensibles de Jarvis.

Pensé pour le mode AUTONOME de Jarvis (pas de confirmation à cliquer) :
  - MODE "audit" (défaut, JARVIS_GATE_MODE=audit) : Jarvis agit librement ; le
    gate JOURNALISE chaque action sensible dans un journal append-only chaîné
    (HMAC) et ne BLOQUE que le catastrophique (délégué à safe_exec). Un kill
    switch coupe toutes les actions sensibles d'un coup.
  - MODE "approve" (JARVIS_GATE_MODE=approve) : renvoie CONFIRM pour que
    l'appelant transforme en demande d'autorisation (non câblé par défaut).

Le journal est infalsifiable : chaque entrée chaîne le hash de la précédente.
`verify_chain()` détecte toute altération ou suppression.
"""

import hashlib
import hmac
import json
import os
import threading
from datetime import datetime
from pathlib import Path

GATE_DIR = Path(os.getenv("JARVIS_GATE_DIR", str(Path(__file__).parent / "memory" / "gate")))
AUDIT_PATH = GATE_DIR / "audit.log.jsonl"
KILL_PATH = GATE_DIR / "kill_switch.on"
_AUDIT_KEY = os.getenv("JARVIS_AUDIT_KEY", "jarvis-local-audit").encode("utf-8")
MODE = os.getenv("JARVIS_GATE_MODE", "audit").lower()

ALLOW, CONFIRM, BLOCK = "allow", "confirm", "block"
_lock = threading.Lock()


def _ensure() -> None:
    GATE_DIR.mkdir(parents=True, exist_ok=True)


# ── Kill switch ──────────────────────────────────────────────────────────────

def kill_switch_on() -> bool:
    return KILL_PATH.exists()


def set_kill_switch(on: bool) -> None:
    _ensure()
    if on:
        KILL_PATH.touch()
    elif KILL_PATH.exists():
        KILL_PATH.unlink()


# ── Journal chaîné (HMAC append-only) ────────────────────────────────────────

def _last_hash() -> str:
    try:
        last = None
        with AUDIT_PATH.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    last = line
        if last:
            return json.loads(last).get("hash", "GENESIS")
    except Exception:
        pass
    return "GENESIS"


def audit(action: str, detail: str = "", decision: str = ALLOW, source: str = "ai") -> None:
    """Ajoute une entrée au journal chaîné. Best-effort, jamais bloquant."""
    try:
        _ensure()
        with _lock:
            prev = _last_hash()
            entry = {
                "ts": datetime.now().isoformat(),
                "action": action,
                "detail": str(detail)[:300],
                "decision": decision,
                "source": source,
                "prev": prev,
            }
            payload = json.dumps(entry, ensure_ascii=False, sort_keys=True)
            entry["hash"] = hmac.new(
                _AUDIT_KEY, (prev + payload).encode("utf-8"), hashlib.sha256
            ).hexdigest()
            with AUDIT_PATH.open("a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception as e:
        print(f"[GATE] audit error: {e}")


# ── Décisions ────────────────────────────────────────────────────────────────

def check_shell(command: str, source: str = "ai"):
    """Décision pour une commande shell. Kill switch → BLOCK. Catastrophe
    (safe_exec HARD_BLOCK) → BLOCK. Sinon ALLOW (mode autonome) + journalisé.
    Retourne (decision, reason)."""
    if kill_switch_on():
        audit("shell", command, BLOCK, source)
        return BLOCK, "kill switch actif"
    try:
        import safe_exec
        d = safe_exec.classify(command, source=source)
        if d.action == safe_exec.BLOCK:
            audit("shell", command, BLOCK, source)
            return BLOCK, d.reason
    except Exception as e:
        print(f"[GATE] safe_exec indisponible: {e}")
    audit("shell", command, ALLOW, source)
    return ALLOW, "autorisé (autonome)"


def guard_action(action: str, detail: str = "", source: str = "ai"):
    """Garde générique d'une action état-modifiante (envoi email, suppression,
    clic de validation…). Kill switch → BLOCK ; sinon journalisé + ALLOW.
    En MODE=approve, renvoie CONFIRM pour laisser l'appelant demander l'accord."""
    if kill_switch_on():
        audit(action, detail, BLOCK, source)
        return BLOCK, "kill switch actif"
    if MODE == "approve":
        audit(action, detail, CONFIRM, source)
        return CONFIRM, "confirmation requise (mode approve)"
    audit(action, detail, ALLOW, source)
    return ALLOW, "autorisé (autonome)"


def verify_chain() -> dict:
    """Vérifie l'intégrité du journal chaîné. Retourne {ok, entries}."""
    _ensure()
    ok, n, prev = True, 0, "GENESIS"
    try:
        with AUDIT_PATH.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                e = json.loads(line)
                stored = e.pop("hash", "")
                payload = json.dumps(e, ensure_ascii=False, sort_keys=True)
                calc = hmac.new(
                    _AUDIT_KEY, (e.get("prev", "") + payload).encode("utf-8"), hashlib.sha256
                ).hexdigest()
                if calc != stored or e.get("prev") != prev:
                    ok = False
                prev = stored
                n += 1
    except FileNotFoundError:
        pass
    except Exception as e:
        print(f"[GATE] verify_chain error: {e}")
        ok = False
    return {"ok": ok, "entries": n}
