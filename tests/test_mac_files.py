"""Tests des opérations fichiers natives (backend/mac_files.py).

Les opérations réelles sont testées dans un dossier temporaire isolé ; le
routage des phrases est testé sans rien exécuter sur le système.
"""

import asyncio
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

import mac_files as mf  # noqa: E402


def _run(coro):
    return asyncio.run(coro)


# ─── Opérations réelles (dossier temporaire) ──────────────────────────────────

def test_create_folder_is_writable(tmp_path):
    """Régression : mkdir en positionnel créait un dossier sans droits."""
    res = _run(mf.create_folder("dossier_test", str(tmp_path)))
    cible = tmp_path / "dossier_test"
    assert cible.is_dir()
    assert os.access(cible, os.W_OK), "le dossier créé doit être accessible en écriture"
    assert "créé" in res


def test_create_existing_folder_is_reported(tmp_path):
    _run(mf.create_folder("deja_la", str(tmp_path)))
    assert "existe déjà" in _run(mf.create_folder("deja_la", str(tmp_path)))


def test_rename_keeps_extension(tmp_path):
    f = tmp_path / "note.txt"
    f.write_text("x")
    _run(mf.rename_file(str(f), "renomme"))
    assert (tmp_path / "renomme.txt").exists(), "l'extension doit être conservée"


def test_rename_never_overwrites(tmp_path):
    (tmp_path / "a.txt").write_text("A")
    (tmp_path / "b.txt").write_text("B")
    res = _run(mf.rename_file(str(tmp_path / "a.txt"), "b.txt"))
    assert "existe déjà" in res
    assert (tmp_path / "b.txt").read_text() == "B", "le fichier cible est intact"


def test_move_file(tmp_path):
    src = tmp_path / "fichier.txt"
    src.write_text("contenu")
    dest = tmp_path / "sous_dossier"
    dest.mkdir()
    _run(mf.move_file(str(src), str(dest)))
    assert (dest / "fichier.txt").exists()
    assert not src.exists()


def test_move_never_overwrites(tmp_path):
    src = tmp_path / "x.txt"
    src.write_text("source")
    dest = tmp_path / "dest"
    dest.mkdir()
    (dest / "x.txt").write_text("existant")
    res = _run(mf.move_file(str(src), str(dest)))
    assert "existe déjà" in res
    assert (dest / "x.txt").read_text() == "existant"


def test_file_info_reports_size_and_date(tmp_path):
    f = tmp_path / "info.txt"
    f.write_text("douze mots")
    res = _run(mf.file_info(str(f)))
    assert "info.txt" in res and "fichier" in res


def test_read_text_file(tmp_path):
    f = tmp_path / "lecture.txt"
    f.write_text("Bonjour Ada")
    assert "Bonjour Ada" in _run(mf.read_text_file(str(f)))


def test_read_truncates_long_files(tmp_path):
    f = tmp_path / "long.txt"
    f.write_text("a" * 10000)
    assert "tronquée" in _run(mf.read_text_file(str(f), max_chars=100))


def test_read_directory_is_reported(tmp_path):
    assert "dossier" in _run(mf.read_text_file(str(tmp_path)))


def test_missing_target_is_reported():
    assert "Introuvable" in _run(mf.file_info("zzz_fichier_inexistant_xyz"))


def test_disk_usage_reports_space():
    res = _run(mf.disk_usage())
    assert "Disque" in res and "libres" in res


# ─── Routage des phrases (sans exécution système) ─────────────────────────────

@pytest.mark.parametrize("phrase", [
    "combien il me reste d'espace disque",
    "montre-moi mes fichiers récents",
    "cherche le fichier rapport",
    "crée un dossier Projets sur le bureau",
    "renomme photo en vacances",
    "supprime le fichier zzz_inexistant",
    "mets le fichier vieux truc à la corbeille",
    "jette zzz_inexistant à la corbeille",
])
def test_file_phrases_are_routed(phrase):
    assert _run(mf.route(phrase)) is not None


@pytest.mark.parametrize("phrase", [
    "ouvre TextEdit",
    "appelle Ivan",
    "ferme Safari",
    "règle la luminosité à 40%",
    "envoie un message à Ivan",
    "",
])
def test_other_phrases_are_left_alone(phrase):
    assert _run(mf.route(phrase)) is None
