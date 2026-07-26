"""Tests du pont vers le navigateur intégré (backend/browser_bridge.py).

Vérifie le protocole de commande, la corrélation des réponses, et surtout le
garde-fou : le modèle ne peut pas faire exécuter de JavaScript arbitraire.
"""

import asyncio
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

import browser_bridge as bb  # noqa: E402


def _bridge_repondant(reponse: dict):
    """Pont dont l'interface répond immédiatement `reponse`."""
    pont = bb.BrowserBridge()
    envoyes = []

    async def emit(event, payload):
        envoyes.append((event, payload))
        await asyncio.sleep(0)
        pont.resolve({"id": payload["id"], **reponse})

    pont.set_emitter(emit)
    return pont, envoyes


# ─── Sûreté ───────────────────────────────────────────────────────────────────

def test_only_closed_actions_are_allowed():
    assert bb.ACTIONS == {"navigate", "read", "click", "fill", "submit", "back", "url"}


@pytest.mark.parametrize("action", ["execute_js", "eval", "run", "__import__"])
def test_arbitrary_actions_are_refused_before_sending(action):
    """Aucune commande hors liste ne doit même partir vers l'interface."""
    pont, envoyes = _bridge_repondant({"ok": True})
    res = asyncio.run(pont.send(action, code="alert(1)"))
    assert res["ok"] is False
    assert "inconnue" in res["error"]
    assert envoyes == []


def test_no_emitter_means_clear_error():
    res = asyncio.run(bb.BrowserBridge().send("read"))
    assert res["ok"] is False
    assert "non connect" in res["error"]


# ─── Protocole ────────────────────────────────────────────────────────────────

def test_round_trip_returns_data():
    pont, _ = _bridge_repondant({"ok": True, "data": "Bonjour"})
    res = asyncio.run(pont.send("read"))
    assert res == {"ok": True, "data": "Bonjour", "error": ""}


def test_command_carries_action_and_params():
    pont, envoyes = _bridge_repondant({"ok": True})
    asyncio.run(pont.send("fill", field="email", value="a@b.c"))
    event, payload = envoyes[0]
    assert event == "browser_command"
    assert payload["action"] == "fill"
    assert payload["field"] == "email" and payload["value"] == "a@b.c"
    assert payload["id"]


def test_timeout_when_interface_stays_silent():
    pont = bb.BrowserBridge()

    async def muet(event, payload):
        return None

    pont.set_emitter(muet)
    res = asyncio.run(pont.send("read", timeout=0.3))
    assert res["ok"] is False
    assert "temps" in res["error"]


def test_failure_from_interface_is_propagated():
    pont, _ = _bridge_repondant({"ok": False, "error": "élément introuvable"})
    res = asyncio.run(pont.send("click", text="Connexion"))
    assert res["ok"] is False and "introuvable" in res["error"]


def test_unknown_response_id_is_ignored():
    """Une réponse orpheline ne doit rien casser."""
    pont = bb.BrowserBridge()
    pont.resolve({"id": "inexistant", "ok": True})
    pont.resolve({})
    pont.resolve(None)


def test_concurrent_commands_are_correlated():
    """Deux commandes simultanées ne doivent pas mélanger leurs réponses."""
    pont = bb.BrowserBridge()
    vus = {}

    async def emit(event, payload):
        vus[payload["action"]] = payload["id"]
        await asyncio.sleep(0.05 if payload["action"] == "read" else 0.01)
        pont.resolve({"id": payload["id"], "ok": True, "data": payload["action"]})

    pont.set_emitter(emit)

    async def go():
        return await asyncio.gather(pont.send("read"), pont.send("url"))

    r_read, r_url = asyncio.run(go())
    assert r_read["data"] == "read"
    assert r_url["data"] == "url"
    assert vus["read"] != vus["url"]


# ─── Façade ───────────────────────────────────────────────────────────────────

def test_run_reports_when_interface_absent(monkeypatch):
    monkeypatch.setattr(bb, "_BRIDGE", bb.BrowserBridge())
    out = asyncio.run(bb.run("read"))
    assert "interface d'Ada" in out


def test_run_formats_read_result(monkeypatch):
    pont, _ = _bridge_repondant({"ok": True, "data": "Contenu de la page"})
    monkeypatch.setattr(bb, "_BRIDGE", pont)
    assert asyncio.run(bb.run("read")) == "Contenu de la page"


def test_run_formats_failure(monkeypatch):
    pont, _ = _bridge_repondant({"ok": False, "error": "page absente"})
    monkeypatch.setattr(bb, "_BRIDGE", pont)
    out = asyncio.run(bb.run("click", text="X"))
    assert out.startswith("Échec (click)") and "page absente" in out
