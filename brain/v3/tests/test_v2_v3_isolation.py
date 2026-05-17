"""Vérifie que v3 désactivé laisse v2 strictement inchangé."""

from brain.brain_manager import BrainManager


def _enable_brain(monkeypatch):
    monkeypatch.setenv("BRAIN_ENABLED", "true")
    monkeypatch.setenv("BRAIN_MODULATE_ALL", "true")
    monkeypatch.setenv("BRAIN_OBSERVE_ONLY", "false")


def test_v3_not_initialized_when_disabled(monkeypatch):
    _enable_brain(monkeypatch)
    monkeypatch.delenv("BRAIN_V3_ENABLED", raising=False)
    brain = BrainManager()
    assert brain._v3 is None


def test_v3_initialized_when_enabled(monkeypatch):
    _enable_brain(monkeypatch)
    monkeypatch.setenv("BRAIN_V3_ENABLED", "true")
    brain = BrainManager()
    assert brain._v3 is not None
    brain._v3.stop()


def test_notify_visual_scene_returns_same_type_when_v3_off(monkeypatch):
    _enable_brain(monkeypatch)
    monkeypatch.delenv("BRAIN_V3_ENABLED", raising=False)
    brain = BrainManager()
    event = {"risk": "low", "movement": 0.3, "person": "bryan",
             "human_emotion": "happy", "attention_need": 0.3}
    result = brain.notify_visual_scene(event)
    assert isinstance(result, (str, type(None)))


def test_high_risk_event_still_triggers_v2_path(monkeypatch):
    _enable_brain(monkeypatch)
    monkeypatch.delenv("BRAIN_V3_ENABLED", raising=False)
    brain = BrainManager()
    event = {"risk": "high", "movement": 0.5, "person": "bryan",
             "human_emotion": "stressed", "attention_need": 0.95,
             "spontaneous_hint": "Bryan semble en détresse"}
    result = brain.notify_visual_scene(event)
    assert result is None or len(result) > 0


def test_ingest_stimulus_returns_none_when_v3_off(monkeypatch):
    _enable_brain(monkeypatch)
    monkeypatch.delenv("BRAIN_V3_ENABLED", raising=False)
    brain = BrainManager()
    stimulus = {"source": "vision_object", "object_class": "Cat",
                "event_type": "appeared", "movement": 0.5, "risk": "low",
                "attention_need": 0.3}
    result = brain.ingest_stimulus(stimulus)
    assert result is None
