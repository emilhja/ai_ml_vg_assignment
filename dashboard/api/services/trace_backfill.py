"""Mirror orphan JSONL sessions into the canonical SQLite observability DB."""

from __future__ import annotations

import logging
import os
import sqlite3
import threading
from pathlib import Path

from sqlalchemy.orm import Session

from vg_agent.sqlite_store import SQLiteTraceStore

from ..models import SessionRow
from ..paths import find_jsonl_path, resolve_sqlite_path

logger = logging.getLogger(__name__)

_BACKFILL_LOCK = threading.Lock()
_BACKFILLED: set[str] = set()
_MAX_BACKFILL_BYTES = 50 * 1024 * 1024


def backfill_enabled() -> bool:
    """When false, the dashboard never writes the agent SQLite file (Docker default)."""
    flag = os.environ.get("VG_DASHBOARD_NO_BACKFILL", "").strip().lower()
    return flag not in ("1", "true", "yes")


def _session_in_db(db: Session | None, session_id: str) -> bool:
    if db is None:
        return False
    return db.get(SessionRow, session_id) is not None


def ensure_session_mirrored(db: Session | None, session_id: str) -> bool:
    """Backfill JSONL into SQLite when the session row is missing. Returns True if mirrored."""
    if not backfill_enabled():
        return False
    if _session_in_db(db, session_id):
        return True
    path = find_jsonl_path(session_id)
    if path is None or not path.is_file():
        return False
    with _BACKFILL_LOCK:
        if session_id in _BACKFILLED:
            if db is not None:
                db.expire_all()
            return _session_in_db(db, session_id) if db is not None else True
        try:
            size = path.stat().st_size
        except OSError:
            return False
        if size > _MAX_BACKFILL_BYTES:
            return False
        db_path = resolve_sqlite_path()
        store = SQLiteTraceStore(
            db_path.parent.parent,
            db_path=db_path,
            redaction_enabled=True,
        )
        try:
            count = store.backfill_jsonl_file(path)
        except sqlite3.Error as exc:
            logger.warning(
                "dashboard backfill skipped for %s (%s): %s",
                session_id,
                db_path,
                exc,
            )
            return False
        finally:
            store.close()
        if count > 0:
            _BACKFILLED.add(session_id)
        if db is not None:
            db.expire_all()
        return count > 0
