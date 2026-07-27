"""Tests de la dérive de tempérament (brain/limbic.py).

Un caractère se forme sur des semaines. Ces tests vérifient que la dérive est
réelle, lente, et bornée — Ada évolue sans devenir méconnaissable.
"""

import pytest

from brain.limbic import BASELINE, CerveauEmotif


def test_temperament_starts_at_baseline():
    lim = CerveauEmotif()
    for hormone, valeur in BASELINE.items():
        assert lim.temperament[hormone] == pytest.approx(valeur)


def test_temperament_drifts_toward_lived_experience():
    lim = CerveauEmotif()
    depart = lim.temperament["self_confidence"]
    lim.self_confidence = 0.95
    for _ in range(60 * 24 * 7):        # une semaine à un appel par minute
        lim.derive_temperament()
    assert lim.temperament["self_confidence"] > depart


def test_drift_is_slow():
    """Une soirée ne doit pas changer un caractère."""
    lim = CerveauEmotif()
    depart = lim.temperament["self_confidence"]
    lim.self_confidence = 0.95
    for _ in range(60 * 4):             # quatre heures
        lim.derive_temperament()
    assert lim.temperament["self_confidence"] - depart < 0.10


def test_drift_is_bounded():
    """Ada peut changer, jamais devenir quelqu'un d'autre."""
    lim = CerveauEmotif()
    lim.self_confidence = 1.0
    for _ in range(60 * 24 * 365):      # une année entière
        lim.derive_temperament()
    ecart = lim.temperament["self_confidence"] - BASELINE["self_confidence"]
    assert ecart <= 0.15 + 1e-6


def test_drift_works_in_both_directions():
    lim = CerveauEmotif()
    lim.self_confidence = 0.0
    for _ in range(60 * 24 * 30):
        lim.derive_temperament()
    assert lim.temperament["self_confidence"] < BASELINE["self_confidence"]


def test_decay_targets_temperament_not_constant():
    """La décroissance ramène vers le tempérament acquis, pas vers la constante."""
    lim = CerveauEmotif()
    lim.temperament["self_confidence"] = 0.75
    lim.self_confidence = 0.75
    for _ in range(200):
        lim._decroissance()
    assert lim.self_confidence == pytest.approx(0.75, abs=0.02)


def test_values_stay_valid():
    lim = CerveauEmotif()
    for hormone in BASELINE:
        setattr(lim, hormone, 1.0)
    for _ in range(1000):
        lim.derive_temperament()
    for valeur in lim.temperament.values():
        assert 0.0 <= valeur <= 1.0
