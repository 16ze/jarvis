"""
WorkspaceManager — stockage local des workspaces ADA OS.

Les workspaces vivent sous projects/<workspace>/workspace afin de rester lisibles
dans le repo tout en gardant un index SQLite fiable pour l'UI.
"""

from __future__ import annotations

import json
import re
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path


ITEM_KINDS = {"note", "source", "artifact", "capture", "task"}


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _slugify(value: str, fallback: str = "workspace") -> str:
    safe = re.sub(r"[^a-zA-Z0-9 _-]+", "", value or "").strip()
    safe = re.sub(r"\s+", "-", safe)
    return safe[:80] or fallback


class WorkspaceManager:
    def __init__(self, jarvis_root: Path | str):
        self.root = Path(jarvis_root).resolve()
        self.projects_dir = self.root / "projects"
        self.projects_dir.mkdir(parents=True, exist_ok=True)
        self.active_file = self.projects_dir / ".active_workspace"

    # ─── Public API ──────────────────────────────────────────────────────────

    def create_workspace(self, name: str, goal: str | None = None) -> str:
        workspace_name = self._safe_workspace_name(name)
        paths = self._ensure_workspace_dirs(workspace_name)
        self._ensure_db(paths["db"])
        self._set_active(workspace_name)
        if goal:
            self._write_goal(paths["workspace"], goal)
        self._record_event("workspace_created", {"name": workspace_name, "goal": goal})
        return f"Workspace '{workspace_name}' prêt."

    def switch_workspace(self, name: str) -> str:
        workspace_name = self._safe_workspace_name(name)
        if not self._workspace_dir(workspace_name).exists():
            return f"Workspace '{workspace_name}' introuvable."
        self._set_active(workspace_name)
        self._record_event("workspace_switched", {"name": workspace_name})
        return f"Workspace actif : {workspace_name}."

    def get_active_workspace(self) -> dict:
        name = self._active_name()
        paths = self._ensure_workspace_dirs(name)
        self._ensure_db(paths["db"])
        return {
            "activeWorkspace": name,
            "goal": self._read_goal(paths["workspace"]),
            "items": self.list_items(),
        }

    def add_source(self, url: str, title: str, summary: str) -> str:
        name = self._active_name()
        filename = f"{_utc_now().replace(':', '-')}-{_slugify(title, 'source')}.md"
        path = self._write_workspace_file(
            name=name,
            folder="sources",
            filename=filename,
            content=f"# {title}\n\nURL: {url}\n\n{summary}\n",
        )
        item = self._insert_item(
            kind="source",
            title=title,
            path=path,
            url=url,
            summary=summary,
            tags=[],
        )
        return item["id"]

    def add_note(self, title: str, content: str, tags: list[str] | None = None) -> str:
        filename = f"{_utc_now().replace(':', '-')}-{_slugify(title, 'note')}.md"
        path = self._write_workspace_file(
            name=self._active_name(),
            folder="notes",
            filename=filename,
            content=f"# {title}\n\n{content}\n",
        )
        item = self._insert_item(
            kind="note",
            title=title,
            path=path,
            summary=content[:500],
            tags=tags or [],
        )
        return item["id"]

    def add_artifact(self, filename: str, content: str, kind: str = "artifact") -> str:
        if kind not in ITEM_KINDS:
            kind = "artifact"
        safe_filename = Path(filename).name or "artifact.md"
        path = self._write_workspace_file(
            name=self._active_name(),
            folder="artifacts",
            filename=safe_filename,
            content=content,
        )
        item = self._insert_item(
            kind=kind,
            title=Path(safe_filename).stem,
            path=path,
            summary=content[:500],
            tags=[],
        )
        return item["id"]

    def list_items(self, kind: str | None = None) -> list[dict]:
        name = self._active_name()
        db_path = self._ensure_workspace_dirs(name)["db"]
        self._ensure_db(db_path)
        normalized_kind = None if kind in (None, "", "all") else kind
        query = (
            "SELECT id, kind, title, path, url, summary, tags_json, created_at, updated_at "
            "FROM workspace_items"
        )
        params: list[str] = []
        if normalized_kind:
            query += " WHERE kind = ?"
            params.append(normalized_kind.rstrip("s"))
        query += " ORDER BY created_at DESC"
        with sqlite3.connect(db_path) as conn:
            rows = conn.execute(query, params).fetchall()
        return [self._row_to_item(row) for row in rows]

    def record_event(self, event_type: str, payload: dict) -> str:
        return self._record_event(event_type, payload)

    # ─── Internals ───────────────────────────────────────────────────────────

    def _safe_workspace_name(self, name: str) -> str:
        return _slugify(name, "default")

    def _workspace_dir(self, name: str) -> Path:
        return self._validate_path(self.projects_dir / name)

    def _ensure_workspace_dirs(self, name: str) -> dict[str, Path]:
        project_dir = self._workspace_dir(name)
        workspace_dir = self._validate_path(project_dir / "workspace")
        paths = {
            "project": project_dir,
            "workspace": workspace_dir,
            "db": workspace_dir / "manifest.sqlite",
        }
        for folder in ("notes", "sources", "artifacts", "captures", "exports"):
            paths[folder] = workspace_dir / folder
        for path in paths.values():
            if path.suffix != ".sqlite":
                path.mkdir(parents=True, exist_ok=True)
        return paths

    def _ensure_db(self, db_path: Path) -> None:
        with sqlite3.connect(db_path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS workspace_items(
                  id TEXT PRIMARY KEY,
                  kind TEXT NOT NULL,
                  title TEXT NOT NULL,
                  path TEXT,
                  url TEXT,
                  summary TEXT,
                  tags_json TEXT NOT NULL DEFAULT '[]',
                  created_at TEXT NOT NULL,
                  updated_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS workspace_events(
                  id TEXT PRIMARY KEY,
                  event_type TEXT NOT NULL,
                  payload_json TEXT NOT NULL,
                  created_at TEXT NOT NULL
                )
                """
            )
            conn.commit()

    def _active_name(self) -> str:
        if self.active_file.exists():
            value = self.active_file.read_text(encoding="utf-8").strip()
            if value:
                return self._safe_workspace_name(value)
        self.create_workspace("default")
        return "default"

    def _set_active(self, name: str) -> None:
        self.active_file.write_text(self._safe_workspace_name(name), encoding="utf-8")

    def _write_goal(self, workspace_dir: Path, goal: str) -> None:
        (workspace_dir / "goal.md").write_text(goal.strip() + "\n", encoding="utf-8")

    def _read_goal(self, workspace_dir: Path) -> str | None:
        goal_path = workspace_dir / "goal.md"
        if not goal_path.exists():
            return None
        return goal_path.read_text(encoding="utf-8").strip() or None

    def _write_workspace_file(self, name: str, folder: str, filename: str, content: str) -> str:
        paths = self._ensure_workspace_dirs(name)
        target = self._validate_path(paths[folder] / Path(filename).name)
        if target.exists():
            stem, suffix = target.stem, target.suffix
            target = target.with_name(f"{stem}-{uuid.uuid4().hex[:8]}{suffix}")
        target.write_text(content, encoding="utf-8")
        return str(target.relative_to(self.root))

    def _insert_item(
        self,
        kind: str,
        title: str,
        path: str | None = None,
        url: str | None = None,
        summary: str | None = None,
        tags: list[str] | None = None,
    ) -> dict:
        now = _utc_now()
        item_id = uuid.uuid4().hex
        db_path = self._ensure_workspace_dirs(self._active_name())["db"]
        with sqlite3.connect(db_path) as conn:
            conn.execute(
                """
                INSERT INTO workspace_items
                (id, kind, title, path, url, summary, tags_json, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    item_id,
                    kind,
                    title,
                    path,
                    url,
                    summary,
                    json.dumps(tags or [], ensure_ascii=False),
                    now,
                    now,
                ),
            )
            conn.commit()
        item = {
            "id": item_id,
            "kind": kind,
            "title": title,
            "path": path,
            "url": url,
            "summary": summary,
            "tags": tags or [],
            "createdAt": now,
            "updatedAt": now,
        }
        self._record_event("item_created", item)
        return item

    def _record_event(self, event_type: str, payload: dict) -> str:
        event_id = uuid.uuid4().hex
        now = _utc_now()
        db_path = self._ensure_workspace_dirs(self._active_name())["db"]
        with sqlite3.connect(db_path) as conn:
            conn.execute(
                "INSERT INTO workspace_events (id, event_type, payload_json, created_at) VALUES (?, ?, ?, ?)",
                (event_id, event_type, json.dumps(payload, ensure_ascii=False), now),
            )
            conn.commit()
        return event_id

    def _validate_path(self, path: Path) -> Path:
        resolved = path.resolve()
        if not resolved.is_relative_to(self.root):
            raise ValueError("Chemin hors de JARVIS_ROOT refusé.")
        return resolved

    @staticmethod
    def _row_to_item(row: tuple) -> dict:
        return {
            "id": row[0],
            "kind": row[1],
            "title": row[2],
            "path": row[3],
            "url": row[4],
            "summary": row[5],
            "tags": json.loads(row[6] or "[]"),
            "createdAt": row[7],
            "updatedAt": row[8],
        }
