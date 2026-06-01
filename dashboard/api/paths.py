"""Resolve workspace, traces dir, and SQLite path (handles repo-root vs workspace/traces)."""

from __future__ import annotations

import os
import sqlite3
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path

from vg_agent import config as agent_config

_SQLITE_NAME = Path(agent_config.SQLITE_TRACE_DB).name


def _repo_root() -> Path:
    return Path.cwd().resolve()


def workspace_root() -> Path:
    raw = os.environ.get("VG_WORKSPACE_ROOT", "workspace")
    path = Path(raw)
    if not path.is_absolute():
        path = _repo_root() / path
    return path.resolve()


def _sqlite_has_sessions(path: Path) -> bool:
    if not path.is_file() or path.stat().st_size < 512:
        return False
    try:
        conn = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)
        try:
            row = conn.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='sessions' LIMIT 1"
            ).fetchone()
            return row is not None
        finally:
            conn.close()
    except sqlite3.Error:
        return False


def _sqlite_session_count(path: Path) -> int:
    if not _sqlite_has_sessions(path):
        return 0
    try:
        conn = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)
        try:
            row = conn.execute("SELECT COUNT(*) FROM sessions").fetchone()
            return int(row[0]) if row else 0
        finally:
            conn.close()
    except sqlite3.Error:
        return 0


@lru_cache(maxsize=1)
def all_traces_dirs() -> tuple[Path, ...]:
    """Every traces/ folder to scan (workspace + repo root are both common)."""
    dirs: list[Path] = []
    seen: set[str] = set()
    explicit = os.environ.get("VG_TRACES_DIR", "").strip()
    candidates = [
        Path(explicit) if explicit else None,
        workspace_root() / "traces",
        _repo_root() / "traces",
    ]
    for candidate in candidates:
        if candidate is None:
            continue
        resolved = candidate.resolve()
        key = str(resolved)
        if key in seen or not resolved.is_dir():
            continue
        seen.add(key)
        dirs.append(resolved)
    return tuple(dirs)


def find_jsonl_path(session_id: str) -> Path | None:
    for directory in all_traces_dirs():
        path = directory / f"{session_id}.jsonl"
        if path.is_file() and path.stat().st_size > 0:
            return path
    return None


@lru_cache(maxsize=1)
def resolve_sqlite_path() -> Path:
    """Pick the observability DB with the richest session mirror."""
    explicit = os.environ.get("VG_SQLITE_PATH", "").strip()
    if explicit:
        return Path(explicit).resolve()

    candidates: list[Path] = []
    seen: set[str] = set()

    def add(path: Path) -> None:
        key = str(path.resolve())
        if key not in seen:
            seen.add(key)
            candidates.append(path.resolve())

    for directory in all_traces_dirs():
        add(directory / _SQLITE_NAME)
    add(workspace_root() / agent_config.SQLITE_TRACE_DB)
    add(_repo_root() / agent_config.SQLITE_TRACE_DB)

    workspace_db = workspace_root() / agent_config.SQLITE_TRACE_DB
    if _sqlite_has_sessions(workspace_db):
        return workspace_db.resolve()

    best: Path | None = None
    best_count = -1
    for path in candidates:
        if path.resolve() == workspace_db.resolve():
            continue
        count = _sqlite_session_count(path)
        if count > best_count:
            best = path
            best_count = count

    if best is not None and best_count > 0:
        return best

    for path in candidates:
        if _sqlite_has_sessions(path):
            return path

    return candidates[0] if candidates else workspace_db


@lru_cache(maxsize=1)
def resolve_traces_dir() -> Path:
    """Primary traces dir (for display); JSONL lookup uses all_traces_dirs()."""
    explicit = os.environ.get("VG_TRACES_DIR", "").strip()
    if explicit:
        return Path(explicit).resolve()
    db = resolve_sqlite_path()
    if db.parent.name == "traces":
        return db.parent
    for directory in all_traces_dirs():
        if any(directory.glob("*.jsonl")):
            return directory
    return workspace_root() / "traces"


def sqlite_path() -> Path:
    return resolve_sqlite_path()


def traces_dir() -> Path:
    return resolve_traces_dir()


def daily_spend_path() -> Path:
    root = workspace_root()
    primary = root / agent_config.DAILY_SPEND_FILE
    if primary.is_file():
        return primary
    alt = _repo_root() / agent_config.DAILY_SPEND_FILE
    if alt.is_file():
        return alt
    return primary


def jsonl_path_for_session(session_id: str) -> Path:
    found = find_jsonl_path(session_id)
    if found is not None:
        return found
    return resolve_traces_dir() / f"{session_id}.jsonl"


def schema_ready() -> bool:
    for directory in all_traces_dirs():
        if _sqlite_has_sessions(directory / _SQLITE_NAME):
            return True
    return _sqlite_has_sessions(resolve_sqlite_path())


def latest_jsonl_session_id() -> str | None:
    candidates: list[tuple[float, str]] = []
    for directory in all_traces_dirs():
        for path in directory.glob("*.jsonl"):
            if path.stat().st_size <= 0:
                continue
            try:
                candidates.append((path.stat().st_mtime, path.stem))
            except OSError:
                continue
    if not candidates:
        return None
    candidates.sort(reverse=True)
    return candidates[0][1]


def mtime_iso(path: Path) -> str:
    return datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc).isoformat()


def clear_path_cache() -> None:
    all_traces_dirs.cache_clear()
    resolve_sqlite_path.cache_clear()
    resolve_traces_dir.cache_clear()
