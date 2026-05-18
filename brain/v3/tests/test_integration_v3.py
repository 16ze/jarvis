"""Tests d'intégration bout-en-bout : YOLO → BrainManager → V3Manager."""

from brain.brain_manager import BrainManager


def _enable_brain(monkeypatch):
    monkeypatch.setenv("BRAIN_ENABLED", "true")
    monkeypatch.setenv("BRAIN_MODULATE_ALL", "true")
    monkeypatch.setenv("BRAIN_OBSERVE_ONLY", "false")
    monkeypatch.setenv("BRAIN_V3_ENABLED", "true")


def test_ingest_stimulus_runs_through_v3(monkeypatch):
    _enable_brain(monkeypatch)
    monkeypatch.setenv("BRAIN_V3_SHADOW_MODE", "true")
    brain = BrainManager()
    stimulus = {"source": "vision_object", "object_class": "Cat",
                "event_type": "appeared", "movement": 0.6, "risk": "low",
                "attention_need": 0.4, "spontaneous_hint": "Un chat"}
    brain.ingest_stimulus(stimulus)
    state = brain._v3.get_debug_state()
    assert state["recent_decisions"]
    assert state["recent_decisions"][0]["stimulus"].startswith("obj:cat")
    brain._v3.stop()


def test_high_risk_stimulus_returns_react_prompt(monkeypatch):
    _enable_brain(monkeypatch)
    monkeypatch.setenv("BRAIN_V3_SHADOW_MODE", "false")
    brain = BrainManager()
    stimulus = {"source": "vision_object", "object_class": "Fire",
                "event_type": "appeared", "movement": 0.3, "risk": "high",
                "attention_need": 0.95, "spontaneous_hint": "Du feu !"}
    result = brain.ingest_stimulus(stimulus)
    assert result is not None
    assert result.prompt == "Du feu !"
    assert result.action == "REACT"
    assert result.saliency > 0.0
    brain._v3.stop()


def test_repeated_stimulus_eventually_suppressed_by_habituation(monkeypatch):
    _enable_brain(monkeypatch)
    monkeypatch.setenv("BRAIN_V3_SHADOW_MODE", "false")
    monkeypatch.setenv("BRAIN_V3_REACTION_THRESHOLD", "0.55")
    monkeypatch.setenv("BRAIN_V3_REFRACTORY_VISION_OBJECT", "0.0")
    brain = BrainManager()
    stimulus = {"source": "vision_object", "object_class": "Cat",
                "event_type": "appeared", "movement": 0.5, "risk": "low",
                "attention_need": 0.3, "spontaneous_hint": "Un chat"}
    reactions = 0
    for _ in range(30):
        result = brain.ingest_stimulus(stimulus)
        if result is not None:
            reactions += 1
    assert reactions < 10
    brain._v3.stop()


def test_notify_user_message_observes_in_v3_without_gating(monkeypatch):
    _enable_brain(monkeypatch)
    monkeypatch.setenv("BRAIN_V3_SHADOW_MODE", "false")
    brain = BrainManager()
    brain.notify_user_message("salut, comment vas-tu ?", audio_features=None)
    state = brain._v3.get_debug_state()
    text_traces = [
        decision for decision in state["recent_decisions"]
        if decision["stimulus"].startswith("text:")
    ]
    assert text_traces, "v3 devrait avoir observé le texte user"
    assert text_traces[0]["action"] == "OBSERVE"
    assert text_traces[0]["reason"] == "passive_observe"
    brain._v3.stop()
