"""Packaging contract: .env.example, config.example.toml, and Compose layout."""

from __future__ import annotations

import subprocess
from pathlib import Path
from shutil import which

import pytest

try:
    import tomllib
except ModuleNotFoundError:
    import tomli as tomllib  # type: ignore[no-redef]

from vg_agent.runtime_settings import KNOWN_ENV_VARS, _MODEL_TOML_KEYS

ROOT = Path(__file__).resolve().parents[1]


def _parse_env_example_keys() -> set[str]:
    text = (ROOT / ".env.example").read_text(encoding="utf-8")
    keys: set[str] = set()
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" in line:
            keys.add(line.split("=", 1)[0].strip())
    return keys


def test_env_example_vg_vars_in_known_env_vars() -> None:
    keys = _parse_env_example_keys()
    vg_keys = {k for k in keys if k.startswith("VG_")}
    missing = vg_keys - set(KNOWN_ENV_VARS)
    assert not missing, f".env.example lists unknown VG_* vars: {sorted(missing)}"


def test_config_example_toml_keys_accepted() -> None:
    payload = tomllib.loads((ROOT / "config.example.toml").read_text(encoding="utf-8"))
    models = payload.get("models")
    assert isinstance(models, dict)
    for key in models:
        assert key in _MODEL_TOML_KEYS, f"unexpected models key: {key}"
    budget = payload.get("budget")
    assert isinstance(budget, dict)
    assert set(budget) <= {"max_usd_per_run", "max_usd_per_day", "max_tokens_per_run"}
    approval = payload.get("approval")
    assert isinstance(approval, dict)
    assert set(approval) <= {"mode"}


def test_env_gitignored() -> None:
    env_path = ROOT / ".env"
    if not env_path.exists():
        pytest.skip("no .env file in checkout")

    result = subprocess.run(
        ["git", "check-ignore", "-q", ".env"],
        cwd=ROOT,
        capture_output=True,
    )
    assert result.returncode == 0, ".env should be gitignored"


def test_compose_defines_vg_dashboard_service() -> None:
    text = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    assert "vg-dashboard:" in text
    assert "Dockerfile.dashboard" in text
    assert "./workspace:/workspace" in text
    assert "./traces:/workspace/traces" in text
    assert '"8787:8787"' in text or "8787:8787" in text
    assert "VG_WORKSPACE_ROOT" in text
    assert "VG_DASHBOARD_SERVE_UI" in text
    assert (ROOT / "Dockerfile.dashboard").is_file()


def test_docker_compose_config_exits_zero() -> None:
    if which("docker") is None:
        pytest.skip("docker not on PATH")
    result = subprocess.run(
        ["docker", "compose", "config"],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr or result.stdout
