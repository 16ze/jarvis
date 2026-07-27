"""Tests de la barrière anti-secrets (backend/safe_git.py).

Contexte : l'agent d'auto-correction d'Ada faisait `git add -A` et a indexé un
jeton OAuth Google. Seule la protection de GitHub a empêché sa publication.
Ces tests verrouillent la barrière qui remplace ce comportement.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from safe_git import is_sensitive  # noqa: E402


# ─── Noms de fichiers ─────────────────────────────────────────────────────────

@pytest.mark.parametrize("chemin", [
    "backend/google_token.json.old",     # le fichier de l'incident réel
    "backend/google_token.json",
    "backend/google_credentials.json",
    "backend/.spotify_token",
    ".env",
    "backend/.env.bak.1779234929",
    "backend/devices.json.bak2",
    "cle_privee.pem",
    "serveur.key",
    "mon_password.txt",
    "config.backup",
])
def test_sensitive_names_are_blocked(chemin):
    bloque, raison = is_sensitive(chemin)
    assert bloque is True
    assert raison


@pytest.mark.parametrize("chemin", [
    "backend/knowledge.py",
    "backend/ada.py",
    "src/App.jsx",
    "README.md",
    "tests/test_planner.py",
    "package.json",
    ".github/workflows/ci.yml",
])
def test_ordinary_files_pass_through(chemin):
    bloque, _ = is_sensitive(chemin)
    assert bloque is False


# ─── Contenu ──────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("contenu", [
    '{"refresh_token": "1//0eXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX"}',
    '{"access_token": "ya29.aXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX"}',
    'CLE = "sk-abcdefghijklmnopqrstuvwxyz012345"',
    'GOOGLE = "AIzaSyBXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX"',
    'GH = "ghp_abcdefghijklmnopqrstuvwxyz0123"',
    'SLACK = "xoxb-123456789012-abcdefghijkl"',
    "-----BEGIN RSA PRIVATE KEY-----\nMIIE...",
])
def test_token_like_content_is_blocked(tmp_path, contenu):
    """Un nom anodin ne doit pas suffire à faire passer un secret."""
    fichier = tmp_path / "config_anodin.py"
    fichier.write_text(contenu)
    bloque, raison = is_sensitive("config_anodin.py", tmp_path)
    assert bloque is True
    assert "contenu" in raison


def test_ordinary_content_passes(tmp_path):
    fichier = tmp_path / "module.py"
    fichier.write_text("def bonjour():\n    return 'salut'\n")
    bloque, _ = is_sensitive("module.py", tmp_path)
    assert bloque is False


def test_missing_file_does_not_block(tmp_path):
    bloque, _ = is_sensitive("inexistant.py", tmp_path)
    assert bloque is False


def test_binary_file_is_survivable(tmp_path):
    fichier = tmp_path / "image.png"
    fichier.write_bytes(bytes(range(256)) * 10)
    is_sensitive("image.png", tmp_path)  # ne doit pas lever


def test_check_without_root_uses_name_only():
    """Sans racine fournie, seul le nom est examiné — et ça suffit ici."""
    assert is_sensitive("backend/google_token.json.old")[0] is True
    assert is_sensitive("backend/ada.py")[0] is False
