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


def _sqlite_connect_ro(path: Path) -> sqlite3.Connection:
    """Open observability SQLite read-only.

    Prefer a normal WAL-aware read; fall back to immutable when bind mounts
    cannot open the WAL sidecar (common for Docker on Windows).
    """
    ro_uri = f"file:{path.as_posix()}?mode=ro"
    try:
        conn = sqlite3.connect(ro_uri, uri=True, timeout=2.0)
        conn.execute("SELECT 1 FROM sqlite_master LIMIT 1").fetchone()
        return conn
    except sqlite3.Error:
        immutable_uri = f"file:{path.as_posix()}?mode=ro&immutable=1"
        return sqlite3.connect(immutable_uri, uri=True, timeout=2.0)


def _sqlite_has_sessions(path: Path) -> bool:
    if not path.is_file() or path.stat().st_size < 512:
        return False
    try:
        conn = _sqlite_connect_ro(path)
        try:
            row = conn.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='sessions' LIMIT 1"
            ).fetchone()
            return row is not None
        finally:
            conn.close()
    except sqlite3.Error:
        return False


def _sqlite_db_metrics(path: Path) -> tuple[int, int]:
    """Return (session_count, run_token_total); (0, 0) when unreadable."""
    if not _sqlite_has_sessions(path):
        return 0, 0
    try:
        conn = _sqlite_connect_ro(path)
        try:
            sessions = conn.execute("SELECT COUNT(*) FROM sessions").fetchone()
            session_count = int(sessions[0]) if sessions else 0
            tokens = 0
            has_runs = conn.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='runs' LIMIT 1"
            ).fetchone()
            if has_runs:
                row = conn.execute(
                    "SELECT COALESCE(SUM(total_tokens), 0) FROM runs"
                ).fetchone()
                tokens = int(row[0]) if row else 0
            return session_count, tokens
        finally:
            conn.close()
    except sqlite3.Error:
        return 0, 0


def _sqlite_session_count(path: Path) -> int:
    return _sqlite_db_metrics(path)[0]


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

    ws_root = workspace_root()
    try:
        ws_parts = len(ws_root.parts)
    except OSError:
        ws_parts = 0
    if ws_parts > 0:
        for path in ws_root.glob("**/traces"):
            if not path.is_dir():
                continue
            if len(path.parts) - ws_parts > 4:
                continue
            key = str(path.resolve())
            if key in seen:
                continue
            seen.add(key)
            dirs.append(path.resolve())

    return tuple(dirs)


def find_jsonl_path(session_id: str) -> Path | None:
    for directory in all_traces_dirs():
        path = directory / f"{session_id}.jsonl"
        if path.is_file() and path.stat().st_size > 0:
            return path
    return None


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

    best: Path | None = None
    best_sessions = -1
    best_tokens = -1
    best_priority = len(candidates) + 1
    for priority, path in enumerate(candidates):
        sessions, tokens = _sqlite_db_metrics(path)
        if sessions > best_sessions or (
            sessions == best_sessions and tokens > best_tokens
        ):
            best = path
            best_sessions = sessions
            best_tokens = tokens
            best_priority = priority
        elif (
            sessions == best_sessions
            and tokens == best_tokens
            and sessions > 0
            and (
                priority < best_priority
                or path.resolve() == workspace_db.resolve()
            )
        ):
            best = path
            best_priority = priority

    if best is not None and best_sessions > 0:
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
    resolve_traces_dir.cache_clear()
