from brain.brain_manager import get_brain


def test_singleton():
    assert get_brain() is get_brain()


def test_start_idempotent(monkeypatch):
    monkeypatch.setenv("BRAIN_ENABLED", "true")
    brain = get_brain()
    brain.start(lambda: (False, 0.0, 0.0))
    first = brain._adapter
    brain.start(lambda: (True, 0.1, 0.9))
    assert brain._adapter is first
    brain.stop()
