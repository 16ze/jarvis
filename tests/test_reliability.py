"""Tests du traqueur de fiabilité (backend/reliability.py).

La confiance ne se code pas, mais elle se MESURE. Ces tests garantissent
qu'Ada rend compte de ses résultats sans jamais les embellir.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from reliability import MIN_POUR_TAUX, ReliabilityTracker, _categoriser  # noqa: E402


@pytest.fixture(autouse=True)
def _isolate(tmp_path, monkeypatch):
    monkeypatch.setenv("RELIABILITY_PATH", str(tmp_path / "fiabilite.json"))
    monkeypatch.setenv("RELIABILITY_ENABLED", "true")


def _remplir(t, n_ok, n_ko, tache="ouvre TextEdit", outil="routine_native"):
    for _ in range(n_ok):
        t.record(tache, True, outil)
    for _ in range(n_ko):
        t.record(tache, False, outil)


# ─── Catégorisation ───────────────────────────────────────────────────────────

@pytest.mark.parametrize("tache,outil,attendu", [
    ("connecte-moi au site", "browser_control", "web"),
    ("cherche le fichier X", "mac_files", "fichiers"),
    ("envoie un message à Ivan", "", "communication"),
    ("règle la luminosité", "", "système"),
    ("ouvre TextEdit", "", "applications"),
    ("allume la lumière", "", "domotique"),
    ("explique-moi les threads", "think_deeply", "réflexion"),
])
def test_tasks_are_categorised(tache, outil, attendu):
    assert _categoriser(tache, outil) == attendu


# ─── Mesure ───────────────────────────────────────────────────────────────────

def test_success_rate_is_computed():
    t = ReliabilityTracker()
    _remplir(t, 8, 2)
    s = t.stats()
    assert s["total"] == 10 and s["reussies"] == 8
    assert s["taux"] == pytest.approx(0.8)


def test_per_category_breakdown():
    t = ReliabilityTracker()
    _remplir(t, 5, 0, "ouvre TextEdit")
    _remplir(t, 1, 4, "connecte-moi au site", "browser_control")
    cats = t.stats()["par_categorie"]
    assert cats["applications"]["taux"] == pytest.approx(1.0)
    assert cats["web"]["taux"] == pytest.approx(0.2)


def test_weak_categories_are_identified():
    t = ReliabilityTracker()
    _remplir(t, 10, 0, "ouvre TextEdit")
    _remplir(t, 1, 5, "connecte-moi au site", "browser_control")
    faibles = dict(t.weakest_categories())
    assert "web" in faibles
    assert "applications" not in faibles


def test_recent_failures_are_kept():
    t = ReliabilityTracker()
    t.record("tâche ratée", False, "x", detail="raison précise")
    echecs = t.recent_failures()
    assert echecs and echecs[-1]["detail"] == "raison précise"


# ─── Honnêteté ────────────────────────────────────────────────────────────────

def test_no_claim_without_enough_history():
    """Ada ne prétend rien tant qu'elle n'a pas de quoi être honnête."""
    t = ReliabilityTracker()
    _remplir(t, MIN_POUR_TAUX - 2, 0)
    assert "pas encore assez" in t.to_speech()


def test_speech_states_the_real_numbers():
    t = ReliabilityTracker()
    _remplir(t, 30, 7)
    parle = t.to_speech()
    assert "37" in parle and "30" in parle and "81" in parle


def test_speech_admits_weak_areas():
    t = ReliabilityTracker()
    _remplir(t, 14, 0, "ouvre TextEdit")
    _remplir(t, 2, 6, "connecte-moi au site", "browser_control")
    assert "web" in t.to_speech()


def test_speech_never_inflates():
    """Le pourcentage annoncé doit correspondre exactement au réel."""
    t = ReliabilityTracker()
    _remplir(t, 5, 5)
    assert "50" in t.to_speech()


# ─── Persistance ──────────────────────────────────────────────────────────────

def test_history_survives_restart():
    t = ReliabilityTracker()
    _remplir(t, 12, 3)
    assert t.save() is True

    rechargé = ReliabilityTracker()
    assert rechargé.load() is True
    assert rechargé.stats()["total"] == 15


def test_load_without_file_is_safe():
    assert ReliabilityTracker().load() is False


def test_disabled_by_env(monkeypatch):
    monkeypatch.setenv("RELIABILITY_ENABLED", "false")
    t = ReliabilityTracker()
    assert t.save() is False and t.load() is False
