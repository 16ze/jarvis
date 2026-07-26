"""Tests de la théorie de l'esprit (brain/user_state.py).

Ada infère l'état de Bryan pour s'y adapter — sans jamais le transformer en
diagnostic chiffré, et sans rien prétendre tant qu'elle manque d'éléments.
"""

from datetime import datetime

import pytest

from brain.user_state import UserStateModel

NUIT = datetime(2026, 7, 26, 3, 0).timestamp()
JOUR = datetime(2026, 7, 26, 14, 0).timestamp()


def _modele(*observations) -> UserStateModel:
    m = UserStateModel()
    for obs in observations:
        obs(m)
    return m


# ─── Inférence ────────────────────────────────────────────────────────────────

def test_late_night_short_messages_read_as_tired_and_busy():
    m = _modele(
        lambda x: x.observe_message("ok", now=NUIT),
        lambda x: x.observe_message("fais-le", now=NUIT + 30),
        lambda x: x.observe_message("non", now=NUIT + 50),
    )
    etat = m.current(now=NUIT + 60)
    assert etat.energie < 0.42
    assert etat.disponibilite < 0.48


def test_angry_face_and_negative_exchange_read_as_tense():
    m = _modele(
        lambda x: x.observe_message("ça ne marche toujours pas", now=JOUR),
        lambda x: x.observe_face("angry", 0.85, now=JOUR + 5),
        lambda x: x.observe_appraisal(-0.7, 0.8, now=JOUR + 10),
    )
    assert m.current(now=JOUR + 15).tension > 0.58


def test_positive_signals_read_as_relaxed():
    m = _modele(
        lambda x: x.observe_message("salut ! comment ça va ? j'ai bien avancé", now=JOUR),
        lambda x: x.observe_face("happy", 0.9, now=JOUR + 5),
        lambda x: x.observe_appraisal(0.6, 0.3, now=JOUR + 10),
    )
    assert m.current(now=JOUR + 15).tension < 0.30


def test_confident_face_signal_weighs_more_than_a_weak_one():
    fort = _modele(lambda x: x.observe_face("angry", 0.95, now=JOUR))
    faible = _modele(lambda x: x.observe_face("angry", 0.40, now=JOUR))
    assert fort.current(now=JOUR).tension > faible.current(now=JOUR).tension


def test_low_confidence_face_is_ignored():
    m = _modele(lambda x: x.observe_face("angry", 0.1, now=JOUR))
    assert m.current(now=JOUR).confidence == 0.0


# ─── Prudence ─────────────────────────────────────────────────────────────────

def test_no_claim_without_enough_observations():
    m = _modele(lambda x: x.observe_message("test", now=JOUR))
    assert m.current(now=JOUR).is_reliable is False
    assert m.directives(now=JOUR) == []
    assert m.contagion(now=JOUR) == {}


def test_stale_observations_stop_being_trusted():
    m = _modele(
        lambda x: x.observe_message("ok", now=JOUR),
        lambda x: x.observe_message("ok", now=JOUR + 1),
        lambda x: x.observe_message("ok", now=JOUR + 2),
    )
    assert m.current(now=JOUR + 10).is_reliable is True
    assert m.current(now=JOUR + 7200).is_reliable is False   # 2 h plus tard


def test_empty_message_is_ignored():
    m = _modele(lambda x: x.observe_message("   ", now=JOUR))
    assert m.current(now=JOUR).confidence == 0.0


# ─── Usages ───────────────────────────────────────────────────────────────────

def test_directives_describe_behaviour_not_measurements():
    """Des manières d'être, jamais un diagnostic chiffré."""
    m = _modele(
        lambda x: x.observe_message("ok", now=NUIT),
        lambda x: x.observe_message("vas-y", now=NUIT + 20),
        lambda x: x.observe_message("non", now=NUIT + 40),
    )
    texte = " ".join(m.directives(now=NUIT + 50))
    assert texte
    for interdit in ("0.", "score", "niveau", "mesure", "modèle", "%"):
        assert interdit not in texte.lower()


def test_tension_is_contagious():
    m = _modele(
        lambda x: x.observe_face("angry", 0.9, now=JOUR),
        lambda x: x.observe_appraisal(-0.8, 0.9, now=JOUR + 5),
        lambda x: x.observe_appraisal(-0.7, 0.8, now=JOUR + 10),
    )
    assert m.contagion(now=JOUR + 15).get("cortisol", 0) > 0


def test_contagion_stays_small():
    """Ada est influencée par l'état de Bryan, jamais pilotée par lui."""
    m = _modele(
        lambda x: x.observe_face("angry", 1.0, now=JOUR),
        lambda x: x.observe_appraisal(-1.0, 1.0, now=JOUR + 5),
        lambda x: x.observe_appraisal(-1.0, 1.0, now=JOUR + 10),
        lambda x: x.observe_appraisal(-1.0, 1.0, now=JOUR + 15),
    )
    for delta in m.contagion(now=JOUR + 20).values():
        assert abs(delta) < 0.12


def test_debug_state_exposes_the_estimate():
    m = _modele(lambda x: x.observe_message("bonjour à toi", now=JOUR))
    etat = m.get_debug_state()
    assert set(etat) >= {"energie", "disponibilite", "tension", "confiance"}


def test_malformed_input_is_survivable():
    m = UserStateModel()
    m.observe_face("", 0.0)
    m.observe_appraisal(float("nan"), 0.0)
    assert m.current() is not None
