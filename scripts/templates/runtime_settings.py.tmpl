"""Generated runtime config loader (.env, workspace/config.toml)."""

from __future__ import annotations

import os
import re
from argparse import Namespace
from pathlib import Path
from typing import Any

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - Python 3.10
    import tomli as tomllib  # type: ignore[no-redef]

from dotenv import load_dotenv

from . import config

KNOWN_ENV_VARS: tuple[str, ...] = (
    "VG_PARENT_MODEL",
    "VG_GRILLING_MODEL",
    "VG_EXPLORER_MODEL",
    "VG_CODER_MODEL",
    "VG_REVIEWER_MODEL",
    "VG_COMPACTOR_MODEL",
    "VG_MAX_USD_PER_RUN",
    "VG_MAX_USD_PER_DAY",
    "VG_MAX_TOKENS_PER_RUN",
    "VG_APPROVAL_MODE",
    "VG_K_COMPACT",
    "VG_MAX_OUTPUT_TOKENS",
    "VG_STRICT_MODEL_PRICING",
)

_SECRET_KEY_RE = re.compile(r"(?:_KEY|_TOKEN|_SECRET|_PASSWORD)$", re.IGNORECASE)

_MODEL_TOML_KEYS: dict[str, str] = {
    "parent": "PARENT_MODEL_ID",
    "grilling": "GRILLING_MODEL_ID",
    "explorer": "EXPLORER_MODEL_ID",
    "coder": "CODER_MODEL_ID",
    "reviewer": "REVIEWER_MODEL_ID",
    "compactor": "COMPACTOR_MODEL_ID",
}

_ENV_MODEL_VARS: dict[str, str] = {
    "VG_PARENT_MODEL": "PARENT_MODEL_ID",
    "VG_GRILLING_MODEL": "GRILLING_MODEL_ID",
    "VG_EXPLORER_MODEL": "EXPLORER_MODEL_ID",
    "VG_CODER_MODEL": "CODER_MODEL_ID",
    "VG_REVIEWER_MODEL": "REVIEWER_MODEL_ID",
    "VG_COMPACTOR_MODEL": "COMPACTOR_MODEL_ID",
}


def normalize_model_id(raw: str) -> str:
    text = raw.strip()
    if not text:
        raise ValueError("model id must not be empty")
    if not text.startswith("openrouter/"):
        return f"openrouter/{text}"
    return text


def find_repo_root(workspace: Path) -> Path:
    parent = workspace.parent
    if (parent / "pyproject.toml").is_file():
        return parent.resolve()
    return Path.cwd().resolve()


def load_dotenv_file(repo_root: Path) -> None:
    path = repo_root / ".env"
    if path.is_file():
        load_dotenv(path, override=False)


def _reject_secret_keys(section: dict[str, Any], *, where: str) -> None:
    for key in section:
        if _SECRET_KEY_RE.search(key):
            raise ValueError(f"secret-like key {key!r} not allowed in {where}")


def load_workspace_toml(workspace: Path) -> dict[str, Any]:
    path = workspace / "config.toml"
    if not path.is_file():
        return {}
    payload = tomllib.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("config.toml root must be a table")
    for section_name, section in payload.items():
        if isinstance(section, dict):
            _reject_secret_keys(section, where=f"[{section_name}]")
    return payload


def _set_model_attr(attr: str, value: str) -> None:
    setattr(config, attr, normalize_model_id(value))


def _refresh_subagent_model_ids() -> None:
    config.SUBAGENT_MODEL_IDS.clear()
    config.SUBAGENT_MODEL_IDS.update(
        {
            "grilling": config.GRILLING_MODEL_ID,
            "explorer": config.EXPLORER_MODEL_ID,
            "coder": config.CODER_MODEL_ID,
            "reviewer": config.REVIEWER_MODEL_ID,
        }
    )


