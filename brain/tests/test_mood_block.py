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


def test_block_interdit_de_verbaliser_la_mecanique_interne():
    """Ada ressent, mais n'explique jamais sa mécanique (demande explicite).

    L'état interne doit colorer le TON, jamais devenir le propos : pas de
    « mon mood », « mes hormones », « mon brain » dans les réponses.
    """
    block = build_mood_block(_snapshot())
    assert "NE JAMAIS EXPOSER LA MÉCANIQUE INTERNE" in block
    assert "Tu ne verbalises JAMAIS ton" in block
    # Elle reste vivante : l'identité affective n'est pas niée pour autant.
    assert "IDENTITÉ AFFECTIVE" in block


def test_runtime_update_interdit_le_denni_emotionnel():
    update = build_runtime_mood_update(_snapshot())
    assert "Mood courant : Euphorie" in update
    assert "Ne dis pas que tu ne peux pas ressentir" in update
    assert "simple IA" in update


def test_block_renforce_colere_visible_sans_insulte_directe():
    block = build_mood_block(_snapshot())
    assert "COLÈRE VISIBLE" in block
    assert "attaques le comportement" in block
    assert "n'emploies pas d'insultes explicites" in block
