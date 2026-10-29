"""Tests de reminder_manager.ReminderManager.

Couvre création / liste / suppression / persistance sur un fichier temporaire
(aucun réseau, aucune clé API). Le chemin de stockage est redirigé vers tmp_path
via monkeypatch du global REMINDERS_PATH avant chaque instanciation.
"""
import json

import pytest

import reminder_manager
from reminder_manager import ReminderManager

FUTURE_ISO = "2099-01-01T10:00:00"


@pytest.fixture
def store_path(tmp_path, monkeypatch):
    """Redirige le JSON des rappels vers un fichier temporaire isolé."""
    path = tmp_path / "memory" / "reminders.json"
    monkeypatch.setattr(reminder_manager, "REMINDERS_PATH", path)
    return path


def _extract_id(confirmation: str) -> str:
    # "Rappel #ab12cd34 créé : ..." → "ab12cd34"
    assert "#" in confirmation
    return confirmation.split("#", 1)[1].split(" ", 1)[0]


def test_set_creates_reminder_and_persists(store_path):
    mgr = ReminderManager()
    result = mgr.set("acheter du pain", FUTURE_ISO)

    assert isinstance(result, str)
    assert "créé" in result
    rid = _extract_id(result)
    assert len(rid) == 8

    # Persistance sur disque
    assert store_path.exists()
    data = json.loads(store_path.read_text(encoding="utf-8"))
    assert len(data) == 1
    assert data[0]["id"] == rid
    assert data[0]["message"] == "acheter du pain"
    # trigger_utc normalisé en UTC (suffixe +00:00)
    assert data[0]["trigger_utc"].endswith("+00:00")


def test_list_reminders_empty(store_path):
    mgr = ReminderManager()
    assert mgr.list_reminders() == "Aucun rappel actif."


def test_list_reminders_shows_created(store_path):
    mgr = ReminderManager()
    mgr.set("réunion équipe", FUTURE_ISO)
    listing = mgr.list_reminders()
    assert "réunion équipe" in listing
    assert "#" in listing


def test_delete_removes_and_persists(store_path):
    mgr = ReminderManager()
    rid = _extract_id(mgr.set("rappel à virer", FUTURE_ISO))

    res = mgr.delete(rid)
    assert "supprimé" in res

    assert mgr.list_reminders() == "Aucun rappel actif."
    data = json.loads(store_path.read_text(encoding="utf-8"))
    assert data == []


def test_delete_unknown_id_is_graceful(store_path):
    mgr = ReminderManager()
    res = mgr.delete("deadbeef")
    assert "introuvable" in res


def test_persistence_across_instances(store_path):
    mgr1 = ReminderManager()
    rid = _extract_id(mgr1.set("persiste-moi", FUTURE_ISO))

    # Nouvelle instance : doit recharger depuis le même fichier
    mgr2 = ReminderManager()
    listing = mgr2.list_reminders()
    assert "persiste-moi" in listing
    assert rid in listing


def test_invalid_date_returns_french_error_no_exception(store_path):
    mgr = ReminderManager()
    res = mgr.set("date pourrie", "pas-une-date")
    assert isinstance(res, str)
    assert "invalide" in res.lower()
    # Rien n'a été persisté
    assert not store_path.exists() or json.loads(store_path.read_text()) == []


def test_set_with_timezone_aware_iso(store_path):
    mgr = ReminderManager()
    res = mgr.set("avec tz", "2099-01-01T10:00:00+02:00")
    assert "créé" in res
    data = json.loads(store_path.read_text(encoding="utf-8"))
    # 10:00 Paris (+02:00) → 08:00 UTC
    assert "T08:00:00+00:00" in data[0]["trigger_utc"]
