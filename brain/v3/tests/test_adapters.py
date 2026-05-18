"""Tests de la normalisation payload → Stimulus."""
import pytest

from brain.v3.adapters import canonical_id_for, from_payload


def test_vision_object_canonical_id():
    payload = {"object_class": "Cat", "event_type": "appeared"}
    assert canonical_id_for("vision_object", payload) == "obj:cat:appeared"


def test_vision_scene_canonical_id():
    payload = {"person": "Bryan", "human_emotion": "Happy"}
    assert canonical_id_for("vision_scene", payload) == "scene:bryan:happy"


def test_face_motion_canonical_id():
    assert canonical_id_for(
        "face_motion",
        {"presence_bool": True, "person": "Bryan", "movement": 0.8},
    ) == "face:bryan:present:high"
    assert canonical_id_for("face_motion", {"presence_bool": False}) == "face:unknown:absent:low"


def test_gesture_canonical_id():
    assert canonical_id_for(
        "gesture",
        {"gesture_type": "click", "phase": "observed"},
    ) == "gesture:click:observed"


def test_text_canonical_id_buckets_valence():
    assert canonical_id_for("text", {"valence": 0.8}) == "text:positive"
    assert canonical_id_for("text", {"valence": -0.6}) == "text:negative"
    assert canonical_id_for("text", {"valence": 0.0}) == "text:neutral"


def test_unknown_channel_canonical_id_safe():
    assert canonical_id_for("weird", {}) == "weird:unknown"


def test_from_payload_vision_object_normalizes_fields():
    payload = {
        "source": "vision_object",
        "object_class": "Cat",
        "event_type": "appeared",
        "movement": 0.6,
        "risk": "low",
        "attention_need": 0.4,
        "valence": 0.0,
        "spontaneous_hint": "Un chat apparaît.",
    }
    stim = from_payload(payload, channel="VISION_OBJECT")
    assert stim.canonical_id == "obj:cat:appeared"
    assert stim.channel == "vision_object"
    assert stim.intensity == pytest.approx(0.6)
    assert stim.risk == "low"
    assert stim.attention_need == pytest.approx(0.4)
    assert stim.raw is payload  # passé par référence pour limbic v2


def test_from_payload_vision_scene_uses_movement_as_intensity():
    payload = {"movement": 0.7, "attention_need": 0.5, "risk": "none",
                "person": "Bryan", "human_emotion": "sad", "valence": -0.3}
    stim = from_payload(payload, channel="vision_scene")
    assert stim.canonical_id == "scene:bryan:sad"
    # intensité = max(movement, attention_need)
    assert stim.intensity == pytest.approx(0.7)
    assert stim.valence == pytest.approx(-0.3)


def test_from_payload_gesture_uses_intensity():
    payload = {
        "gesture_type": "click",
        "phase": "observed",
        "intensity": 0.8,
        "attention_need": 0.6,
    }
    stim = from_payload(payload, channel="gesture")
    assert stim.canonical_id == "gesture:click:observed"
    assert stim.channel == "gesture"
    assert stim.intensity == pytest.approx(0.8)


def test_from_payload_clamps_intensity_to_unit():
    payload = {"object_class": "Cat", "event_type": "appeared", "movement": 999.0,
                "risk": "none", "attention_need": -5.0}
    stim = from_payload(payload, channel="vision_object")
    assert 0.0 <= stim.intensity <= 1.0
    assert 0.0 <= stim.attention_need <= 1.0


def test_from_payload_unknown_risk_defaults_none():
    stim = from_payload({"risk": "nuclear"}, channel="vision_object")
    assert stim.risk == "none"


def test_canonical_id_stable_across_calls():
    p1 = {"object_class": "Cat", "event_type": "appeared"}
    p2 = {"object_class": "cat", "event_type": "APPEARED"}
    assert canonical_id_for("vision_object", p1) == canonical_id_for("vision_object", p2)
