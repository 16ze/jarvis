"""Tests de AttentionField (5 neurones + inhibition latérale + intégration habituation)."""
import time

from brain.v3.attention import AttentionField
from brain.v3.habituation import HabituationTracker
from brain.v3.types import ModulationVector, Stimulus


def _stim(channel: str, canonical: str, intensity: float = 0.8) -> Stimulus:
    return Stimulus(canonical, channel, intensity, 0.0, "none", 0.0, time.monotonic(), {})


def test_unknown_channel_returns_false():
    field = AttentionField()
    s = _stim("weird", "x:y", 0.9)
    assert field.tick(s, ModulationVector.neutral(), HabituationTracker()) is False


def test_spike_on_strong_stimulus():
    field = AttentionField()
    s = _stim("vision_object", "obj:cat:appeared", intensity=0.95)
    s_strong = _stim("vision_object", "obj:fire:appeared", intensity=2.0)
    assert field.tick(s_strong, ModulationVector.neutral(), HabituationTracker()) is True


def test_familiarity_reduces_effective_intensity():
    field = AttentionField()
    hab = HabituationTracker(halflife_sec=120.0)
    canonical = "obj:cat:appeared"
    for _ in range(15):
        hab.imprint(canonical)
    s = _stim("vision_object", canonical, intensity=1.2)
    assert field.tick(s, ModulationVector.neutral(), hab) is False


def test_modulation_threshold_gain_makes_easier_to_spike():
    field = AttentionField()
    s = _stim("vision_object", "obj:knife:appeared", intensity=0.7)
    assert field.tick(s, ModulationVector.neutral(), HabituationTracker()) is False
    field2 = AttentionField()
    mod = ModulationVector(threshold_gain=0.6, decay_gain=1.0, budget_refill=0.0)
    assert field2.tick(s, mod, HabituationTracker()) is True


def test_refractory_per_channel():
    field = AttentionField()
    s = _stim("vision_object", "obj:gun:appeared", intensity=3.0)
    assert field.tick(s, ModulationVector.neutral(), HabituationTracker()) is True
    assert field.tick(s, ModulationVector.neutral(), HabituationTracker()) is False
