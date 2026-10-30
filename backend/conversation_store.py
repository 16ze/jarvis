"""Stockage canonique des conversations Ada pour la synchronisation multi-device.

Le frontend reste offline-first avec ``localStorage``. Ce module centralise une
copie transactionnelle dans SQLite et fusionne les snapshots par conversation
selon une règle Last-Write-Wins déterministe.
"""

from __future__ import annotations

import json
import re
import sqlite3
import time
from pathlib import Path
from typing import Any


MAX_CONVERSATIONS = 60
MAX_MESSAGES = 500
MAX_TOMBSTONES = 500
MAX_TEXT_CHARS = 100_000
MAX_CONVERSATION_BYTES = 2_000_000
MAX_FUTURE_CLOCK_SKEW_MS = 86_400_000

_SAFE_ID = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS conversation_records (
    id            TEXT PRIMARY KEY,
    payload_json  TEXT,
    version       INTEGER NOT NULL,
    device_id     TEXT NOT NULL,
    deleted       INTEGER NOT NULL DEFAULT 0 CHECK (deleted IN (0, 1))
);

CREATE TABLE IF NOT EXISTS conversation_meta (
    key    TEXT PRIMARY KEY,
    value  INTEGER NOT NULL
);

INSERT OR IGNORE INTO conversation_meta(key, value) VALUES ('revision', 0);
CREATE INDEX IF NOT EXISTS idx_conversation_records_version
    ON conversation_records(deleted, version DESC);
