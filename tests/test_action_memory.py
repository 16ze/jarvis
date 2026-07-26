"""Tests de la mémoire procédurale (backend/action_memory.py).

Ada doit cesser de rejouer une approche qui échoue systématiquement — le cas
observé en réel : trois clics droits sur le Dock pour fermer une app.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from action_memory import MIN_OBSERVATIONS, ActionMemory, signature  # noqa: E402


@pytest.fixture(autouse=True)
def _isolate(tmp_path, monkeypatch):
    monkeypatch.setenv("ACTION_MEMORY_PATH", str(tmp_path / "actions.json"))
    monkeypatch.setenv("ACTION_MEMORY_ENABLED", "true")


# ─── Signature : généraliser d'une tâche à l'autre ────────────────────────────

@pytest.mark.parametrize("task,attendu", [
    ("ferme les Réglages Système", "fermer"),
    ("quitte Safari", "fermer"),
    ("éteins Spotify", "fermer"),
    ("ouvre TextEdit", "ouvrir"),
    ("lance Notes", "ouvrir"),
    ("écris bonjour", "ecrire"),
    ("appelle Ivan", "appeler"),
    ("blabla incompréhensible", "autre"),
])
def test_signature_groups_equivalent_intents(task, attendu):
    assert signature(task) == attendu


# ─── Apprentissage ────────────────────────────────────────────────────────────

def _echouer(m, task, approches, n=MIN_OBSERVATIONS):
    for _ in range(n):
        m.record_plan(task, approches, success=False)


def _reussir(m, task, approches, n=MIN_OBSERVATIONS):
    for _ in range(n):
        m.record_plan(task, approches, success=True)


def test_repeated_failure_marks_an_approach_to_avoid():
    m = ActionMemory()
    _echouer(m, "ferme les Réglages Système", ["right_click"])
    assert "right_click" in m.failing_approaches("ferme Notes")


def test_repeated_success_marks_an_approach_to_prefer():
    m = ActionMemory()
    _reussir(m, "quitte Safari", ["quit_applescript"])
    assert "quit_applescript" in m.working_approaches("ferme Notes")


def test_learning_generalises_across_apps():
    """Appris sur une app, appliqué au même TYPE de tâche sur une autre."""
    m = ActionMemory()
    _echouer(m, "ferme les Réglages Système", ["right_click"])
    assert "right_click" in m.failing_approaches("quitte Mail")


def test_learning_does_not_leak_between_task_types():
    """Un échec sur « fermer » ne doit pas polluer « ouvrir »."""
    m = ActionMemory()
    _echouer(m, "ferme Safari", ["right_click"])
    assert m.failing_approaches("ouvre Safari") == []


def test_single_failure_is_not_enough_to_condemn():
    m = ActionMemory()
    m.record_plan("ferme Safari", ["right_click"], success=False)
    assert m.failing_approaches("ferme Safari") == []


def test_mostly_successful_approach_is_not_condemned():
    m = ActionMemory()
    _reussir(m, "ferme Safari", ["quit_applescript"], n=8)
    m.record_plan("ferme Safari", ["quit_applescript"], success=False)
    assert "quit_applescript" not in m.failing_approaches("ferme Safari")


def test_duplicate_actions_in_a_plan_count_once():
    m = ActionMemory()
    m.record_plan("ferme Safari", ["click", "click", "click"], success=False)
    stats = m.get_debug_state()["fermer"]["click"]
    assert stats["échecs"] == 1


# ─── Conseil injecté dans le prompt ───────────────────────────────────────────

def test_advice_is_empty_without_experience():
    assert ActionMemory().advice("ferme Safari") == ""


def test_advice_lists_what_to_avoid_and_what_works():
    m = ActionMemory()
    _echouer(m, "ferme Safari", ["right_click"])
    _reussir(m, "quitte Mail", ["quit_applescript"])
    conseil = m.advice("ferme Notes")
    assert "ne les reprends pas" in conseil and "right_click" in conseil
    assert "privilégie-les" in conseil and "quit_applescript" in conseil


# ─── Persistance & robustesse ─────────────────────────────────────────────────

def test_experience_survives_restart():
    m = ActionMemory()
    _echouer(m, "ferme Safari", ["right_click"])
    assert m.save() is True

    rechargee = ActionMemory()
    assert rechargee.load() is True
    assert "right_click" in rechargee.failing_approaches("ferme Notes")


def test_load_without_file_is_safe():
    assert ActionMemory().load() is False


def test_disabled_by_env(monkeypatch):
    monkeypatch.setenv("ACTION_MEMORY_ENABLED", "false")
    m = ActionMemory()
    assert m.save() is False
    assert m.load() is False


def test_empty_approach_is_ignored():
    m = ActionMemory()
    m.record("ferme Safari", "", success=False)
    assert m.get_debug_state() == {}
