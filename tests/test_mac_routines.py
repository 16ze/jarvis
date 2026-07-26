"""Tests du routage des routines macOS natives (backend/mac_routines.py).

On teste la RECONNAISSANCE (quelle phrase déclenche quelle routine), pas
l'exécution : ces actions touchent le vrai système.
"""

import asyncio
import os
import sys
from unittest.mock import AsyncMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

import mac_routines as mr  # noqa: E402


def _route(phrase: str):
    """Route la phrase en neutralisant toute action système réelle."""
    with patch.object(mr, "_run"), patch.object(mr, "_osa", return_value=""):
        return asyncio.run(mr.route(phrase))


# ─── Panneaux de Réglages ─────────────────────────────────────────────────────

@pytest.mark.parametrize("phrase,attendu", [
    ("ouvre les réglages de son", "Son"),
    ("ouvre les réglages caméra", "Caméra"),
    ("va dans les réglages accessibilité", "Accessibilité"),
    ("ouvre les paramètres bluetooth", "Bluetooth"),
    ("affiche les réglages de confidentialité", "Confidentialité"),
    ("ouvre les préférences batterie", "Batterie"),
])
def test_settings_panels_are_recognised(phrase, attendu):
    res = _route(phrase)
    assert res is not None and attendu in res


def test_plain_settings_request_falls_through():
    """« ouvre les réglages » sans sujet → ouverture d'app classique."""
    assert _route("ouvre les réglages") is None


def test_unknown_panel_falls_through():
    assert _route("ouvre les réglages de quantique") is None


# ─── Fenêtres ─────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("phrase,attendu", [
    ("réduis la fenêtre", "réduite"),
    ("mets en plein écran", "Plein écran"),
    ("ferme cette fenêtre", "Fenêtre fermée"),
    ("masque tout", "masquées"),
])
def test_window_actions(phrase, attendu):
    res = _route(phrase)
    assert res is not None and attendu in res


# ─── Média ────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("phrase", [
    "mets en pause", "piste suivante", "morceau précédent",
])
def test_media_controls_are_recognised(phrase):
    assert _route(phrase) is not None


# ─── Divers ───────────────────────────────────────────────────────────────────

def test_brightness_with_explicit_level():
    assert "Luminosité" in (_route("règle la luminosité à 40%") or "")


def test_screenshot_is_recognised():
    with patch.object(mr, "_run"), patch.object(mr, "_osa", return_value=""):
        res = asyncio.run(mr.route("fais une capture d'écran"))
    assert res is not None


def test_lock_screen_is_recognised():
    assert "verrouillé" in (_route("verrouille l'écran") or "").lower()


# ─── Non-régression : ne pas voler les autres commandes ───────────────────────

@pytest.mark.parametrize("phrase", [
    "ouvre TextEdit",
    "ferme Safari",
    "envoie un message à Ivan disant bonjour",
    "appelle Ivan",
    "cherche la météo à Libreville",
    "ouvre TextEdit et écris bonjour",
])
def test_other_commands_are_left_alone(phrase):
    """Les routines natives ne doivent capter QUE ce qui les concerne."""
    assert _route(phrase) is None


def test_empty_input_is_safe():
    assert _route("") is None
