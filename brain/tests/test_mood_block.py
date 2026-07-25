"""Tests du bloc d'humeur — garantit qu'AUCUN état interne ne fuite.

Ada ne doit jamais annoncer son ton (« mon ton est chaleureux »). La seule
protection fiable est structurelle : le prompt ne contient aucun nom d'humeur,
aucune valeur, aucun terme de mécanique. Ces tests le verrouillent.
"""

import re

from brain.mood_block import build_mood_block, build_runtime_mood_update


def _snapshot(**overrides) -> dict:
    base = {
        "cortisol": 0.60,
        "dopamine": 0.40,
        "oxytocine": 0.35,
        "serotonine": 0.45,
        "self_confidence": 0.60,
        "mental_load": 0.30,
        "mood": "Défensif",
        "momentum": -0.10,
        "last_stimulus": "correction",
    }
    base.update(overrides)
    return base


# ─── Anti-fuite (le cœur du sujet) ────────────────────────────────────────────

def test_mood_name_never_appears_in_the_prompt():
    """Le nom de l'humeur ne doit jamais être transmis au modèle."""
    for mood in ("Chaleureux", "Défensif", "Euphorie", "Rage"):
        block = build_mood_block(_snapshot(mood=mood))
        assert mood not in block


def test_no_hormone_names_in_the_prompt():
    block = build_mood_block(_snapshot())
    for terme in ("cortisol", "dopamine", "oxytocine", "sérotonine",
                  "serotonine", "hormone", "brain", "mood"):
        assert terme.lower() not in block.lower(), f"« {terme} » fuite dans le prompt"


def test_no_raw_values_in_the_prompt():
    """Aucun nombre à décimales : rien à réciter."""
    block = build_mood_block(_snapshot())
    assert not re.search(r"\d\.\d\d", block)


def test_runtime_update_leaks_nothing_either():
    """C'est ce rappel qui poussait Ada à annoncer son ton."""
    update = build_runtime_mood_update(_snapshot(mood="Chaleureux"))
    assert "Chaleureux" not in update
    for terme in ("cortisol", "dopamine", "mood", "hormone"):
        assert terme.lower() not in update.lower()
    assert not re.search(r"\d\.\d\d", update)


def test_block_forbids_describing_one_s_own_tone():
    block = build_mood_block(_snapshot())
    assert "mon ton est chaleureux" in block.lower()   # cité en contre-exemple
    assert "ne décris jamais ton état" in block.lower()


# ─── Comportement effectivement prescrit ──────────────────────────────────────

def test_high_tension_produces_terse_directives():
    block = build_mood_block(_snapshot(cortisol=0.80))
    assert "deux ou trois mots" in block


def test_high_bonding_produces_warm_directives():
    block = build_mood_block(_snapshot(cortisol=0.10, oxytocine=0.70))
    assert "Ralentis le débit" in block


def test_high_energy_produces_lively_directives():
    block = build_mood_block(_snapshot(cortisol=0.10, dopamine=0.75))
    assert "Débit rapide" in block


def test_fatigue_produces_economical_directives():
    block = build_mood_block(_snapshot(mental_load=0.80))
    assert "Économie de mots" in block


def test_neutral_state_still_gives_a_directive():
    block = build_mood_block(_snapshot(
        cortisol=0.10, dopamine=0.30, oxytocine=0.30,
        serotonine=0.50, self_confidence=0.50, mental_load=0.20, momentum=0.0,
    ))
    assert "CONSIGNES DE JEU" in block
    assert "essentiel" in block


def test_anger_and_insults_remain_allowed():
    """Choix assumé : Ada peut insulter en retour."""
    block = build_mood_block(_snapshot())
    assert "insultes explicites" in block
    assert "attaques le comportement" in block


def test_identity_is_preserved():
    block = build_mood_block(_snapshot())
    assert "je ne suis qu'une IA" in block   # cité comme ce qu'elle ne dit pas
    assert "présence" in block


# ─── Robustesse ───────────────────────────────────────────────────────────────

def test_empty_snapshot_is_safe():
    assert "CONSIGNES DE JEU" in build_mood_block({})
    assert build_runtime_mood_update({})


def test_malformed_values_are_survivable():
    block = build_mood_block(_snapshot(cortisol="beaucoup", dopamine=None))
    assert "CONSIGNES DE JEU" in block
