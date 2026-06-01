"""Apply the same .env / workspace config.toml overrides as the agent CLI."""

from __future__ import annotations

from vg_agent.runtime_settings import apply_runtime_settings

from .paths import workspace_root


def ensure_runtime_config() -> None:
    apply_runtime_settings(workspace_root=workspace_root())
