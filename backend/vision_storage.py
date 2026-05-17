"""Stockage transactionnel des events vision (SQLite + ChromaDB).

SQLite → factuel (compte, time-range, classe).
ChromaDB → sémantique (recherche floue : "où j'ai laissé un truc rouge").
Une seule méthode publique d'écriture (`persist`) pour garantir la cohérence.
"""
from __future__ import annotations

import json
import logging
import sqlite3
import time
from datetime import datetime, timezone
from typing import Any

from vision_deduplicator import EventType, ObjectEvent

_LOG = logging.getLogger("vision_object")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS object_events (
    event_id        TEXT PRIMARY KEY,
    event_type      TEXT NOT NULL,
    source          TEXT NOT NULL,
    timestamp       REAL NOT NULL,
    timestamp_iso   TEXT NOT NULL,
    class_id        INTEGER NOT NULL,
    class_name      TEXT NOT NULL,
    class_fr        TEXT NOT NULL,
    confidence      REAL NOT NULL,
    bbox_x          REAL NOT NULL,
    bbox_y          REAL NOT NULL,
    bbox_w          REAL NOT NULL,
    bbox_h          REAL NOT NULL,
    track_id        INTEGER,
    location_hint   TEXT,
    metadata_json   TEXT
);

CREATE TABLE IF NOT EXISTS current_objects (
    track_id        INTEGER PRIMARY KEY,
    class_name      TEXT NOT NULL,
    class_fr        TEXT NOT NULL,
    source          TEXT NOT NULL,
    last_seen       REAL NOT NULL,
    bbox_x          REAL NOT NULL,
    bbox_y          REAL NOT NULL,
    bbox_w          REAL NOT NULL,
    bbox_h          REAL NOT NULL,
    confidence      REAL NOT NULL,
    is_present      INTEGER NOT NULL DEFAULT 1
);

