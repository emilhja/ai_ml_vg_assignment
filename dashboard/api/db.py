"""SQLAlchemy read-only engine and session factory."""

from __future__ import annotations

from collections.abc import Generator
from contextlib import contextmanager

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from .config import schema_ready, sqlite_path

_engine = None
_SessionLocal: sessionmaker[Session] | None = None


def get_engine():
    global _engine, _SessionLocal
    if not schema_ready():
        raise RuntimeError(
            f"SQLite observability schema not found at {sqlite_path()}. "
            "Run vg-agent with tracing first, or set VG_SQLITE_PATH / VG_TRACES_DIR."
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
    return sqlite_path().is_file() and schema_ready()
