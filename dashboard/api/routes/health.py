from fastapi import APIRouter

from ..config import schema_ready, sqlite_path, traces_dir, workspace_root
from ..paths import all_traces_dirs, resolve_sqlite_path
from ..schemas import HealthResponse

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    path = resolve_sqlite_path()
    ready = schema_ready()
    hint = None
    if not ready:
        hint = (
            "No observability tables in the resolved SQLite file. "
            "Run `vg-agent --task ...` or `--chat` to populate traces, "
            "or set VG_SQLITE_PATH to traces/vg_agent.sqlite3 with data."
        )
    return HealthResponse(
        ok=ready,
        workspace_root=str(workspace_root()),
        sqlite_path=str(path),
        traces_dir=str(traces_dir()),
        traces_dirs=[str(d) for d in all_traces_dirs()],
        sqlite_exists=path.is_file(),
        schema_ready=ready,
        hint=hint,
    )
