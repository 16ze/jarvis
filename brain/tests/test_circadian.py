"""Tests du rythme circadien et de la latence expressive."""

from datetime import datetime

import pytest

from brain import circadian
from brain.limbic import CerveauEmotif
from brain.modulators import get_gemini_params

NUIT = datetime(2026, 7, 25, 3, 0)
MATIN = datetime(2026, 7, 25, 8, 0)
APRES_MIDI = datetime(2026, 7, 25, 14, 0)


# ── Rythme circadien ──────────────────────────────────────────────────────────

def test_energy_peaks_in_the_afternoon_and_dips_at_night():
    assert circadian.energy_offset(APRES_MIDI) > circadian.energy_offset(MATIN)
    assert circadian.energy_offset(NUIT) < 0


def test_fatigue_pressure_is_highest_at_night():
    assert circadian.fatigue_offset(NUIT) > circadian.fatigue_offset(APRES_MIDI)


def test_fatigue_is_never_negative():
    for h in range(24):
        assert circadian.fatigue_offset(datetime(2026, 7, 25, h, 0)) >= 0.0


def test_modulation_stays_discreet():
    """Coloration de fond, pas pilotage : l'amplitude reste faible."""
    for h in range(24):
        t = datetime(2026, 7, 25, h, 0)
        assert abs(circadian.energy_offset(t)) <= 0.15
        assert circadian.fatigue_offset(t) <= 0.15


def test_describe_covers_the_day():
    assert circadian.describe(NUIT) == "milieu de nuit"
    assert circadian.describe(APRES_MIDI) == "après-midi"


def test_apply_nudges_the_limbic_within_bounds():
    lim = CerveauEmotif()
    avant = (lim.serotonine, lim.mental_load)
    result = circadian.apply(lim, NUIT)

    assert result["moment"] == "milieu de nuit"
    assert 0.0 <= lim.serotonine <= 1.0
    assert 0.0 <= lim.mental_load <= 1.0
    assert (lim.serotonine, lim.mental_load) != avant  # quelque chose a bougé


def test_apply_disabled_is_a_noop(monkeypatch):
    monkeypatch.setenv("BRAIN_CIRCADIAN_ENABLED", "false")
    lim = CerveauEmotif()
    avant = (lim.serotonine, lim.mental_load)
    assert circadian.apply(lim, NUIT) == {}
    assert (lim.serotonine, lim.mental_load) == avant


def test_apply_with_none_is_safe():
    assert circadian.apply(None) == {}


# ── Latence expressive ────────────────────────────────────────────────────────

def _budget(hormones) -> int:
    return get_gemini_params("Neutre", hormones)["thinking_budget"]


def test_tired_ada_takes_longer_to_answer():
    repose = _budget({"mental_load": 0.15, "cortisol": 0.10, "dopamine": 0.30})
    fatiguee = _budget({"mental_load": 0.85, "cortisol": 0.10, "dopamine": 0.30})
    assert fatiguee > repose


def test_tense_ada_weighs_her_words():
    calme = _budget({"mental_load": 0.30, "cortisol": 0.15, "dopamine": 0.30})
    tendue = _budget({"mental_load": 0.30, "cortisol": 0.85, "dopamine": 0.30})
    assert tendue > calme


def test_energised_ada_bounces_back_fast():
    """Une forte dopamine raccourcit la réflexion, sans jamais passer sous zéro."""
    base = get_gemini_params("Mélancolie", {"mental_load": 0.2, "cortisol": 0.1,
                                            "dopamine": 0.2})["thinking_budget"]
    vive = get_gemini_params("Mélancolie", {"mental_load": 0.2, "cortisol": 0.1,
                                            "dopamine": 0.95})["thinking_budget"]
    assert vive < base
    assert vive >= 0


def test_budget_is_bounded():
    extreme = _budget({"mental_load": 1.0, "cortisol": 1.0, "dopamine": 0.0})
    assert 0 <= extreme <= 900


def test_without_hormones_behaviour_is_unchanged():
    """Rétro-compatibilité : sans état, le profil d'humeur seul s'applique."""
    assert get_gemini_params("Mélancolie")["thinking_budget"] == 400


def test_malformed_hormones_are_survivable():
    assert _budget({"mental_load": "beaucoup", "cortisol": None}) >= 0
