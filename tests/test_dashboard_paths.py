"""Dashboard path resolution tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from dashboard.api.paths import all_traces_dirs, clear_path_cache, resolve_sqlite_path, schema_ready


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
