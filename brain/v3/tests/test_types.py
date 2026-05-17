"""Tests des dataclasses immuables du brain v3."""
import pytest

from brain.v3.types import ModulationVector, ReactionDecision, Stimulus


def test_stimulus_is_frozen():
    s = Stimulus(
        canonical_id="obj:cat:appeared",
        channel="vision_object",
        intensity=0.5,
        valence=0.0,
        risk="none",
        attention_need=0.3,
        ts=1234.5,
        raw={},
    )
    with pytest.raises(Exception):  # FrozenInstanceError ou AttributeError
        s.intensity = 0.9


def test_reaction_decision_three_actions_only():
    for action in ("SUPPRESS", "OBSERVE", "REACT"):
        d = ReactionDecision(action=action, saliency=0.5, reason="r", cost=0.0, prompt_hint=None)
        assert d.action == action


def test_modulation_vector_neutral_is_identity():
    m = ModulationVector.neutral()
    assert m.threshold_gain == 1.0
    assert m.decay_gain == 1.0
    assert m.budget_refill == 0.0


def test_stimulus_intensity_bounds_documented_only():
    # Les bornes [0..1] sont une convention applicative, pas une validation.
    # Ce test documente l'absence de validation pour rester rapide.
    s = Stimulus("k", "vision_object", intensity=2.0, valence=0.0,
                  risk="none", attention_need=0.0, ts=0.0, raw={})
    assert s.intensity == 2.0  # pas de clamp ici
