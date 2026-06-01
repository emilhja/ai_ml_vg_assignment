"""Dashboard runtime configuration."""

from __future__ import annotations

import os

from .paths import (
    daily_spend_path,
    jsonl_path_for_session,
    schema_ready,
    sqlite_path,
    traces_dir,
    workspace_root,
)

__all__ = [
    "daily_spend_path",
    "jsonl_path_for_session",
    "schema_ready",
    "sqlite_path",
    "traces_dir",
    "workspace_root",
]


def active_session_id_override() -> str | None:
    value = os.environ.get("VG_ACTIVE_SESSION_ID", "").strip()
    return value or None


def dashboard_host() -> str:
    return os.environ.get("VG_DASHBOARD_HOST", "127.0.0.1")


def dashboard_port() -> int:
    return int(os.environ.get("VG_DASHBOARD_PORT", "8787"))
