"""Runtime config loader (.env, config.toml, CLI precedence)."""

from __future__ import annotations

import argparse
from pathlib import Path

import pytest

from vg_agent import config
from vg_agent.runtime_settings import (
    KNOWN_ENV_VARS,
    apply_runtime_settings,
    load_workspace_toml,
    models_missing_local_pricing,
    normalize_model_id,
    strict_model_pricing_enabled,
    validate_configured_models,
)
from vg_agent.__main__ import _apply_model_overrides, _guard_overrides


@pytest.fixture
def config_snapshot() -> dict[str, object]:
    keys = [
        "PARENT_MODEL_ID",
        "GRILLING_MODEL_ID",
        "EXPLORER_MODEL_ID",
        "CODER_MODEL_ID",
        "REVIEWER_MODEL_ID",
        "COMPACTOR_MODEL_ID",
        "MAX_USD_PER_RUN",
        "MAX_TOKENS_PER_RUN",
        "K_COMPACT",
        "REQUIRE_APPROVAL_DEFAULT",
    ]
    snap = {k: getattr(config, k) for k in keys}
    snap["SUBAGENT_MODEL_IDS"] = dict(config.SUBAGENT_MODEL_IDS)
    yield snap
    for key, value in snap.items():
        if key == "SUBAGENT_MODEL_IDS":
            config.SUBAGENT_MODEL_IDS.clear()
            config.SUBAGENT_MODEL_IDS.update(value)  # type: ignore[arg-type]
        else:
            setattr(config, key, value)


def test_normalize_model_id_adds_openrouter_prefix() -> None:
    assert normalize_model_id("google/gemini-2.5-flash-lite") == (
        "openrouter/google/gemini-2.5-flash-lite"
    )
    assert normalize_model_id("openrouter/google/gemini-2.5-flash") == (
        "openrouter/google/gemini-2.5-flash"
    )


def test_env_overrides_compactor_model(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, config_snapshot: object
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("VG_COMPACTOR_MODEL", "google/gemini-2.5-flash-lite")
    apply_runtime_settings(workspace_root=workspace)
    assert config.COMPACTOR_MODEL_ID == "openrouter/google/gemini-2.5-flash-lite"


def test_toml_then_env_precedence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, config_snapshot: object
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "config.toml").write_text(
        '[models]\ncompactor = "openrouter/google/gemini-2.5-flash"\n',
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("VG_COMPACTOR_MODEL", "openrouter/qwen/qwen3-coder")
    apply_runtime_settings(workspace_root=workspace)
    assert config.COMPACTOR_MODEL_ID == "openrouter/qwen/qwen3-coder"


def test_cli_parent_model_beats_env(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, config_snapshot: object
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("VG_PARENT_MODEL", "openrouter/google/gemini-2.5-flash")
    apply_runtime_settings(workspace_root=workspace)
    args = argparse.Namespace(parent_model="anthropic/claude-haiku-4.5", subagent_model=None)
    _apply_model_overrides(args)
    assert config.PARENT_MODEL_ID == "openrouter/anthropic/claude-haiku-4.5"


def test_toml_rejects_secret_keys(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "config.toml").write_text('[models]\napi_key = "secret"\n', encoding="utf-8")
    with pytest.raises(ValueError, match="secret-like"):
        load_workspace_toml(workspace)


def test_guard_overrides_use_post_loader_config(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, config_snapshot: object
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("VG_MAX_USD_PER_RUN", "0.99")
    apply_runtime_settings(workspace_root=workspace)
    args = argparse.Namespace(max_usd=None, max_tokens=None)
    overrides = _guard_overrides(args)
    assert overrides["max_usd"] == pytest.approx(0.99)


def test_known_env_vars_complete() -> None:
    assert "VG_COMPACTOR_MODEL" in KNOWN_ENV_VARS
    assert "VG_K_COMPACT" in KNOWN_ENV_VARS
    assert "VG_STRICT_MODEL_PRICING" in KNOWN_ENV_VARS


def test_validate_configured_models_default_profile_priced(config_snapshot: object) -> None:
    assert validate_configured_models(strict=False) == []


def test_validate_configured_models_strict_exits_on_unpriced(
    config_snapshot: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    config.PARENT_MODEL_ID = "openrouter/example/unpriced-model"
    monkeypatch.setenv("VG_STRICT_MODEL_PRICING", "1")
    assert strict_model_pricing_enabled()
    with pytest.raises(SystemExit, match="no local pricing"):
        validate_configured_models(strict=True)


def test_models_missing_local_pricing_lists_unpriced_role(config_snapshot: object) -> None:
    config.CODER_MODEL_ID = "openrouter/example/another-unpriced"
    missing = models_missing_local_pricing()
    assert "openrouter/example/another-unpriced" in missing
