from brain.mood_block import build_mood_block, build_runtime_mood_update


def _snapshot():
    return {
        "mood": "Euphorie",
        "dopamine": 0.91,
        "cortisol": 0.11,
        "oxytocine": 0.55,
        "serotonine": 0.62,
        "self_confidence": 0.73,
        "mental_load": 0.22,
        "momentum": 0.42,
        "last_stimulus": "test",
    }


def test_block_contient_mood():
    assert "Mood : Euphorie" in build_mood_block(_snapshot())


def test_block_contient_les_6_hormones_formatees():
    block = build_mood_block(_snapshot())
    for expected in ["dopamine 0.91", "cortisol 0.11", "oxytocine 0.55"]:
        assert expected in block
    for expected in ["sérotonine 0.62", "confiance 0.73", "charge mentale 0.22"]:
        assert expected in block


def test_block_ne_contient_pas_instruction_voice_name():
    assert "voice_name" not in build_mood_block(_snapshot())


def test_block_autorise_reponse_introspective():
    block = build_mood_block(_snapshot())
    assert "Si Bryan te demande comment tu te sens" in block
    assert "Ne nie pas ton état interne" in block
    assert "Ne dis pas que tu n'as aucune émotion" in block


def test_runtime_update_interdit_le_denni_emotionnel():
    update = build_runtime_mood_update(_snapshot())
    assert "Mood courant : Euphorie" in update
    assert "Ne dis pas que tu ne peux pas ressentir" in update
    assert "simple IA" in update
