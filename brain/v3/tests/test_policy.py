"""Tests du ReactionPolicy et AttentionBudget."""
import random
import time

import pytest

from brain.v3.policy import AttentionBudget, ReactionPolicy
from brain.v3.types import ModulationVector, Stimulus


def _stim(channel="vision_object", canonical="obj:cat:appeared",
          intensity=0.8, risk="none", attention_need=0.3, valence=0.0):
    return Stimulus(canonical, channel, intensity, valence, risk,
                    attention_need, time.monotonic(), {"spontaneous_hint": "hi"})


def test_budget_can_afford_initially():
    b = AttentionBudget(initial=1.0, max_budget=1.5)
    assert b.can_afford(0.3) is True
    assert b.level == 1.0


def test_policy_exposes_threshold():
    policy = ReactionPolicy(threshold=0.42)
    assert policy.threshold == 0.42


def test_budget_consume_then_refuse():
    b = AttentionBudget(initial=0.5)
    b.consume(0.4)
    assert b.can_afford(0.3) is False


def test_budget_refill_bounded_by_max():
    b = AttentionBudget(initial=1.0, max_budget=1.5)
    b.refill(10.0)
    assert b.level == 1.5


def test_budget_consume_does_not_go_negative():
    b = AttentionBudget(initial=0.2)
    b.consume(1.0)
    assert b.level == 0.0


def test_high_risk_always_reacts():
    policy = ReactionPolicy(threshold=0.55)
    budget = AttentionBudget(initial=0.0)
    s = _stim(risk="high")
    d = policy.decide(s, spike=False, familiarity=1.0,
                      modulation=ModulationVector.neutral(), budget=budget,
                      threshold=0.55)
    assert d.action == "REACT"
    assert d.cost <= 0.1


def test_no_spike_no_reaction():
    policy = ReactionPolicy(threshold=0.55)
    budget = AttentionBudget(initial=1.0)
    s = _stim(intensity=0.5)
    d = policy.decide(s, spike=False, familiarity=0.0,
                      modulation=ModulationVector.neutral(), budget=budget,
                      threshold=0.55)
    assert d.action == "OBSERVE"


def test_saliency_below_threshold_observes():
    policy = ReactionPolicy(threshold=0.55)
    budget = AttentionBudget(initial=1.0)
    s = _stim(intensity=0.1, attention_need=0.1, valence=0.0)
    d = policy.decide(s, spike=True, familiarity=0.9,
                      modulation=ModulationVector.neutral(), budget=budget,
                      threshold=0.55)
    assert d.action == "OBSERVE"


def test_no_budget_observes():
    random.seed(0)
    policy = ReactionPolicy(threshold=0.55)
    budget = AttentionBudget(initial=0.05)
    s = _stim(intensity=0.95, attention_need=0.9)
    d = policy.decide(s, spike=True, familiarity=0.0,
                      modulation=ModulationVector.neutral(), budget=budget,
                      threshold=0.55)
    assert d.action == "OBSERVE"
    assert "budget" in d.reason


def test_reaction_with_full_budget_and_high_saliency():
    random.seed(42)
    policy = ReactionPolicy(threshold=0.55)
    budget = AttentionBudget(initial=1.0)
    s = _stim(intensity=0.95, attention_need=0.9, valence=0.5)
    actions = set()
    for seed in range(10):
        random.seed(seed)
        d = policy.decide(s, spike=True, familiarity=0.0,
                          modulation=ModulationVector.neutral(), budget=budget,
                          threshold=0.55)
        actions.add(d.action)
    assert "REACT" in actions


def test_cost_higher_for_vision_scene():
    policy = ReactionPolicy(threshold=0.55)
    budget = AttentionBudget(initial=1.0)
    s_obj = _stim(channel="vision_object", intensity=0.95, attention_need=0.9)
    s_scene = _stim(channel="vision_scene", intensity=0.95, attention_need=0.9)
    cost_obj = policy._cost_for(s_obj)
    cost_scene = policy._cost_for(s_scene)
    assert cost_scene > cost_obj


def test_prompt_hint_propagated_on_react():
    random.seed(0)
    policy = ReactionPolicy(threshold=0.10)
    budget = AttentionBudget(initial=1.0)
    s = _stim(intensity=1.0, attention_need=1.0)
    found_react = False
    for seed in range(20):
        random.seed(seed)
        d = policy.decide(s, spike=True, familiarity=0.0,
                          modulation=ModulationVector.neutral(), budget=budget,
                          threshold=0.10)
        if d.action == "REACT":
            assert d.prompt_hint == "hi"
            found_react = True
            break
    assert found_react


def test_policy_does_not_consume_budget_on_react():
    random.seed(1)
    policy = ReactionPolicy(threshold=0.10)
    budget = AttentionBudget(initial=1.0)
    s = _stim(intensity=1.0, attention_need=1.0)
    d = policy.decide(s, spike=True, familiarity=0.0,
                      modulation=ModulationVector.neutral(), budget=budget,
                      threshold=0.10)
    assert d.action == "REACT"
    assert d.cost > 0.0
    assert budget.level == 1.0
