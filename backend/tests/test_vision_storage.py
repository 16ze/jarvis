"""Tests du stockage vision (SQLite + ChromaDB)."""
import sqlite3
import time

from yolo_detector import Detection
from vision_deduplicator import EventType, ObjectEvent
from vision_storage import _VisionStorage


def _evt(
    event_type: EventType = EventType.APPEARED,
    track_id: int = 1,
    cls_fr: str = "téléphone",
    ts: float = 1000.0,
    source: str = "camera",
) -> ObjectEvent:
    det = Detection(
        class_id=0, class_name="Mobile phone", class_fr=cls_fr,
        confidence=0.9, bbox=(0.5, 0.5, 0.1, 0.1), track_id=track_id,
    )
    return ObjectEvent(
        event_id=f"evt_{track_id}_{event_type.value}_{int(ts)}",
        event_type=event_type, source=source, timestamp=ts,
        detection=det, track_id=track_id,
    )


def test_storage_creates_schema_on_init(temp_db_path, mock_memory_manager):
    _VisionStorage(db_path=temp_db_path, memory_manager=mock_memory_manager)
    conn = sqlite3.connect(temp_db_path)
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert "object_events" in tables
    assert "current_objects" in tables


def test_storage_persists_appeared_event(temp_db_path, mock_memory_manager):
    storage = _VisionStorage(db_path=temp_db_path, memory_manager=mock_memory_manager)
    storage.persist([_evt(event_type=EventType.APPEARED, track_id=42, cls_fr="chat")])

    conn = sqlite3.connect(temp_db_path)
    rows = conn.execute(
        "SELECT event_type, class_fr, track_id FROM object_events"
    ).fetchall()
    assert rows == [("appeared", "chat", 42)]

    current = conn.execute(
        "SELECT track_id, class_fr, is_present FROM current_objects"
    ).fetchall()
    assert current == [(42, "chat", 1)]


def test_storage_marks_object_absent_on_disappeared(temp_db_path, mock_memory_manager):
    storage = _VisionStorage(db_path=temp_db_path, memory_manager=mock_memory_manager)
    storage.persist([_evt(EventType.APPEARED, track_id=5)])
    storage.persist([_evt(EventType.DISAPPEARED, track_id=5, ts=1010.0)])

    conn = sqlite3.connect(temp_db_path)
    is_present = conn.execute(
        "SELECT is_present FROM current_objects WHERE track_id = 5"
    ).fetchone()[0]
    assert is_present == 0


def test_storage_indexes_only_appeared_and_moved_in_chroma(temp_db_path, mock_memory_manager):
    storage = _VisionStorage(db_path=temp_db_path, memory_manager=mock_memory_manager)
    storage.persist([
        _evt(EventType.APPEARED, track_id=1),
        _evt(EventType.MOVED, track_id=2),
        _evt(EventType.DISAPPEARED, track_id=3),
        _evt(EventType.UPDATED, track_id=4),
    ])
    assert mock_memory_manager.vision_collection.add.call_count == 2


def test_query_recent_by_class(temp_db_path, mock_memory_manager):
    storage = _VisionStorage(db_path=temp_db_path, memory_manager=mock_memory_manager)
    storage.persist([_evt(EventType.APPEARED, track_id=1, cls_fr="livre", ts=1000.0)])
    storage.persist([_evt(EventType.APPEARED, track_id=2, cls_fr="livre", ts=2000.0)])
    storage.persist([_evt(EventType.APPEARED, track_id=3, cls_fr="chat",  ts=1500.0)])

    results = storage.query_by_class("livre", since_ts=0.0, max_results=10)
    assert len(results) == 2
    assert results[0]["timestamp"] >= results[1]["timestamp"]


def test_count_distinct_track_ids(temp_db_path, mock_memory_manager):
    storage = _VisionStorage(db_path=temp_db_path, memory_manager=mock_memory_manager)
    for ts in (1000.0, 1001.0, 1002.0):
        storage.persist([_evt(EventType.APPEARED, track_id=1, cls_fr="chat", ts=ts)])
    storage.persist([_evt(EventType.APPEARED, track_id=2, cls_fr="chat", ts=1100.0)])

    count = storage.count_distinct("chat", since_ts=0.0, until_ts=9999.0)
    assert count == 2


def test_get_current_objects_present(temp_db_path, mock_memory_manager):
    storage = _VisionStorage(db_path=temp_db_path, memory_manager=mock_memory_manager)
    storage.persist([
        _evt(EventType.APPEARED, track_id=1, cls_fr="téléphone"),
        _evt(EventType.APPEARED, track_id=2, cls_fr="chat"),
    ])
    storage.persist([_evt(EventType.DISAPPEARED, track_id=2, cls_fr="chat", ts=1010.0)])

    current = storage.get_current_objects()
    classes = sorted([o["class_fr"] for o in current])
    assert classes == ["téléphone"]


def test_cleanup_removes_old_events(temp_db_path, mock_memory_manager):
    storage = _VisionStorage(db_path=temp_db_path, memory_manager=mock_memory_manager)
    storage.persist([_evt(EventType.APPEARED, track_id=1, ts=1.0)])
    storage.persist([_evt(EventType.APPEARED, track_id=2, ts=time.time())])

    deleted = storage.cleanup_older_than(retention_days=30)
    assert deleted == 1

    conn = sqlite3.connect(temp_db_path)
    remaining = conn.execute("SELECT COUNT(*) FROM object_events").fetchone()[0]
    assert remaining == 1
