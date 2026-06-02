from fastapi import APIRouter

from ..config import schema_ready, sqlite_path, traces_dir, workspace_root
from ..db import sqlite_usable
from ..paths import all_traces_dirs, resolve_sqlite_path
from ..schemas import HealthResponse
from ..services.trace_backfill import backfill_enabled

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    path = resolve_sqlite_path()
    has_schema = schema_ready()
    usable = sqlite_usable()
    hint = None
    if path.is_file() and not usable:
        hint = (
            "SQLite file exists but is corrupt, locked, or not an observability DB. "
            "Use VG_DASHBOARD_NO_BACKFILL=1 while the agent runs, remove "
            "traces/vg_agent.sqlite3* if needed, and restart the agent to rebuild "
            "the mirror from JSONL."
        )
    elif not has_schema:
        hint = (
            "No observability tables in the resolved SQLite file. "
            "Run `vg-agent --task ...` or `--chat` to populate traces, "
            "or set VG_SQLITE_PATH to traces/vg_agent.sqlite3 with data."
        )
    elif not backfill_enabled():
        hint = (
            "Dashboard JSONL→SQLite backfill is disabled (VG_DASHBOARD_NO_BACKFILL). "
            "Sessions are served from SQLite when healthy and JSONL otherwise."
        )
    return HealthResponse(
        ok=usable,
        workspace_root=str(workspace_root()),
        sqlite_path=str(path),
        traces_dir=str(traces_dir()),
        traces_dirs=[str(d) for d in all_traces_dirs()],
        sqlite_exists=path.is_file(),
        schema_ready=has_schema and usable,
        hint=hint,
    )
