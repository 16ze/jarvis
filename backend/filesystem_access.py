"""Accès universel en lecture seule au système de fichiers local."""

from __future__ import annotations

import fnmatch
import json
import mimetypes
import os
from pathlib import Path
import sqlite3
import time
from typing import Any


_CONTENT_READ_LIMIT = 2_000_000
_IGNORED_ABSOLUTE_DIRS = (
    os.path.realpath("/System"),
    os.path.realpath("/private/var/vm"),
)
_IGNORED_DIR_NAMES = {
    ".git",
    ".mypy_cache",
    ".next",
    ".pytest_cache",
    ".ruff_cache",
    "__pycache__",
    "build",
    "dist",
    "node_modules",
    "target",
}
_TEXT_MIME_SUFFIXES = ("+json", "+xml")
_TEXT_MIME_TYPES = {
    "application/javascript",
    "application/json",
    "application/sql",
    "application/xml",
}


def _normalize_path(path: Any) -> str:
    return os.path.realpath(os.path.expanduser(os.fspath(path)))


def _positive_int(value: Any, default: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return parsed if parsed > 0 else default


def _positive_float(value: Any, default: float) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return default
    return parsed if parsed > 0 else default


def _json(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2, default=str)


def _is_text_mime(mime_type: str | None) -> bool:
    if not mime_type:
        return True
    return (
        mime_type.startswith("text/")
        or mime_type in _TEXT_MIME_TYPES
        or mime_type.endswith(_TEXT_MIME_SUFFIXES)
    )


def _is_binary(path: str, sample: bytes) -> tuple[bool, str | None]:
    mime_type, _ = mimetypes.guess_type(path)
    return b"\x00" in sample or not _is_text_mime(mime_type), mime_type


def _error(action: str, path: Any, exc: BaseException) -> str:
    return f"Impossible de {action} « {path} » : {exc}."


def list_dir(path: str, show_hidden: bool = True, max_entries: int = 500) -> str:
    """Liste un dossier sans restreindre son emplacement."""
    try:
        normalized = _normalize_path(path)
        limit = _positive_int(max_entries, 500)
        entries = []
        with os.scandir(normalized) as iterator:
            for entry in iterator:
                if not show_hidden and entry.name.startswith("."):
                    continue
                stat = entry.stat(follow_symlinks=False)
                if entry.is_symlink():
                    entry_type = "symlink"
                elif entry.is_dir(follow_symlinks=False):
                    entry_type = "dir"
                else:
                    entry_type = "file"
                entries.append(
                    {
                        "name": entry.name,
                        "type": entry_type,
                        "size": stat.st_size,
                        "modified_at": time.strftime(
                            "%Y-%m-%dT%H:%M:%S%z", time.localtime(stat.st_mtime)
                        ),
                    }
                )

        entries.sort(
            key=lambda item: (
                0 if item["type"] == "dir" else 1,
                item["name"].casefold(),
            )
        )
        total = len(entries)
        return _json(
            {
                "path": normalized,
                "entries": entries[:limit],
                "count": min(total, limit),
                "total": total,
                "truncated": total > limit,
                "note": (
                    f"Liste tronquée à {limit} entrées sur {total}."
                    if total > limit
                    else None
                ),
            }
        )
    except Exception as exc:
        return _error("lister le dossier", path, exc)


def read_file(path: str, max_bytes: int = 2_000_000) -> str:
    """Lit un fichier texte ou renvoie les métadonnées d'un fichier binaire."""
    try:
        normalized = _normalize_path(path)
        limit = _positive_int(max_bytes, 2_000_000)
        if not os.path.isfile(normalized):
            return f"Impossible de lire « {normalized} » : fichier absent ou non régulier."

        size = os.path.getsize(normalized)
        with open(normalized, "rb") as handle:
            data = handle.read(limit + 1)

        binary, mime_type = _is_binary(normalized, data[:8192])
        if binary:
            return _json(
                {
                    "path": normalized,
                    "type": "binary",
                    "mime_type": mime_type or "application/octet-stream",
                    "size": size,
                    "note": "Fichier binaire : contenu non affiché.",
                }
            )

        truncated = size > limit
        content = data[:limit].decode("utf-8", errors="replace")
        if truncated:
            content += (
                f"\n\n[Lecture tronquée à {limit} / {size} octets.]"
            )
        return content
    except Exception as exc:
        return _error("lire le fichier", path, exc)


def _is_explicitly_inside(root: str, ignored: str) -> bool:
    try:
        return os.path.commonpath((root, ignored)) == ignored
    except ValueError:
        return False


def _should_skip_dir(path: str, root: str) -> bool:
    name = os.path.basename(path)
    if name in _IGNORED_DIR_NAMES and path != root:
        return True
    return any(
        _is_explicitly_inside(path, ignored)
        and not _is_explicitly_inside(root, ignored)
        for ignored in _IGNORED_ABSOLUTE_DIRS
    )


def _name_matches(name: str, query: str) -> bool:
    folded_name = name.casefold()
    folded_query = query.casefold()
    return folded_query in folded_name or fnmatch.fnmatch(folded_name, folded_query)


def _content_matches(
    path: str, query: str, deadline: float
) -> list[dict[str, Any]]:
    if os.path.getsize(path) > _CONTENT_READ_LIMIT:
        return []
    with open(path, "rb") as handle:
        data = handle.read(_CONTENT_READ_LIMIT + 1)
    if time.monotonic() >= deadline or len(data) > _CONTENT_READ_LIMIT:
        return []
    binary, _ = _is_binary(path, data[:8192])
    if binary:
        return []

    needle = query.casefold()
    matches = []
    for line_number, line in enumerate(
        data.decode("utf-8", errors="replace").splitlines(), start=1
    ):
        if time.monotonic() >= deadline:
            break
        if needle in line.casefold():
            matches.append(
                {
                    "path": path,
                    "line": line_number,
                    "excerpt": line.strip()[:500],
                }
            )
    return matches


def search_files(
    query: str,
    root: str = "~",
    mode: str = "name",
    max_results: int = 100,
    max_depth: int = 8,
    timeout_s: float = 20,
) -> str:
    """Recherche des fichiers par nom ou contenu avec des bornes de ressources."""
    try:
        if not isinstance(query, str) or not query.strip():
            return "Recherche impossible : la requête est vide."
        if mode not in {"name", "content"}:
            return "Recherche impossible : le mode doit être « name » ou « content »."

        normalized_root = _normalize_path(root)
        if not os.path.exists(normalized_root):
            return f"Recherche impossible : le chemin « {normalized_root} » n'existe pas."

        limit = _positive_int(max_results, 100)
        depth_limit = _positive_int(max_depth, 8)
        timeout = _positive_float(timeout_s, 20.0)
        deadline = time.monotonic() + timeout
        results: list[Any] = []
        timed_out = False
        limit_reached = False

        def inspect_file(file_path: str) -> None:
            nonlocal timed_out, limit_reached
            if time.monotonic() >= deadline:
                timed_out = True
                return
            try:
                if mode == "name":
                    if _name_matches(os.path.basename(file_path), query):
                        results.append(file_path)
                else:
                    for match in _content_matches(file_path, query, deadline):
                        results.append(match)
                        if len(results) >= limit:
                            limit_reached = True
                            break
            except (OSError, UnicodeError):
                return
            if len(results) >= limit:
                limit_reached = True

        if os.path.isfile(normalized_root):
            inspect_file(normalized_root)
        else:
            for current_root, dirs, files in os.walk(
                normalized_root, topdown=True, followlinks=False
            ):
                if time.monotonic() >= deadline or limit_reached:
                    timed_out = time.monotonic() >= deadline
                    break

                relative = os.path.relpath(current_root, normalized_root)
                depth = 0 if relative == "." else relative.count(os.sep) + 1
                dirs[:] = sorted(
                    (
                        name
                        for name in dirs
                        if not _should_skip_dir(
                            os.path.join(current_root, name), normalized_root
                        )
                    ),
                    key=str.casefold,
                )
                if depth >= depth_limit:
                    dirs[:] = []

                for filename in sorted(files, key=str.casefold):
                    inspect_file(os.path.join(current_root, filename))
                    if timed_out or limit_reached:
                        break

        return _json(
            {
                "query": query,
                "root": normalized_root,
                "mode": mode,
                "results": results[:limit],
                "count": min(len(results), limit),
                "truncated": limit_reached,
                "timed_out": timed_out,
            }
        )
    except Exception as exc:
        return _error("rechercher dans", root, exc)


def _sqlite_value(value: Any) -> Any:
    if isinstance(value, bytes):
        return {"type": "binary", "size": len(value)}
    return value


def read_sqlite(path: str, query: str | None = None, max_rows: int = 200) -> str:
    """Interroge une base SQLite via une connexion immuable en lecture seule."""
    try:
        normalized = _normalize_path(path)
        if not os.path.isfile(normalized):
            return f"Impossible de lire la base « {normalized} » : fichier absent."

        statement = query.strip() if isinstance(query, str) and query.strip() else None
        if statement:
            first_keyword = statement.split(maxsplit=1)[0].casefold().rstrip(";")
            if first_keyword not in {"select", "pragma"}:
                return "Requête refusée : seules les requêtes SELECT et PRAGMA sont autorisées."

        limit = _positive_int(max_rows, 200)
        uri = f"file:{normalized}?mode=ro&immutable=1"
        with sqlite3.connect(uri, uri=True, timeout=1.0) as connection:
            connection.execute("PRAGMA query_only = ON")
            cursor = connection.execute(
                statement
                or "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
            )
            columns = [description[0] for description in cursor.description or ()]
            raw_rows = cursor.fetchmany(limit + 1)

        truncated = len(raw_rows) > limit
        rows = [
            {
                column: _sqlite_value(value)
                for column, value in zip(columns, row)
            }
            for row in raw_rows[:limit]
        ]
        return _json(
            {
                "path": normalized,
                "query": statement or "liste des tables",
                "columns": columns,
                "rows": rows,
                "count": len(rows),
                "truncated": truncated,
            }
        )
    except Exception as exc:
        return _error("lire la base SQLite", path, exc)