CREATE INDEX IF NOT EXISTS idx_events_class_time   ON object_events(class_fr, timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_events_time         ON object_events(timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_events_source_time  ON object_events(source, timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_current_class       ON current_objects(class_fr);
"""


class _VisionStorage:
    """Stockage SQLite + ChromaDB. Tolère un memory_manager sans `vision_collection`."""

    def __init__(self, db_path: str, memory_manager: Any | None) -> None:
        self._db_path = db_path
        self._memory = memory_manager
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path, timeout=5.0)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_schema(self) -> None:
        with self._connect() as conn:
            conn.executescript(_SCHEMA)

    def persist(self, events: list[ObjectEvent]) -> None:
        """Persiste un batch d'events. Skip silencieusement si SQLite locked après retries.
        Indexe Chroma uniquement pour APPEARED + MOVED."""
        if not events:
            return

        for attempt in range(3):
            try:
                with self._connect() as conn:
                    for evt in events:
                        self._insert_event(conn, evt)
                        self._upsert_current(conn, evt)
                break
            except sqlite3.OperationalError as exc:
                if "locked" in str(exc).lower() and attempt < 2:
                    time.sleep(0.01 * (10 ** attempt))
                    continue
                _LOG.warning("[VISION_OBJ] SQLite persist failed: %s", exc)
                return

        if self._memory is not None and getattr(self._memory, "vision_collection", None) is not None:
            for evt in events:
                if evt.event_type in (EventType.APPEARED, EventType.MOVED):
                    self._index_chroma(evt)

    def _insert_event(self, conn: sqlite3.Connection, evt: ObjectEvent) -> None:
        iso = datetime.fromtimestamp(evt.timestamp, tz=timezone.utc).isoformat()
        xc, yc, w, h = evt.detection.bbox
        conn.execute(
            """INSERT OR REPLACE INTO object_events (
                event_id, event_type, source, timestamp, timestamp_iso,
                class_id, class_name, class_fr, confidence,
                bbox_x, bbox_y, bbox_w, bbox_h,
                track_id, location_hint, metadata_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                evt.event_id, evt.event_type.value, evt.source,
                evt.timestamp, iso,
                evt.detection.class_id, evt.detection.class_name, evt.detection.class_fr,
                evt.detection.confidence,
                xc, yc, w, h,
                evt.track_id, evt.location_hint, json.dumps(evt.metadata or {}),
            ),
        )

    def _upsert_current(self, conn: sqlite3.Connection, evt: ObjectEvent) -> None:
        if evt.track_id is None:
            return
        xc, yc, w, h = evt.detection.bbox
        if evt.event_type == EventType.DISAPPEARED:
            conn.execute(
                "UPDATE current_objects SET is_present = 0, last_seen = ? WHERE track_id = ?",
                (evt.timestamp, evt.track_id),
            )
            return
        conn.execute(
            """INSERT INTO current_objects (
                track_id, class_name, class_fr, source, last_seen,
                bbox_x, bbox_y, bbox_w, bbox_h, confidence, is_present
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)
            ON CONFLICT(track_id) DO UPDATE SET
                class_name = excluded.class_name,
                class_fr = excluded.class_fr,
                source = excluded.source,
                last_seen = excluded.last_seen,
                bbox_x = excluded.bbox_x, bbox_y = excluded.bbox_y,
                bbox_w = excluded.bbox_w, bbox_h = excluded.bbox_h,
                confidence = excluded.confidence,
                is_present = 1""",
            (
                evt.track_id, evt.detection.class_name, evt.detection.class_fr,
                evt.source, evt.timestamp,
                xc, yc, w, h, evt.detection.confidence,
            ),
        )

    def _index_chroma(self, evt: ObjectEvent) -> None:
        try:
            xc, yc, w, h = evt.detection.bbox
            iso = datetime.fromtimestamp(evt.timestamp, tz=timezone.utc).isoformat()
            doc = (
                f"{evt.detection.class_fr} vu sur {evt.source} à {iso} "
                f"position ({xc:.2f}, {yc:.2f}) confiance {evt.detection.confidence:.2f}"
            )
            self._memory.vision_collection.add(
                ids=[evt.event_id],
                documents=[doc],
                metadatas=[{
                    "class_name": evt.detection.class_name,
                    "class_fr": evt.detection.class_fr,
                    "source": evt.source,
                    "timestamp": evt.timestamp,
                    "track_id": evt.track_id if evt.track_id is not None else -1,
                    "bbox": json.dumps([xc, yc, w, h]),
                }],
            )
        except Exception as exc:
            _LOG.warning("[VISION_OBJ] Chroma index failed: %s", exc)

    def query_by_class(
        self, class_fr: str, since_ts: float, max_results: int = 10,
    ) -> list[dict]:
        with self._connect() as conn:
            rows = conn.execute(
                """SELECT event_id, event_type, source, timestamp, timestamp_iso,
                          class_fr, confidence, bbox_x, bbox_y, bbox_w, bbox_h,
                          track_id, location_hint
                   FROM object_events
                   WHERE class_fr LIKE ? AND timestamp >= ?
                   ORDER BY timestamp DESC
                   LIMIT ?""",
                (f"%{class_fr}%", since_ts, max_results),
            ).fetchall()
            return [dict(r) for r in rows]

    def count_distinct(
        self, class_fr: str, since_ts: float, until_ts: float,
    ) -> int:
        with self._connect() as conn:
            row = conn.execute(
                """SELECT COUNT(DISTINCT track_id) FROM object_events
                   WHERE class_fr LIKE ? AND event_type = 'appeared'
                     AND timestamp >= ? AND timestamp <= ?""",
                (f"%{class_fr}%", since_ts, until_ts),
            ).fetchone()
            return int(row[0]) if row else 0

    def get_current_objects(self) -> list[dict]:
        with self._connect() as conn:
            rows = conn.execute(
                """SELECT track_id, class_fr, source, last_seen,
                          bbox_x, bbox_y, bbox_w, bbox_h, confidence
                   FROM current_objects WHERE is_present = 1
                   ORDER BY last_seen DESC"""
            ).fetchall()
            return [dict(r) for r in rows]

    def cleanup_older_than(self, retention_days: int) -> int:
        cutoff = time.time() - retention_days * 86400.0
        with self._connect() as conn:
            cur = conn.execute("DELETE FROM object_events WHERE timestamp < ?", (cutoff,))
            deleted = cur.rowcount
            conn.execute(
                "DELETE FROM current_objects WHERE is_present = 0 AND last_seen < ?",
                (cutoff,),
            )
            conn.commit()
        # VACUUM ne peut PAS tourner dans une transaction → connexion autocommit séparée
        vacuum_conn = sqlite3.connect(self._db_path, timeout=5.0, isolation_level=None)
        try:
            vacuum_conn.execute("VACUUM")
        except sqlite3.OperationalError as exc:
            _LOG.warning("[VISION_OBJ] VACUUM skipped: %s", exc)
        finally:
            vacuum_conn.close()
        return deleted
