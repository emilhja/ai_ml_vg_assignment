"""VG Agent trace dashboard API."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse, Response

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

    if schema_ready():
        try:
            ensure_metadata_table(get_engine())
        except RuntimeError:
            pass

    sys.stderr.write(
        f"dashboard: sqlite={resolve_sqlite_path()} schema_ready={schema_ready()}\n"
        f"dashboard: trace_dirs={list(all_traces_dirs())}\n"
    )

_UI_DEV_URL = "http://127.0.0.1:5173"


@app.get("/", include_in_schema=False)
def root() -> RedirectResponse:
    """Browser hint: the React UI is served by Vite, not this API process."""
    return RedirectResponse(url=_UI_DEV_URL, status_code=307)


@app.get("/api", include_in_schema=False)
def api_index() -> JSONResponse:
    return JSONResponse(
        {
            "service": "vg-agent-dashboard-api",
            "docs": "/docs",
            "health": f"{API_PREFIX}/health",
            "ui_dev": _UI_DEV_URL,
            "note": "Run `npm run dev` in dashboard/web, then open the UI URL above.",
        }
    )


@app.get("/favicon.ico", include_in_schema=False)
def favicon() -> Response:
    return Response(status_code=204)


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