"""


class ConversationStore:
    """Fusionne et persiste les conversations d'un propriétaire Ada unique."""

    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path)
        parent_existed = self.db_path.parent.exists()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        if not parent_existed:
            self._chmod_if_possible(self.db_path.parent, 0o700)
        self._init_schema()
        self._secure_database_files()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=5.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA busy_timeout = 5000")
        conn.execute("PRAGMA journal_mode = WAL")
        self._secure_database_files()
        return conn

    def _init_schema(self) -> None:
        with self._connect() as conn:
            conn.executescript(_SCHEMA)

    def sync(
        self,
        device_id: str,
        conversations: list[dict[str, Any]],
        tombstones: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Fusionne un snapshot client et retourne l'état canonique complet.

        ``updatedAt`` et ``deletedAt`` sont des versions millisecondes générées
        par les appareils. En cas d'égalité, une suppression gagne, puis le
        ``device_id`` tranche de façon stable.
        """

        safe_device_id = self._validate_id(device_id, "deviceId")
        safe_conversations = self._validate_conversations(conversations)
        safe_tombstones = self._validate_tombstones(tombstones)

        conn = self._connect()
        changed = False
        try:
            conn.execute("BEGIN IMMEDIATE")
            for conversation in safe_conversations:
                changed |= self._merge_record(
                    conn=conn,
                    record_id=conversation["id"],
                    version=conversation["updatedAt"],
                    device_id=safe_device_id,
                    deleted=False,
                    payload=conversation,
                )
            for tombstone in safe_tombstones:
                changed |= self._merge_record(
                    conn=conn,
                    record_id=tombstone["id"],
                    version=tombstone["deletedAt"],
                    device_id=safe_device_id,
                    deleted=True,
                    payload=None,
                )

            changed |= self._enforce_active_limit(conn)
            if changed:
                conn.execute(
                    "UPDATE conversation_meta SET value = value + 1 WHERE key = 'revision'"
                )
            result = self._export_state(conn)
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()
            self._secure_database_files()

        result["changed"] = changed
        return result

    def snapshot(self) -> dict[str, Any]:
        """Retourne l'état canonique sans appliquer de mutation."""

        with self._connect() as conn:
            result = self._export_state(conn)
        self._secure_database_files()
        result["changed"] = False
        return result

    def _merge_record(
        self,
        conn: sqlite3.Connection,
        record_id: str,
        version: int,
        device_id: str,
        deleted: bool,
        payload: dict[str, Any] | None,
    ) -> bool:
        current = conn.execute(
            "SELECT payload_json, version, device_id, deleted "
            "FROM conversation_records WHERE id = ?",
            (record_id,),
        ).fetchone()
        payload_json = None if deleted else json.dumps(
            payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True
        )

        if current is not None:
            current_key = (
                int(current["version"]),
                int(current["deleted"]),
                str(current["device_id"]),
            )
            incoming_key = (version, int(deleted), device_id)
            same_value = current_key == incoming_key and current["payload_json"] == payload_json
            if same_value or incoming_key <= current_key:
                return False

        conn.execute(
            """INSERT INTO conversation_records(id, payload_json, version, device_id, deleted)
               VALUES (?, ?, ?, ?, ?)
               ON CONFLICT(id) DO UPDATE SET
                   payload_json = excluded.payload_json,
                   version = excluded.version,
                   device_id = excluded.device_id,
                   deleted = excluded.deleted""",
            (record_id, payload_json, version, device_id, int(deleted)),
        )
        return True

    def _enforce_active_limit(self, conn: sqlite3.Connection) -> bool:
        rows = conn.execute(
            """SELECT id, version FROM conversation_records
               WHERE deleted = 0
               ORDER BY version DESC, device_id DESC, id DESC"""
        ).fetchall()
        if len(rows) <= MAX_CONVERSATIONS:
            return False

        now_ms = time.time_ns() // 1_000_000
        for row in rows[MAX_CONVERSATIONS:]:
            deleted_at = max(now_ms, int(row["version"]) + 1)
            conn.execute(
                """UPDATE conversation_records
                   SET payload_json = NULL, version = ?, device_id = ?, deleted = 1
                   WHERE id = ?""",
                (deleted_at, "__server__", row["id"]),
            )
        return True

    def _export_state(self, conn: sqlite3.Connection) -> dict[str, Any]:
        revision_row = conn.execute(
            "SELECT value FROM conversation_meta WHERE key = 'revision'"
        ).fetchone()
        rows = conn.execute(
            """SELECT id, payload_json, version, deleted
               FROM conversation_records
               ORDER BY version DESC, id DESC"""
        ).fetchall()
        conversations: list[dict[str, Any]] = []
        tombstones: list[dict[str, Any]] = []
        for row in rows:
            if row["deleted"]:
                tombstones.append({"id": row["id"], "deletedAt": int(row["version"])})
            elif row["payload_json"]:
                conversations.append(json.loads(row["payload_json"]))
        return {
            "revision": int(revision_row["value"]) if revision_row else 0,
            "conversations": conversations,
            "tombstones": tombstones,
        }

    def _validate_conversations(
        self, conversations: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        if not isinstance(conversations, list):
            raise ValueError("conversations doit être une liste")
        if len(conversations) > MAX_CONVERSATIONS:
            raise ValueError(f"maximum {MAX_CONVERSATIONS} conversations par synchronisation")

        seen: set[str] = set()
        normalized: list[dict[str, Any]] = []
        for raw in conversations:
            if not isinstance(raw, dict):
                raise ValueError("conversation invalide")
            conversation_id = self._validate_id(raw.get("id"), "conversation.id")
            if conversation_id in seen:
                raise ValueError(f"conversation dupliquée: {conversation_id}")
            seen.add(conversation_id)

            title = raw.get("title", "Nouvelle conversation")
            if not isinstance(title, str) or len(title) > 200:
                raise ValueError("conversation.title invalide")
            updated_at = self._validate_version(raw.get("updatedAt"), "updatedAt")
            messages = raw.get("messages", [])
            if not isinstance(messages, list) or len(messages) > MAX_MESSAGES:
                raise ValueError(f"maximum {MAX_MESSAGES} messages par conversation")

            safe_messages = [self._validate_message(message) for message in messages]
            conversation = {
                "id": conversation_id,
                "title": title.strip() or "Nouvelle conversation",
                "messages": safe_messages,
                "updatedAt": updated_at,
            }
            encoded = json.dumps(conversation, ensure_ascii=False).encode("utf-8")
            if len(encoded) > MAX_CONVERSATION_BYTES:
                raise ValueError("conversation trop volumineuse")
            normalized.append(conversation)
        return normalized

    def _validate_tombstones(
        self, tombstones: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        if not isinstance(tombstones, list):
            raise ValueError("tombstones doit être une liste")
        if len(tombstones) > MAX_TOMBSTONES:
            raise ValueError(f"maximum {MAX_TOMBSTONES} tombstones")
        seen: set[str] = set()
        normalized: list[dict[str, Any]] = []
        for raw in tombstones:
            if not isinstance(raw, dict):
                raise ValueError("tombstone invalide")
            record_id = self._validate_id(raw.get("id"), "tombstone.id")
            if record_id in seen:
                raise ValueError(f"tombstone dupliqué: {record_id}")
            seen.add(record_id)
            normalized.append({
                "id": record_id,
                "deletedAt": self._validate_version(raw.get("deletedAt"), "deletedAt"),
            })
        return normalized

    @staticmethod
    def _validate_message(raw: Any) -> dict[str, Any]:
        if not isinstance(raw, dict):
            raise ValueError("message invalide")
        sender = raw.get("sender")
        text = raw.get("text")
        if not isinstance(sender, str) or not sender or len(sender) > 40:
            raise ValueError("message.sender invalide")
        if not isinstance(text, str) or len(text) > MAX_TEXT_CHARS:
            raise ValueError("message.text invalide")

        message: dict[str, Any] = {"sender": sender, "text": text}
        if "time" in raw:
            if not isinstance(raw["time"], str) or len(raw["time"]) > 64:
                raise ValueError("message.time invalide")
            message["time"] = raw["time"]
        if raw.get("edited") is True:
            message["edited"] = True
        return message

    @staticmethod
    def _validate_id(value: Any, field: str) -> str:
        if not isinstance(value, str) or not _SAFE_ID.fullmatch(value):
            raise ValueError(f"{field} invalide")
        return value

    @staticmethod
    def _validate_version(value: Any, field: str) -> int:
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise ValueError(f"{field} invalide")
        now_ms = time.time_ns() // 1_000_000
        if value > now_ms + MAX_FUTURE_CLOCK_SKEW_MS:
            raise ValueError(f"{field} trop éloigné dans le futur")
        return value

    def _secure_database_files(self) -> None:
        for suffix in ("", "-wal", "-shm"):
            path = Path(f"{self.db_path}{suffix}")
            if path.exists():
                self._chmod_if_possible(path, 0o600)

    @staticmethod
    def _chmod_if_possible(path: Path, mode: int) -> None:
        try:
            path.chmod(mode)
        except (OSError, NotImplementedError):
            # Windows et certains volumes externes ne proposent pas ces bits.
            pass
