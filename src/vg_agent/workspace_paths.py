"""Workspace root resolution (shared with dashboard via VG_WORKSPACE_ROOT)."""

from __future__ import annotations

import os
from pathlib import Path


def resolve_workspace_root() -> Path:
    """Return the agent workspace root (traces, daily spend, fixture paths)."""
    raw = os.environ.get("VG_WORKSPACE_ROOT", "workspace").strip() or "workspace"
    path = Path(raw)
    if not path.is_absolute():
        path = Path.cwd() / path
    return path.resolve()
