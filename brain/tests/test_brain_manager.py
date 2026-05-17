from brain.network import EtatEveil
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


def test_notify_visual_scene_banal_ne_reagit_pas(monkeypatch):
    monkeypatch.setenv("BRAIN_ENABLED", "true")
    brain = get_brain()
    brain.reseau._etat = EtatEveil.SOMMEIL
    event = {
        "description": "tasse sur la table",
        "risk": "none",
        "human_emotion": "unknown",
        "movement": 0.05,
        "attention_need": 0.1,
    }
    assert brain.notify_visual_scene(event) is None
