"""Tests du codage prédictif (brain/expectations.py).

Vérifie qu'Ada apprend des habitudes, prédit, et que la violation d'une attente
produit une émotion DOTÉE D'UN OBJET — c'est le point central.
"""

from datetime import datetime

import pytest

from brain.expectations import ExpectationEngine, PredictionError
from brain.limbic import CerveauEmotif

SOIR = datetime(2026, 7, 1, 22, 0).timestamp()
NUIT = datetime(2026, 7, 1, 4, 0).timestamp()
JOUR = 86400


@pytest.fixture(autouse=True)
def _isolate(tmp_path, monkeypatch):
    monkeypatch.setenv("BRAIN_EXPECTATIONS_PATH", str(tmp_path / "expect.json"))


def _habitue(engine, present, at, jours=20):
    for j in range(jours):
        engine.observe_presence(present, now=at + j * JOUR)


def test_engine_learns_a_habit():
    eng = ExpectationEngine()
    _habitue(eng, True, SOIR)
    attendu, confiance = eng.expected_presence(now=SOIR + 21 * JOUR)
    assert attendu > 0.9
    assert confiance == pytest.approx(1.0)


def test_no_surprise_when_reality_matches_expectation():
    eng = ExpectationEngine()
    _habitue(eng, True, SOIR)
    assert eng.evaluate_presence(True, now=SOIR + 21 * JOUR) is None


def test_no_surprise_without_enough_observations():
    """Sans habitude établie, rien n'est surprenant."""
    eng = ExpectationEngine()
    eng.observe_presence(True, now=SOIR)
    assert eng.evaluate_presence(False, now=SOIR + JOUR) is None


def test_unexpected_absence_is_negative_and_named():
    eng = ExpectationEngine()
    _habitue(eng, True, SOIR)
    err = eng.evaluate_presence(False, now=SOIR + 21 * JOUR)

    assert err is not None
    assert err.kind == "absence_inattendue"
    assert err.valence < 0
    assert err.magnitude > 0.5
    # L'objet de l'émotion : une cause en clair, pas une simple intensité.
    assert "22h" in err.description and "pas là" in err.description


def test_unexpected_presence_is_positive_and_named():
    eng = ExpectationEngine()
    _habitue(eng, False, NUIT)
    err = eng.evaluate_presence(True, now=NUIT + 21 * JOUR)

    assert err is not None
    assert err.kind == "presence_inattendue"
    assert err.valence > 0
    assert "4h" in err.description


def test_surprise_has_a_refractory_period():
    """Ada ne se surprend pas en boucle du même écart."""
    eng = ExpectationEngine()
    _habitue(eng, True, SOIR)
    t = SOIR + 21 * JOUR
    assert eng.evaluate_presence(False, now=t) is not None
    assert eng.evaluate_presence(False, now=t + 60) is None  # trop tôt


def test_observations_are_throttled():
    """À 2 Hz, on n'enregistre pas 2 observations par seconde."""
    eng = ExpectationEngine()
    assert eng.observe_presence(True, now=SOIR) is True
    assert eng.observe_presence(True, now=SOIR + 1) is False


def test_negative_surprise_raises_cortisol_and_sets_cause():
    """L'émotion ressentie porte sa cause dans dernier_stimulus."""
    lim = CerveauEmotif()
    cortisol_avant = lim.cortisol
    err = PredictionError(
        magnitude=0.9, valence=-0.9, kind="absence_inattendue",
        description="Bryan n'est pas là alors qu'il y est toujours (22h, le soir)",
        confidence=1.0,
    )
    lim.ressentir_surprise(err)

    assert lim.cortisol > cortisol_avant
    assert lim.oxytocine > 0.30  # le manque, pas seulement le stress
    assert lim.dernier_stimulus == err.description


def test_positive_surprise_raises_dopamine():
    lim = CerveauEmotif()
    dopamine_avant = lim.dopamine
    lim.ressentir_surprise(
        PredictionError(0.9, 0.9, "presence_inattendue", "Bryan est là à 4h", 1.0)
    )
    assert lim.dopamine > dopamine_avant


def test_feeling_none_is_safe():
    lim = CerveauEmotif()
    lim.ressentir_surprise(None)  # ne doit pas lever


def test_habits_survive_save_and_load():
    """Les habitudes ne s'oublient pas — contrairement aux hormones."""
    eng = ExpectationEngine()
    _habitue(eng, True, SOIR)
    assert eng.save() is True

    rechargé = ExpectationEngine()
    assert rechargé.load() is True
    attendu, confiance = rechargé.expected_presence(now=SOIR + 21 * JOUR)
    assert attendu > 0.9
    assert confiance == pytest.approx(1.0)


def test_load_without_file_is_safe():
    assert ExpectationEngine().load() is False


def test_debug_state_lists_learned_hours():
    eng = ExpectationEngine()
    _habitue(eng, True, SOIR)
    state = eng.get_debug_state()
    assert state["total_heures_connues"] == 1
    assert state["habitudes_apprises"][0]["heure"] == 22
