"""Tests du pont hormones v2 -> ModulationVector."""
import pytest

from brain.v3.neuromodulation import derive
from brain.v3.types import ModulationVector


def _baseline_snapshot() -> dict:
    return {
        "cortisol": 0.10,
        "dopamine": 0.28,
        "oxytocine": 0.30,
        "serotonine": 0.42,
        "self_confidence": 0.60,
        "mental_load": 0.15,
    }


def test_baseline_returns_near_neutral():
    m = derive(_baseline_snapshot())
    assert 0.95 <= m.threshold_gain <= 1.10
    assert 0.95 <= m.decay_gain <= 1.05


def test_high_cortisol_lowers_threshold_gain():
    snap = _baseline_snapshot()
    snap["cortisol"] = 0.80
    m = derive(snap)
    assert m.threshold_gain < 0.9


def test_high_fatigue_increases_decay():
    snap = _baseline_snapshot()
    snap["mental_load"] = 0.85
    m = derive(snap)
    assert m.decay_gain > 1.1


def test_high_dopamine_increases_budget_refill():
    snap = _baseline_snapshot()
    snap["dopamine"] = 0.90
    m = derive(snap)
    assert m.budget_refill > 0.0005


def test_threshold_gain_bounded():
    snap = _baseline_snapshot()
    snap["cortisol"] = 5.0
    m = derive(snap)
    assert 0.6 <= m.threshold_gain <= 1.4


def test_missing_keys_safe():
    m = derive({})
    assert isinstance(m, ModulationVector)
    assert 0.6 <= m.threshold_gain <= 1.4


def test_neutral_factory():
    m = ModulationVector.neutral()
    assert m.threshold_gain == 1.0
    assert m.decay_gain == 1.0
    assert m.budget_refill == 0.0
