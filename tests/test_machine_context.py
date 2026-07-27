"""Tests de la conscience du contexte machine (backend/machine_context.py)."""

import asyncio
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

import machine_context as mc  # noqa: E402


def _ctx(**kw) -> mc.MachineContext:
    base = dict(app_active="Safari", document="Le Monde", apps_ouvertes=["Safari", "Notes"],
                batterie="batterie 80%", disque="disque 40% utilisé", reseau="", heure="14:00")
    base.update(kw)
    return mc.MachineContext(**base)


# ─── Extraction du document ───────────────────────────────────────────────────

def test_window_title_equal_to_app_is_not_a_document():
    """« Tu es dans Claude, sur Claude » n'apprend rien."""
    assert mc._document_depuis_titre("Claude", "Claude") == ""


def test_browser_title_is_kept_as_is():
    assert mc._document_depuis_titre("Safari", "Le Monde — Actualités") == "Le Monde — Actualités"


def test_editor_suffix_is_stripped():
    assert mc._document_depuis_titre("TextEdit", "rapport.txt — Documents") == "rapport.txt"
    assert mc._document_depuis_titre("Pages", "note (modifié)") == "note"


def test_empty_title_is_safe():
    assert mc._document_depuis_titre("Notes", "") == ""


# ─── Restitution ──────────────────────────────────────────────────────────────

def test_prompt_block_mentions_app_and_document():
    bloc = _ctx().to_prompt()
    assert "Safari" in bloc and "Le Monde" in bloc
    assert "CE QUE TU VOIS DE SA MACHINE" in bloc


def test_prompt_block_is_empty_without_signal():
    vide = mc.MachineContext()
    assert vide.to_prompt() == ""


def test_speech_is_natural():
    parle = _ctx().to_speech()
    assert parle.startswith("Tu es dans Safari")
    assert parle.endswith(".")


def test_speech_without_signal_is_honest():
    assert "n'arrive pas" in mc.MachineContext().to_speech()


def test_low_battery_is_flagged(monkeypatch):
    monkeypatch.setattr(mc, "_run", lambda *a, **k: type(
        "R", (), {"stdout": "Now drawing from 'Battery Power'\n -InternalBattery-0 15%; discharging; 1:02 remaining",
                  "returncode": 0})())
    assert "faible" in mc._batterie()


# ─── Routage ──────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("phrase", [
    "qu'est-ce que je fais ?",
    "sur quoi je travaille",
    "quelles applications sont ouvertes ?",
    "combien de batterie ?",
])
def test_context_questions_are_routed(phrase, monkeypatch):
    async def faux(force=False):
        return _ctx()
    monkeypatch.setattr(mc, "get_context", faux)
    assert asyncio.run(mc.route(phrase)) is not None


@pytest.mark.parametrize("phrase", [
    "ouvre TextEdit", "appelle Ivan", "cherche le fichier rapport", "",
])
def test_other_phrases_are_left_alone(phrase):
    assert asyncio.run(mc.route(phrase)) is None


def test_context_read_never_raises(monkeypatch):
    def explose(*a, **k):
        raise RuntimeError("système indisponible")
    monkeypatch.setattr(mc, "_lire_sync", explose)
    mc._CACHE = None
    assert asyncio.run(mc.get_context(force=True)) is not None