def _apply_toml_payload(payload: dict[str, Any]) -> None:
    models = payload.get("models")
    if isinstance(models, dict):
        for key, attr in _MODEL_TOML_KEYS.items():
            if key in models:
                _set_model_attr(attr, str(models[key]))

    budget = payload.get("budget")
    if isinstance(budget, dict):
        _reject_secret_keys(budget, where="[budget]")
        if "max_usd_per_run" in budget:
            config.MAX_USD_PER_RUN = float(budget["max_usd_per_run"])
        if "max_usd_per_day" in budget:
            config.MAX_USD_PER_DAY = float(budget["max_usd_per_day"])
        if "max_tokens_per_run" in budget:
            config.MAX_TOKENS_PER_RUN = int(budget["max_tokens_per_run"])

    approval = payload.get("approval")
    if isinstance(approval, dict):
        _reject_secret_keys(approval, where="[approval]")
        if "mode" in approval:
            config.REQUIRE_APPROVAL_DEFAULT = str(approval["mode"])

    _refresh_subagent_model_ids()


def _apply_env() -> None:
    for env_var, attr in _ENV_MODEL_VARS.items():
        value = os.environ.get(env_var, "").strip()
        if value:
            _set_model_attr(attr, value)

    raw = os.environ.get("VG_MAX_USD_PER_RUN", "").strip()
    if raw:
        config.MAX_USD_PER_RUN = float(raw)
    raw = os.environ.get("VG_MAX_USD_PER_DAY", "").strip()
    if raw:
        config.MAX_USD_PER_DAY = float(raw)
    raw = os.environ.get("VG_MAX_TOKENS_PER_RUN", "").strip()
    if raw:
        config.MAX_TOKENS_PER_RUN = int(raw)
    raw = os.environ.get("VG_APPROVAL_MODE", "").strip()
    if raw:
        config.REQUIRE_APPROVAL_DEFAULT = raw
    raw = os.environ.get("VG_K_COMPACT", "").strip()
    if raw:
        config.K_COMPACT = int(raw)
    raw = os.environ.get("VG_MAX_OUTPUT_TOKENS", "").strip()
    if raw:
        parsed = int(raw)
        if parsed > 0:
            config.PARENT_MAX_OUTPUT_TOKENS = parsed

    _refresh_subagent_model_ids()


def configured_model_ids() -> set[str]:
    return {
        config.PARENT_MODEL_ID,
        config.GRILLING_MODEL_ID,
        config.EXPLORER_MODEL_ID,
        config.CODER_MODEL_ID,
        config.REVIEWER_MODEL_ID,
        config.COMPACTOR_MODEL_ID,
    }


def models_missing_local_pricing() -> list[str]:
    return sorted(m for m in configured_model_ids() if m not in config.PRICING_USD_PER_MTOK)


def strict_model_pricing_enabled() -> bool:
    raw = os.environ.get("VG_STRICT_MODEL_PRICING", "").strip().lower()
    return raw in {"1", "true", "yes", "on"}


def format_missing_pricing_warning(missing: list[str]) -> str:
    short = [m.removeprefix("openrouter/") if m.startswith("openrouter/") else m for m in missing]
    joined = ", ".join(short)
    return (
        f"warning: no local pricing for configured model(s): {joined}. "
        "Preflight may block on usd_cap; statusline omits (next ~$) for unpriced models. "
        "Add rates to MODEL_CONFIG.md, regenerate (python scripts/generate_project.py --clean), "
        "or set VG_STRICT_MODEL_PRICING=1 to fail at startup. See docs/PRICE.md."
    )


def validate_configured_models(*, strict: bool = False) -> list[str]:
    missing = models_missing_local_pricing()
    if missing and strict:
        raise SystemExit(format_missing_pricing_warning(missing))
    return missing


def apply_runtime_settings(*, workspace_root: Path, cli: Namespace | None = None) -> None:
    del cli  # CLI overrides are applied in __main__ after this call.
    repo_root = find_repo_root(workspace_root)
    load_dotenv_file(repo_root)
    try:
        payload = load_workspace_toml(workspace_root)
    except (ValueError, TypeError) as exc:
        raise SystemExit(f"error: config.toml: {exc}") from exc
    if payload:
        _apply_toml_payload(payload)
    _apply_env()
