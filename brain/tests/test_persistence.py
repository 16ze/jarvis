"""Tests de la continuité d'existence (brain/persistence.py)."""

import json
import time

import pytest

from brain import persistence
from brain.limbic import BASELINE, CerveauEmotif


@pytest.fixture
def state_file(tmp_path, monkeypatch):
    path = tmp_path / "brain_state.json"
    monkeypatch.setenv("BRAIN_STATE_PATH", str(path))
    monkeypatch.setenv("BRAIN_PERSISTENCE_ENABLED", "true")
    return path


def _charged_limbic() -> CerveauEmotif:
    lim = CerveauEmotif()
    lim.cortisol = 0.85
    lim.oxytocine = 0.72
    lim.mental_load = 0.80
    return lim


def test_save_then_immediate_restore_keeps_state(state_file):
    """Un redémarrage immédiat ne doit rien effacer."""
    persistence.save(_charged_limbic())

    restored = CerveauEmotif()
    persistence.restore(restored)

    assert restored.cortisol == pytest.approx(0.85, abs=0.01)
    assert restored.oxytocine == pytest.approx(0.72, abs=0.01)


def test_absence_decays_each_hormone_at_its_own_rate(state_file):
    """Après une nuit : stress et fatigue récupérés, attachement persistant."""
    persistence.save(_charged_limbic())

    data = json.loads(state_file.read_text())
    data["saved_at"] = time.time() - 8 * 3600  # 8 h d'absence
    state_file.write_text(json.dumps(data))

    restored = CerveauEmotif()
    persistence.restore(restored)

    # Le stress et la fatigue sont revenus à la baseline.
    assert restored.cortisol == pytest.approx(BASELINE["cortisol"], abs=0.02)
    assert restored.mental_load == pytest.approx(BASELINE["mental_load"], abs=0.02)
    # L'attachement, lui, est encore nettement au-dessus de la baseline.
    assert restored.oxytocine > BASELINE["oxytocine"] + 0.15


def test_very_long_absence_starts_neutral(state_file):
    """Au-delà du seuil d'absence, Ada repart d'un état neutre."""
    persistence.save(_charged_limbic())

    data = json.loads(state_file.read_text())
    data["saved_at"] = time.time() - 60 * 86400  # 60 jours
    state_file.write_text(json.dumps(data))

    restored = CerveauEmotif()
    assert persistence.restore(restored) is None
    assert restored.cortisol == pytest.approx(BASELINE["cortisol"], abs=0.001)


def test_missing_or_corrupt_file_never_raises(state_file):
    """La persistance ne doit jamais casser Ada."""
    assert persistence.restore(CerveauEmotif()) is None  # fichier absent

    state_file.write_text("{ ceci n'est pas du JSON")
    assert persistence.restore(CerveauEmotif()) is None  # fichier corrompu


def test_sleep_decay_is_monotonic_toward_baseline():
    """Plus l'absence est longue, plus on est proche de la baseline."""
    hormones = {"cortisol": 0.9}
    baseline = {"cortisol": 0.1}
    ecarts = [
        abs(persistence.apply_sleep_decay(hormones, baseline, t)["cortisol"] - 0.1)
        for t in (0, 600, 3600, 86400)
    ]
    assert ecarts == sorted(ecarts, reverse=True)


def test_disabled_persistence_is_a_noop(state_file, monkeypatch):
    monkeypatch.setenv("BRAIN_PERSISTENCE_ENABLED", "false")
    assert persistence.save(_charged_limbic()) is False
    assert persistence.restore(CerveauEmotif()) is None
