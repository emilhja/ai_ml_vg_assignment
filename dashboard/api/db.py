"""SQLAlchemy read-only engine and session factory."""

from __future__ import annotations

import sqlite3
from collections.abc import Generator
from contextlib import contextmanager

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from .config import schema_ready, sqlite_path

_engine = None
_SessionLocal: sessionmaker[Session] | None = None
_sqlite_unusable: bool = False


def sqlite_usable() -> bool:
    """False when the observability DB is missing, corrupt, or unreadable."""
    global _sqlite_unusable
    if _sqlite_unusable or not schema_ready():
        return False
    path = sqlite_path()
    if not path.is_file():
        return False
    try:
        conn = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)
        try:
            conn.execute("SELECT 1 FROM sessions LIMIT 1").fetchone()
            return True
        finally:
            conn.close()
    except sqlite3.Error:
        _sqlite_unusable = True
        return False


def get_engine():
    global _engine, _SessionLocal
    if not sqlite_usable():
        raise RuntimeError(
            f"SQLite observability DB unavailable at {sqlite_path()}. "
            "Run vg-agent with tracing first, set VG_SQLITE_PATH / VG_TRACES_DIR, "
            "or remove a corrupt vg_agent.sqlite3* and restart the agent."
        )
    if _engine is None:
        db_file = sqlite_path()
        url = f"sqlite:///{db_file.as_posix()}"
        _engine = create_engine(
            url,
            connect_args={"check_same_thread": False},
            pool_pre_ping=True,
        )
        _SessionLocal = sessionmaker(bind=_engine, autoflush=False, autocommit=False)
    return _engine


@contextmanager
def get_db() -> Generator[Session, None, None]:
    get_engine()
    assert _SessionLocal is not None
    session = _SessionLocal()
    try:
        yield session
    finally:
        session.close()


def db_exists() -> bool:
    return sqlite_usable()


def reset_db_cache() -> None:
    """Clear cached engine state (tests)."""
    global _engine, _SessionLocal, _sqlite_unusable
    _engine = None
    _SessionLocal = None
    _sqlite_unusable = False
