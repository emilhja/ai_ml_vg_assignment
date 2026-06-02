"""Session display names (SQLite + JSON sidecar)."""

from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import OperationalError as SAOperationalError

from .paths import all_traces_dirs, find_jsonl_path, resolve_traces_dir

DISPLAY_NAME_MAX_LEN = 120
METADATA_JSON_NAME = "session_metadata.json"


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def metadata_json_paths() -> list[Path]:
    seen: set[Path] = set()
    paths: list[Path] = []
    for directory in all_traces_dirs():
        path = directory / METADATA_JSON_NAME
        resolved = path.resolve()
        if resolved not in seen:
            seen.add(resolved)
            paths.append(path)
    return paths


def ensure_metadata_table(engine: Engine) -> None:
    try:
        with engine.begin() as conn:
            conn.execute(
                text(
                    """
                    CREATE TABLE IF NOT EXISTS session_metadata (
                        session_id TEXT PRIMARY KEY,
                        display_name TEXT,
                        updated_at TEXT
                    )
                    """
                )
            )
    except (sqlite3.OperationalError, SAOperationalError):
        # Read-only observability DB (Docker bind mount / WAL); JSON sidecar still works.
        return


def _normalize_display_name(value: str | None) -> str | None:
    if value is None:
        return None
    trimmed = value.strip()
    if not trimmed:
        return None
    if len(trimmed) > DISPLAY_NAME_MAX_LEN:
        trimmed = trimmed[:DISPLAY_NAME_MAX_LEN]
    return trimmed


def _read_json_file(path: Path) -> dict[str, dict]:
    if not path.is_file():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(raw, dict):
        return {}
    out: dict[str, dict] = {}
    for key, entry in raw.items():
        if isinstance(key, str) and isinstance(entry, dict):
            out[key] = entry
    return out


def _write_json_file_atomic(path: Path, data: dict[str, dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def _merge_json_sidecars() -> dict[str, dict]:
    merged: dict[str, dict] = {}
    for path in metadata_json_paths():
        for session_id, entry in _read_json_file(path).items():
            existing = merged.get(session_id)
            if existing is None or str(entry.get("updated_at") or "") > str(
                existing.get("updated_at") or ""
            ):
                merged[session_id] = entry
    return merged


def _sqlite_entry(engine: Engine, session_id: str) -> dict | None:
    ensure_metadata_table(engine)
    try:
        with engine.connect() as conn:
            row = conn.execute(
                text(
                    "SELECT display_name, updated_at FROM session_metadata WHERE session_id = :sid"
                ),
                {"sid": session_id},
            ).fetchone()
    except sqlite3.OperationalError:
        return None
    if row is None:
        return None
    return {"display_name": row[0], "updated_at": row[1]}


def _pick_entry(*entries: dict | None) -> dict | None:
    best: dict | None = None
    for entry in entries:
        if entry is None:
            continue
        if best is None or str(entry.get("updated_at") or "") > str(best.get("updated_at") or ""):
            best = entry
    return best


def get_display_name(engine: Engine | None, session_id: str) -> str | None:
    sqlite_entry = _sqlite_entry(engine, session_id) if engine is not None else None
    json_entries = _merge_json_sidecars()
    json_entry = json_entries.get(session_id)
    chosen = _pick_entry(sqlite_entry, json_entry)
    if chosen is None:
        return None
    name = chosen.get("display_name")
    return str(name) if name else None


def load_all_display_names(engine: Engine | None) -> dict[str, str]:
    by_id: dict[str, dict] = dict(_merge_json_sidecars())
    if engine is not None:
        ensure_metadata_table(engine)
        try:
            with engine.connect() as conn:
                rows = conn.execute(
                    text("SELECT session_id, display_name, updated_at FROM session_metadata")
                ).fetchall()
        except sqlite3.OperationalError:
            rows = []
        for session_id, display_name, updated_at in rows:
            entry = {
                "display_name": display_name,
                "updated_at": updated_at,
            }
            existing = by_id.get(session_id)
            if existing is None or str(entry.get("updated_at") or "") > str(
                existing.get("updated_at") or ""
            ):
                by_id[session_id] = entry
    out: dict[str, str] = {}
    for session_id, entry in by_id.items():
        name = entry.get("display_name")
        if name:
            out[session_id] = str(name)
    return out


def _json_targets_for_session(session_id: str) -> list[Path]:
    targets: list[Path] = []
    seen: set[Path] = set()
    jsonl = find_jsonl_path(session_id)
    if jsonl is not None:
        path = jsonl.parent / METADATA_JSON_NAME
        resolved = path.resolve()
        if resolved not in seen:
            seen.add(resolved)
            targets.append(path)
    primary = resolve_traces_dir() / METADATA_JSON_NAME
    resolved_primary = primary.resolve()
    if resolved_primary not in seen:
        targets.append(primary)
    return targets


def set_display_name(
    engine: Engine | None,
    session_id: str,
    display_name: str | None,
) -> str | None:
    normalized = _normalize_display_name(display_name)
    updated_at = _utc_now_iso()
    entry = {"display_name": normalized, "updated_at": updated_at}

    if engine is not None:
        ensure_metadata_table(engine)
        with engine.begin() as conn:
            if normalized is None:
                conn.execute(
                    text("DELETE FROM session_metadata WHERE session_id = :sid"),
                    {"sid": session_id},
                )
            else:
                conn.execute(
                    text(
                        """
                        INSERT INTO session_metadata (session_id, display_name, updated_at)
                        VALUES (:sid, :name, :ts)
                        ON CONFLICT(session_id) DO UPDATE SET
                            display_name = excluded.display_name,
                            updated_at = excluded.updated_at
                        """
                    ),
                    {"sid": session_id, "name": normalized, "ts": updated_at},
                )

    for json_path in _json_targets_for_session(session_id):
        data = _read_json_file(json_path)
        if normalized is None:
            data.pop(session_id, None)
        else:
            data[session_id] = entry
        _write_json_file_atomic(json_path, data)

    return normalized
