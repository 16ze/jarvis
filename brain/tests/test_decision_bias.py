"""Tests du couplage émotion → décision (brain/decision_bias.py).

L'état interne doit infléchir la CONDUITE (prudence, persévérance, initiative),
sans jamais franchir les règles de sûreté.
"""

import pytest

from brain.decision_bias import BASE_TENTATIVES, compute, prompt_block

SEREINE = dict(cortisol=0.08, self_confidence=0.85, mental_load=0.15,
               serotonine=0.70, dopamine=0.60)
TENDUE = dict(cortisol=0.80, self_confidence=0.45, mental_load=0.40,
              serotonine=0.30, dopamine=0.25)
EPUISEE = dict(cortisol=0.30, self_confidence=0.50, mental_load=0.90,
               serotonine=0.35, dopamine=0.20)


# ─── Inflexions ───────────────────────────────────────────────────────────────

def test_tension_raises_caution():
    assert compute(TENDUE).prudence > compute(SEREINE).prudence


def test_confidence_raises_perseverance():
    assert compute(SEREINE).perseverance > compute(TENDUE).perseverance


def test_exhaustion_lowers_perseverance():
    """Épuisée, Ada s'arrête plutôt que de s'acharner."""
    assert compute(EPUISEE).perseverance < compute(SEREINE).perseverance


def test_exhaustion_raises_concision():
    assert compute(EPUISEE).concision > compute(SEREINE).concision


def test_serenity_raises_initiative():
    assert compute(SEREINE).initiative > compute(TENDUE).initiative


def test_user_tension_lowers_initiative():
    """Ada ne propose pas d'aller plus loin quand Bryan est sous pression."""
    seule = compute(SEREINE).initiative
    avec = compute(SEREINE, user_tension=0.9).initiative
    assert avec < seule


def test_user_tension_raises_caution():
    assert compute(SEREINE, user_tension=0.9).prudence > compute(SEREINE).prudence


# ─── Effet opérationnel réel ──────────────────────────────────────────────────

def test_retry_count_follows_perseverance():
    """C'est l'effet concret : le nombre de tentatives change vraiment."""
    assert compute(SEREINE).tentatives_max > compute(EPUISEE).tentatives_max


def test_retry_count_stays_bounded():
    for etat in (SEREINE, TENDUE, EPUISEE, {}):
        n = compute(etat).tentatives_max
        assert 1 <= n <= BASE_TENTATIVES + 2


def test_extreme_state_never_disables_retries():
    """Même au plus bas, Ada tente au moins une fois."""
    effondree = dict(cortisol=1.0, self_confidence=0.0, mental_load=1.0,
                     serotonine=0.0, dopamine=0.0)
    assert compute(effondree).tentatives_max >= 1


# ─── Consignes ────────────────────────────────────────────────────────────────

def test_tense_state_asks_for_confirmation():
    assert compute(TENDUE).demande_confirmation_elargie is True


def test_serene_state_offers_next_step():
    assert compute(SEREINE).propose_suite is True


def test_tense_state_does_not_offer_next_step():
    assert compute(TENDUE).propose_suite is False


def test_directives_contain_no_measurements():
    """Des manières d'agir, jamais de valeurs — cohérent avec l'anti-fuite."""
    for etat in (SEREINE, TENDUE, EPUISEE):
        texte = " ".join(compute(etat).directives()).lower()
        for interdit in ("0.", "score", "niveau", "cortisol", "dopamine", "%"):
            assert interdit not in texte


def test_prompt_block_is_injectable():
    bloc = prompt_block(TENDUE)
    assert "TA MANIÈRE D'AGIR" in bloc


def test_prompt_block_disabled_by_env(monkeypatch):
    monkeypatch.setenv("BRAIN_DECISION_BIAS_ENABLED", "false")
    assert prompt_block(TENDUE) == ""


# ─── Robustesse ───────────────────────────────────────────────────────────────

def test_empty_snapshot_is_safe():
    biais = compute(None)
    assert 0.0 <= biais.prudence <= 1.0
    assert biais.tentatives_max >= 1


def test_malformed_values_are_survivable():
    biais = compute({"cortisol": "beaucoup", "self_confidence": None})
    assert 0.0 <= biais.prudence <= 1.0
