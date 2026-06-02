"""VG Agent trace dashboard API."""

from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles

from .config import dashboard_host, dashboard_port
from .routes import health, runs, sessions, stats_route

API_PREFIX = "/api/v1"

app = FastAPI(title="VG Agent Dashboard", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://127.0.0.1:5173",
        "http://localhost:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router, prefix=API_PREFIX)
app.include_router(sessions.router, prefix=API_PREFIX)
app.include_router(runs.router, prefix=API_PREFIX)
app.include_router(stats_route.router, prefix=API_PREFIX)


@app.on_event("startup")
def _log_resolved_paths() -> None:
    import sys

    from .db import get_engine
    from .metadata import ensure_metadata_table
    from .paths import all_traces_dirs, resolve_sqlite_path, schema_ready
    from .runtime_config import ensure_runtime_config

    ensure_runtime_config()

    if schema_ready():
        try:
            ensure_metadata_table(get_engine())
        except (RuntimeError, OSError):
            pass

    sys.stderr.write(
        f"dashboard: sqlite={resolve_sqlite_path()} schema_ready={schema_ready()}\n"
        f"dashboard: trace_dirs={list(all_traces_dirs())}\n"
    )

_UI_DEV_URL = "http://127.0.0.1:5173"


def _ui_dist_dir() -> Path | None:
    dist = Path(__file__).resolve().parents[1] / "web" / "dist"
    if (dist / "index.html").is_file():
        return dist
    return None


def _serve_built_ui() -> bool:
    flag = os.environ.get("VG_DASHBOARD_SERVE_UI", "").strip().lower()
    return flag in ("1", "true", "yes") and _ui_dist_dir() is not None


def _built_ui_response(dist: Path, index: Path, spa_path: str) -> FileResponse:
    if spa_path.startswith("api"):
        raise HTTPException(status_code=404)
    dist_resolved = dist.resolve()
    candidate = (dist_resolved / spa_path).resolve()
    try:
        candidate.relative_to(dist_resolved)
    except ValueError as exc:
        raise HTTPException(status_code=404) from exc
    if spa_path and candidate.is_file():
        return FileResponse(candidate)
    return FileResponse(index)


@app.get("/api", include_in_schema=False)
def api_index() -> JSONResponse:
    body: dict[str, str] = {
        "service": "vg-agent-dashboard-api",
        "docs": "/docs",
        "health": f"{API_PREFIX}/health",
    }
    if _serve_built_ui():
        body["ui"] = "/"
        body["note"] = "React UI is served from this process (production / Docker)."
    else:
        body["ui_dev"] = _UI_DEV_URL
        body["note"] = "Run `npm run dev` in dashboard/web, then open the UI URL above."
    return JSONResponse(body)


if not _serve_built_ui():

    @app.get("/", include_in_schema=False)
    def root() -> RedirectResponse:
        """Browser hint: the React UI is served by Vite, not this API process."""
        return RedirectResponse(url=_UI_DEV_URL, status_code=307)

    @app.get("/favicon.ico", include_in_schema=False)
    def favicon() -> Response:
        return Response(status_code=204)
else:
    _dist = _ui_dist_dir()
    assert _dist is not None
    _dist = _dist.resolve()
    _index = (_dist / "index.html").resolve()
    _assets = _dist / "assets"
    if _assets.is_dir():
        app.mount("/assets", StaticFiles(directory=str(_assets)), name="ui-assets")

    @app.get("/", include_in_schema=False)
    def spa_root() -> FileResponse:
        return FileResponse(_index)

    @app.get("/{spa_path:path}", include_in_schema=False)
    def spa_fallback(spa_path: str) -> FileResponse:
        return _built_ui_response(_dist, _index, spa_path)


def run() -> None:
    import uvicorn

    uvicorn.run(
        "dashboard.api.main:app",
        host=dashboard_host(),
        port=dashboard_port(),
        reload=True,
    )


if __name__ == "__main__":
    run()
