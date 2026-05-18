"""Tests de la façade V3Manager."""
import time

from brain.v3.tests.conftest import MockLimbic
from brain.v3.v3_manager import V3Manager


def _payload(**overrides) -> dict:
    payload = {
        "object_class": "cat",
        "event_type": "appeared",
        "movement": 1.0,
        "attention_need": 0.8,
        "valence": 0.0,
        "risk": "none",
        "spontaneous_hint": "regarde le chat",
    }
    payload.update(overrides)
    return payload


def test_manager_disabled_by_default(monkeypatch):
    monkeypatch.delenv("BRAIN_V3_ENABLED", raising=False)
    manager = V3Manager(MockLimbic())
    try:
        assert manager.enabled is False
    finally:
        manager.stop()


def test_manager_enabled_with_env(monkeypatch):
    monkeypatch.setenv("BRAIN_V3_ENABLED", "true")
    manager = V3Manager(MockLimbic())
    try:
        assert manager.enabled is True
    finally:
        manager.stop()


def test_shadow_mode_default_false(monkeypatch):
    monkeypatch.delenv("BRAIN_V3_SHADOW_MODE", raising=False)
    manager = V3Manager(MockLimbic())
    try:
        assert manager.shadow_mode is False
    finally:
        manager.stop()


def test_attention_budget_env_vars(monkeypatch):
    monkeypatch.setenv("BRAIN_V3_ATTENTION_BUDGET_INIT", "0.25")
    monkeypatch.setenv("BRAIN_V3_ATTENTION_BUDGET_MAX", "0.4")
    manager = V3Manager(MockLimbic())
    try:
        assert manager.get_debug_state()["budget"] == 0.25
        manager._budget.refill(1.0)
        assert manager.get_debug_state()["budget"] == 0.4
    finally:
        manager.stop()


def test_process_returns_reaction_decision(monkeypatch):
    monkeypatch.setenv("BRAIN_V3_ENABLED", "true")
    manager = V3Manager(MockLimbic())
    try:
        decision = manager.process(_payload(), "vision_object")
        assert decision is not None
        assert decision.__class__.__name__ == "ReactionDecision"
    finally:
        manager.stop()


def test_high_risk_always_reacts_and_prompt_hint_propagates(monkeypatch):
    monkeypatch.setenv("BRAIN_V3_ENABLED", "true")
    manager = V3Manager(MockLimbic())
    try:
        decision = manager.process(
            _payload(risk="high", spontaneous_hint="danger près du bureau"),
            "vision_object",
        )
        assert decision is not None
        assert decision.action == "REACT"
        assert decision.prompt_hint == "danger près du bureau"
    finally:
        manager.stop()


def test_traces_records_decisions(monkeypatch):
    monkeypatch.setenv("BRAIN_V3_ENABLED", "true")
    manager = V3Manager(MockLimbic())
    try:
        manager.process(_payload(risk="high"), "vision_object")
        state = manager.get_debug_state()
        recent = state["recent_decisions"]
        assert len(recent) == 1
        assert recent[0]["stimulus"] == "obj:cat:appeared"
        assert recent[0]["action"] == "REACT"
    finally:
        manager.stop()


def test_exception_marks_degraded(monkeypatch):
    monkeypatch.setenv("BRAIN_V3_ENABLED", "true")
    manager = V3Manager(MockLimbic())

    class BadPayload:
        def get(self, _key, _default=None):
            raise RuntimeError("boom")

    try:
        assert manager.process(BadPayload(), "vision_object") is None
        assert manager.get_debug_state()["degraded"] is True
        assert manager.enabled is False
    finally:
        manager.stop()


def test_p95_latency_under_3ms_over_100_process_calls(monkeypatch):
    monkeypatch.setenv("BRAIN_V3_ENABLED", "true")
    manager = V3Manager(MockLimbic())
    durations = []
    try:
        for index in range(100):
            start = time.perf_counter()
            manager.process(
                _payload(object_class=f"cat_{index}", event_type="appeared"),
                "vision_object",
            )
            durations.append((time.perf_counter() - start) * 1000.0)

        p95 = sorted(durations)[94]
        assert p95 < 3.0
    finally:
        manager.stop()


def test_observe_does_not_consume_budget(monkeypatch):
    monkeypatch.setenv("BRAIN_V3_ENABLED", "true")
    manager = V3Manager(MockLimbic())
    try:
        before = manager.get_debug_state()["budget"]
        manager.observe(_payload(risk="high"), "vision_object")
        after = manager.get_debug_state()["budget"]
        assert after == before
        assert manager.get_debug_state()["recent_decisions"][0]["action"] == "OBSERVE"
    finally:
        manager.stop()
