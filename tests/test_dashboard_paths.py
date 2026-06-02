"""Dashboard path resolution tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from dashboard.api.paths import all_traces_dirs, clear_path_cache, find_jsonl_path, resolve_sqlite_path, schema_ready


def test_resolve_sqlite_prefers_populated_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    empty_ws = tmp_path / "workspace" / "traces"
    empty_ws.mkdir(parents=True)
    empty_db = empty_ws / "vg_agent.sqlite3"
    empty_db.write_bytes(b"")

    good = tmp_path / "traces"
    good.mkdir()
    good_db = good / "vg_agent.sqlite3"
    import sqlite3

    conn = sqlite3.connect(good_db)
    conn.executescript(
        """
        CREATE TABLE sessions (session_id TEXT PRIMARY KEY, first_seen_at TEXT, last_seen_at TEXT,
            run_count INTEGER, total_turns INTEGER, total_tokens INTEGER, total_cost_usd REAL,
            status TEXT, redaction_enabled INTEGER);
        INSERT INTO sessions (session_id, first_seen_at, last_seen_at, status, redaction_enabled)
        VALUES ('abc', '2020-01-01', '2020-01-01', 'ok', 1);
        """
    )
    conn.commit()
    conn.close()

    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("VG_WORKSPACE_ROOT", "workspace")
    clear_path_cache()

    monkeypatch.setenv("VG_TRACES_DIR", str(tmp_path / "traces"))
    monkeypatch.setenv("VG_SQLITE_PATH", str(good_db))
    clear_path_cache()
    resolved = resolve_sqlite_path()
    assert resolved == good_db.resolve()
    assert schema_ready()
    assert len(all_traces_dirs()) >= 1


def test_resolve_sqlite_skips_empty_workspace_schema(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Empty workspace DB with sessions table must not beat a populated repo/traces DB."""
    import sqlite3

    empty_ws = tmp_path / "workspace" / "traces"
    empty_ws.mkdir(parents=True)
    empty_db = empty_ws / "vg_agent.sqlite3"
    conn = sqlite3.connect(empty_db)
    conn.executescript(
        """
        CREATE TABLE sessions (session_id TEXT PRIMARY KEY, first_seen_at TEXT, last_seen_at TEXT,
            run_count INTEGER, total_turns INTEGER, total_tokens INTEGER, total_cost_usd REAL,
            status TEXT, redaction_enabled INTEGER);
        """
    )
    conn.commit()
    conn.close()

    good = tmp_path / "traces"
    good.mkdir()
    good_db = good / "vg_agent.sqlite3"
    conn = sqlite3.connect(good_db)
    conn.executescript(
        """
        CREATE TABLE sessions (session_id TEXT PRIMARY KEY, first_seen_at TEXT, last_seen_at TEXT,
            run_count INTEGER, total_turns INTEGER, total_tokens INTEGER, total_cost_usd REAL,
            status TEXT, redaction_enabled INTEGER);
        INSERT INTO sessions (session_id, first_seen_at, last_seen_at, status, redaction_enabled)
        VALUES ('populated', '2020-01-01', '2020-01-01', 'ok', 1);
        """
    )
    conn.commit()
    conn.close()

    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("VG_WORKSPACE_ROOT", "workspace")
    monkeypatch.delenv("VG_SQLITE_PATH", raising=False)
    clear_path_cache()
    resolved = resolve_sqlite_path()
    assert resolved == good_db.resolve()


def test_all_traces_dirs_includes_workspace_and_repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (tmp_path / "workspace" / "traces").mkdir(parents=True)
    (tmp_path / "traces").mkdir(parents=True)
    (tmp_path / "traces" / "abc.jsonl").write_text('{"kind":"user_prompt","prompt":"hi"}\n', encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("VG_WORKSPACE_ROOT", "workspace")
    clear_path_cache()
    dirs = {str(d).replace("\\", "/") for d in all_traces_dirs()}
    assert any(d.endswith("/workspace/traces") for d in dirs)
    assert any(d.endswith("/traces") and not d.endswith("/workspace/traces") for d in dirs)


def test_resolve_sqlite_prefers_richer_db_over_nested(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Nested workspace/workspace/traces must not beat a richer primary traces DB."""
    import sqlite3

    schema = """
        CREATE TABLE sessions (session_id TEXT PRIMARY KEY, first_seen_at TEXT, last_seen_at TEXT,
            run_count INTEGER, total_turns INTEGER, total_tokens INTEGER, total_cost_usd REAL,
            status TEXT, redaction_enabled INTEGER);
        CREATE TABLE runs (run_id TEXT PRIMARY KEY, session_id TEXT, started_at TEXT,
            total_tokens INTEGER, total_cost_usd REAL);
        """

    primary = tmp_path / "workspace" / "traces"
    primary.mkdir(parents=True)
    primary_db = primary / "vg_agent.sqlite3"
    conn = sqlite3.connect(primary_db)
    conn.executescript(schema)
    conn.execute(
        "INSERT INTO sessions VALUES ('big', '2020-01-01', '2020-01-01', 1, 1, 1000, 1.0, 'ok', 1)"
    )
    conn.execute(
        "INSERT INTO runs VALUES ('r1', 'big', '2020-01-01', 50000, 1.0)"
    )
    conn.commit()
    conn.close()

    nested = tmp_path / "workspace" / "workspace" / "traces"
    nested.mkdir(parents=True)
    nested_db = nested / "vg_agent.sqlite3"
    conn = sqlite3.connect(nested_db)
    conn.executescript(schema)
    conn.execute(
        "INSERT INTO sessions VALUES ('small', '2020-01-01', '2020-01-01', 1, 1, 100, 0.1, 'ok', 1)"
    )
    conn.execute(
        "INSERT INTO runs VALUES ('r2', 'small', '2020-01-01', 952, 0.0001)"
    )
    conn.commit()
    conn.close()

    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("VG_WORKSPACE_ROOT", "workspace")
    monkeypatch.delenv("VG_SQLITE_PATH", raising=False)
    clear_path_cache()
    assert resolve_sqlite_path() == primary_db.resolve()


def test_all_traces_dirs_includes_nested_workspace_traces(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    nested = tmp_path / "workspace" / "workspace" / "traces"
    nested.mkdir(parents=True)
    (nested / "nested.jsonl").write_text('{"kind":"user_prompt","prompt":"hi"}\n', encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("VG_WORKSPACE_ROOT", "workspace")
    clear_path_cache()
    assert find_jsonl_path("nested") is not None
    assert find_jsonl_path("nested").name == "nested.jsonl"
