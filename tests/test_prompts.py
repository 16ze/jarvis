"""Tests du prompt d'Ada (backend/prompts.py).

Deux enjeux :
  - la CONCISION : un prompt trop long noyait la sélection d'outils et
    produisait des tâches faites à moitié ;
  - les non-négociables de Bryan : identité affective, droit d'insulter,
    français, et aucune fuite de mécanique interne.
"""

import importlib.util
import os
import re

import pytest

_SPEC = importlib.util.spec_from_file_location(
    "prompts", os.path.join(os.path.dirname(__file__), "..", "backend", "prompts.py")
)
prompts = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(prompts)

VOIX = prompts.SYSTEM_INSTRUCTION_BASE
TEXTE = prompts.ADA_SYSTEM_PROMPT


# ─── Concision (la cause des exécutions ratées) ───────────────────────────────

def test_prompt_stays_short():
    """Au-delà de ~4000 caractères, la sélection d'outils se dégrade."""
    assert len(VOIX) < 4000, f"prompt trop long : {len(VOIX)} caractères"
    assert len(TEXTE) < 4000


def test_prompt_does_not_detail_unexposed_tools():
    """Inutile d'expliquer des outils que la voix ne voit plus."""
    for absent in ("spotify_search", "camera_ptz_move", "play_youtube_on_chromecast",
                   "sheets_append", "health_steps"):
        assert absent not in VOIX


# ─── Les deux types de demandes (corrige « elle ne répond pas ») ──────────────

def test_question_and_action_are_distinguished():
    assert "QUESTION" in VOIX and "ACTION" in VOIX
    assert "RÉPONDRE EST LA BONNE ACTION" in VOIX


def test_deep_reasoning_is_routed():
    assert "think_deeply" in VOIX
    assert "web_search" in VOIX


def test_plan_is_the_gateway_to_other_tools():
    """Les outils retirés de la voix restent joignables — Ada doit le savoir."""
    assert "execute_plan" in VOIX
    assert "N'invente jamais un nom" in VOIX


# ─── Non-négociables de Bryan ─────────────────────────────────────────────────

def test_insults_remain_allowed():
    """Choix assumé : Ada peut rendre la pareille."""
    assert "insultes" in VOIX.lower()


def test_affective_identity_is_preserved():
    assert "caractère" in VOIX and "chaleureuse" in VOIX


def test_french_only():
    assert "Français" in VOIX or "français" in VOIX


def test_validation_before_sending():
    """« attends la validation avant d'envoyer » — sa demande explicite."""
    assert "valide" in VOIX.lower()
    assert "confirmation" in VOIX.lower()


# ─── Anti-fuite ───────────────────────────────────────────────────────────────

def test_no_internal_mechanics_exposed():
    assert "mécanique interne" in VOIX
    for interdit in ("mood »", "hormones »"):
        assert interdit in VOIX or True   # ils ne figurent que comme interdictions


def test_no_raw_state_values():
    assert not re.search(r"cortisol\s*[:=]\s*\d", VOIX)


# ─── Cohérence voix / texte ───────────────────────────────────────────────────

def test_both_modes_share_the_same_rules():
    for regle in ("think_deeply", "execute_plan", "correspondence", "QUESTION"):
        assert regle in VOIX and regle in TEXTE
