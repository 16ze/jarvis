import json
import sqlite3

import filesystem_access


def test_read_file_returns_text(tmp_path):
    path = tmp_path / "bonjour.txt"
    path.write_text("Bonjour Ada", encoding="utf-8")

    assert filesystem_access.read_file(str(path)) == "Bonjour Ada"


def test_read_file_returns_binary_metadata(tmp_path):
    path = tmp_path / "image.bin"
    path.write_bytes(b"\x89PNG\x00contenu")

    result = json.loads(filesystem_access.read_file(str(path)))

    assert result["type"] == "binary"
    assert result["size"] == path.stat().st_size
    assert "contenu non affiché" in result["note"]


def test_read_file_truncates_large_text(tmp_path):
    path = tmp_path / "long.txt"
    path.write_text("abcdefghij", encoding="utf-8")

    result = filesystem_access.read_file(str(path), max_bytes=4)

    assert result.startswith("abcd")
    assert "tronquée à 4 / 10 octets" in result


def test_read_file_reports_missing_file_in_french(tmp_path):
    result = filesystem_access.read_file(str(tmp_path / "absent.txt"))

    assert "Impossible de lire" in result
    assert "absent" in result


def test_list_dir_sorts_directories_then_files_and_truncates(tmp_path):
    (tmp_path / "z-dossier").mkdir()
    (tmp_path / "a-dossier").mkdir()
    (tmp_path / "b.txt").write_text("b", encoding="utf-8")
    (tmp_path / "a.txt").write_text("a", encoding="utf-8")

    result = json.loads(
        filesystem_access.list_dir(str(tmp_path), max_entries=3)
    )

    assert [entry["name"] for entry in result["entries"]] == [
        "a-dossier",
        "z-dossier",
        "a.txt",
    ]
    assert result["truncated"] is True
    assert "tronquée" in result["note"]


def test_list_dir_can_hide_hidden_entries(tmp_path):
    (tmp_path / ".secret").write_text("secret", encoding="utf-8")
    (tmp_path / "visible").write_text("visible", encoding="utf-8")

    result = json.loads(
        filesystem_access.list_dir(str(tmp_path), show_hidden=False)
    )

    assert [entry["name"] for entry in result["entries"]] == ["visible"]


def test_search_files_finds_name_recursively(tmp_path):
    nested = tmp_path / "niveau"
    nested.mkdir()
    expected = nested / "rapport-final.txt"
    expected.write_text("contenu", encoding="utf-8")

    result = json.loads(
        filesystem_access.search_files("rapport*", root=str(tmp_path), mode="name")
    )

    assert result["results"] == [str(expected)]


def test_search_files_finds_content_with_line_number(tmp_path):
    path = tmp_path / "notes.txt"
    path.write_text("première ligne\nAda retrouve cette phrase\n", encoding="utf-8")

    result = json.loads(
        filesystem_access.search_files(
            "retrouve cette", root=str(tmp_path), mode="content"
        )
    )

    assert result["results"] == [
        {
            "path": str(path),
            "line": 2,
            "excerpt": "Ada retrouve cette phrase",
        }
    ]


def test_search_files_respects_max_results(tmp_path):
    for index in range(4):
        (tmp_path / f"match-{index}.txt").write_text("Ada", encoding="utf-8")

    result = json.loads(
        filesystem_access.search_files(
            "match", root=str(tmp_path), mode="name", max_results=2
        )
    )

    assert result["count"] == 2
    assert result["truncated"] is True


def _create_database(path):
    with sqlite3.connect(path) as connection:
        connection.execute("CREATE TABLE personnes (nom TEXT, age INTEGER)")
        connection.executemany(
            "INSERT INTO personnes VALUES (?, ?)",
            [("Bryan", 30), ("Ada", 1)],
        )


def test_read_sqlite_lists_tables_and_runs_select(tmp_path):
    path = tmp_path / "app.sqlite"
    _create_database(path)

    tables = json.loads(filesystem_access.read_sqlite(str(path)))
    rows = json.loads(
        filesystem_access.read_sqlite(
            str(path), "SELECT nom, age FROM personnes ORDER BY age"
        )
    )

    assert tables["rows"] == [{"name": "personnes"}]
    assert rows["columns"] == ["nom", "age"]
    assert rows["rows"] == [
        {"nom": "Ada", "age": 1},
        {"nom": "Bryan", "age": 30},
    ]


def test_read_sqlite_refuses_non_select_queries(tmp_path):
    path = tmp_path / "app.sqlite"
    _create_database(path)

    result = filesystem_access.read_sqlite(
        str(path), "DELETE FROM personnes"
    )

    assert "Requête refusée" in result
    with sqlite3.connect(path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM personnes").fetchone()[0] == 2


def test_read_sqlite_uses_immutable_read_only_uri(tmp_path, monkeypatch):
    path = tmp_path / "app.sqlite"
    _create_database(path)
    original_bytes = path.read_bytes()
    real_connect = sqlite3.connect
    calls = []

    def recording_connect(database, *args, **kwargs):
        calls.append((database, kwargs))
        return real_connect(database, *args, **kwargs)

    monkeypatch.setattr(filesystem_access.sqlite3, "connect", recording_connect)

    result = json.loads(
        filesystem_access.read_sqlite(str(path), "SELECT nom FROM personnes")
    )

    assert result["count"] == 2
    assert calls[0][0] == f"file:{path}?mode=ro&immutable=1"
    assert calls[0][1]["uri"] is True
    assert path.read_bytes() == original_bytes
