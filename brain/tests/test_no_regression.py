from brain.brain_manager import BrainManager, get_brain


def test_brain_disabled_returns_none_mood_block(monkeypatch):
    monkeypatch.setenv("BRAIN_ENABLED", "false")
    assert get_brain().get_mood_block() is None


def test_brain_disabled_returns_default_params(monkeypatch):
    monkeypatch.setenv("BRAIN_ENABLED", "false")
    params = get_brain().get_gemini_params(0.7, 0)
    assert params["temperature"] == 0.7
    assert params["thinking_budget"] == 0
    assert "voice_name" not in params


def test_observe_only_no_modulation(monkeypatch):
    monkeypatch.setenv("BRAIN_ENABLED", "true")
    monkeypatch.setenv("BRAIN_OBSERVE_ONLY", "true")
    monkeypatch.setenv("BRAIN_MODULATE_ALL", "false")
    params = get_brain().get_gemini_params(0.7, 0)
    assert params["temperature"] == 0.7
    assert get_brain().get_mood_block() is None


def test_brain_crash_does_not_kill_caller(monkeypatch):
    monkeypatch.setenv("BRAIN_ENABLED", "true")
    monkeypatch.setenv("BRAIN_MODULATE_ALL", "true")
    monkeypatch.setattr(BrainManager, "_internal_compute_block", lambda self: 1 / 0)
    assert get_brain().get_mood_block() is None


def test_modulation_when_stressed(monkeypatch):
    monkeypatch.setenv("BRAIN_ENABLED", "true")
    monkeypatch.setenv("BRAIN_MODULATE_ALL", "true")
    brain = get_brain()
    brain._last_temperature = None
    for _ in range(5):
        brain.notify_user_message("t'es vraiment nul connard inutile")
    params = brain.get_gemini_params(0.7, 0)
    assert params["temperature"] < 0.7
