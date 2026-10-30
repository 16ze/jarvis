"""Tests du stockage canonique des conversations multi-device."""

import sqlite3
import stat
import time

import pytest

from conversation_store import MAX_CONVERSATIONS, MAX_MESSAGES, ConversationStore


def _conversation(
    conversation_id: str = "conv-1",
    updated_at: int = 100,
    text: str = "Bonjour Ada",
) -> dict:
    return {
        "id": conversation_id,
        "title": "Discussion",
        "messages": [{"sender": "Bryan", "text": text, "time": "10:00"}],
        "updatedAt": updated_at,
    }


def test_schema_et_round_trip_unicode(tmp_path):
    db_path = tmp_path / "conversations.sqlite"
    store = ConversationStore(db_path)
    result = store.sync("mac-bryan", [_conversation(text="Mémoire 🧠")], [])

    assert result["changed"] is True
    assert result["revision"] == 1
    assert result["conversations"][0]["messages"][0]["text"] == "Mémoire 🧠"

    with sqlite3.connect(db_path) as conn:
        tables = {row[0] for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        )}
    assert {"conversation_records", "conversation_meta"} <= tables


def test_version_plus_recente_gagne_et_snapshot_identique_est_idempotent(tmp_path):
    store = ConversationStore(tmp_path / "sync.sqlite")
    store.sync("mac", [_conversation(updated_at=200, text="récent")], [])

    stale = store.sync("iphone", [_conversation(updated_at=100, text="ancien")], [])
    same = store.sync("ipad", [_conversation(updated_at=200, text="récent")], [])

    assert stale["changed"] is False
    assert same["changed"] is False
    assert same["revision"] == 1
    assert same["conversations"][0]["messages"][0]["text"] == "récent"


def test_tombstone_empeche_resurrection_ancienne(tmp_path):
    store = ConversationStore(tmp_path / "sync.sqlite")
    store.sync("mac", [_conversation(updated_at=100)], [])
    deleted = store.sync("iphone", [], [{"id": "conv-1", "deletedAt": 200}])
    stale = store.sync("ipad", [_conversation(updated_at=150)], [])

    assert deleted["conversations"] == []
    assert stale["conversations"] == []
    assert stale["tombstones"] == [{"id": "conv-1", "deletedAt": 200}]


def test_tombstone_plus_recent_remplace_le_precedent(tmp_path):
    store = ConversationStore(tmp_path / "sync.sqlite")
    store.sync("mac", [_conversation(updated_at=100)], [])
    store.sync("iphone", [], [{"id": "conv-1", "deletedAt": 200}])
    refreshed = store.sync("ipad", [], [{"id": "conv-1", "deletedAt": 400}])
    stale = store.sync("mac", [_conversation(updated_at=300)], [])

    assert refreshed["changed"] is True
    assert refreshed["tombstones"] == [{"id": "conv-1", "deletedAt": 400}]
    assert stale["conversations"] == []


def test_recreation_explicite_plus_recente_remplace_tombstone(tmp_path):
    store = ConversationStore(tmp_path / "sync.sqlite")
    store.sync("mac", [_conversation(updated_at=100)], [])
    store.sync("iphone", [], [{"id": "conv-1", "deletedAt": 200}])
    recreated = store.sync("ipad", [_conversation(updated_at=201, text="recréée")], [])

    assert recreated["tombstones"] == []
    assert recreated["conversations"][0]["messages"][0]["text"] == "recréée"


def test_suppression_gagne_en_cas_egalite_de_version(tmp_path):
    store = ConversationStore(tmp_path / "sync.sqlite")
    store.sync("zz-device", [_conversation(updated_at=300)], [])
    result = store.sync("aa-device", [], [{"id": "conv-1", "deletedAt": 300}])

    assert result["conversations"] == []
    assert result["tombstones"][0]["deletedAt"] == 300


def test_egalite_active_est_tranchee_par_device_id(tmp_path):
    store = ConversationStore(tmp_path / "sync.sqlite")
    store.sync("device-a", [_conversation(updated_at=100, text="A")], [])
    result = store.sync("device-z", [_conversation(updated_at=100, text="Z")], [])
    ignored = store.sync("device-b", [_conversation(updated_at=100, text="B")], [])

    assert result["conversations"][0]["messages"][0]["text"] == "Z"
    assert ignored["changed"] is False


def test_deux_instances_partagent_revision_et_donnees(tmp_path):
    db_path = tmp_path / "sync.sqlite"
    first = ConversationStore(db_path)
    second = ConversationStore(db_path)

    first.sync("mac", [_conversation()], [])
    result = second.sync("iphone", [_conversation("conv-2", 200)], [])

    assert result["revision"] == 2
    assert [item["id"] for item in result["conversations"]] == ["conv-2", "conv-1"]


def test_limites_et_payloads_invalides_sont_refuses(tmp_path):
    store = ConversationStore(tmp_path / "sync.sqlite")

    with pytest.raises(ValueError, match="deviceId"):
        store.sync("device avec espaces", [], [])
    with pytest.raises(ValueError, match="maximum 60"):
        store.sync("mac", [_conversation(f"conv-{i}", i) for i in range(MAX_CONVERSATIONS + 1)], [])

    too_many_messages = _conversation()
    too_many_messages["messages"] = [
        {"sender": "Bryan", "text": str(i)} for i in range(MAX_MESSAGES + 1)
    ]
    with pytest.raises(ValueError, match="maximum 500"):
        store.sync("mac", [too_many_messages], [])

    invalid_message = _conversation()
    invalid_message["messages"] = [{"sender": "", "text": "x"}]
    with pytest.raises(ValueError, match="sender"):
        store.sync("mac", [invalid_message], [])


def test_entrees_ne_sont_pas_mutees(tmp_path):
    store = ConversationStore(tmp_path / "sync.sqlite")
    conversation = _conversation()
    tombstones = [{"id": "absente", "deletedAt": 50}]

    store.sync("mac", [conversation], tombstones)

    assert conversation == _conversation()
    assert tombstones == [{"id": "absente", "deletedAt": 50}]


def test_horloge_future_refusee_et_fichier_prive(tmp_path):
    db_path = tmp_path / "runtime" / "sync.sqlite"
    store = ConversationStore(db_path)
    future = int(time.time() * 1000) + 86_400_001

    with pytest.raises(ValueError, match="futur"):
        store.sync("mac", [_conversation(updated_at=future)], [])

    assert stat.S_IMODE(db_path.stat().st_mode) == 0o600
