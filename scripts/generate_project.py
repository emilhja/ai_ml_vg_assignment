from __future__ import annotations

import argparse
import hashlib
import re
import shutil
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE_INPUTS = [
    ROOT / "specs" / "00_overview.md",
    ROOT / "specs" / "10_main_agent.md",
    ROOT / "specs" / "11_subagent_explorer.md",
    ROOT / "specs" / "20_tools.md",
    ROOT / "specs" / "30_runtime_governance.md",
    ROOT / "specs" / "40_demo_and_eval.md",
    ROOT / "PROMPTS.md",
    ROOT / "MODEL_CONFIG.md",
    ROOT / "CONTEXT_WINDOWS.md",
]


def read_config() -> dict[str, str]:
    text = (ROOT / "MODEL_CONFIG.md").read_text(encoding="utf-8")
    keys = [
        "PARENT_MODEL_ID",
        "GRILLING_MODEL_ID",
        "EXPLORER_MODEL_ID",
        "CODER_MODEL_ID",
        "REVIEWER_MODEL_ID",
        "COMPACTOR_MODEL_ID",
        "GEMINI_2_0_FLASH_INPUT_PER_MTOK",
        "GEMINI_2_0_FLASH_OUTPUT_PER_MTOK",
        "GEMINI_2_5_FLASH_INPUT_PER_MTOK",
        "GEMINI_2_5_FLASH_OUTPUT_PER_MTOK",
        "GEMINI_2_5_FLASH_LITE_INPUT_PER_MTOK",
        "GEMINI_2_5_FLASH_LITE_OUTPUT_PER_MTOK",
        "CLAUDE_SONNET_4_6_INPUT_PER_MTOK",
        "CLAUDE_SONNET_4_6_OUTPUT_PER_MTOK",
        "CLAUDE_HAIKU_4_5_INPUT_PER_MTOK",
        "CLAUDE_HAIKU_4_5_OUTPUT_PER_MTOK",
        "QWEN3_CODER_30B_INPUT_PER_MTOK",
        "QWEN3_CODER_30B_OUTPUT_PER_MTOK",
        "DEEPSEEK_V4_FLASH_INPUT_PER_MTOK",
        "DEEPSEEK_V4_FLASH_OUTPUT_PER_MTOK",
        "EXPENSIVE_OPENROUTER_PROVIDER_SLUGS",
        "UNKNOWN_MODEL_INPUT_ESTIMATE_PER_MTOK",
        "UNKNOWN_MODEL_OUTPUT_ESTIMATE_PER_MTOK",
        "OPENROUTER_ENDPOINT_HOST",
    ]
    values: dict[str, str] = {}
    for key in keys:
        match = re.search(rf"^{key}:\s*([^\n]+)$", text, flags=re.MULTILINE)
        if not match:
            raise SystemExit(f"missing {key} in MODEL_CONFIG.md")
        values[key] = match.group(1).strip()
    return values


def read_context_windows() -> dict[str, str]:
    text = (ROOT / "CONTEXT_WINDOWS.md").read_text(encoding="utf-8")
    keys = [
        "GEMINI_2_0_FLASH_CONTEXT_WINDOW",
        "GEMINI_2_0_FLASH_COMPACT_FRACTION",
        "GEMINI_2_5_FLASH_CONTEXT_WINDOW",
        "GEMINI_2_5_FLASH_COMPACT_FRACTION",
        "GEMINI_2_5_FLASH_LITE_CONTEXT_WINDOW",
        "GEMINI_2_5_FLASH_LITE_COMPACT_FRACTION",
        "CLAUDE_HAIKU_4_5_CONTEXT_WINDOW",
        "CLAUDE_HAIKU_4_5_COMPACT_FRACTION",
        "CLAUDE_SONNET_4_6_CONTEXT_WINDOW",
        "CLAUDE_SONNET_4_6_COMPACT_FRACTION",
        "QWEN3_CODER_30B_CONTEXT_WINDOW",
        "QWEN3_CODER_30B_COMPACT_FRACTION",
        "DEEPSEEK_V4_FLASH_CONTEXT_WINDOW",
        "DEEPSEEK_V4_FLASH_COMPACT_FRACTION",
    ]
    values: dict[str, str] = {}
    for key in keys:
        match = re.search(rf"^{key}:\s*([^\n]+)$", text, flags=re.MULTILINE)
        if not match:
            raise SystemExit(f"missing {key} in CONTEXT_WINDOWS.md")
        values[key] = match.group(1).strip()
    return values


def read_prompts() -> dict[str, str]:
    text = (ROOT / "PROMPTS.md").read_text(encoding="utf-8")
    sections: dict[str, str] = {}
    section_titles = {
        "PARENT_SYSTEM_PROMPT": "## Parent system prompt",
        "GRILLING_SYSTEM_PROMPT": "## Grilling system prompt",
        "EXPLORER_SYSTEM_PROMPT": "## Explorer system prompt",
        "CODER_SYSTEM_PROMPT": "## Coder system prompt",
        "REVIEWER_SYSTEM_PROMPT": "## Reviewer system prompt",
        "COMPACTION_SYSTEM_PROMPT": "## Tool-result compaction prompt",
        "CONVERSATION_COMPACTION_SYSTEM_PROMPT": "## Conversation compaction prompt",
    }
    for key, header in section_titles.items():
        pattern = re.escape(header) + r"\s*\n(.*?)(?=\n## |\Z)"
        match = re.search(pattern, text, flags=re.DOTALL)
        if not match:
            raise SystemExit(f"missing section {header!r} in PROMPTS.md")
        body = match.group(1).strip()
        sections[key] = body
    return sections


def python_str_literal(value: str) -> str:
    """Render a Python string literal that round-trips through generator output."""
    return repr(value)


def spec_digest() -> str:
    h = hashlib.sha256()
    for path in SOURCE_INPUTS:
        h.update(path.name.encode("utf-8"))
        h.update(b"\0")
        h.update(path.read_bytes())
        h.update(b"\0")
    return h.hexdigest()


def render(text: str, digest: str, cfg: dict[str, str], prompts: dict[str, str]) -> str:
    for key, value in cfg.items():
        text = text.replace(f"__{key}__", value)
    for key, value in prompts.items():
        text = text.replace(f"__{key}_LITERAL__", python_str_literal(value))
    return text.replace("__SPEC_DIGEST__", digest)


GENERATED_FILES: dict[str, str] = {
    "__init__.py": '''"""Generated VG agent runtime."""

SPEC_DIGEST = "__SPEC_DIGEST__"

__all__ = ["SPEC_DIGEST"]
''',
    "config.py": '''"""Generated runtime constants from MODEL_CONFIG.md."""

SPEC_DIGEST = "__SPEC_DIGEST__"

PARENT_MODEL_ID = "__PARENT_MODEL_ID__"
GRILLING_MODEL_ID = "__GRILLING_MODEL_ID__"
EXPLORER_MODEL_ID = "__EXPLORER_MODEL_ID__"
CODER_MODEL_ID = "__CODER_MODEL_ID__"
REVIEWER_MODEL_ID = "__REVIEWER_MODEL_ID__"
COMPACTOR_MODEL_ID = "__COMPACTOR_MODEL_ID__"

SUBAGENT_MODEL_IDS = {
    "grilling": GRILLING_MODEL_ID,
    "explorer": EXPLORER_MODEL_ID,
    "coder": CODER_MODEL_ID,
    "reviewer": REVIEWER_MODEL_ID,
}

PRICING_USD_PER_MTOK = {
    "openrouter/google/gemini-2.0-flash-001": {"input": __GEMINI_2_0_FLASH_INPUT_PER_MTOK__, "output": __GEMINI_2_0_FLASH_OUTPUT_PER_MTOK__},
    "openrouter/google/gemini-2.5-flash": {"input": __GEMINI_2_5_FLASH_INPUT_PER_MTOK__, "output": __GEMINI_2_5_FLASH_OUTPUT_PER_MTOK__},
    "openrouter/google/gemini-2.5-flash-lite": {"input": __GEMINI_2_5_FLASH_LITE_INPUT_PER_MTOK__, "output": __GEMINI_2_5_FLASH_LITE_OUTPUT_PER_MTOK__},
    "openrouter/anthropic/claude-haiku-4.5": {"input": __CLAUDE_HAIKU_4_5_INPUT_PER_MTOK__, "output": __CLAUDE_HAIKU_4_5_OUTPUT_PER_MTOK__},
    "openrouter/anthropic/claude-sonnet-4.6": {"input": __CLAUDE_SONNET_4_6_INPUT_PER_MTOK__, "output": __CLAUDE_SONNET_4_6_OUTPUT_PER_MTOK__},
    "openrouter/qwen/qwen3-coder-30b-a3b-instruct": {"input": __QWEN3_CODER_30B_INPUT_PER_MTOK__, "output": __QWEN3_CODER_30B_OUTPUT_PER_MTOK__},
    "openrouter/deepseek/deepseek-v4-flash": {"input": __DEEPSEEK_V4_FLASH_INPUT_PER_MTOK__, "output": __DEEPSEEK_V4_FLASH_OUTPUT_PER_MTOK__},
}
UNKNOWN_MODEL_ESTIMATE_USD_PER_MTOK = {"input": __UNKNOWN_MODEL_INPUT_ESTIMATE_PER_MTOK__, "output": __UNKNOWN_MODEL_OUTPUT_ESTIMATE_PER_MTOK__}
EXPENSIVE_OPENROUTER_PROVIDER_SLUGS = __EXPENSIVE_OPENROUTER_PROVIDER_SLUGS_TUPLE__

CONTEXT_WINDOW_TOKENS = {
    "openrouter/google/gemini-2.0-flash-001": __GEMINI_2_0_FLASH_CONTEXT_WINDOW__,
    "openrouter/google/gemini-2.5-flash": __GEMINI_2_5_FLASH_CONTEXT_WINDOW__,
    "openrouter/google/gemini-2.5-flash-lite": __GEMINI_2_5_FLASH_LITE_CONTEXT_WINDOW__,
    "openrouter/anthropic/claude-haiku-4.5": __CLAUDE_HAIKU_4_5_CONTEXT_WINDOW__,
    "openrouter/anthropic/claude-sonnet-4.6": __CLAUDE_SONNET_4_6_CONTEXT_WINDOW__,
    "openrouter/qwen/qwen3-coder-30b-a3b-instruct": __QWEN3_CODER_30B_CONTEXT_WINDOW__,
    "openrouter/deepseek/deepseek-v4-flash": __DEEPSEEK_V4_FLASH_CONTEXT_WINDOW__,
}
AUTO_COMPACT_FRACTION = {
    "openrouter/google/gemini-2.0-flash-001": __GEMINI_2_0_FLASH_COMPACT_FRACTION__,
    "openrouter/google/gemini-2.5-flash": __GEMINI_2_5_FLASH_COMPACT_FRACTION__,
    "openrouter/google/gemini-2.5-flash-lite": __GEMINI_2_5_FLASH_LITE_COMPACT_FRACTION__,
    "openrouter/anthropic/claude-haiku-4.5": __CLAUDE_HAIKU_4_5_COMPACT_FRACTION__,
    "openrouter/anthropic/claude-sonnet-4.6": __CLAUDE_SONNET_4_6_COMPACT_FRACTION__,
    "openrouter/qwen/qwen3-coder-30b-a3b-instruct": __QWEN3_CODER_30B_COMPACT_FRACTION__,
    "openrouter/deepseek/deepseek-v4-flash": __DEEPSEEK_V4_FLASH_COMPACT_FRACTION__,
}
DEFAULT_CONTEXT_WINDOW = 128_000
DEFAULT_COMPACT_FRACTION = 0.80
COMPACT_KEEP_RECENT_TURNS = 4
COMPACTOR_MAX_OUTPUT_TOKENS = 400
COMPACTOR_MAX_INPUT_CHARS = 120_000
COMPACTOR_MAX_SUMMARY_TOKENS = 300

MAX_PARENT_STEPS = 15
FINAL_STEP_RESERVE = 1
MAX_PARALLEL_CODER_RETRIES_PER_CALL = 2
MAX_SUBAGENT_STEPS = 8
MAX_SUBAGENT_DEPTH = 1
MAX_CONCURRENT_SUBAGENTS = 2
MAX_PARALLEL_SUBAGENTS = 4
SUBAGENT_TYPES = ("grilling", "explorer", "coder", "reviewer")
MAX_TOKENS_PER_RUN = 80_000
MAX_USD_PER_RUN = 0.50
MAX_USD_PER_DAY = 5.00
WARN_USD_FRACTION = 0.8
WARN_TOKEN_FRACTION = 0.8
WARN_STEP_FRACTION = 0.8
WALL_CLOCK_TIMEOUT = 120
TOOL_TIMEOUT = 30
K_COMPACT = 4000
PARENT_MAX_OUTPUT_TOKENS = 4096

OPENROUTER_ENDPOINT_HOST = "__OPENROUTER_ENDPOINT_HOST__"
MAX_TOOL_RESULT_BYTES = 1_048_576
DAILY_SPEND_FILE = ".vg_daily_spend.json"
APPROVALS_FILE = ".vg_approvals.json"
REQUIRE_APPROVAL_DEFAULT = "off"
STEP_EXTEND_PROMPT_ON_LAST_STEP = True
SQLITE_TRACE_DB = "traces/vg_agent.sqlite3"
''',
    "runtime_settings.py": '''"""Generated runtime config loader (.env, workspace/config.toml)."""

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
''',
    "budget.py": '''"""Generated budget guard."""

from __future__ import annotations

import json
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from . import config


class PricingUnavailable(RuntimeError):
    pass


@dataclass
class BudgetDecision:
    allowed: bool
    budget_reason: str | None = None
    details: dict[str, object] = field(default_factory=dict)


def _today_utc_key() -> str:
    return datetime.now(timezone.utc).date().isoformat()


def format_usd_display(value: float) -> str:
    """USD with $ prefix; no scientific notation; sub-cent caps stay readable."""
    value = float(value)
    if abs(value) < 1e-12:
        return "$0.00"
    if abs(value) >= 0.01:
        return f"${value:.2f}"
    for decimals in range(4, 10):
        formatted = f"{value:.{decimals}f}"
        if abs(float(formatted)) >= 1e-12:
            body = formatted.rstrip("0").rstrip(".") if "." in formatted else formatted
            return f"${body}"
    return f"${value:.8f}".rstrip("0").rstrip(".")


def format_usd_number(value: float) -> str:
    """Plain USD amount (no $) for slash-command / budget lines."""
    text = format_usd_display(value)
    return text[1:] if text.startswith("$") else text


class DailySpendLedger:
    """UTC date-keyed persistent ledger under workspace root."""

    def __init__(self, root: Path | None) -> None:
        self.root = root
        self.path: Path | None = None
        self.data: dict[str, float] = {}
        self.fail_closed: bool = False
        if root is None:
            return
        self.path = Path(root) / config.DAILY_SPEND_FILE
        if not self.path.exists():
            return
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(payload, dict):
                raise ValueError("ledger payload must be an object")
            self.data = {str(k): float(v) for k, v in payload.items()}
        except (OSError, ValueError, json.JSONDecodeError):
            self.data = {}
            self.fail_closed = True

    def today_spent(self) -> float:
        return float(self.data.get(_today_utc_key(), 0.0))

    def remaining_today(self) -> float:
        if self.fail_closed:
            return 0.0
        return max(0.0, config.MAX_USD_PER_DAY - self.today_spent())

    def add(self, cost: float) -> None:
        if self.path is None or self.fail_closed:
            return
        key = _today_utc_key()
        self.data[key] = self.today_spent() + float(cost)
        try:
            self.path.write_text(
                json.dumps(self.data, sort_keys=True),
                encoding="utf-8",
                newline="\\n",
            )
        except OSError:
            pass


@dataclass
class BudgetGuard:
    max_steps: int = config.MAX_PARENT_STEPS
    max_tokens: int = config.MAX_TOKENS_PER_RUN
    max_usd: float = config.MAX_USD_PER_RUN
    daily_remaining_usd: float = config.MAX_USD_PER_DAY
    running_tokens: int = 0
    running_input_tokens: int = 0
    running_output_tokens: int = 0
    running_usd: float = 0.0
    parent_step_count: int = 0
    step_count: int = 0
    last_tool_signature: tuple[str, str] | None = None
    repeat_count: int = 0
    ledger: DailySpendLedger | None = None
    per_agent_type_tokens: dict[str, int] = field(default_factory=dict)
    per_agent_type_input_tokens: dict[str, int] = field(default_factory=dict)
    per_agent_type_output_tokens: dict[str, int] = field(default_factory=dict)
    per_agent_type_model_calls: dict[str, int] = field(default_factory=dict)
    per_agent_type_usd: dict[str, float] = field(default_factory=dict)
    warned: set[str] = field(default_factory=set)
    step_extend_prompted: bool = False
    wall_clock_extra_s: float = 0.0
    lock: object = field(default_factory=threading.RLock, compare=False, repr=False)

    @classmethod
    def for_workspace(cls, root: Path | None, **kwargs: object) -> "BudgetGuard":
        ledger = DailySpendLedger(root)
        kwargs.setdefault("daily_remaining_usd", ledger.remaining_today())
        kwargs["ledger"] = ledger
        return cls(**kwargs)  # type: ignore[arg-type]

    def estimate_cost(self, model: str, input_tokens: int, output_tokens: int) -> float:
        price = config.PRICING_USD_PER_MTOK.get(model, config.UNKNOWN_MODEL_ESTIMATE_USD_PER_MTOK)
        return (input_tokens / 1_000_000) * price["input"] + (output_tokens / 1_000_000) * price["output"]

    def before_model_call(
        self,
        model: str,
        worst_input_tokens: int,
        worst_output_tokens: int,
        *,
        enforce_parent_step_cap: bool = False,
    ) -> BudgetDecision:
        with self.lock:
            if enforce_parent_step_cap and self.parent_step_count >= self.max_steps:
                return BudgetDecision(False, "step_cap", {"steps": self.parent_step_count, "max_steps": self.max_steps})
            if self.running_tokens + worst_input_tokens + worst_output_tokens > self.max_tokens:
                return BudgetDecision(False, "token_cap", {"tokens": self.running_tokens, "max_tokens": self.max_tokens})
            worst_cost = self.estimate_cost(model, worst_input_tokens, worst_output_tokens)
            if self.running_usd + worst_cost > self.max_usd:
                return BudgetDecision(False, "usd_cap", {"running_usd": self.running_usd, "worst_next_usd": worst_cost, "max_usd": self.max_usd})
            if self.running_usd + worst_cost > self.daily_remaining_usd:
                return BudgetDecision(False, "daily_cap", {"running_usd": self.running_usd, "daily_remaining_usd": self.daily_remaining_usd})
            return BudgetDecision(True)

    def record_model_call(self, model: str, input_tokens: int, output_tokens: int, cost_usd: float | None = None, agent_type: str = "parent") -> float:
        with self.lock:
            self.step_count += 1
            if agent_type == "parent":
                self.parent_step_count += 1
            self.running_tokens += input_tokens + output_tokens
            self.running_input_tokens += input_tokens
            self.running_output_tokens += output_tokens
            if cost_usd is not None:
                cost = float(cost_usd)
            elif model in config.PRICING_USD_PER_MTOK:
                cost = self.estimate_cost(model, input_tokens, output_tokens)
            else:
                raise PricingUnavailable(
                    f"no local pricing for live model {model!r}; OpenRouter/LiteLLM must return explicit response cost"
                )
            self.running_usd += cost
            self.per_agent_type_tokens[agent_type] = self.per_agent_type_tokens.get(agent_type, 0) + input_tokens + output_tokens
            self.per_agent_type_input_tokens[agent_type] = self.per_agent_type_input_tokens.get(agent_type, 0) + input_tokens
            self.per_agent_type_output_tokens[agent_type] = self.per_agent_type_output_tokens.get(agent_type, 0) + output_tokens
            self.per_agent_type_model_calls[agent_type] = self.per_agent_type_model_calls.get(agent_type, 0) + 1
            self.per_agent_type_usd[agent_type] = self.per_agent_type_usd.get(agent_type, 0.0) + cost
            if self.ledger is not None:
                self.ledger.add(cost)
            return cost

    def pending_warnings(self) -> list[BudgetDecision]:
        """Return budget warnings whose threshold was newly crossed (once each).

        Soft warnings never abort; the hard caps remain the only termination triggers.
        """
        with self.lock:
            out: list[BudgetDecision] = []
            if "warn_usd" not in self.warned and self.max_usd > 0 and self.running_usd >= config.WARN_USD_FRACTION * self.max_usd:
                self.warned.add("warn_usd")
                out.append(BudgetDecision(True, "warn_usd", {"running_usd": self.running_usd, "max_usd": self.max_usd, "crossed_at_step": self.step_count}))
            if "warn_tokens" not in self.warned and self.max_tokens > 0 and self.running_tokens >= config.WARN_TOKEN_FRACTION * self.max_tokens:
                self.warned.add("warn_tokens")
                out.append(BudgetDecision(True, "warn_tokens", {"running_tokens": self.running_tokens, "max_tokens": self.max_tokens, "crossed_at_step": self.step_count}))
            if "warn_steps" not in self.warned and self.max_steps > 0 and self.parent_step_count >= config.WARN_STEP_FRACTION * self.max_steps:
                self.warned.add("warn_steps")
                out.append(
                    BudgetDecision(
                        True,
                        "warn_steps",
                        {
                            "step_count": self.parent_step_count,
                            "max_steps": self.max_steps,
                            "crossed_at_step": self.parent_step_count,
                        },
                    )
                )
            return out

    def should_offer_step_extend(self) -> bool:
        with self.lock:
            if not config.STEP_EXTEND_PROMPT_ON_LAST_STEP:
                return False
            if self.step_extend_prompted or self.max_steps <= 1:
                return False
            return self.parent_step_count > 0 and self.parent_step_count == self.max_steps - 1

    def at_final_step_reserve(self) -> bool:
        """True when the parent should reserve the last step for synthesis (not spawns)."""
        with self.lock:
            # Only meaningful when the cap leaves room for work plus a finalize step.
            if self.max_steps <= config.FINAL_STEP_RESERVE * 2:
                return False
            return self.parent_step_count >= self.max_steps - config.FINAL_STEP_RESERVE

    def mark_step_extend_prompted(self) -> None:
        with self.lock:
            self.step_extend_prompted = True

    def record_tool_signature(self, tool: str, args_key: str) -> BudgetDecision:
        with self.lock:
            signature = (tool, args_key)
            if signature == self.last_tool_signature:
                self.repeat_count += 1
            else:
                self.last_tool_signature = signature
                self.repeat_count = 1
            if self.repeat_count >= 3:
                return BudgetDecision(False, "repetition_abort", {"tool": tool, "args_key": args_key, "repeat_count": self.repeat_count})
            return BudgetDecision(True)

    def configure_caps(
        self,
        *,
        max_steps: int | None = None,
        max_tokens: int | None = None,
        max_usd: float | None = None,
        daily_remaining_usd: float | None = None,
    ) -> str | None:
        """Update session caps from ``/budget``; returns an error message or None."""
        with self.lock:
            if max_steps is not None:
                if max_steps < 1:
                    return "max_steps must be >= 1"
                if max_steps < self.parent_step_count:
                    return f"max_steps must be >= step_count ({self.parent_step_count})"
                self.max_steps = max_steps
            if max_tokens is not None:
                if max_tokens < 1:
                    return "max_tokens must be >= 1"
                if max_tokens < self.running_tokens:
                    return f"max_tokens must be >= running tokens ({self.running_tokens})"
                self.max_tokens = max_tokens
            if max_usd is not None:
                if max_usd <= 0:
                    return "max_usd must be > 0"
                if max_usd < self.running_usd:
                    return f"max_usd must be >= running usd ({format_usd_number(self.running_usd)})"
                self.max_usd = float(max_usd)
            if daily_remaining_usd is not None:
                if daily_remaining_usd <= 0:
                    return "daily_remaining_usd must be > 0"
                self.daily_remaining_usd = float(daily_remaining_usd)
        return None

    def extend_cap(self, reason: str, *, once: bool) -> None:
        """Raise a hard cap after interactive approval."""
        with self.lock:
            if reason == "step_cap":
                self.max_steps = (self.parent_step_count + 1) if once else (self.max_steps + max(5, self.max_steps // 4))
            elif reason == "token_cap":
                bump = max(10_000, self.max_tokens // 4)
                self.max_tokens = (self.running_tokens + bump) if once else (self.max_tokens + bump)
            elif reason == "usd_cap":
                bump = max(0.05, self.max_usd * 0.25)
                self.max_usd = (self.running_usd + bump) if once else (self.max_usd + bump)
            elif reason == "daily_cap":
                bump = max(0.25, self.daily_remaining_usd * 0.25) if self.daily_remaining_usd > 0 else 0.5
                self.daily_remaining_usd += bump
            elif reason == "timeout":
                self.wall_clock_extra_s += 60.0 if once else float(config.WALL_CLOCK_TIMEOUT)
            elif reason == "repetition_abort":
                self.repeat_count = 0
                self.last_tool_signature = None
''',
    "live_model_client.py": '''"""Generated LiteLLM OpenRouter live-model client."""

from __future__ import annotations

import contextlib
import io
import json
import logging
import os
import sys
import urllib.parse
from dataclasses import dataclass, field
from typing import Any

from . import config


class _LiteLLMNoiseFilter(io.TextIOBase):
    """Drops LiteLLM's raw ``print()`` calls (e.g. the red ``Provider List`` banner)
    while letting through anything else written to the wrapped stream."""

    _DROP_MARKERS = ("Provider List:", "GetLLMProvider")

    def __init__(self, wrapped: Any) -> None:
        self._wrapped = wrapped
        self._buffer = ""

    def write(self, text: str) -> int:
        self._buffer += text
        if "\\n" in self._buffer:
            lines = self._buffer.split("\\n")
            self._buffer = lines.pop()
            for line in lines:
                if not any(marker in line for marker in self._DROP_MARKERS):
                    self._wrapped.write(line + "\\n")
        return len(text)

    def flush(self) -> None:
        if self._buffer:
            if not any(marker in self._buffer for marker in self._DROP_MARKERS):
                self._wrapped.write(self._buffer)
            self._buffer = ""
        self._wrapped.flush()


class MissingOpenRouterKey(RuntimeError):
    pass


class EndpointPinViolation(RuntimeError):
    pass


class LiveModelError(RuntimeError):
    retryable = False


class LiveModelRateLimitError(LiveModelError):
    retryable = True

    def __init__(self, message: str, *, provider_detail: str | None = None) -> None:
        super().__init__(message)
        self.provider_detail = provider_detail


@dataclass
class ToolCall:
    tool_use_id: str
    name: str
    args: dict[str, Any] = field(default_factory=dict)


@dataclass
class ModelTurn:
    assistant_text: str
    tool_calls: list[ToolCall] = field(default_factory=list)
    stop_reason: str = "end_turn"
    input_tokens: int = 0
    output_tokens: int = 0
    raw_content: list[dict[str, Any]] = field(default_factory=list)
    model_id: str = ""
    cost_usd: float | None = None
    openrouter_provider: str | None = None


class LiveModelClient:
    endpoint = "https://openrouter.ai/api/v1"

    def __init__(self, api_key: str, endpoint: str | None = None, recorder: Any | None = None) -> None:
        self.api_key = api_key
        self.recorder = recorder
        if endpoint is not None:
            self.endpoint = endpoint

    @classmethod
    def from_env(cls, recorder: Any | None = None) -> "LiveModelClient":
        api_key = os.environ.get("OPENROUTER_API_KEY")
        if not api_key:
            raise MissingOpenRouterKey("OPENROUTER_API_KEY is required when --live-model is used")
        return cls(api_key, recorder=recorder)

    def _assert_endpoint_pinned(self) -> None:
        parsed_url = urllib.parse.urlparse(self.endpoint)
        if parsed_url.hostname != config.OPENROUTER_ENDPOINT_HOST:
            if self.recorder is not None:
                self.recorder.emit(
                    "egress_blocked",
                    host=parsed_url.hostname,
                    expected_host=config.OPENROUTER_ENDPOINT_HOST,
                    endpoint=self.endpoint,
                )
            raise EndpointPinViolation(
                f"refusing to call non-pinned host {parsed_url.hostname!r}; "
                f"endpoint must use {config.OPENROUTER_ENDPOINT_HOST!r}"
            )

    def complete(
        self,
        *,
        model: str,
        system_prompt: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        max_tokens: int = 4096,
    ) -> ModelTurn:
        self._assert_endpoint_pinned()
        if not model.startswith("openrouter/"):
            raise RuntimeError(f"live model id must use LiteLLM OpenRouter form 'openrouter/...': {model!r}")

        logging.getLogger("LiteLLM").setLevel(logging.ERROR)
        logging.getLogger("litellm").setLevel(logging.ERROR)
        os.environ.setdefault("LITELLM_LOG", "ERROR")
        try:
            import litellm
        except ImportError as exc:
            raise RuntimeError("LiteLLM is required for --live-model runs; install the project dependencies") from exc
        litellm.suppress_debug_info = True
        litellm.set_verbose = False

        stdout_filter = _LiteLLMNoiseFilter(sys.stdout)
        stderr_filter = _LiteLLMNoiseFilter(sys.stderr)
        extra_body = _openrouter_extra_body(model)
        completion_kwargs: dict[str, Any] = {
            "model": model,
            "messages": _to_litellm_messages(system_prompt, messages),
            "tools": _to_litellm_tools(tools) if tools else None,
            "max_tokens": max_tokens,
            "api_key": self.api_key,
            "api_base": self.endpoint,
            "extra_headers": _openrouter_headers(),
        }
        if extra_body is not None:
            completion_kwargs["extra_body"] = extra_body
        with contextlib.redirect_stdout(stdout_filter), contextlib.redirect_stderr(stderr_filter):
            try:
                response = litellm.completion(**completion_kwargs)
            except Exception as exc:
                if _is_rate_limit_error(exc):
                    raise LiveModelRateLimitError(
                        _rate_limit_message(model),
                        provider_detail=_provider_error_detail(exc),
                    ) from exc
                raise
            finally:
                stdout_filter.flush()
                stderr_filter.flush()
        return _normalise_response(response, model)


LiteLLMOpenRouterClient = LiveModelClient


def _openrouter_headers() -> dict[str, str] | None:
    headers: dict[str, str] = {}
    site_url = os.environ.get("OPENROUTER_SITE_URL")
    app_name = os.environ.get("OPENROUTER_APP_NAME")
    if site_url:
        headers["HTTP-Referer"] = site_url
    if app_name:
        headers["X-Title"] = app_name
    return headers or None


def _parse_csv_env(name: str) -> list[str] | None:
    raw = os.environ.get(name)
    if raw is None or not str(raw).strip():
        return None
    parts = [part.strip() for part in str(raw).split(",")]
    slugs = [part for part in parts if part]
    return slugs or None


def _openrouter_provider_body(model: str) -> dict[str, Any] | None:
    model_lower = model.lower()
    if "/deepseek/" in model_lower:
        only_deepseek = _parse_csv_env("OPENROUTER_PROVIDER_ONLY_DEEPSEEK")
        if only_deepseek is not None:
            return {"only": only_deepseek}
    provider: dict[str, Any] = {}
    order = _parse_csv_env("OPENROUTER_PROVIDER_ORDER")
    if order is not None:
        provider["order"] = order
    only = _parse_csv_env("OPENROUTER_PROVIDER_ONLY")
    if only is not None:
        provider["only"] = only
    sort_raw = os.environ.get("OPENROUTER_PROVIDER_SORT")
    if sort_raw is not None and str(sort_raw).strip():
        provider["sort"] = str(sort_raw).strip()
    allow_raw = os.environ.get("OPENROUTER_PROVIDER_ALLOW_FALLBACKS")
    if allow_raw is not None and str(allow_raw).strip():
        provider["allow_fallbacks"] = str(allow_raw).strip().lower() in ("1", "true", "yes", "on")
    if not provider:
        return None
    return provider


def _openrouter_extra_body(model: str) -> dict[str, Any] | None:
    provider = _openrouter_provider_body(model)
    if provider is None:
        return None
    return {"provider": provider}


def _to_litellm_tools(tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
    converted: list[dict[str, Any]] = []
    for tool in tools:
        converted.append({
            "type": "function",
            "function": {
                "name": tool["name"],
                "description": tool.get("description", ""),
                "parameters": tool.get("input_schema", {"type": "object", "properties": {}}),
            },
        })
    return converted


def _to_litellm_messages(system_prompt: str, messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    converted: list[dict[str, Any]] = [{"role": "system", "content": system_prompt}]
    for message in messages:
        role = str(message.get("role") or "user")
        content = message.get("content", "")
        if role == "assistant" and isinstance(content, list):
            text_parts: list[str] = []
            tool_calls: list[dict[str, Any]] = []
            for block in content:
                if not isinstance(block, dict):
                    continue
                if block.get("type") == "text":
                    text_parts.append(str(block.get("text", "")))
                elif block.get("type") == "tool_use":
                    tool_calls.append({
                        "id": str(block.get("id", "")),
                        "type": "function",
                        "function": {
                            "name": str(block.get("name", "")),
                            "arguments": json.dumps(block.get("input") or {}, ensure_ascii=False),
                        },
                    })
            converted_message: dict[str, Any] = {"role": "assistant", "content": "\\n".join(text_parts) or None}
            if tool_calls:
                converted_message["tool_calls"] = tool_calls
            converted.append(converted_message)
        elif role == "user" and isinstance(content, list):
            for block in content:
                if isinstance(block, dict) and block.get("type") == "tool_result":
                    converted.append({
                        "role": "tool",
                        "tool_call_id": str(block.get("tool_use_id", "")),
                        "content": str(block.get("content", "")),
                    })
                else:
                    converted.append({"role": "user", "content": str(block)})
        else:
            converted.append({"role": role, "content": content})
    return converted


def _value(obj: Any, key: str, default: Any = None) -> Any:
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


def _is_rate_limit_error(exc: BaseException) -> bool:
    status_code = getattr(exc, "status_code", None)
    if status_code == 429:
        return True
    class_name = type(exc).__name__.lower()
    text = str(exc).lower()
    return (
        "ratelimit" in class_name
        or "rate_limit" in class_name
        or "429" in text
        or "too many requests" in text
        or "temporarily rate-limited" in text
        or "rate limited" in text
    )


def _rate_limit_message(model: str) -> str:
    return (
        f"live model provider rate-limited {model}. Retry shortly, switch models, "
        "or add your own provider key in OpenRouter integrations."
    )


def _provider_error_detail(exc: BaseException) -> str | None:
    flag = os.environ.get("VG_PROVIDER_ERROR_DETAIL", "").strip().lower()
    if flag not in {"1", "true", "yes", "on"}:
        return None
    text = str(exc).strip()
    if not text:
        return None
    if len(text) > 4000:
        text = text[:4000] + "…"
    from .trace import _redact

    redacted, _ = _redact(text)
    return redacted


def _normalise_response(response: Any, requested_model: str) -> ModelTurn:
    choices = _value(response, "choices", []) or []
    choice = choices[0] if choices else {}
    message = _value(choice, "message", {}) or {}
    content = _value(message, "content", "") or ""
    stop_reason = str(_value(choice, "finish_reason", None) or "end_turn")
    tool_calls: list[ToolCall] = []
    raw_content: list[dict[str, Any]] = []
    if content:
        raw_content.append({"type": "text", "text": str(content)})
    for call in _value(message, "tool_calls", []) or []:
        function = _value(call, "function", {}) or {}
        args_raw = _value(function, "arguments", "{}") or "{}"
        try:
            args = json.loads(args_raw) if isinstance(args_raw, str) else dict(args_raw)
        except (TypeError, ValueError):
            args = {"_raw_arguments": str(args_raw)}
        tool_call = ToolCall(
            tool_use_id=str(_value(call, "id", "")),
            name=str(_value(function, "name", "")),
            args=args,
        )
        tool_calls.append(tool_call)
        raw_content.append({
            "type": "tool_use",
            "id": tool_call.tool_use_id,
            "name": tool_call.name,
            "input": tool_call.args,
        })
    usage = _value(response, "usage", {}) or {}
    cost = _extract_cost_usd(response)
    return ModelTurn(
        assistant_text=str(content),
        tool_calls=tool_calls,
        stop_reason=stop_reason,
        input_tokens=int(_value(usage, "prompt_tokens", _value(usage, "input_tokens", 0)) or 0),
        output_tokens=int(_value(usage, "completion_tokens", _value(usage, "output_tokens", 0)) or 0),
        raw_content=raw_content,
        model_id=requested_model,
        cost_usd=cost,
        openrouter_provider=_extract_openrouter_provider(response),
    )


def _extract_openrouter_provider(response: Any) -> str | None:
    """OpenRouter backend slug (e.g. novita, alibaba) from a completion response."""
    value = _value(response, "provider", None)
    if value:
        return str(value)
    hidden = _value(response, "_hidden_params", {}) or {}
    value = _value(hidden, "provider", None)
    if value:
        return str(value)
    original = _value(hidden, "original_response", None)
    if original is not None:
        if isinstance(original, str):
            try:
                original = json.loads(original)
            except (TypeError, ValueError):
                original = None
        value = _value(original, "provider", None)
        if value:
            return str(value)
    return None


def _extract_cost_usd(response: Any) -> float | None:
    for key in ("response_cost", "cost", "cost_usd"):
        value = _value(response, key, None)
        if value is not None:
            return float(value)
    hidden = _value(response, "_hidden_params", {}) or {}
    value = _value(hidden, "response_cost", None)
    return float(value) if value is not None else None
''',
    "tools.py": '''"""Generated local tools."""

from __future__ import annotations

import re
import shlex
import subprocess
import sys
import time
from pathlib import Path

TOOL_TIMEOUT = 30
MAX_TOOL_RESULT_BYTES = 1_048_576


MAX_PY_COMPILE_TARGETS = 8
SAFE_COMMANDS = {"grep", "rg", "find", "ls", "pwd", "cat", "head", "tail", "wc", "rm", "mkdir"}
DESTRUCTIVE_TOKENS = {
    "del", "erase", "rmdir", "remove-item", "ri", "rd",
    "mv", "move", "cp", "copy", "chmod", "chown", "mkfs", "dd",
    "curl", "wget", "pip", "npm", "pnpm", "yarn", "uv", "python",
    "powershell", "pwsh", "cmd",
    "nc", "ncat", "netcat", "ssh", "scp", "rsync", "ftp", "git",
    "sftp", "telnet", "socat",
}
FORBIDDEN_ARG_TOKENS = {
    "-exec", "-execdir", "-delete", "-ok", "-okdir",
    "-fprint", "-fprintf", "-fls",
}
SHELL_CONTROL_MARKERS = [";", "&&", "||", "|", ">", "<", "`", "$("]
GLOB_MARKERS = ["*", "?", "["]

SENSITIVE_PATH_PATTERNS = [
    re.compile(r"(?:^|/)\\.env(?:$|\\.(?!example))"),
    re.compile(r"(?:^|/)id_rsa(?:\\..*)?$"),
    re.compile(r"(?:^|/)id_ed25519(?:\\..*)?$"),
    re.compile(r"\\.pem$"),
    re.compile(r"\\.key$"),
    re.compile(r"\\.pfx$"),
    re.compile(r"\\.p12$"),
    re.compile(r"(?:^|/)\\.aws/"),
    re.compile(r"(?:^|/)\\.ssh/"),
    re.compile(r"(?:^|/)\\.netrc$"),
    re.compile(r"(?:^|/)credentials(?:\\.json)?$"),
    re.compile(r"(?:^|/)\\.vg_daily_spend\\.json$"),
    re.compile(r"(?:^|/)\\.vg_approvals\\.json$"),
]


def estimate_tokens(text: str) -> int:
    return max(1, len(text) // 4)


def resolve_workspace_path(root: Path, rel_path: str) -> Path:
    root_resolved = root.resolve()
    requested = Path(rel_path)
    if requested.is_absolute():
        raise ValueError(f"path {rel_path!r} must be relative to the workspace")
    resolved = (root_resolved / requested).resolve()
    if resolved != root_resolved and root_resolved not in resolved.parents:
        raise ValueError(f"path {rel_path!r} escapes the workspace root")
    return resolved


def _sensitive_path_hint(normalized: str) -> str:
    if re.search(r"(?:^|/)\\.env(?:$|\\.(?!example))", normalized):
        return "Use '.env.example' for variable names without secret values."
    if re.search(r"(?:^|/)id_rsa(?:\\..*)?$", normalized) or re.search(
        r"(?:^|/)id_ed25519(?:\\..*)?$", normalized
    ):
        return "SSH private keys cannot be read or written by the agent."
    if normalized.endswith((".pem", ".key", ".pfx", ".p12")):
        return "Cryptographic key files are blocked."
    if re.search(r"(?:^|/)\\.aws/", normalized) or re.search(
        r"(?:^|/)credentials(?:\\.json)?$", normalized
    ):
        return "Cloud credential files are blocked."
    if re.search(r"(?:^|/)\\.ssh/", normalized):
        return "SSH credential directories are blocked."
    if re.search(r"(?:^|/)\\.netrc$", normalized):
        return "Netrc credential files are blocked."
    if re.search(r"(?:^|/)\\.vg_daily_spend\\.json$", normalized) or re.search(
        r"(?:^|/)\\.vg_approvals\\.json$", normalized
    ):
        return "Internal governance files are not accessible to the agent."
    return "Secrets and credentials cannot be read or written by the agent."


def validate_sensitive_path(rel_path: str) -> str | None:
    normalized = rel_path.replace("\\\\", "/")
    if normalized.endswith(".env.example") or normalized == ".env.example":
        return None
    for pattern in SENSITIVE_PATH_PATTERNS:
        if pattern.search(normalized):
            hint = _sensitive_path_hint(normalized)
            return f"sensitive path: cannot access {rel_path!r} - blocked for safety. {hint}"
    return None


def _path_token_error(token: str) -> str | None:
    if token.startswith("-"):
        return None
    if token in {".", "./"}:
        return None
    looks_like_path = "/" in token or "\\\\" in token or token in {".."} or token.startswith("~")
    if not looks_like_path:
        return None
    candidate = Path(token)
    if candidate.is_absolute() or token.startswith("~") or token.startswith("/"):
        return f"path token {token!r} must stay inside the workspace"
    if ".." in candidate.parts:
        return f"path token {token!r} escapes the workspace root"
    return None


def rm_delete_target(command: str) -> str | None:
    try:
        tokens = shlex.split(command, posix=True)
    except ValueError:
        return None
    if not tokens:
        return None
    head = Path(tokens[0]).name.lower()
    if head.endswith(".exe"):
        head = head[:-4]
    if head != "rm" or len(tokens) != 2:
        return None
    return tokens[1]


def _validate_rm_tokens(tokens: list[str]) -> str | None:
    if len(tokens) != 2:
        return "rm may delete exactly one file and accepts no flags"
    target = tokens[1]
    if target.startswith("-"):
        return "rm flags are not allowed"
    if target in {".", "./", "..", "../"}:
        return "rm target must be a regular file, not a directory"
    if any(marker in target for marker in GLOB_MARKERS):
        return "rm glob patterns are not allowed"
    sensitive = validate_sensitive_path(target)
    if sensitive:
        return sensitive
    return _path_token_error(target)


def _mkdir_paths_from_tokens(tokens: list[str]) -> tuple[list[str], str | None]:
    if len(tokens) < 2:
        return [], "mkdir requires at least one directory path"
    paths: list[str] = []
    for token in tokens[1:]:
        if token == "-p":
            continue
        if token.startswith("-"):
            return [], "mkdir accepts only the -p flag"
        paths.append(token)
    if not paths:
        return [], "mkdir requires at least one directory path"
    return paths, None


def _py_compile_target_from_tokens(tokens: list[str]) -> str | None:
    if len(tokens) != 4:
        return None
    head = Path(tokens[0]).name.lower()
    if head.endswith(".exe"):
        head = head[:-4]
    if head != "python3":
        return None
    if tokens[1] != "-m" or tokens[2] != "py_compile":
        return None
    return tokens[3]


def _validate_py_compile_tokens(tokens: list[str]) -> str | None:
    target = _py_compile_target_from_tokens(tokens)
    if target is None:
        return "only `python3 -m py_compile <single relative .py path>` is allowed"
    if target.startswith("-"):
        return "py_compile target must be a workspace-relative .py file"
    if any(marker in target for marker in GLOB_MARKERS):
        return "py_compile glob patterns are not allowed"
    sensitive = validate_sensitive_path(target)
    if sensitive:
        return sensitive
    path_error = _path_token_error(target)
    if path_error:
        return path_error
    if not target.endswith(".py"):
        return "py_compile target must be a .py file"
    return None


def _validate_mkdir_target(target: str) -> str | None:
    if target in {"..", "../"}:
        return "mkdir target must stay inside the workspace"
    if any(marker in target for marker in GLOB_MARKERS):
        return "mkdir glob patterns are not allowed"
    sensitive = validate_sensitive_path(target)
    if sensitive:
        return sensitive
    return _path_token_error(target)


def _validate_mkdir_tokens(tokens: list[str]) -> str | None:
    paths, error = _mkdir_paths_from_tokens(tokens)
    if error:
        return error
    for target in paths:
        target_error = _validate_mkdir_target(target)
        if target_error:
            return target_error
    return None


def mkdir_create_targets(command: str) -> list[str] | None:
    try:
        tokens = shlex.split(command, posix=True)
    except ValueError:
        return None
    if not tokens:
        return None
    head = Path(tokens[0]).name.lower()
    if head.endswith(".exe"):
        head = head[:-4]
    if head != "mkdir":
        return None
    paths, error = _mkdir_paths_from_tokens(tokens)
    if error:
        return None
    return paths


def validate_shell_command(command: str) -> str | None:
    lowered = command.lower()
    for marker in SHELL_CONTROL_MARKERS:
        if marker in lowered:
            return f"shell control or redirection marker {marker!r} is not allowed"
    try:
        tokens = shlex.split(command, posix=True)
    except ValueError as exc:
        return f"could not parse command: {exc}"
    if not tokens:
        return "empty command is not allowed"
    normalized = []
    for token in tokens:
        base = Path(token).name.lower()
        if base.endswith(".exe"):
            base = base[:-4]
        normalized.append(base)
    py_compile_target = _py_compile_target_from_tokens(tokens)
    if py_compile_target is not None:
        return _validate_py_compile_tokens(tokens)
    if normalized[0] == "rm":
        return _validate_rm_tokens(tokens)
    if normalized[0] == "mkdir":
        return _validate_mkdir_tokens(tokens)
    if normalized[0] not in SAFE_COMMANDS:
        return f"command {normalized[0]!r} is not in the read-only allowlist"
    for token in normalized:
        if token in DESTRUCTIVE_TOKENS:
            return f"destructive token {token!r} is not allowed"
    for token in tokens[1:]:
        lower_token = token.lower()
        if lower_token in FORBIDDEN_ARG_TOKENS or lower_token.startswith("--exec"):
            return f"forbidden argument token {token!r} is not allowed"
    for token in tokens[1:]:
        path_error = _path_token_error(token)
        if path_error:
            return path_error
    return None


def validate_shell_command_for_workspace(root: Path, command: str) -> str | None:
    syntax_error = validate_shell_command(command)
    if syntax_error:
        return syntax_error
    try:
        tokens = shlex.split(command, posix=True)
    except ValueError:
        return "could not parse command"
    py_compile_target = _py_compile_target_from_tokens(tokens)
    if py_compile_target is not None:
        try:
            path = resolve_workspace_path(root, py_compile_target)
        except ValueError as exc:
            return str(exc)
        if not path.exists():
            return f"py_compile target {py_compile_target!r} does not exist"
        if not path.is_file():
            return "py_compile target must be a regular file"
        return None
    target = rm_delete_target(command)
    if target is not None:
        try:
            path = resolve_workspace_path(root, target)
        except ValueError as exc:
            return str(exc)
        if not path.exists():
            return f"rm target {target!r} does not exist"
        if not path.is_file():
            return "rm may delete only regular files"
        return None
    mkdir_targets = mkdir_create_targets(command)
    if mkdir_targets is not None:
        for rel_target in mkdir_targets:
            if rel_target in {".", "./"}:
                continue
            try:
                path = resolve_workspace_path(root, rel_target)
            except ValueError as exc:
                return str(exc)
            if path.exists() and not path.is_dir():
                return f"mkdir target {rel_target!r} exists and is not a directory"
        return None
    return None


def _result(tool_use_id: str, tool: str, content: str, status: str, started: float) -> dict[str, object]:
    return {
        "tool_use_id": tool_use_id,
        "tool": tool,
        "result_full": content,
        "bytes": len(content.encode("utf-8")),
        "tokens": estimate_tokens(content),
        "latency_ms": int((time.perf_counter() - started) * 1000),
        "status": status,
    }


def read_file(root: Path, rel_path: str, tool_use_id: str) -> dict[str, object]:
    started = time.perf_counter()
    refusal = validate_sensitive_path(rel_path)
    if refusal:
        return _result(tool_use_id, "read_file", refusal, "error", started)
    try:
        path = resolve_workspace_path(root, rel_path)
        content = path.read_text(encoding="utf-8")
        return _result(tool_use_id, "read_file", content, "ok", started)
    except (OSError, ValueError) as exc:
        return _result(tool_use_id, "read_file", str(exc), "error", started)


def read_file_range(root: Path, rel_path: str, start_line: int, end_line: int, tool_use_id: str) -> dict[str, object]:
    started = time.perf_counter()
    refusal = validate_sensitive_path(rel_path)
    if refusal:
        return _result(tool_use_id, "read_file_range", refusal, "error", started)
    try:
        path = resolve_workspace_path(root, rel_path)
        lines = path.read_text(encoding="utf-8").splitlines()
        content = "\\n".join(lines[max(0, int(start_line) - 1):int(end_line)])
        return _result(tool_use_id, "read_file_range", content, "ok", started)
    except (OSError, ValueError) as exc:
        return _result(tool_use_id, "read_file_range", str(exc), "error", started)


def write_file(root: Path, rel_path: str, content: str, tool_use_id: str) -> dict[str, object]:
    started = time.perf_counter()
    refusal = validate_sensitive_path(rel_path)
    if refusal:
        return _result(tool_use_id, "write_file", refusal, "error", started)
    try:
        path = resolve_workspace_path(root, rel_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8", newline="\\n")
        return _result(tool_use_id, "write_file", f"wrote {rel_path}", "ok", started)
    except (OSError, ValueError) as exc:
        return _result(tool_use_id, "write_file", str(exc), "error", started)


def edit_file(root: Path, rel_path: str, old: str, new: str, tool_use_id: str) -> dict[str, object]:
    started = time.perf_counter()
    refusal = validate_sensitive_path(rel_path)
    if refusal:
        return _result(tool_use_id, "edit_file", refusal, "error", started)
    try:
        path = resolve_workspace_path(root, rel_path)
        content = path.read_text(encoding="utf-8")
        occurrences = content.count(old)
        if occurrences == 0:
            return _result(tool_use_id, "edit_file", f"old text not found in {rel_path}", "error", started)
        path.write_text(content.replace(old, new), encoding="utf-8", newline="\\n")
        return _result(tool_use_id, "edit_file", f"edited {rel_path}; replaced {occurrences} occurrence(s)", "ok", started)
    except (OSError, ValueError) as exc:
        return _result(tool_use_id, "edit_file", str(exc), "error", started)


def run_bash(root: Path, command: str, tool_use_id: str) -> dict[str, object]:
    started = time.perf_counter()
    safety_error = validate_shell_command_for_workspace(root, command)
    if safety_error:
        return _result(tool_use_id, "run_bash", f"run_bash blocked: {safety_error}", "error", started)
    mkdir_targets = mkdir_create_targets(command)
    if mkdir_targets is not None:
        rel_targets = [target for target in mkdir_targets if target not in {".", "./"}]
        if rel_targets:
            existing: list[str] = []
            for rel_target in rel_targets:
                try:
                    path = resolve_workspace_path(root, rel_target)
                except ValueError:
                    existing = []
                    break
                if path.is_dir():
                    existing.append(rel_target)
                else:
                    existing = []
                    break
            if existing and len(existing) == len(rel_targets):
                joined = ", ".join(existing)
                return _result(
                    tool_use_id,
                    "run_bash",
                    f"mkdir: directory already exists: {joined}",
                    "ok",
                    started,
                )
    completed = subprocess.run(["bash", "-c", command], cwd=root, text=True, capture_output=True, timeout=TOOL_TIMEOUT)
    content = completed.stdout + completed.stderr
    status = "ok" if completed.returncode == 0 else "error"
    return _result(tool_use_id, "run_bash", content, status, started)


def validate_run_tests_path(root: Path, rel_path: str) -> str | None:
    refusal = validate_sensitive_path(rel_path)
    if refusal:
        return refusal
    try:
        path = resolve_workspace_path(root, rel_path)
    except ValueError as exc:
        return str(exc)
    if not path.exists():
        return f"run_tests path {rel_path!r} does not exist"
    if path.is_file():
        name = path.name
        if not (name.startswith("test_") and name.endswith(".py")):
            return f"run_tests file must match test_*.py, got {rel_path!r}"
    elif not path.is_dir():
        return f"run_tests path must be a test file or directory, got {rel_path!r}"
    return None


def run_tests(root: Path, rel_path: str, tool_use_id: str) -> dict[str, object]:
    started = time.perf_counter()
    path_error = validate_run_tests_path(root, rel_path)
    if path_error:
        return _result(tool_use_id, "run_tests", f"run_tests blocked: {path_error}", "error", started)
    try:
        resolved = resolve_workspace_path(root, rel_path)
    except ValueError as exc:
        return _result(tool_use_id, "run_tests", str(exc), "error", started)
    try:
        completed = subprocess.run(
            [sys.executable, "-m", "pytest", str(resolved), "-q", "--tb=short"],
            cwd=root,
            text=True,
            capture_output=True,
            timeout=TOOL_TIMEOUT,
        )
    except subprocess.TimeoutExpired:
        return _result(tool_use_id, "run_tests", f"run_tests timed out after {TOOL_TIMEOUT}s", "error", started)
    content = (completed.stdout or "") + (completed.stderr or "")
    if not content.strip():
        content = f"pytest exit code {completed.returncode}"
    encoded = content.encode("utf-8")
    if len(encoded) > MAX_TOOL_RESULT_BYTES:
        half = MAX_TOOL_RESULT_BYTES // 2
        content = content[:half] + f"\\n[TRUNCATED at {MAX_TOOL_RESULT_BYTES} bytes]"
    status = "ok" if completed.returncode == 0 else "error"
    if completed.returncode != 0 and status == "error":
        content = f"pytest exit code {completed.returncode}\\n{content}"
    return _result(tool_use_id, "run_tests", content, status, started)
''',
    "trace.py": '''"""Generated JSONL trace and rendering helpers."""

from __future__ import annotations

import json
import re
import sys
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable
from uuid import uuid4

from .sqlite_store import SQLiteTraceStore


REDACTION_PATTERNS = [
    ("openrouter_key", re.compile(r"sk-or-v1-[A-Za-z0-9_\\-]+")),
    ("aws_key_id", re.compile(r"AKIA[0-9A-Z]{16}")),
    ("bearer_token", re.compile(r"(?i)bearer\\s+[a-z0-9._\\-]+")),
]


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _redact(content: str) -> tuple[str, list[tuple[str, int]]]:
    summary: list[tuple[str, int]] = []
    redacted = content
    for name, pattern in REDACTION_PATTERNS:
        redacted, count = pattern.subn("***REDACTED***", redacted)
        if count:
            summary.append((name, count))
    return redacted, summary


def _redact_event_fields(event: dict[str, Any]) -> tuple[dict[str, Any], list[tuple[str, int]]]:
    summary: list[tuple[str, int]] = []
    redacted: dict[str, Any] = {}
    for key, value in event.items():
        if isinstance(value, str):
            new_value, hits = _redact(value)
            if hits:
                summary.extend(hits)
            redacted[key] = new_value
        else:
            redacted[key] = value
    return redacted, summary


@dataclass
class TraceRecorder:
    root: Path
    run_id: str = field(default_factory=lambda: uuid4().hex[:12])
    session_id: str | None = None
    events: list[dict[str, object]] = field(default_factory=list)
    redact: bool = True
    event_sink: Callable[[dict[str, object]], None] | None = None
    sqlite_enabled: bool = True

    def __post_init__(self) -> None:
        self.trace_dir = self.root / "traces"
        self.trace_dir.mkdir(parents=True, exist_ok=True)
        self.path = self.trace_dir / f"{self.run_id}.jsonl"
        if self.session_id is None:
            self.session_id = self.run_id
        self.turn_counter = 0
        self.current_turn_id: str | None = None
        # Reentrant lock: parallel sub-agents (spawn_subagents) emit concurrently,
        # and emit() re-enters via _emit_redaction.
        self._lock = threading.RLock()
        self.sqlite_store: SQLiteTraceStore | None = None
        if self.sqlite_enabled:
            try:
                self.sqlite_store = SQLiteTraceStore(self.root, redaction_enabled=self.redact)
            except Exception as exc:  # pragma: no cover - best-effort mirror
                sys.stderr.write(f"warning: sqlite trace disabled: {exc}\\n")

    def emit(self, kind: str, agent_id: str = "parent", parent_id: str | None = None, agent_type: str = "parent", **fields: object) -> dict[str, object]:
        with self._lock:
            if kind == "user_prompt":
                self.turn_counter += 1
                self.current_turn_id = f"{self.session_id}:turn:{self.turn_counter}"
                fields.setdefault("turn_id", self.current_turn_id)
                fields.setdefault("turn_index", self.turn_counter)
            elif self.current_turn_id is not None:
                fields.setdefault("turn_id", self.current_turn_id)
                fields.setdefault("turn_index", self.turn_counter)
            event: dict[str, object] = {
                "run_id": self.run_id,
                "session_id": self.session_id,
                "event_idx": len(self.events),
                "timestamp_iso": now_iso(),
                "agent_id": agent_id,
                "agent_type": agent_type,
                "parent_id": parent_id,
                "kind": kind,
            }
            event.update(fields)
            redaction_summary: list[tuple[str, int]] = []
            if self.redact:
                event, redaction_summary = _redact_event_fields(event)
            self.events.append(event)
            with self.path.open("a", encoding="utf-8", newline="\\n") as fh:
                fh.write(json.dumps(event, ensure_ascii=False, sort_keys=True) + "\\n")
            if self.sqlite_store is not None:
                try:
                    self.sqlite_store.record_event(event)
                except Exception as exc:  # pragma: no cover - JSONL remains canonical
                    sys.stderr.write(f"warning: sqlite trace write failed: {exc}\\n")
                    self.sqlite_store = None
            if self.event_sink is not None:
                self.event_sink(event)
            if redaction_summary and kind != "redaction":
                self._emit_redaction(int(event["event_idx"]), redaction_summary)
            return event

    def _emit_redaction(self, original_event_idx: int, summary: list[tuple[str, int]]) -> None:
        for pattern_name, count in summary:
            self.emit(
                "redaction",
                original_event_idx=original_event_idx,
                pattern=pattern_name,
                count=count,
            )


def load_trace(path: Path) -> list[dict[str, object]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def render_tree(events: list[dict[str, object]]) -> str:
    lines: list[str] = []
    for event in events:
        prefix = "  " if event.get("parent_id") else ""
        kind = event["kind"]
        if kind == "llm_start":
            lines.append(f"{prefix}{event['event_idx']:03d} {event['agent_id']} llm_start step {event.get('step_idx')} model={event.get('model')}")
        elif kind == "assistant_step":
            provider = event.get("openrouter_provider")
            provider_suffix = f" provider={provider}" if provider else ""
            lines.append(
                f"{prefix}{event['event_idx']:03d} {event['agent_id']} assistant step "
                f"{event.get('step_idx')} model={event.get('model')}{provider_suffix}"
            )
        elif kind == "tool_result":
            lines.append(f"{prefix}{event['event_idx']:03d} {event['agent_id']} tool_result {event.get('tool')} tokens={event.get('tokens')} status={event.get('status')}")
        elif kind == "compaction":
            lines.append(f"{prefix}{event['event_idx']:03d} compacted {event.get('before_tokens')} -> {event.get('after_tokens')} tokens (tool_use {event.get('tool_use_id')})")
        elif kind == "budget_event":
            reason = event.get("budget_reason")
            details = event.get("details") or {}
            extra = ""
            if reason == "warn_expensive_provider" and isinstance(details, dict):
                slug = details.get("openrouter_provider")
                if slug:
                    extra = f" provider={slug}"
            lines.append(f"{prefix}{event['event_idx']:03d} budget_event {reason}{extra}")
        elif kind == "approval":
            lines.append(f"{prefix}{event['event_idx']:03d} approval {event.get('tool')} decision={event.get('decision')} scope={event.get('scope_key')}")
        elif kind == "model_error":
            lines.append(f"{prefix}{event['event_idx']:03d} {event['agent_id']} model_error {event.get('error_type')} retryable={event.get('retryable')}")
        elif kind == "egress_blocked":
            lines.append(f"{prefix}{event['event_idx']:03d} egress_blocked host={event.get('host')!r}")
        elif kind == "redaction":
            lines.append(f"{prefix}{event['event_idx']:03d} redaction {event.get('pattern')} count={event.get('count')} orig_idx={event.get('original_event_idx')}")
        elif kind == "session_reset":
            lines.append(f"{prefix}{event['event_idx']:03d} session_reset")
        elif kind == "session_new":
            lines.append(f"{prefix}{event['event_idx']:03d} session_new")
        elif kind == "run_end":
            lines.append(f"{prefix}{event['event_idx']:03d} run_end {event.get('final_status')} cost={event.get('total_cost_usd')}")
        else:
            lines.append(f"{prefix}{event['event_idx']:03d} {event['agent_id']} {kind}")
    return "\\n".join(lines)


def compacted_marker(event: dict[str, object]) -> str:
    return (
        f"[COMPACTED tool_result for tool_use_id={event['tool_use_id']}]\\n"
        f"Summary (<=300 tokens): {event['summary']}\\n"
        f"Original size: {event['before_tokens']} tokens. Trace pointer: {event['run_id']}:event:{event['original_event_idx']}.\\n"
        "Use read_file_range or re-invoke the tool to retrieve specific details."
    )


def show_context(events: list[dict[str, object]], step_idx: int) -> list[dict[str, object]]:
    context: list[dict[str, object]] = []
    tool_result_positions: dict[str, int] = {}
    for event in events:
        if event.get("agent_id") != "parent":
            continue
        kind = event["kind"]
        if kind == "user_prompt":
            context.append({"role": "user", "content": event["prompt"]})
        elif kind == "assistant_step":
            if int(event.get("step_idx") or 0) > step_idx:
                break
            context.append({
                "role": "assistant",
                "step_idx": event["step_idx"],
                "content": event.get("assistant_text", ""),
                "tool_calls": event.get("tool_calls", []),
            })
        elif kind == "tool_result":
            item = {
                "role": "tool",
                "tool_use_id": event["tool_use_id"],
                "tool": event["tool"],
                "content": event["result_full"],
            }
            tool_result_positions[str(event["tool_use_id"])] = len(context)
            context.append(item)
        elif kind == "compaction":
            pos = tool_result_positions.get(str(event["tool_use_id"]))
            if pos is not None:
                context[pos]["content"] = compacted_marker(event)
                context[pos]["compacted"] = True
        elif kind == "context_compaction":
            context.append({
                "role": "meta",
                "kind": "context_compaction",
                "content": (
                    f"Conversation compacted {event.get('before_tokens')} -> {event.get('after_tokens')} "
                    f"tokens ({event.get('percent_reduced')}% reduced, reason={event.get('reason')}). "
                    f"{event.get('summary')}"
                ),
                "trace_pointer": event.get("trace_pointer"),
            })
        elif kind == "approval":
            context.append({
                "role": "meta",
                "kind": "approval",
                "tool": event.get("tool"),
                "decision": event.get("decision"),
                "scope_key": event.get("scope_key"),
            })
        elif kind == "redaction":
            context.append({
                "role": "meta",
                "kind": "redaction",
                "pattern": event.get("pattern"),
                "count": event.get("count"),
            })
        elif kind == "egress_blocked":
            context.append({
                "role": "meta",
                "kind": "egress_blocked",
                "host": event.get("host"),
            })
        elif kind == "model_error":
            context.append({
                "role": "meta",
                "kind": "model_error",
                "message": event.get("message"),
                "retryable": event.get("retryable"),
            })
    return context


def _parent_assistant_positions(events: list[dict[str, object]]) -> list[tuple[int, int]]:
    """Return (step_idx, event_index) for each parent assistant_step, sorted by step."""
    positions: list[tuple[int, int]] = []
    for index, event in enumerate(events):
        if event.get("kind") == "assistant_step" and event.get("agent_id") == "parent":
            positions.append((int(event.get("step_idx") or 0), index))
    return sorted(positions, key=lambda pair: pair[0])


def _turn_start_before_event_index(events: list[dict[str, object]], event_index: int) -> int:
    for index in range(event_index, -1, -1):
        if events[index].get("kind") == "user_prompt":
            return index
    return 0


def _event_slice_through_parent_step(events: list[dict[str, object]], step_idx: int) -> tuple[int, int]:
    """List slice [start, end) covering the turn through completion of parent step ``step_idx``."""
    positions = _parent_assistant_positions(events)
    target = next((index for step, index in positions if step == step_idx), None)
    if target is None:
        return 0, len(events)
    turn_start = _turn_start_before_event_index(events, target)
    next_assistant = next((index for step, index in positions if step > step_idx), len(events))
    return turn_start, next_assistant


def _tool_names_from_assistant_event(event: dict[str, object]) -> list[str]:
    names: list[str] = []
    for call in event.get("tool_calls") or []:
        if isinstance(call, dict):
            names.append(str(call.get("name") or call.get("tool") or "tool"))
    return names


def show_context_overview(events: list[dict[str, object]]) -> list[dict[str, object]]:
    """Per parent-step summary for ``/show-context`` without a step index."""
    rows: list[dict[str, object]] = []
    for step_idx, event_index in _parent_assistant_positions(events):
        context = show_context(events, step_idx)
        tool_calls = _tool_names_from_assistant_event(events[event_index])
        compacted = sum(1 for item in context if item.get("compacted"))
        tool_results = sum(1 for item in context if item.get("role") == "tool")
        parallel_note: str | None = None
        if "spawn_subagents" in tool_calls:
            start, end = _event_slice_through_parent_step(events, step_idx)
            summary = parallel_subagent_summary(events, since_event_idx=start, before_event_idx=end)
            if summary is not None:
                overlap = "yes" if summary.overlap else "no"
                parallel_note = f"{len(summary.returns)} parallel sub-agents (overlap {overlap})"
        elif "spawn_subagent" in tool_calls:
            parallel_note = "1 sub-agent"
        rows.append(
            {
                "step_idx": step_idx,
                "context_messages": len(context),
                "tool_calls": tool_calls,
                "tool_results_visible": tool_results,
                "compacted_results": compacted,
                "parallel": parallel_note,
            }
        )
    return rows


def format_show_context_overview(events: list[dict[str, object]]) -> str:
    rows = show_context_overview(events)
    if not rows:
        return "No parent steps yet. Run a task first.\\n"
    lines = [
        "Parent context overview — use /show-context N for full JSON at step N",
        f"{'step':>4}  {'ctx':>4}  {'tools':>5}  {'results':>7}  {'compact':>7}  notes",
        "-" * 72,
    ]
    for row in rows:
        step = int(row["step_idx"])
        tools = row["tool_calls"]
        tool_count = len(tools) if isinstance(tools, list) else 0
        tool_label = ", ".join(tools) if isinstance(tools, list) and tools else "-"
        if tool_count > 3:
            tool_label = ", ".join(tools[:3]) + f", +{tool_count - 3} more"
        notes: list[str] = [tool_label]
        parallel = row.get("parallel")
        if parallel:
            notes.append(str(parallel))
        lines.append(
            f"{step:>4}  {int(row['context_messages']):>4}  {tool_count:>5}  "
            f"{int(row['tool_results_visible']):>7}  {int(row['compacted_results']):>7}  "
            + " · ".join(notes)
        )
    lines.append("")
    return "\\n".join(lines) + "\\n"


def _parse_iso_timestamp(value: object) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None


def _intervals_overlap(
    a_start: datetime,
    a_end: datetime,
    b_start: datetime,
    b_end: datetime,
) -> bool:
    return a_start <= b_end and b_start <= a_end


def _duration_seconds(started_at: object, ended_at: object) -> float | None:
    start = _parse_iso_timestamp(started_at)
    end = _parse_iso_timestamp(ended_at)
    if start is None or end is None:
        return None
    return max(0.0, (end - start).total_seconds())


@dataclass(frozen=True)
class SubagentReturnInfo:
    child_agent_id: str
    agent_type: str
    question: str
    started_at: str
    ended_at: str
    status: str
    payload_snippet: str
    duration_sec: float | None


@dataclass(frozen=True)
class ParallelSubagentSummary:
    returns: tuple[SubagentReturnInfo, ...]
    overlap: bool


def _spawn_questions_by_child(events: list[dict[str, object]]) -> dict[str, str]:
    questions: dict[str, str] = {}
    for event in events:
        if event.get("kind") != "subagent_spawn":
            continue
        child = str(event.get("child_agent_id") or "")
        if child:
            questions[child] = str(event.get("question") or "")[:60]
    return questions


def _collect_subagent_return_infos(
    events: list[dict[str, object]],
    *,
    since_event_idx: int,
    before_event_idx: int,
    child_ids: set[str] | None = None,
) -> list[SubagentReturnInfo]:
    questions = _spawn_questions_by_child(events[:before_event_idx])
    returns: list[SubagentReturnInfo] = []
    for event in events[since_event_idx:before_event_idx]:
        if event.get("kind") != "subagent_return":
            continue
        child = str(event.get("child_agent_id") or "")
        if child_ids is not None and child not in child_ids:
            continue
        payload = str(event.get("summary") or "")
        returns.append(
            SubagentReturnInfo(
                child_agent_id=child,
                agent_type=str(event.get("agent_type") or "explorer"),
                question=questions.get(child, ""),
                started_at=str(event.get("started_at") or ""),
                ended_at=str(event.get("ended_at") or ""),
                status=str(event.get("status") or "ok"),
                payload_snippet=payload[:120],
                duration_sec=_duration_seconds(event.get("started_at"), event.get("ended_at")),
            )
        )
    return returns


def _summary_from_return_infos(returns: list[SubagentReturnInfo]) -> ParallelSubagentSummary | None:
    if len(returns) < 2:
        return None
    intervals: list[tuple[datetime, datetime]] = []
    for item in returns:
        start = _parse_iso_timestamp(item.started_at)
        end = _parse_iso_timestamp(item.ended_at)
        if start is not None and end is not None:
            intervals.append((start, end))
    overlap = False
    for index, (a_start, a_end) in enumerate(intervals):
        for b_start, b_end in intervals[index + 1 :]:
            if _intervals_overlap(a_start, a_end, b_start, b_end):
                overlap = True
                break
        if overlap:
            break
    return ParallelSubagentSummary(returns=tuple(returns), overlap=overlap)


def parallel_subagent_summary(
    events: list[dict[str, object]],
    *,
    since_event_idx: int = 0,
    before_event_idx: int | None = None,
) -> ParallelSubagentSummary | None:
    """Summarise subagent_return rows in an event slice; overlap from started_at/ended_at."""
    end = before_event_idx if before_event_idx is not None else len(events)
    returns = _collect_subagent_return_infos(
        events,
        since_event_idx=since_event_idx,
        before_event_idx=end,
        child_ids=None,
    )
    return _summary_from_return_infos(returns)


def spawn_subagents_child_ids(event: dict[str, object]) -> set[str]:
    """Child agent_id values from one parent spawn_subagents tool_result."""
    return _child_ids_from_spawn_subagents_result(event)


def _child_ids_from_spawn_subagents_result(event: dict[str, object]) -> set[str]:
    try:
        parsed = json.loads(str(event.get("result_full") or ""))
    except json.JSONDecodeError:
        return set()
    if not isinstance(parsed, list):
        return set()
    child_ids: set[str] = set()
    for entry in parsed:
        if isinstance(entry, dict):
            agent_id = str(entry.get("agent_id") or "").strip()
            if agent_id:
                child_ids.add(agent_id)
    return child_ids


def parallel_subagent_summary_for_tool_result(
    events: list[dict[str, object]],
    tool_result_idx: int,
) -> ParallelSubagentSummary | None:
    """Summarise only sub-agents listed in one parent spawn_subagents tool_result."""
    if tool_result_idx < 0 or tool_result_idx >= len(events):
        return None
    event = events[tool_result_idx]
    if (
        event.get("kind") != "tool_result"
        or event.get("tool") != "spawn_subagents"
        or event.get("status") != "ok"
        or event.get("agent_id") != "parent"
    ):
        return None
    child_ids = _child_ids_from_spawn_subagents_result(event)
    if len(child_ids) < 2:
        return None
    returns = _collect_subagent_return_infos(
        events,
        since_event_idx=0,
        before_event_idx=tool_result_idx,
        child_ids=child_ids,
    )
    return _summary_from_return_infos(returns)


def iter_spawn_subagents_batch_summaries(
    events: list[dict[str, object]],
    *,
    since_event_idx: int = 0,
    before_event_idx: int | None = None,
) -> list[ParallelSubagentSummary]:
    """One summary per successful spawn_subagents tool_result in the slice."""
    end = before_event_idx if before_event_idx is not None else len(events)
    summaries: list[ParallelSubagentSummary] = []
    for idx in range(since_event_idx, end):
        summary = parallel_subagent_summary_for_tool_result(events, idx)
        if summary is not None:
            summaries.append(summary)
    return summaries


def latest_spawn_subagents_batch_summary(
    events: list[dict[str, object]],
    *,
    since_event_idx: int = 0,
    before_event_idx: int | None = None,
) -> ParallelSubagentSummary | None:
    batches = iter_spawn_subagents_batch_summaries(
        events,
        since_event_idx=since_event_idx,
        before_event_idx=before_event_idx,
    )
    return batches[-1] if batches else None


def format_parallel_progress_lines(
    summary: ParallelSubagentSummary,
    *,
    spawn_payload: list[dict[str, object]] | None = None,
) -> list[str]:
    """stderr lines after spawn_subagents tool_result."""
    durations = [item.duration_sec for item in summary.returns if item.duration_sec is not None]
    dur_text = ""
    if durations:
        parts = [f"{value:.1f}s" for value in durations[:4]]
        dur_text = f" · {' / '.join(parts)}"
    overlap_label = "yes" if summary.overlap else "no"
    types = {item.agent_type for item in summary.returns}
    type_label = next(iter(types)) if len(types) == 1 else "mixed"
    header = (
        f"[parallel] {len(summary.returns)} {type_label} finished "
        f"({'concurrently' if summary.overlap else 'sequentially'}) "
        f"(overlap {overlap_label}{dur_text})"
    )
    lines = [header]
    payload_by_child: dict[str, str] = {}
    if spawn_payload:
        for entry in spawn_payload:
            if isinstance(entry, dict):
                child = str(entry.get("agent_id") or "")
                payload_by_child[child] = str(entry.get("payload") or "")[:60]
    for item in summary.returns:
        snippet = payload_by_child.get(item.child_agent_id) or item.question or item.payload_snippet
        child_short = item.child_agent_id.split(".")[-1] if "." in item.child_agent_id else item.child_agent_id
        lines.append(f"  · {child_short}: {snippet}")
    return lines


def parallel_finops_batch_lines(events: list[dict[str, object]]) -> list[str]:
    """Short parallel-batch summary for /finops."""
    prompt_positions = [
        index for index, event in enumerate(events) if event.get("kind") == "user_prompt"
    ]
    if not prompt_positions:
        return []
    batches: list[str] = []
    batch_num = 0
    for turn_num, start in enumerate(prompt_positions, start=1):
        end = prompt_positions[turn_num] if turn_num < len(prompt_positions) else len(events)
        for summary in iter_spawn_subagents_batch_summaries(
            events, since_event_idx=start, before_event_idx=end
        ):
            batch_num += 1
            overlap_label = "overlapping wall-clock" if summary.overlap else "no overlap detected"
            batches.append(
                f"  turn {turn_num}: spawn_subagents · {len(summary.returns)} sub-agents · {overlap_label}"
            )
    if not batches:
        return []
    return [f"Parallel batches this session: {batch_num}", *batches]


def _turn_event_bounds(events: list[dict[str, object]], turn_index: int) -> tuple[int, int] | None:
    """Return (start_list_index, end_list_index) for 1-based user_prompt turn_index."""
    prompt_positions = [
        index for index, event in enumerate(events) if event.get("kind") == "user_prompt"
    ]
    if turn_index < 1 or turn_index > len(prompt_positions):
        return None
    start = prompt_positions[turn_index - 1]
    end = prompt_positions[turn_index] if turn_index < len(prompt_positions) else len(events)
    return start, end


def format_turn_review(
    events: list[dict[str, object]],
    *,
    turn_index: int | None = None,
    trace_path: Path | str | None = None,
    tool_summary_fn: Any | None = None,
) -> str:
    """Human-readable recap of one chat turn for /review."""
    prompt_positions = [
        index for index, event in enumerate(events) if event.get("kind") == "user_prompt"
    ]
    if not prompt_positions:
        return "No turns recorded yet.\\n"
    chosen = turn_index if turn_index is not None else len(prompt_positions)
    bounds = _turn_event_bounds(events, chosen)
    if bounds is None:
        return f"Turn {chosen} not found ({len(prompt_positions)} turn(s) in session).\\n"
    start, end = bounds
    turn_events = events[start:end]
    lines: list[str] = [f"=== Turn {chosen} review ===", ""]
    user_prompt = next((event for event in turn_events if event.get("kind") == "user_prompt"), None)
    if user_prompt:
        lines.extend(["Prompt:", str(user_prompt.get("prompt") or ""), ""])
    lines.append("Parent plan:")
    plan_found = False
    for event in turn_events:
        if event.get("kind") != "assistant_step" or event.get("agent_id") != "parent":
            continue
        tool_calls = event.get("tool_calls") or []
        if not isinstance(tool_calls, list):
            continue
        for call in tool_calls:
            if not isinstance(call, dict):
                continue
            name = str(call.get("name") or call.get("tool") or "tool")
            args = call.get("args") or {}
            if tool_summary_fn is not None:
                summary = tool_summary_fn(name, args if isinstance(args, dict) else {})
            else:
                summary = name
            lines.append(f"  - {summary}")
            plan_found = True
    if not plan_found:
        lines.append("  (no tool calls)")
    lines.append("")
    batch_summaries = iter_spawn_subagents_batch_summaries(
        events, since_event_idx=start, before_event_idx=end
    )
    lines.append("Parallel:")
    if not batch_summaries:
        lines.append("  (no parallel sub-agent batch)")
    else:
        for batch_index, summary in enumerate(batch_summaries, start=1):
            prefix = f"  batch {batch_index}: " if len(batch_summaries) > 1 else "  "
            lines.append(
                f"{prefix}{len(summary.returns)} sub-agents · overlap "
                f"{'yes' if summary.overlap else 'no'}"
            )
            for item in summary.returns:
                dur = f"{item.duration_sec:.1f}s" if item.duration_sec is not None else "?"
                lines.append(
                    f"  · {item.child_agent_id} ({item.agent_type}, {dur}): "
                    f"{item.payload_snippet or item.question}"
                )
    lines.append("")
    compactions = [event for event in turn_events if event.get("kind") == "compaction"]
    context_compactions = [event for event in turn_events if event.get("kind") == "context_compaction"]
    lines.append("Context engineering:")
    if not compactions and not context_compactions:
        lines.append("  (no compaction events)")
    else:
        for event in compactions:
            summary = str(event.get("summary") or "").strip()
            if len(summary) > 80:
                summary = summary[:80] + "…"
            lines.append(
                f"  - tool_result compacted {event.get('before_tokens')} -> {event.get('after_tokens')} tokens "
                f"(trace event {event.get('original_event_idx')}, model={event.get('compactor_model')}, "
                f"fallback={event.get('compactor_fallback')})"
            )
            if summary:
                lines.append(f"    summary: {summary}")
        for event in context_compactions:
            summary = str(event.get("summary") or "").strip()
            if len(summary) > 80:
                summary = summary[:80] + "…"
            lines.append(
                f"  - conversation compacted {event.get('before_tokens')} -> {event.get('after_tokens')} tokens "
                f"(reason={event.get('reason')}, {event.get('percent_reduced')}% reduced)"
            )
            if summary:
                lines.append(f"    summary: {summary}")
    lines.append("")
    answer = ""
    for event in reversed(turn_events):
        if event.get("kind") != "assistant_step" or event.get("agent_id") != "parent":
            continue
        tool_calls = event.get("tool_calls") or []
        text = str(event.get("assistant_text") or "").strip()
        if not tool_calls and text:
            answer = text
            break
    lines.append("Answer:")
    if not answer:
        lines.append("  (no final parent text)")
    elif len(answer) > 2048:
        lines.append(answer[:2048])
        lines.append(f"  … truncated ({len(answer)} chars; full text in trace)")
    else:
        lines.append(answer)
    lines.append("")
    if trace_path:
        lines.append(f"trace: {trace_path}")
    parent_steps = [
        int(event.get("step_idx") or 0)
        for event in turn_events
        if event.get("kind") == "assistant_step" and event.get("agent_id") == "parent"
    ]
    if parent_steps:
        lines.append(f"Tip: /show-context {max(parent_steps)} for parent-visible context at final step.")
    lines.append("")
    return "\\n".join(lines)
''',
    "demo_fixture.py": '''"""Generated deterministic fixture repository."""

from __future__ import annotations

from pathlib import Path


APP = """from auth.middleware import require_auth
from auth.session import load_session
from utils import render_response


def foo(user_id: str) -> str:
    session = load_session(user_id)
    return render_response("foo", session["user_id"])


@require_auth
def protected_dashboard(request):
    return render_response("dashboard", request.user_id)


if __name__ == "__main__":
    print(foo("demo-user"))
"""

SESSION = """SESSION_SECRET = "fixture-secret"


def issue_token(user_id: str) -> str:
    return f"token::{user_id}::{SESSION_SECRET}"


def validate_token(token: str) -> bool:
    parts = token.split("::")
    return len(parts) == 3 and parts[0] == "token" and parts[2] == SESSION_SECRET


def load_session(user_id: str) -> dict[str, str]:
    token = issue_token(user_id)
    if not validate_token(token):
        raise ValueError("invalid session token")
    return {"user_id": user_id, "token": token}
"""

MIDDLEWARE = """from functools import wraps

from .session import validate_token


class AuthError(RuntimeError):
    pass


def require_auth(handler):
    @wraps(handler)
    def wrapper(request, *args, **kwargs):
        token = getattr(request, "token", "")
        if not validate_token(token):
            raise AuthError("authentication required")
        return handler(request, *args, **kwargs)

    return wrapper
"""

UTILS = """def render_response(name: str, user_id: str) -> str:
    return f"{name}: {user_id}"
"""


def sample_log() -> str:
    lines = []
    for i in range(6200):
        lines.append(f"2026-05-10T12:{i % 60:02d}:00Z INFO request_id=req-{i:05d} route=/health status=200 latency_ms={20 + (i % 17)}")
    return "\\n".join(lines) + "\\n"


def write_fixture(root: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)
    (root / "auth").mkdir(exist_ok=True)
    (root / "data").mkdir(exist_ok=True)
    (root / "app.py").write_text(APP, encoding="utf-8", newline="\\n")
    (root / "auth" / "__init__.py").write_text("", encoding="utf-8", newline="\\n")
    (root / "auth" / "session.py").write_text(SESSION, encoding="utf-8", newline="\\n")
    (root / "auth" / "middleware.py").write_text(MIDDLEWARE, encoding="utf-8", newline="\\n")
    (root / "utils.py").write_text(UTILS, encoding="utf-8", newline="\\n")
    (root / "README.md").write_text("# Demo Repo\\n\\nSmall auth-heavy fixture for VG Agent demos.\\n", encoding="utf-8", newline="\\n")
    (root / "data" / "sample.log").write_text(sample_log(), encoding="utf-8", newline="\\n")
''',
    "agent.py": '''"""Generated parent agent, live loop, and Explorer."""

from __future__ import annotations

import hashlib
import json
import os
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass, field
from typing import Any, Callable
from pathlib import Path

from . import config, tools
from .live_model_client import LiveModelClient, LiveModelError, ModelTurn, ToolCall
from .budget import BudgetDecision, BudgetGuard, format_usd_display
from .trace import TraceRecorder, compacted_marker, now_iso


PARENT_SYSTEM_PROMPT = __PARENT_SYSTEM_PROMPT_LITERAL__

GRILLING_SYSTEM_PROMPT = __GRILLING_SYSTEM_PROMPT_LITERAL__

EXPLORER_SYSTEM_PROMPT = __EXPLORER_SYSTEM_PROMPT_LITERAL__

CODER_SYSTEM_PROMPT = __CODER_SYSTEM_PROMPT_LITERAL__

REVIEWER_SYSTEM_PROMPT = __REVIEWER_SYSTEM_PROMPT_LITERAL__

COMPACTION_SYSTEM_PROMPT = __COMPACTION_SYSTEM_PROMPT_LITERAL__

CONVERSATION_COMPACTION_SYSTEM_PROMPT = __CONVERSATION_COMPACTION_SYSTEM_PROMPT_LITERAL__

SUBAGENT_SYSTEM_PROMPTS = {
    "grilling": GRILLING_SYSTEM_PROMPT,
    "explorer": EXPLORER_SYSTEM_PROMPT,
    "coder": CODER_SYSTEM_PROMPT,
    "reviewer": REVIEWER_SYSTEM_PROMPT,
}

# Tool surface per typed sub-agent. The parent has NO write tools; Coder is the
# only mutation path in the system (specs/10, specs/12).
SUBAGENT_TOOL_NAMES = {
    "grilling": set(),
    "explorer": {"read_file", "read_file_range", "run_bash"},
    "coder": {"read_file", "read_file_range", "run_bash", "run_tests", "write_file", "edit_file"},
    "reviewer": {"read_file", "read_file_range", "run_bash"},
}


def _normalise_agent_type(value: object) -> str:
    text = str(value or "explorer").strip().lower()
    return text if text in config.SUBAGENT_TYPES else "explorer"


GATED_WRITES = {"write_file", "edit_file", "run_bash", "run_tests", "spawn_subagent", "spawn_subagents"}
SOFT_RECOVERABLE_PARENT_TOOLS = {"run_tests"}
GATED_ALL = {"read_file", "read_file_range"} | GATED_WRITES
BUDGET_CAP_TOOL = "budget_cap"


@dataclass
class ApprovalRequest:
    tool: str
    path: str | None
    args: dict[str, Any]
    summary: str


@dataclass
class ApprovalOutcome:
    decision: str
    scope_key: str | None = None
    reason: str = ""


class ApprovalScopeCache:
    def __init__(self) -> None:
        self._grants: set[tuple[str, str]] = set()

    def lookup(self, tool: str, candidates: list[str]) -> str | None:
        for key in candidates:
            if (tool, key) in self._grants:
                return key
        return None

    def grant(self, tool: str, scope_key: str) -> None:
        self._grants.add((tool, scope_key))

    def clear(self) -> None:
        self._grants.clear()

    def listing(self) -> list[tuple[str, str]]:
        return sorted(self._grants)


def _scope_candidates(request: ApprovalRequest) -> list[str]:
    if request.tool == "run_bash":
        if request.path:
            normalized = request.path.replace("\\\\", "/")
            parts = [p for p in normalized.split("/") if p and p != "."]
            parent = "/".join(parts[:-1])
            return [parent, "*"] if parent else ["", "*"]
        command = str(request.args.get("command") or "")
        head = command.strip().split()[0] if command.strip() else ""
        return [f"cmd:{head}", "*"] if head else ["*"]
    if request.tool in {"spawn_subagent", "spawn_subagents"}:
        return ["*"]
    if request.path is None:
        return ["*"]
    normalized = request.path.replace("\\\\", "/")
    parts = [p for p in normalized.split("/") if p and p != "."]
    if not parts:
        return ["", "*"]
    candidates: list[str] = []
    parent = "/".join(parts[:-1])
    while True:
        candidates.append(parent)
        if not parent:
            break
        parent = "/".join(parent.split("/")[:-1])
    candidates.append("*")
    seen: set[str] = set()
    deduped: list[str] = []
    for key in candidates:
        if key in seen:
            continue
        seen.add(key)
        deduped.append(key)
    return deduped


@dataclass
class ApprovalPolicy:
    mode: str = "off"
    auto_yes: bool = False
    step_extend_prompt: bool = True
    prompt: Callable[[ApprovalRequest], ApprovalOutcome] | None = None
    cache: ApprovalScopeCache = field(default_factory=ApprovalScopeCache)

    def gated_tools(self) -> set[str]:
        if self.mode == "off":
            return set()
        if self.mode == "writes":
            return set(GATED_WRITES)
        if self.mode == "all":
            return set(GATED_ALL)
        return set()

    def check(self, request: ApprovalRequest) -> ApprovalOutcome:
        if request.tool not in self.gated_tools():
            return ApprovalOutcome(decision="auto", scope_key=None)
        if self.auto_yes:
            return ApprovalOutcome(decision="auto", scope_key=None)
        candidates = _scope_candidates(request)
        cached = self.cache.lookup(request.tool, candidates)
        if cached is not None:
            return ApprovalOutcome(decision="approved_scoped", scope_key=cached, reason="scope cache hit")
        if self.prompt is None:
            return ApprovalOutcome(decision="denied", reason="no interactive prompt available")
        outcome = self.prompt(request)
        if outcome.decision == "approved_scoped" and outcome.scope_key is not None:
            self.cache.grant(request.tool, outcome.scope_key)
        elif outcome.decision == "approved_always":
            self.cache.grant(request.tool, "*")
            outcome.scope_key = "*"
        return outcome

    def check_budget_cap(self, reason: str, details: dict[str, Any], summary: str) -> ApprovalOutcome:
        if self.auto_yes:
            return ApprovalOutcome(decision="auto", reason="auto_yes")
        if self.prompt is None:
            return ApprovalOutcome(decision="denied", reason="no interactive prompt available")
        candidates = [reason, "*"]
        cached = self.cache.lookup(BUDGET_CAP_TOOL, candidates)
        if cached is not None:
            return ApprovalOutcome(decision="approved_scoped", scope_key=cached, reason="budget scope cache hit")
        request = ApprovalRequest(tool=BUDGET_CAP_TOOL, path=reason, args=details, summary=summary)
        outcome = self.prompt(request)
        if outcome.decision == "approved_scoped" and outcome.scope_key is not None:
            self.cache.grant(BUDGET_CAP_TOOL, outcome.scope_key)
        elif outcome.decision == "approved_always":
            self.cache.grant(BUDGET_CAP_TOOL, "*")
            outcome.scope_key = "*"
        return outcome


def _single_line_summary(text: str, *, limit: int = 160) -> str:
    flat = str(text).replace("\\r", "").replace("\\n", " ↵ ")
    return flat[:limit]


def _args_summary(tool: str, args: dict[str, Any]) -> str:
    if tool in {"read_file", "read_file_range", "write_file", "edit_file"}:
        path = args.get("path") or args.get("rel_path") or ""
        if tool == "edit_file":
            old = str(args.get("old") or "")
            new = str(args.get("new") or "")
            return _single_line_summary(f"{path}  - {old[:40]!r} -> + {new[:40]!r}", limit=160)
        return str(path)
    if tool == "run_bash":
        return _single_line_summary(str(args.get("command") or ""), limit=160)
    if tool == "run_tests":
        return str(args.get("path") or "")
    if tool == "spawn_subagent":
        return _single_line_summary(str(args.get("question") or ""), limit=120)
    if tool == "spawn_subagents":
        requests = args.get("requests") or []
        if isinstance(requests, list):
            return f"{len(requests)} sub-agent requests"
        return "parallel sub-agent requests"
    return _single_line_summary(json.dumps(args, sort_keys=True, ensure_ascii=False), limit=160)


def _request_for(call: ToolCall) -> ApprovalRequest:
    path = call.args.get("path") or call.args.get("rel_path")
    if call.name == "run_bash":
        command = str(call.args.get("command") or "")
        path = tools.rm_delete_target(command) or path
    return ApprovalRequest(
        tool=call.name,
        path=str(path) if path else None,
        args=dict(call.args),
        summary=_args_summary(call.name, call.args),
    )


def _emit_approval(recorder: TraceRecorder, call: ToolCall, outcome: ApprovalOutcome) -> None:
    recorder.emit(
        "approval",
        tool_use_id=call.tool_use_id,
        tool=call.name,
        args_summary=_args_summary(call.name, call.args),
        decision=outcome.decision,
        scope_key=outcome.scope_key,
        reason=outcome.reason,
    )


def _emit_tool_call(recorder: TraceRecorder, call: ToolCall, agent_id: str = "parent", parent_id: str | None = None, agent_type: str = "parent") -> None:
    recorder.emit(
        "tool_call",
        agent_id=agent_id,
        parent_id=parent_id,
        agent_type=agent_type,
        tool_use_id=call.tool_use_id,
        tool=call.name,
        args=call.args,
        args_summary=_args_summary(call.name, call.args),
        path=call.args.get("path") or call.args.get("rel_path"),
        command=call.args.get("command"),
    )

# Concrete file/bash tool schemas keyed by name; reused to compose per-agent surfaces.
FILE_TOOL_SCHEMAS: dict[str, dict[str, Any]] = {
    "read_file": {
        "name": "read_file",
        "description": "Read a UTF-8 text file under the workspace root.",
        "input_schema": {"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]},
    },
    "read_file_range": {
        "name": "read_file_range",
        "description": "Read an inclusive 1-based line range from a UTF-8 text file under the workspace root.",
        "input_schema": {
            "type": "object",
            "properties": {"path": {"type": "string"}, "start_line": {"type": "integer"}, "end_line": {"type": "integer"}},
            "required": ["path", "start_line", "end_line"],
        },
    },
    "write_file": {
        "name": "write_file",
        "description": "Write a UTF-8 text file under the workspace root (Coder only).",
        "input_schema": {"type": "object", "properties": {"path": {"type": "string"}, "content": {"type": "string"}}, "required": ["path", "content"]},
    },
    "edit_file": {
        "name": "edit_file",
        "description": "Replace exact text in a UTF-8 text file under the workspace root (Coder only).",
        "input_schema": {
            "type": "object",
            "properties": {"path": {"type": "string"}, "old": {"type": "string"}, "new": {"type": "string"}},
            "required": ["path", "old", "new"],
        },
    },
    "run_bash": {
        "name": "run_bash",
        "description": "Run one simple inspection command through bash, or exactly `rm <relative-file>` for approved single-file deletion. For top-level folder listings use `find . -maxdepth 1 -type d`. No pipes, redirection, shell control, Python, pytest, package managers, network tools, command chains, rm flags, globs, or directory deletion. Use run_tests for pytest.",
        "input_schema": {"type": "object", "properties": {"command": {"type": "string"}}, "required": ["command"]},
    },
    "run_tests": {
        "name": "run_tests",
        "description": "Run pytest on a workspace-relative test file (test_*.py) or test directory. Fixed invocation only; do not use run_bash for pytest.",
        "input_schema": {"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]},
    },
}

_SUBAGENT_REQUEST_SCHEMA = {
    "type": "object",
    "properties": {
        "type": {"type": "string", "enum": list(config.SUBAGENT_TYPES)},
        "question": {"type": "string"},
        "review_agent_id": {
            "type": "string",
            "description": "Optional coder agent id (e.g. coder-2) whose JSONL slice Reviewer receives. Defaults to the most recent Coder in the trace.",
        },
    },
    "required": ["type", "question"],
}

SPAWN_TOOL_SCHEMAS: list[dict[str, Any]] = [
    {
        "name": "spawn_subagent",
        "description": (
            "Spawn one typed sub-agent (grilling | explorer | coder | reviewer) for a "
            "bounded task. Grilling asks clarifying questions; Explorer inspects read-only; "
            "Coder is the only agent that may write/edit files; Reviewer verifies a Coder change."
        ),
        "input_schema": _SUBAGENT_REQUEST_SCHEMA,
    },
    {
        "name": "spawn_subagents",
        "description": (
            "Spawn two or more typed sub-agents that run concurrently. Use this for >=2 "
            "independent tasks (e.g. inspecting different files) so they execute in parallel."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "requests": {
                    "type": "array",
                    "minItems": 2,
                    "maxItems": config.MAX_PARALLEL_SUBAGENTS,
                    "items": _SUBAGENT_REQUEST_SCHEMA,
                }
            },
            "required": ["requests"],
        },
    },
]

# The parent never writes files directly: its surface is read tools + spawn tools.
PARENT_TOOL_SCHEMAS: list[dict[str, Any]] = [
    FILE_TOOL_SCHEMAS["read_file"],
    FILE_TOOL_SCHEMAS["read_file_range"],
    FILE_TOOL_SCHEMAS["run_bash"],
    FILE_TOOL_SCHEMAS["run_tests"],
    *SPAWN_TOOL_SCHEMAS,
]


def _subagent_tool_schemas(agent_type: str) -> list[dict[str, Any]]:
    names = SUBAGENT_TOOL_NAMES.get(agent_type, set())
    return [FILE_TOOL_SCHEMAS[name] for name in FILE_TOOL_SCHEMAS if name in names]


EXPLORER_TOOL_SCHEMAS = _subagent_tool_schemas("explorer")


def _compactor_stub_summary(tool: str, event: dict[str, object]) -> str:
    lines = str(event.get("result_full") or "").splitlines()
    return (
        f"Large {tool} result with {len(lines)} lines and {event.get('bytes')} bytes. "
        "The full content remains in the JSONL trace; use read_file_range or re-run "
        "a targeted read to retrieve specific lines."
    )


def _clamp_summary_tokens(summary: str, max_tokens: int | None = None) -> str:
    limit = max_tokens if max_tokens is not None else config.COMPACTOR_MAX_SUMMARY_TOKENS
    while summary and tools.estimate_tokens(summary) > limit:
        summary = summary[: max(1, len(summary) - 200)]
    return summary.strip()


def _prepare_compactor_input(body: str, *, trace_pointer: str) -> str:
    if len(body) <= config.COMPACTOR_MAX_INPUT_CHARS:
        return body
    return (
        body[: config.COMPACTOR_MAX_INPUT_CHARS]
        + f"\\n[truncated for compaction input; full payload at {trace_pointer}]"
    )


def _summarize_for_compactor(
    *,
    system_prompt: str,
    body: str,
    tool: str,
    client: Any,
    guard: BudgetGuard,
    recorder: TraceRecorder,
    trace_pointer: str,
    deterministic: bool = False,
    stub_event: dict[str, object] | None = None,
) -> tuple[str, bool]:
    """Return (summary, compactor_fallback)."""
    if deterministic:
        if "SAMPLE_LOG" in body or (stub_event and int(stub_event.get("tokens") or 0) > config.K_COMPACT):
            return "SAMPLE_LOG_SUMMARY_SENTINEL: large log summarised for parent context.", False
        return _compactor_stub_summary(tool, stub_event or {"result_full": body, "bytes": len(body.encode())}), True

    model = config.COMPACTOR_MODEL_ID
    prepared = _prepare_compactor_input(body, trace_pointer=trace_pointer)
    user_content = f"Tool: {tool}\\n\\n{prepared}"
    expected_in = tools.estimate_tokens(system_prompt + "\\n" + user_content)
    decision = guard.before_model_call(model, expected_in, config.COMPACTOR_MAX_OUTPUT_TOKENS)
    if not decision.allowed:
        return _compactor_stub_summary(tool, stub_event or {"result_full": body, "bytes": len(body.encode())}), True

    recorder.emit(
        "llm_start",
        agent_id="compactor",
        agent_type="compactor",
        model=model,
        model_id=model,
        step_idx=guard.step_count,
        tokens_in=expected_in,
        max_tokens=config.COMPACTOR_MAX_OUTPUT_TOKENS,
        endpoint_host=config.OPENROUTER_ENDPOINT_HOST,
        system_prompt_sha256=hashlib.sha256(system_prompt.encode("utf-8")).hexdigest(),
        tool_schema_count=0,
        tool_schema_names=[],
    )
    try:
        turn = client.complete(
            model=model,
            system_prompt=system_prompt,
            messages=[{"role": "user", "content": user_content}],
            tools=[],
            max_tokens=config.COMPACTOR_MAX_OUTPUT_TOKENS,
        )
    except LiveModelError:
        return _compactor_stub_summary(tool, stub_event or {"result_full": body, "bytes": len(body.encode())}), True
    if not isinstance(turn, ModelTurn):
        turn = ModelTurn(**turn)
    summary = _clamp_summary_tokens((turn.assistant_text or "").strip())
    model_id = turn.model_id or model
    input_tokens = turn.input_tokens or expected_in
    output_tokens = turn.output_tokens or tools.estimate_tokens(summary)
    cost = guard.record_model_call(model_id, input_tokens, output_tokens, cost_usd=turn.cost_usd, agent_type="compactor")
    recorder.emit(
        "assistant_step",
        agent_id="compactor",
        agent_type="compactor",
        model=model_id,
        model_id=model_id,
        step_idx=guard.step_count,
        tokens_in=input_tokens,
        tokens_out=output_tokens,
        cost_usd=cost,
        assistant_text=summary,
        tool_calls=[],
        stop_reason=turn.stop_reason,
        openrouter_provider=turn.openrouter_provider,
    )
    _emit_expensive_provider_warning(
        recorder,
        guard,
        openrouter_provider=turn.openrouter_provider,
        model_id=model_id,
        step_idx=guard.step_count,
        agent_id="compactor",
        cost_usd=cost,
    )
    return summary, False


def _compact_if_needed(
    recorder: TraceRecorder,
    event: dict[str, object],
    *,
    client: Any,
    guard: BudgetGuard,
    tool: str,
    deterministic: bool = False,
) -> dict[str, object] | None:
    tokens = int(event["tokens"])
    if tokens <= config.K_COMPACT:
        return None
    full = str(event["result_full"])
    trace_pointer = f"{recorder.run_id}:event:{event['event_idx']}"
    summary, fallback = _summarize_for_compactor(
        system_prompt=COMPACTION_SYSTEM_PROMPT,
        body=full,
        tool=tool or str(event.get("tool") or ""),
        client=client,
        guard=guard,
        recorder=recorder,
        trace_pointer=trace_pointer,
        deterministic=deterministic,
        stub_event=event,
    )
    after_tokens = tools.estimate_tokens(summary)
    return recorder.emit(
        "compaction",
        tool_use_id=event["tool_use_id"],
        before_tokens=tokens,
        after_tokens=after_tokens,
        summary=summary,
        compactor_model=config.COMPACTOR_MODEL_ID,
        compactor_fallback=fallback,
        original_event_idx=event["event_idx"],
        original_sha256=hashlib.sha256(full.encode("utf-8")).hexdigest(),
    )


def _context_window_for_model(model_id: str) -> int:
    return int(config.CONTEXT_WINDOW_TOKENS.get(model_id, config.DEFAULT_CONTEXT_WINDOW))


def _compact_fraction_for_model(model_id: str) -> float:
    return float(config.AUTO_COMPACT_FRACTION.get(model_id, config.DEFAULT_COMPACT_FRACTION))


def _split_messages_for_conversation_compaction(messages: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]] | None:
    user_indices = [index for index, message in enumerate(messages) if message.get("role") == "user"]
    if len(user_indices) <= config.COMPACT_KEEP_RECENT_TURNS:
        return None
    split_at = user_indices[-config.COMPACT_KEEP_RECENT_TURNS]
    if split_at <= 0:
        return None
    return messages[:split_at], messages[split_at:]


def compact_conversation(
    recorder: TraceRecorder,
    messages: list[dict[str, Any]],
    parent_model_id: str,
    guard: BudgetGuard,
    *,
    client: Any,
    reason: str,
    deterministic: bool = False,
) -> dict[str, object] | None:
    split = _split_messages_for_conversation_compaction(messages)
    if split is None:
        return None
    head, tail = split
    before = _estimate_message_tokens(PARENT_SYSTEM_PROMPT, messages)
    head_text = json.dumps(head, sort_keys=True, ensure_ascii=False)
    trace_pointer = str(recorder.run_id)
    summary, fallback = _summarize_for_compactor(
        system_prompt=CONVERSATION_COMPACTION_SYSTEM_PROMPT,
        body=head_text,
        tool="conversation",
        client=client,
        guard=guard,
        recorder=recorder,
        trace_pointer=trace_pointer,
        deterministic=deterministic,
    )
    folded = {
        "role": "user",
        "content": (
            f"[CONVERSATION COMPACTED reason={reason}]\\n"
            f"{summary}\\n"
            f"Trace pointer: {trace_pointer}. Full history remains in JSONL."
        ),
    }
    messages[:] = [folded, *tail]
    after = _estimate_message_tokens(PARENT_SYSTEM_PROMPT, messages)
    if before <= 0:
        percent_reduced = 0.0
    else:
        percent_reduced = round(100.0 - (after / before) * 100.0, 1)
    window = _context_window_for_model(parent_model_id)
    threshold = int(window * _compact_fraction_for_model(parent_model_id))
    return recorder.emit(
        "context_compaction",
        before_tokens=before,
        after_tokens=after,
        percent_reduced=percent_reduced,
        model=parent_model_id,
        window=window,
        threshold=threshold,
        reason=reason,
        summary=summary,
        trace_pointer=trace_pointer,
        compactor_fallback=fallback,
    )


def conversation_compact_skip_reason(
    messages: list[dict[str, Any]],
    parent_model_id: str,
) -> str | None:
    """Return a skip reason when manual compact is unnecessary; None if folding may proceed."""
    if not messages:
        return "no_history"
    user_turns = sum(1 for message in messages if message.get("role") == "user")
    split = _split_messages_for_conversation_compaction(messages)
    if split is None:
        if user_turns <= config.COMPACT_KEEP_RECENT_TURNS:
            return "too_few_user_turns"
        return "no_foldable_head"
    before = _estimate_message_tokens(PARENT_SYSTEM_PROMPT, messages)
    window = _context_window_for_model(parent_model_id)
    threshold = int(window * _compact_fraction_for_model(parent_model_id))
    if before <= threshold:
        return "below_auto_threshold"
    return None


def format_manual_compact_skip_warning(
    reason: str,
    messages: list[dict[str, Any]],
    parent_model_id: str,
) -> str:
    """Human-readable warning when /compact is skipped as unnecessary."""
    keep = config.COMPACT_KEEP_RECENT_TURNS
    if reason == "no_history":
        return "[context] /compact skipped: no conversation history yet — run a task first."
    if reason == "too_few_user_turns":
        user_turns = sum(1 for message in messages if message.get("role") == "user")
        return (
            f"[context] /compact skipped: only {user_turns} user turn(s) in chat memory; "
            f"need more than {keep} to fold older turns while keeping the last {keep} verbatim. "
            "Large tool results are still compacted automatically (see /review)."
        )
    if reason == "no_foldable_head":
        return (
            f"[context] /compact skipped: nothing to fold before the last {keep} user turns."
        )
    if reason == "below_auto_threshold":
        before = _estimate_message_tokens(PARENT_SYSTEM_PROMPT, messages)
        window = _context_window_for_model(parent_model_id)
        fraction = _compact_fraction_for_model(parent_model_id)
        threshold = int(window * fraction)
        pct = int(before / window * 100) if window else 0
        return (
            f"[context] /compact skipped: parent context is ~{before:,} tokens "
            f"({pct}% of {window:,} window) — below the "
            f"auto-fold threshold ({threshold:,} = {fraction:.0%} of window). "
            "Folding would save little. Tool-result compaction already applied on large reads."
        )
    return f"[context] /compact skipped: {reason}."


def _result(tool_use_id: str, tool: str, content: str, status: str, started: float) -> dict[str, object]:
    return {
        "tool_use_id": tool_use_id,
        "tool": tool,
        "result_full": content,
        "bytes": len(content.encode("utf-8")),
        "tokens": tools.estimate_tokens(content),
        "latency_ms": int((time.perf_counter() - started) * 1000),
        "status": status,
    }


def _normalise_tool_call(call: ToolCall | dict[str, Any]) -> ToolCall:
    if isinstance(call, ToolCall):
        return call
    return ToolCall(
        tool_use_id=str(call.get("tool_use_id") or call.get("id") or ""),
        name=str(call.get("name") or call.get("tool") or ""),
        args=dict(call.get("args") or call.get("input") or {}),
    )


def _tool_call_trace(call: ToolCall) -> dict[str, Any]:
    return {"tool_use_id": call.tool_use_id, "name": call.name, "args": call.args}


def _assistant_content(turn: ModelTurn) -> list[dict[str, Any]]:
    if turn.raw_content:
        return turn.raw_content
    content: list[dict[str, Any]] = []
    if turn.assistant_text:
        content.append({"type": "text", "text": turn.assistant_text})
    for call in turn.tool_calls:
        normalised = _normalise_tool_call(call)
        content.append({"type": "tool_use", "id": normalised.tool_use_id, "name": normalised.name, "input": normalised.args})
    return content or [{"type": "text", "text": ""}]


def _estimate_message_tokens(system_prompt: str, messages: list[dict[str, Any]]) -> int:
    return tools.estimate_tokens(system_prompt + "\\n" + json.dumps(messages, sort_keys=True, ensure_ascii=False))


def _expensive_openrouter_provider_slugs() -> tuple[str, ...]:
    raw = os.environ.get("OPENROUTER_EXPENSIVE_PROVIDERS")
    if raw is not None and str(raw).strip():
        parts = [part.strip().lower() for part in str(raw).split(",") if part.strip()]
        if parts:
            return tuple(parts)
    return config.EXPENSIVE_OPENROUTER_PROVIDER_SLUGS


def _is_expensive_openrouter_provider(slug: str | None) -> bool:
    if not slug:
        return False
    normalized = str(slug).strip().lower()
    for entry in _expensive_openrouter_provider_slugs():
        if normalized == entry or normalized.startswith(f"{entry}/"):
            return True
    return False


def _emit_expensive_provider_warning(
    recorder: TraceRecorder,
    guard: BudgetGuard,
    *,
    openrouter_provider: str | None,
    model_id: str,
    step_idx: int,
    agent_id: str,
    cost_usd: float,
) -> None:
    slug = str(openrouter_provider or "").strip()
    if not slug or not _is_expensive_openrouter_provider(slug):
        return
    warn_key = f"warn_expensive_provider:{slug.lower()}"
    if warn_key in guard.warned:
        return
    guard.warned.add(warn_key)
    recorder.emit(
        "budget_event",
        budget_reason="warn_expensive_provider",
        details={
            "openrouter_provider": slug,
            "model_id": model_id,
            "step_idx": step_idx,
            "agent_id": agent_id,
            "cost_usd": cost_usd,
        },
    )


def _record_budget_abort(recorder: TraceRecorder, guard: BudgetGuard, decision: Any, started: float) -> None:
    recorder.emit("budget_event", budget_reason=decision.budget_reason, details=decision.details)
    recorder.emit(
        "run_end",
        final_status="aborted",
        total_cost_usd=round(guard.running_usd, 6),
        total_tokens=guard.running_tokens,
        duration_s=round(time.perf_counter() - started, 3),
    )


def _budget_cap_summary(decision: Any) -> str:
    reason = str(getattr(decision, "budget_reason", None) or "budget")
    details = dict(getattr(decision, "details", None) or {})
    if reason in {"step_extend", "step_cap"}:
        steps = details.get("step_count", details.get("steps"))
        return f"{reason} steps {steps}/{details.get('max_steps')}"
    if reason == "token_cap":
        return f"{reason} tokens {details.get('tokens')}/{details.get('max_tokens')}"
    if reason == "usd_cap":
        cap = float(details.get('max_usd', config.MAX_USD_PER_RUN))
        spent = float(details.get('running_usd') or 0.0)
        step_est = float(details.get('worst_next_usd') or 0.0)
        projected = spent + step_est
        return (
            f"USD cap: next step ~{format_usd_display(projected)} exceeds cap {format_usd_display(cap)} "
            f"(spent {format_usd_display(spent)}, step est. ~{format_usd_display(step_est)})"
        )
    if reason == "daily_cap":
        return f"{reason} daily_remaining {details.get('daily_remaining_usd')}"
    if reason == "timeout":
        return f"{reason} after {details.get('timeout_s', config.WALL_CLOCK_TIMEOUT)}s"
    if reason == "repetition_abort":
        return f"{reason} tool={details.get('tool')} repeats={details.get('repeat_count')}"
    return reason


def _emit_budget_approval(recorder: TraceRecorder, decision: Any, outcome: ApprovalOutcome) -> None:
    reason = str(getattr(decision, "budget_reason", None) or "budget")
    recorder.emit(
        "approval",
        tool_use_id=f"budget-{reason}",
        tool=BUDGET_CAP_TOOL,
        args_summary=_budget_cap_summary(decision),
        decision=outcome.decision,
        scope_key=outcome.scope_key,
        reason=outcome.reason,
        budget_reason=reason,
    )


def _wall_clock_exceeded(started: float, guard: BudgetGuard) -> bool:
    return time.perf_counter() - started > float(config.WALL_CLOCK_TIMEOUT) + guard.wall_clock_extra_s


def _offer_step_extend_if_needed(
    *,
    policy: ApprovalPolicy,
    recorder: TraceRecorder,
    guard: BudgetGuard,
    started: float,
) -> bool:
    """Return False only when the user aborts the proactive step-extend prompt."""
    if not policy.step_extend_prompt or policy.auto_yes or policy.prompt is None:
        return True
    if not guard.should_offer_step_extend():
        return True
    details: dict[str, object] = {"step_count": guard.parent_step_count, "max_steps": guard.max_steps}
    decision = BudgetDecision(False, "step_extend", details)
    summary = _budget_cap_summary(decision)
    outcome = policy.check_budget_cap("step_extend", details, summary)
    _emit_budget_approval(recorder, decision, outcome)
    guard.mark_step_extend_prompted()
    if outcome.decision in {"approved", "approved_scoped", "approved_always", "auto"}:
        once = outcome.decision in {"approved", "auto"}
        guard.extend_cap("step_cap", once=once)
        recorder.emit(
            "budget_event",
            budget_reason="step_extend",
            details={**details, "extended": True},
        )
        return True
    if outcome.decision == "aborted":
        _record_budget_abort(recorder, guard, decision, started)
        return False
    return True


def _handle_budget_cap(
    *,
    policy: ApprovalPolicy,
    recorder: TraceRecorder,
    guard: BudgetGuard,
    decision: Any,
    started: float,
    agent_id: str = "parent",
    parent_id: str | None = None,
    agent_type: str = "parent",
) -> bool:
    """Return True when the caller should retry after extending a hard cap."""
    if getattr(decision, "allowed", True):
        return True
    reason = str(getattr(decision, "budget_reason", None) or "")
    if reason.startswith("warn_"):
        return False
    summary = _budget_cap_summary(decision)
    outcome = policy.check_budget_cap(reason, dict(getattr(decision, "details", None) or {}), summary)
    _emit_budget_approval(recorder, decision, outcome)
    if outcome.decision in {"approved", "approved_scoped", "approved_always", "auto"}:
        once = outcome.decision in {"approved", "auto"}
        guard.extend_cap(reason, once=once)
        recorder.emit(
            "budget_event",
            agent_id=agent_id,
            parent_id=parent_id,
            agent_type=agent_type,
            budget_reason=reason,
            details={**dict(getattr(decision, "details", None) or {}), "extended": True},
        )
        return True
    if agent_id == "parent":
        _record_budget_abort(recorder, guard, decision, started)
    else:
        recorder.emit(
            "budget_event",
            agent_id=agent_id,
            parent_id=parent_id,
            agent_type=agent_type,
            budget_reason=reason,
            details=getattr(decision, "details", None) or {},
        )
    return False


def _record_model_error(
    recorder: TraceRecorder,
    guard: BudgetGuard,
    exc: LiveModelError,
    started: float,
    *,
    model: str,
    step_idx: int,
    agent_id: str = "parent",
    parent_id: str | None = None,
    agent_type: str = "parent",
) -> None:
    fields: dict[str, Any] = {
        "agent_id": agent_id,
        "parent_id": parent_id,
        "agent_type": agent_type,
        "model": model,
        "model_id": model,
        "step_idx": step_idx,
        "error_type": type(exc).__name__,
        "message": str(exc),
        "retryable": getattr(exc, "retryable", False),
    }
    provider_detail = getattr(exc, "provider_detail", None)
    if provider_detail:
        fields["provider_detail"] = provider_detail
    recorder.emit("model_error", **fields)
    if agent_id == "parent":
        recorder.emit(
            "run_end",
            final_status="model_error",
            total_cost_usd=round(guard.running_usd, 6),
            total_tokens=guard.running_tokens,
            duration_s=round(time.perf_counter() - started, 3),
        )


PARENT_TOOL_NAMES = {schema["name"] for schema in PARENT_TOOL_SCHEMAS}


def _execute_live_tool(
    *,
    root: Path,
    call: ToolCall,
    recorder: TraceRecorder,
    client: Any,
    guard: BudgetGuard,
    allowed_tools: set[str],
    started: float,
    policy: ApprovalPolicy,
    agent_id: str = "parent",
    parent_id: str | None = None,
    agent_type: str = "parent",
) -> dict[str, object]:
    tool_name = call.name
    args = call.args
    tool_started = time.perf_counter()
    path = str(args.get("path") or args.get("rel_path") or "")
    _emit_tool_call(recorder, call, agent_id=agent_id, parent_id=parent_id, agent_type=agent_type)

    if tool_name not in allowed_tools:
        return _result(call.tool_use_id, tool_name, f"{agent_type} is not permitted to call {tool_name}", "error", tool_started)

    if tool_name == "run_bash":
        command = str(args.get("command") or "")
        safety_error = tools.validate_shell_command_for_workspace(root, command)
        if safety_error:
            return _result(call.tool_use_id, "run_bash", f"run_bash blocked: {safety_error}", "error", tool_started)

    if tool_name in policy.gated_tools():
        outcome = policy.check(_request_for(call))
        _emit_approval(recorder, call, outcome)
        if outcome.decision == "denied":
            return _result(call.tool_use_id, tool_name, f"approval denied: {outcome.reason}", "error", tool_started)
        if outcome.decision == "aborted":
            return _result(call.tool_use_id, tool_name, "approval aborted by user", "error", tool_started)

    if tool_name == "read_file":
        return tools.read_file(root, path, call.tool_use_id)
    if tool_name == "read_file_range":
        return tools.read_file_range(root, path, int(args.get("start_line", 1)), int(args.get("end_line", 1)), call.tool_use_id)
    if tool_name == "run_bash":
        command = str(args.get("command") or "")
        repeat = guard.record_tool_signature("run_bash", command)
        if not repeat.allowed:
            if not _handle_budget_cap(
                policy=policy,
                recorder=recorder,
                guard=guard,
                decision=repeat,
                started=started,
                agent_id=agent_id,
                parent_id=parent_id,
                agent_type=agent_type,
            ):
                return _result(call.tool_use_id, "run_bash", f"budget abort: {repeat.budget_reason}", "error", tool_started)
            guard.record_tool_signature("run_bash", command)
        return tools.run_bash(root, command, call.tool_use_id)
    if tool_name == "run_tests":
        test_path = str(args.get("path") or path or "")
        return tools.run_tests(root, test_path, call.tool_use_id)
    if tool_name == "write_file":
        return tools.write_file(root, path, str(args.get("content") or ""), call.tool_use_id)
    if tool_name == "edit_file":
        return tools.edit_file(root, path, str(args.get("old") or ""), str(args.get("new") or ""), call.tool_use_id)
    if tool_name in {"spawn_subagent", "spawn_subagents"} and agent_id == "parent":
        if guard.at_final_step_reserve():
            blocked = {
                "status": "near_cap_blocked",
                "message": (
                    "Parent step budget reserves the final step for synthesis. "
                    "Do not spawn sub-agents; summarize progress and answer the user now."
                ),
            }
            return _result(
                call.tool_use_id,
                tool_name,
                json.dumps(blocked, ensure_ascii=False),
                "ok",
                tool_started,
            )
        sig = _spawn_signature_key(tool_name, dict(args))
        repeat = guard.record_tool_signature(tool_name, sig)
        if not repeat.allowed:
            if not _handle_budget_cap(
                policy=policy,
                recorder=recorder,
                guard=guard,
                decision=repeat,
                started=started,
                agent_id=agent_id,
                parent_id=parent_id,
                agent_type=agent_type,
            ):
                return _result(
                    call.tool_use_id,
                    tool_name,
                    f"budget abort: {repeat.budget_reason}",
                    "error",
                    tool_started,
                )
            guard.record_tool_signature(tool_name, sig)
    if tool_name == "spawn_subagent":
        child_type = _normalise_agent_type(args.get("type"))
        question = str(args.get("question") or "")
        review_slice = None
        if child_type == "reviewer":
            coder_id = _resolve_review_coder_id(recorder, args.get("review_agent_id"))
            if not coder_id:
                return _result(
                    call.tool_use_id,
                    "spawn_subagent",
                    "Reviewer requires a prior Coder run in this session; spawn Explorer for read-only review.",
                    "error",
                    tool_started,
                )
            review_slice = _build_review_slice(recorder, coder_id)
        outcome = _spawn_one(root, child_type, question, recorder, client, guard, started, policy, review_slice)
        return _result(call.tool_use_id, "spawn_subagent", json.dumps(outcome, ensure_ascii=False), "ok", tool_started)
    if tool_name == "spawn_subagents":
        raw_requests = args.get("requests") or []
        if not isinstance(raw_requests, list) or len(raw_requests) < 2:
            return _result(call.tool_use_id, tool_name, "spawn_subagents requires at least two requests", "error", tool_started)
        summaries = _spawn_many(root, raw_requests, recorder, client, guard, started, policy)
        return _result(call.tool_use_id, "spawn_subagents", json.dumps(summaries, ensure_ascii=False), "ok", tool_started)
    return _result(call.tool_use_id, tool_name, f"unknown tool {tool_name!r}", "error", tool_started)


def _next_child_id(recorder: TraceRecorder, agent_type: str) -> str:
    n = sum(1 for event in recorder.events if event.get("kind") == "subagent_spawn") + 1
    return f"{agent_type}-{n}"


def _resolve_review_coder_id(recorder: TraceRecorder, requested: object) -> str | None:
    if requested is not None and str(requested).strip():
        return str(requested).strip()
    coder_ids: list[str] = []
    for event in recorder.events:
        if event.get("kind") != "subagent_spawn" or event.get("agent_type") != "coder":
            continue
        child_id = event.get("child_agent_id") or event.get("agent_id")
        if child_id:
            coder_ids.append(str(child_id))
    return coder_ids[-1] if coder_ids else None


def _build_review_slice(recorder: TraceRecorder, coder_agent_id: str, max_bytes: int = 8192) -> str:
    matched: list[dict[str, object]] = []
    for event in recorder.events:
        agent_id = str(event.get("agent_id") or "")
        child_id = str(event.get("child_agent_id") or "")
        if agent_id == coder_agent_id or child_id == coder_agent_id:
            matched.append(event)
    body = "\\n".join(json.dumps(event, ensure_ascii=False, sort_keys=True) for event in matched)
    encoded = body.encode("utf-8")
    if len(encoded) > max_bytes:
        body = body[: max_bytes // 2] + "\\n[review slice truncated]"
    return body


def _is_reviewer_verdict(text: str) -> bool:
    stripped = (text or "").strip()
    upper = stripped.upper()
    return upper.startswith("PASS:") or upper.startswith("FAIL:")


def _question_requires_tests(question: str) -> bool:
    lowered = question.lower()
    return "test_" in lowered or "pytest" in lowered or re.search(r"\\btests?\\b", lowered) is not None


def _is_test_file_path(path: str) -> bool:
    name = Path(str(path).replace("\\\\", "/")).name
    return name.startswith("test_") and name.endswith(".py")


def _is_impl_file_path(path: str) -> bool:
    name = Path(str(path).replace("\\\\", "/")).name
    return name.endswith(".py") and not name.startswith("test_")


def _subagent_error_reason_from_tool_result(tool_name: str, result_text: str) -> str:
    text = str(result_text or "").lower()
    if tool_name in {"read_file", "read_file_range"} and ("is a directory" in text or "not a regular file" in text):
        return "invalid_path_kind"
    if tool_name == "run_bash" and "shell control or redirection marker" in text:
        return "blocked_shell_control"
    if tool_name == "run_bash" and "run_bash blocked:" in text:
        return "blocked_run_bash"
    if "old text not found" in text:
        return "edit_not_found"
    return "tool_error"


def _spawn_signature_key(tool_name: str, args: dict[str, object]) -> str:
    if tool_name == "spawn_subagent":
        payload: object = {
            "type": _normalise_agent_type(args.get("type")),
            "question": str(args.get("question") or "")[:500],
        }
    else:
        norm: list[dict[str, str]] = []
        raw = args.get("requests") or []
        if isinstance(raw, list):
            for item in raw:
                if isinstance(item, dict):
                    norm.append(
                        {
                            "type": _normalise_agent_type(item.get("type")),
                            "question": str(item.get("question") or "")[:200],
                        }
                    )
        norm.sort(key=lambda entry: (entry["type"], entry["question"]))
        payload = {"requests": norm}
    return json.dumps(payload, sort_keys=True, ensure_ascii=False)[:2000]


@dataclass
class _ParallelBatchControl:
    slice_usd: float
    slice_tokens: int
    abort: threading.Event = field(default_factory=threading.Event, compare=False, repr=False)
    lock: object = field(default_factory=threading.Lock, compare=False, repr=False)
    offender_agent_id: str | None = None

    def check_over_slice(self, child_id: str, spent_usd: float, spent_tokens: int) -> bool:
        if spent_usd > self.slice_usd + 1e-9 or spent_tokens > self.slice_tokens:
            with self.lock:
                if self.offender_agent_id is None:
                    self.offender_agent_id = child_id
                self.abort.set()
            return True
        return self.abort.is_set()


def _run_live_subagent(
    root: Path,
    agent_type: str,
    question: str,
    recorder: TraceRecorder,
    client: Any,
    guard: BudgetGuard,
    child_id: str,
    started: float,
    policy: ApprovalPolicy,
    review_slice: str | None = None,
    batch_ctrl: _ParallelBatchControl | None = None,
    spawn_cost_before: tuple[float, int] | None = None,
) -> tuple[str, str, int, int, str | None]:
    """Run one typed sub-agent loop. Returns (summary, status, writes_ok, reads_ok, failure_reason)."""
    system_prompt = SUBAGENT_SYSTEM_PROMPTS[agent_type]
    model = config.SUBAGENT_MODEL_IDS[agent_type]
    tool_schemas = _subagent_tool_schemas(agent_type)
    allowed = set(SUBAGENT_TOOL_NAMES.get(agent_type, set()))
    if review_slice:
        messages: list[dict[str, Any]] = [{"role": "user", "content": f"{question}\\n\\nCoder run under review (JSONL slice):\\n{review_slice}"}]
    else:
        messages = [{"role": "user", "content": question}]
    final_summary = ""
    status = "ok"
    had_tool_error = False
    completed = False
    writes_ok = 0
    reads_ok = 0
    read_tools_ok = 0
    verdict_retry_used = False
    require_impl_read = agent_type == "coder" and _question_requires_tests(question)
    impl_read_ok = False
    empty_turn_retries = 0
    max_empty_turn_retries = 2
    failure_reason: str | None = None

    for local_step in range(1, config.MAX_SUBAGENT_STEPS + 1):
        if batch_ctrl is not None and batch_ctrl.abort.is_set():
            status = "parallel_aborted"
            failure_reason = "parallel_aborted"
            final_summary = (
                f"{agent_type} cancelled because a parallel peer exceeded its budget slice."
            )
            break
        if _wall_clock_exceeded(started, guard):
            timeout = type("Decision", (), {"budget_reason": "timeout", "details": {"timeout_s": config.WALL_CLOCK_TIMEOUT}})()
            if not _handle_budget_cap(
                policy=policy,
                recorder=recorder,
                guard=guard,
                decision=timeout,
                started=started,
                agent_id=child_id,
                parent_id="parent",
                agent_type=agent_type,
            ):
                status = "timeout"
                break
            continue
        expected_in = _estimate_message_tokens(system_prompt, messages)
        decision = guard.before_model_call(model, expected_in, 2048)
        if not decision.allowed:
            if not _handle_budget_cap(
                policy=policy,
                recorder=recorder,
                guard=guard,
                decision=decision,
                started=started,
                agent_id=child_id,
                parent_id="parent",
                agent_type=agent_type,
            ):
                status = "tool_error"
                failure_reason = "subagent_budget_cap"
                break
            continue
        recorder.emit(
            "llm_start",
            agent_id=child_id,
            parent_id="parent",
            agent_type=agent_type,
            model=model,
            model_id=model,
            step_idx=local_step,
            tokens_in=expected_in,
            max_tokens=2048,
            endpoint_host=config.OPENROUTER_ENDPOINT_HOST,
            system_prompt_sha256=hashlib.sha256(system_prompt.encode("utf-8")).hexdigest(),
            tool_schema_count=len(tool_schemas),
            tool_schema_names=[schema["name"] for schema in tool_schemas],
        )
        try:
            turn = client.complete(
                model=model,
                system_prompt=system_prompt,
                messages=messages,
                tools=tool_schemas,
                max_tokens=2048,
            )
        except LiveModelError as exc:
            _record_model_error(recorder, guard, exc, started, model=model, step_idx=local_step, agent_id=child_id, parent_id="parent", agent_type=agent_type)
            final_summary = f"{agent_type} stopped because {exc}"
            status = "tool_error"
            failure_reason = "model_error"
            break
        if not isinstance(turn, ModelTurn):
            turn = ModelTurn(**turn)
        turn.tool_calls = [_normalise_tool_call(c) for c in turn.tool_calls]
        model_id = turn.model_id or model
        input_tokens = turn.input_tokens or expected_in
        output_tokens = turn.output_tokens or tools.estimate_tokens(turn.assistant_text + json.dumps([asdict(c) for c in turn.tool_calls], sort_keys=True))
        cost = guard.record_model_call(model_id, input_tokens, output_tokens, cost_usd=turn.cost_usd, agent_type=agent_type)
        if batch_ctrl is not None and spawn_cost_before is not None:
            spent_usd = guard.running_usd - spawn_cost_before[0]
            spent_tokens = guard.running_tokens - spawn_cost_before[1]
            if batch_ctrl.check_over_slice(child_id, spent_usd, spent_tokens):
                status = "parallel_aborted"
                failure_reason = "parallel_aborted"
                final_summary = (
                    f"{agent_type} stopped: parallel budget slice exceeded "
                    f"(offender may be {batch_ctrl.offender_agent_id or child_id})."
                )
                break
        recorder.emit(
            "assistant_step",
            agent_id=child_id,
            parent_id="parent",
            agent_type=agent_type,
            model=model_id,
            model_id=model_id,
            step_idx=local_step,
            tokens_in=input_tokens,
            tokens_out=output_tokens,
            cost_usd=cost,
            assistant_text=turn.assistant_text,
            tool_calls=[_tool_call_trace(c) for c in turn.tool_calls],
            stop_reason=turn.stop_reason,
            openrouter_provider=turn.openrouter_provider,
        )
        _emit_expensive_provider_warning(
            recorder,
            guard,
            openrouter_provider=turn.openrouter_provider,
            model_id=model_id,
            step_idx=local_step,
            agent_id=child_id,
            cost_usd=cost,
        )
        messages.append({"role": "assistant", "content": _assistant_content(turn)})
        if not turn.tool_calls:
            final_summary = turn.assistant_text[:2048]
            empty_or_truncated_coder_turn = (
                agent_type == "coder"
                and (
                    not str(turn.assistant_text or "").strip()
                    or str(turn.stop_reason or "").strip().lower() == "length"
                )
            )
            if empty_or_truncated_coder_turn:
                empty_turn_retries += 1
                recorder.emit(
                    "budget_event",
                    agent_id=child_id,
                    parent_id="parent",
                    agent_type=agent_type,
                    budget_reason="subagent_empty_turn_retry",
                    details={
                        "empty_turn_retries": empty_turn_retries,
                        "max_empty_turn_retries": max_empty_turn_retries,
                    },
                )
                if empty_turn_retries <= max_empty_turn_retries:
                    messages.append(
                        {
                            "role": "user",
                            "content": (
                                "Your previous response did not complete a valid tool call. "
                                "For this mutation task you must call write_file or edit_file now. "
                                "Do not return empty or truncated text."
                            ),
                        }
                    )
                    continue
                status = "tool_error"
                final_summary = (
                    "Coder returned repeated empty responses without any tool calls."
                )
                failure_reason = "no_terminal_summary"
                recorder.emit(
                    "budget_event",
                    agent_id=child_id,
                    parent_id="parent",
                    agent_type=agent_type,
                    budget_reason="subagent_empty_turn_abort",
                    details={
                        "empty_turn_retries": empty_turn_retries,
                        "max_empty_turn_retries": max_empty_turn_retries,
                    },
                )
                completed = True
                break
            if agent_type == "reviewer":
                if read_tools_ok == 0:
                    if not verdict_retry_used:
                        messages.append(
                            {
                                "role": "user",
                                "content": "You must read_file or read_file_range the changed file on disk before returning a verdict.",
                            }
                        )
                        verdict_retry_used = True
                        continue
                    status = "tool_error"
                    final_summary = "Reviewer returned without reading workspace."
                    failure_reason = "reviewer_no_read"
                    completed = True
                    break
                if not _is_reviewer_verdict(final_summary):
                    if not verdict_retry_used:
                        messages.append(
                            {
                                "role": "user",
                                "content": "Return exactly one line starting with PASS: or FAIL: after verifying the file on disk.",
                            }
                        )
                        verdict_retry_used = True
                        continue
                    status = "tool_error"
                    final_summary = "Reviewer returned without PASS:/FAIL: verdict."
                    failure_reason = "reviewer_no_verdict"
                    completed = True
                    break
            completed = True
            break
        tool_blocks: list[dict[str, Any]] = []
        for c in turn.tool_calls:
            if (
                agent_type == "coder"
                and require_impl_read
                and not impl_read_ok
                and c.name == "write_file"
                and _is_test_file_path(str(c.args.get("path") or ""))
            ):
                result = _result(
                    c.tool_use_id,
                    "write_file",
                    "read the implementation module with read_file before writing test_*.py",
                    "error",
                    time.perf_counter(),
                )
            else:
                result = _execute_live_tool(
                    root=root,
                    call=c,
                    recorder=recorder,
                    client=client,
                    guard=guard,
                    allowed_tools=allowed,
                    started=started,
                    policy=policy,
                    agent_id=child_id,
                    parent_id="parent",
                    agent_type=agent_type,
                )
            recorder.emit("tool_result", agent_id=child_id, parent_id="parent", agent_type=agent_type, **result)
            tool_blocks.append({"type": "tool_result", "tool_use_id": c.tool_use_id, "content": str(result["result_full"]), "is_error": result["status"] != "ok"})
            if result["status"] == "ok":
                if c.name in {"write_file", "edit_file"}:
                    writes_ok += 1
                if c.name in {"read_file", "read_file_range"}:
                    reads_ok += 1
                    read_tools_ok += 1
                    read_path = str(c.args.get("path") or c.args.get("rel_path") or "")
                    if _is_impl_file_path(read_path):
                        impl_read_ok = True
                if c.name == "run_bash":
                    reads_ok += 1
                    if agent_type == "reviewer":
                        read_tools_ok += 1
            if result["status"] != "ok":
                had_tool_error = True
                failure_reason = _subagent_error_reason_from_tool_result(c.name, str(result["result_full"]))
                break
        messages.append({"role": "user", "content": tool_blocks})

    if agent_type == "reviewer" and not _is_reviewer_verdict(final_summary):
        # Contract: reviewer `subagent_return.payload` must start with
        # `PASS:` or `FAIL:` so the parent can always surface a readable
        # verdict (even on budget/timeout/step exhaustion).
        if status == "timeout":
            stop_reason = "timed out"
        elif not completed and status == "ok":
            stop_reason = "reached the reviewer step limit"
        else:
            stop_reason = "stopped before returning a verdict"
        final_summary = f"FAIL: Reviewer did not return PASS:/FAIL: ({stop_reason})."
        status = "tool_error"
        failure_reason = "reviewer_no_verdict"
        completed = True
    elif not final_summary:
        reason_label = failure_reason or ("step_limit" if not completed else "unknown")
        final_summary = f"{agent_type} exited without summary (reason={reason_label})."
    if not completed and status == "ok" and had_tool_error:
        status = "tool_error"
        if failure_reason is None:
            failure_reason = "tool_error"
    if agent_type == "coder" and completed and status == "ok" and writes_ok == 0:
        status = "tool_error"
        if empty_turn_retries > 0:
            failure_reason = failure_reason or "no_terminal_summary"
            final_summary = f"Coder exited without summary (reason={failure_reason})."
        else:
            failure_reason = failure_reason or "no_write"
            final_summary = f"Coder exited without summary (reason={failure_reason})."
    if agent_type == "coder" and completed and status == "ok" and require_impl_read and writes_ok > 0 and not impl_read_ok:
        status = "tool_error"
        failure_reason = "tests_without_impl_read"
        final_summary = f"Coder exited without summary (reason={failure_reason})."
    if status == "tool_error" and failure_reason is None:
        failure_reason = "tool_error"
    return final_summary, status, writes_ok, reads_ok, failure_reason


def _spawn_one(
    root: Path,
    agent_type: str,
    question: str,
    recorder: TraceRecorder,
    client: Any,
    guard: BudgetGuard,
    started: float,
    policy: ApprovalPolicy,
    review_slice: str | None = None,
    child_id: str | None = None,
    barrier: "threading.Barrier | None" = None,
    batch_ctrl: _ParallelBatchControl | None = None,
) -> dict[str, object]:
    child_id = child_id or _next_child_id(recorder, agent_type)
    model = config.SUBAGENT_MODEL_IDS[agent_type]
    started_at = now_iso()
    recorder.emit(
        "subagent_spawn",
        agent_id=child_id,
        parent_id="parent",
        agent_type=agent_type,
        child_agent_id=child_id,
        question=question,
        model=model,
        started_at=started_at,
    )
    cost_before = guard.running_usd
    tok_before = guard.running_tokens
    if barrier is not None:
        try:
            barrier.wait(timeout=config.WALL_CLOCK_TIMEOUT)
        except threading.BrokenBarrierError:
            pass
    run_started_at = now_iso()
    spawn_cost_before = (guard.running_usd, guard.running_tokens)
    summary, status, writes_ok, reads_ok, failure_reason = _run_live_subagent(
        root,
        agent_type,
        question,
        recorder,
        client,
        guard,
        child_id,
        started,
        policy,
        review_slice,
        batch_ctrl=batch_ctrl,
        spawn_cost_before=spawn_cost_before,
    )
    ended_at = now_iso()
    recorder.emit(
        "subagent_return",
        agent_id=child_id,
        parent_id="parent",
        agent_type=agent_type,
        child_agent_id=child_id,
        status=status,
        summary=summary,
        failure_reason=failure_reason,
        writes_ok=writes_ok,
        reads_ok=reads_ok,
        started_at=run_started_at,
        ended_at=ended_at,
        child_total_cost_usd=round(guard.running_usd - cost_before, 6),
        child_total_tokens=guard.running_tokens - tok_before,
    )
    return {
        "agent_id": child_id,
        "agent_type": agent_type,
        "status": status,
        "payload": summary,
        "failure_reason": failure_reason,
        "writes_ok": writes_ok,
        "reads_ok": reads_ok,
        "question": question,
    }


def _spawn_many(
    root: Path,
    raw_requests: list[Any],
    recorder: TraceRecorder,
    client: Any,
    guard: BudgetGuard,
    started: float,
    policy: ApprovalPolicy,
) -> list[dict[str, object]]:
    parsed: list[tuple[str, str, str | None]] = []
    for raw in raw_requests:
        if isinstance(raw, dict):
            review_id = raw.get("review_agent_id")
            review_key = str(review_id).strip() if review_id is not None and str(review_id).strip() else None
            parsed.append((_normalise_agent_type(raw.get("type")), str(raw.get("question") or ""), review_key))
    accepted = parsed[: config.MAX_PARALLEL_SUBAGENTS]
    overflow = parsed[config.MAX_PARALLEL_SUBAGENTS :]

    # Coders never run concurrently with another Coder (overlapping write paths):
    # the runtime serialises them and reports `conflict` for the second.
    runnable: list[tuple[int, str, str, str, str | None]] = []  # (slot, child_id, type, question, review_agent_id)
    conflicts: list[dict[str, object]] = []
    seen_coder = False
    for slot, (atype, question, review_agent_id) in enumerate(accepted):
        child_id = _next_child_id(recorder, atype) + f".{slot}"
        if atype == "coder" and seen_coder:
            conflicts.append({"agent_id": child_id, "agent_type": atype, "status": "conflict", "payload": "serialised: another Coder in the same batch holds the write lock", "slot": slot})
            continue
        if atype == "coder":
            seen_coder = True
        if atype == "reviewer" and _resolve_review_coder_id(recorder, review_agent_id) is None:
            conflicts.append(
                {
                    "agent_id": child_id,
                    "agent_type": atype,
                    "status": "tool_error",
                    "payload": "Reviewer requires a prior Coder run in this session; spawn Explorer for read-only review.",
                    "slot": slot,
                }
            )
            continue
        runnable.append((slot, child_id, atype, question, review_agent_id))

    results_by_slot: dict[int, dict[str, object]] = {}
    barrier = threading.Barrier(len(runnable)) if len(runnable) > 1 else None
    batch_ctrl: _ParallelBatchControl | None = None
    if len(runnable) > 1:
        with guard.lock:
            remaining_usd = max(0.0, guard.max_usd - guard.running_usd)
            remaining_tokens = max(0, guard.max_tokens - guard.running_tokens)
        n = len(runnable)
        batch_ctrl = _ParallelBatchControl(
            slice_usd=max(0.01, remaining_usd / n),
            slice_tokens=max(1000, remaining_tokens // n),
        )
    if runnable:
        with ThreadPoolExecutor(max_workers=len(runnable)) as pool:
            futures = {}
            for slot, child_id, atype, question, review_agent_id in runnable:
                review_slice = None
                if atype == "reviewer":
                    coder_id = _resolve_review_coder_id(recorder, review_agent_id)
                    if coder_id:
                        review_slice = _build_review_slice(recorder, coder_id)
                futures[
                    pool.submit(
                        _spawn_one,
                        root,
                        atype,
                        question,
                        recorder,
                        client,
                        guard,
                        started,
                        policy,
                        review_slice,
                        child_id,
                        barrier,
                        batch_ctrl,
                    )
                ] = slot
            for future, slot in futures.items():
                out = future.result()
                out["slot"] = slot
                results_by_slot[slot] = out
        if batch_ctrl is not None and batch_ctrl.offender_agent_id:
            recorder.emit(
                "budget_event",
                budget_reason="parallel_aborted",
                details={
                    "offender_agent_id": batch_ctrl.offender_agent_id,
                    "slice_usd": batch_ctrl.slice_usd,
                    "slice_tokens": batch_ctrl.slice_tokens,
                },
            )
    for conflict in conflicts:
        results_by_slot[int(conflict["slot"])] = conflict

    summaries = [results_by_slot[slot] for slot in sorted(results_by_slot)]
    for slot, (atype, question, _review_agent_id) in enumerate(overflow, start=len(accepted)):
        summaries.append({"agent_id": f"{atype}-overflow-{slot}", "agent_type": atype, "status": "tool_error", "payload": "parallel cap exceeded"})
    for entry in summaries:
        entry.pop("slot", None)
    return summaries


def _parse_spawn_payload(result: dict[str, object]) -> dict[str, object] | None:
    if str(result.get("tool") or "") != "spawn_subagent":
        return None
    if str(result.get("status") or "") != "ok":
        return None
    body = str(result.get("result_full") or "")
    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, dict):
        return None
    return payload


def _should_retry_coder_spawn(payload: dict[str, object], *, retry_used: bool) -> bool:
    if retry_used:
        return False
    if str(payload.get("agent_type") or "") != "coder":
        return False
    if str(payload.get("status") or "") != "tool_error":
        return False
    reason = str(payload.get("failure_reason") or "")
    return reason in {
        "invalid_path_kind",
        "blocked_shell_control",
        "blocked_run_bash",
        "no_terminal_summary",
        "no_write",
        "tool_error",
    }


def _constrained_retry_question(original_question: str, reason: str) -> str:
    constraints = (
        "Retry this coding task with strict constraints: use read_file on the exact file path "
        "(not a directory), then use write_file/edit_file directly. Do not use run_bash unless "
        "explicitly asked for `python3 -m py_compile <single .py file>`. "
        "Return only after at least one successful write_file or edit_file."
    )
    return f"{original_question}\\n\\nFailure reason from previous attempt: {reason}\\n{constraints}"


def _parallel_spawn_question(entry: dict[str, object]) -> str:
    if "initial" in entry and isinstance(entry.get("initial"), dict):
        initial = entry["initial"]
        return str(initial.get("question") or initial.get("payload") or "")
    return str(entry.get("payload") or "")


def _retry_failed_parallel_coders(
    root: Path,
    summaries: list[dict[str, object]],
    raw_requests: list[Any],
    recorder: TraceRecorder,
    client: Any,
    guard: BudgetGuard,
    started: float,
    policy: ApprovalPolicy,
) -> list[dict[str, object]]:
    """Bounded same-turn constrained retries for failed Coder entries in a parallel batch."""
    retries_done = 0
    out: list[dict[str, object]] = []
    for index, entry in enumerate(summaries):
        merged = dict(entry)
        if retries_done >= config.MAX_PARALLEL_CODER_RETRIES_PER_CALL:
            out.append(merged)
            continue
        if str(merged.get("agent_type") or "") != "coder":
            out.append(merged)
            continue
        if _should_retry_coder_spawn(merged, retry_used=False):
            question = str(merged.get("question") or "")
            if not question and index < len(raw_requests) and isinstance(raw_requests[index], dict):
                question = str(raw_requests[index].get("question") or "")
            if not question:
                question = _parallel_spawn_question(merged)
            retry_question = _constrained_retry_question(
                question,
                str(merged.get("failure_reason") or "tool_error"),
            )
            retry_payload = _spawn_one(
                root,
                "coder",
                retry_question,
                recorder,
                client,
                guard,
                started,
                policy,
            )
            retries_done += 1
            recorder.emit(
                "budget_event",
                budget_reason="coder_constrained_retry",
                details={
                    "reason": str(merged.get("failure_reason") or "tool_error"),
                    "original_agent_id": str(merged.get("agent_id") or ""),
                    "retry_agent_id": str(retry_payload.get("agent_id") or ""),
                    "parallel_index": index,
                },
            )
            merged = {"initial": entry, "retry": retry_payload, **retry_payload}
        out.append(merged)
    return out


def run_live_task(
    root: Path,
    task: str,
    recorder: TraceRecorder | None = None,
    client: Any | None = None,
    guard: BudgetGuard | None = None,
    policy: ApprovalPolicy | None = None,
    history: list[dict[str, Any]] | None = None,
) -> TraceRecorder:
    recorder = recorder or TraceRecorder(root)
    client = client or LiveModelClient.from_env(recorder=recorder)
    if isinstance(client, LiveModelClient) and client.recorder is None:
        client.recorder = recorder
    guard = guard or BudgetGuard.for_workspace(root)
    policy = policy or ApprovalPolicy()
    started = time.perf_counter()
    # `history` lets --chat carry conversation context across turns under one session;
    # when None this is a single-shot task.
    messages: list[dict[str, Any]] = history if history is not None else []
    messages.append({"role": "user", "content": task})
    recorder.emit("user_prompt", prompt=task, live_model=True)
    constrained_coder_retry_used = False

    while True:
        if _wall_clock_exceeded(started, guard):
            timeout = type("Decision", (), {"budget_reason": "timeout", "details": {"timeout_s": config.WALL_CLOCK_TIMEOUT}})()
            if not _handle_budget_cap(policy=policy, recorder=recorder, guard=guard, decision=timeout, started=started):
                return recorder
            continue
        if not _offer_step_extend_if_needed(policy=policy, recorder=recorder, guard=guard, started=started):
            return recorder
        expected_in = _estimate_message_tokens(PARENT_SYSTEM_PROMPT, messages)
        window = _context_window_for_model(config.PARENT_MODEL_ID)
        threshold = int(window * _compact_fraction_for_model(config.PARENT_MODEL_ID))
        if expected_in > threshold:
            compact_conversation(
                recorder,
                messages,
                config.PARENT_MODEL_ID,
                guard,
                client=client,
                reason="auto",
                deterministic=False,
            )
            expected_in = _estimate_message_tokens(PARENT_SYSTEM_PROMPT, messages)
        decision = guard.before_model_call(
            config.PARENT_MODEL_ID,
            expected_in,
            config.PARENT_MAX_OUTPUT_TOKENS,
            enforce_parent_step_cap=True,
        )
        if not decision.allowed:
            if not _handle_budget_cap(policy=policy, recorder=recorder, guard=guard, decision=decision, started=started):
                return recorder
            continue
        recorder.emit(
            "llm_start",
            model=config.PARENT_MODEL_ID,
            model_id=config.PARENT_MODEL_ID,
            step_idx=guard.parent_step_count + 1,
            tokens_in=expected_in,
            max_tokens=config.PARENT_MAX_OUTPUT_TOKENS,
            endpoint_host=config.OPENROUTER_ENDPOINT_HOST,
            system_prompt_sha256=hashlib.sha256(PARENT_SYSTEM_PROMPT.encode("utf-8")).hexdigest(),
            tool_schema_count=len(PARENT_TOOL_SCHEMAS),
            tool_schema_names=[schema["name"] for schema in PARENT_TOOL_SCHEMAS],
        )
        try:
            turn = client.complete(
                model=config.PARENT_MODEL_ID,
                system_prompt=PARENT_SYSTEM_PROMPT,
                messages=messages,
                tools=PARENT_TOOL_SCHEMAS,
                max_tokens=config.PARENT_MAX_OUTPUT_TOKENS,
            )
        except LiveModelError as exc:
            _record_model_error(
                recorder,
                guard,
                exc,
                started,
                model=config.PARENT_MODEL_ID,
                step_idx=guard.parent_step_count + 1,
            )
            return recorder
        if not isinstance(turn, ModelTurn):
            turn = ModelTurn(**turn)
        turn.tool_calls = [_normalise_tool_call(call) for call in turn.tool_calls]
        model_id = turn.model_id or config.PARENT_MODEL_ID
        input_tokens = turn.input_tokens or expected_in
        output_tokens = turn.output_tokens or tools.estimate_tokens(turn.assistant_text + json.dumps([asdict(c) for c in turn.tool_calls], sort_keys=True))
        cost = guard.record_model_call(model_id, input_tokens, output_tokens, cost_usd=turn.cost_usd)
        for warning in guard.pending_warnings():
            recorder.emit("budget_event", budget_reason=warning.budget_reason, details=warning.details)
        step_idx = guard.parent_step_count
        recorder.emit(
            "assistant_step",
            model=model_id,
            model_id=model_id,
            step_idx=step_idx,
            tokens_in=input_tokens,
            tokens_out=output_tokens,
            cost_usd=cost,
            assistant_text=turn.assistant_text,
            tool_calls=[_tool_call_trace(call) for call in turn.tool_calls],
            stop_reason=turn.stop_reason,
            openrouter_provider=turn.openrouter_provider,
        )
        _emit_expensive_provider_warning(
            recorder,
            guard,
            openrouter_provider=turn.openrouter_provider,
            model_id=model_id,
            step_idx=step_idx,
            agent_id="parent",
            cost_usd=cost,
        )
        messages.append({"role": "assistant", "content": _assistant_content(turn)})
        if not turn.tool_calls:
            recorder.emit(
                "run_end",
                final_status="ok",
                total_cost_usd=round(guard.running_usd, 6),
                total_tokens=guard.running_tokens,
                duration_s=round(time.perf_counter() - started, 3),
            )
            return recorder

        tool_blocks: list[dict[str, Any]] = []
        for call in turn.tool_calls:
            result = _execute_live_tool(
                root=root,
                call=call,
                recorder=recorder,
                client=client,
                guard=guard,
                allowed_tools=PARENT_TOOL_NAMES,
                started=started,
                policy=policy,
                agent_type="parent",
            )
            if call.name == "spawn_subagents" and result.get("status") == "ok":
                try:
                    batch = json.loads(str(result.get("result_full") or "[]"))
                except json.JSONDecodeError:
                    batch = None
                if isinstance(batch, list):
                    raw_requests = call.args.get("requests") if isinstance(call.args.get("requests"), list) else []
                    retried = _retry_failed_parallel_coders(
                        root,
                        batch,
                        raw_requests,
                        recorder,
                        client,
                        guard,
                        started,
                        policy,
                    )
                    if any(
                        "retry" in item
                        for item in retried
                        if isinstance(item, dict)
                    ):
                        result = {
                            **result,
                            "result_full": json.dumps(retried, ensure_ascii=False),
                        }
            if call.name == "spawn_subagent":
                payload = _parse_spawn_payload(result)
                if isinstance(payload, dict) and _should_retry_coder_spawn(payload, retry_used=constrained_coder_retry_used):
                    retry_question = _constrained_retry_question(
                        str(call.args.get("question") or ""),
                        str(payload.get("failure_reason") or "tool_error"),
                    )
                    retry_payload = _spawn_one(
                        root,
                        "coder",
                        retry_question,
                        recorder,
                        client,
                        guard,
                        started,
                        policy,
                    )
                    constrained_coder_retry_used = True
                    recorder.emit(
                        "budget_event",
                        budget_reason="coder_constrained_retry",
                        details={
                            "reason": str(payload.get("failure_reason") or "tool_error"),
                            "original_agent_id": str(payload.get("agent_id") or ""),
                            "retry_agent_id": str(retry_payload.get("agent_id") or ""),
                        },
                    )
                    result = {
                        **result,
                        "result_full": json.dumps(
                            {
                                "initial": payload,
                                "retry": retry_payload,
                            },
                            ensure_ascii=False,
                        ),
                    }
            event = recorder.emit("tool_result", **result)
            content = str(result["result_full"])
            compaction = _compact_if_needed(
                recorder,
                event,
                client=client,
                guard=guard,
                tool=call.name,
                deterministic=False,
            )
            if compaction is not None:
                content = compacted_marker(compaction)
            elif len(content.encode("utf-8")) > config.MAX_TOOL_RESULT_BYTES:
                head = content[: config.MAX_TOOL_RESULT_BYTES // 2]
                content = (
                    f"{head}\\n[TRUNCATED at {config.MAX_TOOL_RESULT_BYTES} bytes; full content at "
                    f"trace pointer {recorder.run_id}:event:{event['event_idx']}]"
                )
            tool_blocks.append({"type": "tool_result", "tool_use_id": call.tool_use_id, "content": content, "is_error": result["status"] != "ok"})
            if result["status"] != "ok":
                if call.name not in SOFT_RECOVERABLE_PARENT_TOOLS:
                    recorder.emit(
                        "run_end",
                        final_status="tool_error",
                        total_cost_usd=round(guard.running_usd, 6),
                        total_tokens=guard.running_tokens,
                        duration_s=round(time.perf_counter() - started, 3),
                    )
                    return recorder
        messages.append({"role": "user", "content": tool_blocks})
''',
    "__main__.py": '''"""Generated CLI."""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sys
from pathlib import Path
from typing import Any

try:
    import readline  # enables arrow-key history in input() on POSIX
except ImportError:  # Windows host lacks GNU readline; chat mode requires a TTY anyway
    readline = None

try:
    from prompt_toolkit import PromptSession
    from prompt_toolkit.completion import Completer, Completion
    from prompt_toolkit.history import FileHistory
    from prompt_toolkit.styles import Style
except ImportError:  # pragma: no cover - dependency is optional at runtime fallback level
    PromptSession = None
    Completer = None
    Completion = None
    FileHistory = None
    Style = None

from . import config, tools
from .chat_ui import (
    CHAT_PLACEHOLDER,
    WRITE_EDIT_TOOLS,
    build_session_status,
    capture_write_prior,
    emit_session_statusline,
    format_budget_cap_approval_text,
    format_compaction_banner,
    format_literal_tool_body,
    format_statusline_compact,
    mark_turn_completed,
    print_chat_dashboard_cleared,
    print_turn_output,
    progress_diff_lines,
    progress_stderr_lock,
    prompt_approval,
    refresh_chat_status_bar,
    render_input_bottom_and_footer,
    render_input_top_rule,
    reset_dashboard_mode,
    sanitize_summary_text,
    use_rich_ui,
    write_progress_diff_lines,
)
from .agent import (
    BUDGET_CAP_TOOL,
    ApprovalOutcome,
    ApprovalPolicy,
    ApprovalRequest,
    compact_conversation,
    conversation_compact_skip_reason,
    format_manual_compact_skip_warning,
    run_live_task,
)
from .live_model_client import LiveModelClient, MissingOpenRouterKey
from .budget import BudgetGuard, format_usd_display
from .demo_fixture import write_fixture
from .runtime_settings import (
    _refresh_subagent_model_ids,
    apply_runtime_settings,
    format_missing_pricing_warning,
    normalize_model_id,
    strict_model_pricing_enabled,
    validate_configured_models,
)
from .workspace_paths import resolve_workspace_root
from .trace import (
    TraceRecorder,
    format_parallel_progress_lines,
    format_show_context_overview,
    format_turn_review,
    parallel_finops_batch_lines,
    parallel_subagent_summary,
    parallel_subagent_summary_for_tool_result,
    render_tree,
    show_context,
)


def _stdin_prompt(stream: object | None = None, *, workspace_root: Path | None = None) -> "callable":
    fh = stream if stream is not None else sys.stdin

    def ask(request: ApprovalRequest) -> ApprovalOutcome:
        return prompt_approval(request, input_stream=fh, workspace_root=workspace_root)

    return ask


def _make_policy(args: argparse.Namespace, workspace_root: Path | None = None) -> ApprovalPolicy:
    mode = args.require_approval
    if mode == "off":
        return ApprovalPolicy(mode="off")
    return ApprovalPolicy(
        mode=mode,
        auto_yes=bool(args.yes),
        step_extend_prompt=not bool(getattr(args, "no_step_extend_prompt", False)),
        prompt=_stdin_prompt(workspace_root=workspace_root),
    )


def _print_budget(guard: BudgetGuard) -> None:
    from .budget import format_usd_number

    sys.stdout.write(
        f"steps {guard.parent_step_count}/{guard.max_steps}  "
        f"session_tokens {guard.running_tokens}/{guard.max_tokens}  "
        f"usd {format_usd_number(guard.running_usd)}/{format_usd_number(guard.max_usd)}  "
        f"daily_remaining {format_usd_number(guard.daily_remaining_usd)}\\n"
    )


def _print_budget_set_hint() -> None:
    sys.stdout.write(
        "Set caps: /budget steps N   /budget tokens N   /budget usd N   /budget daily N\\n"
        "  (combine: /budget steps 50 tokens 100000 usd 2 daily 4)\\n"
    )


_BUDGET_SLASH_KEYS = {
    "steps": "max_steps",
    "max_steps": "max_steps",
    "tokens": "max_tokens",
    "max_tokens": "max_tokens",
    "usd": "max_usd",
    "max_usd": "max_usd",
    "daily": "daily_remaining_usd",
    "daily_remaining": "daily_remaining_usd",
    "daily_remaining_usd": "daily_remaining_usd",
}


def _parse_budget_slash(prompt: str) -> tuple[dict[str, float | int], str | None]:
    parts = prompt.split()
    if not parts or parts[0].lower() != "/budget":
        return {}, "not a budget command"
    if len(parts) == 1:
        return {}, None
    caps: dict[str, float | int] = {}
    idx = 1
    while idx < len(parts):
        key = parts[idx].lower()
        field = _BUDGET_SLASH_KEYS.get(key)
        if field is None:
            return {}, f"unknown budget field: {parts[idx]!r} (try steps, tokens, usd, daily)"
        if idx + 1 >= len(parts):
            return {}, f"missing value for {key}"
        raw = parts[idx + 1]
        idx += 2
        try:
            if field == "max_steps":
                value: float | int = int(raw)
            elif field == "max_tokens":
                value = int(raw)
            else:
                value = float(raw)
        except ValueError:
            return {}, f"invalid value for {key}: {raw!r}"
        caps[field] = value
    return caps, None


def _handle_budget_slash(prompt: str, guard: BudgetGuard, recorder: TraceRecorder) -> None:
    caps, err = _parse_budget_slash(prompt)
    if err:
        sys.stdout.write(err + "\\n")
        return
    if not caps:
        _print_budget(guard)
        _print_budget_set_hint()
        return
    msg = guard.configure_caps(**caps)  # type: ignore[arg-type]
    if msg:
        sys.stdout.write(msg + "\\n")
        return
    recorder.emit("budget_event", budget_reason="user_config", details=caps)
    _print_budget(guard)


def _print_chat_status_report(
    recorder: TraceRecorder,
    guard: BudgetGuard,
    args: argparse.Namespace,
    *,
    since_event_idx: int = 0,
) -> None:
    from .chat_ui import estimate_parent_ctx_tokens

    line = _format_chat_statusline(
        recorder,
        guard,
        live_model=bool(args.live_model),
        since_event_idx=since_event_idx,
    )
    sys.stdout.write(line + "\\n")
    parent_ctx = estimate_parent_ctx_tokens(recorder.events)
    sys.stdout.write(
        f"parent_ctx {parent_ctx:,} tokens (next parent prompt via show_context) | "
        f"session_tokens {guard.running_tokens:,} (all models, budget cap)\\n"
    )
    _print_budget(guard)
    sys.stdout.write(f"trace: {recorder.path}\\n")
    final_status = _latest_run_end_status(recorder.events)
    if final_status:
        sys.stdout.write(f"last_run: {final_status}\\n")
    model_error = _latest_model_error(recorder.events)
    if model_error:
        sys.stdout.write(f"last_model_error: {model_error.get('message')}\\n")
        detail = model_error.get("provider_detail")
        if detail:
            sys.stdout.write(f"provider_detail: {detail}\\n")


SLASH_COMMANDS = (
    "/exit",
    "/quit",
    "/budget",
    "/status",
    "/finops",
    "/approvals",
    "/reset",
    "/new",
    "/show-context",
    "/compact",
    "/review",
    "/help",
)
SLASH_COMMAND_USAGE = {
    "/budget": "/budget [steps N] [tokens N] [usd N] [daily N]",
    "/show-context": "/show-context N",
    "/compact": "/compact",
    "/review": "/review [N]",
}
SLASH_COMMAND_META = {
    "/exit": "End chat cleanly",
    "/quit": "Alias for /exit",
    "/budget": "Show or set session caps (steps, tokens, usd, daily)",
    "/status": "Refresh dashboard (TTY) and print session summary on stdout",
    "/finops": "Show per-agent token, tool, and cost table (+ parallel batches)",
    "/review": "Readable recap of a completed turn (default: last)",
    "/approvals": "Show approval history and cached scopes",
    "/reset": "Clear approvals, budget, and chat history",
    "/new": "Start a fresh chat session and trace",
    "/show-context": "Overview, or N for parent context JSON at step N",
    "/compact": "Summarise folded conversation head; keep recent turns verbatim",
    "/help": "Show slash command help",
}


def _format_slash_command_help() -> str:
    lines = ["Slash commands:"]
    usages = {command: SLASH_COMMAND_USAGE.get(command, command) for command in SLASH_COMMANDS}
    usage_width = max(len(usage) for usage in usages.values())
    for command in SLASH_COMMANDS:
        lines.append(f"  {usages[command]:<{usage_width}}  {SLASH_COMMAND_META[command]}")
    lines.extend(
        (
            "",
            "Notes:",
            "  Normal text is sent to the agent as the next task.",
            "  Interactive terminals autocomplete slash commands after typing /.",
            "  TTY: /new, /reset, /status clear the screen and refresh the dashboard.",
            "  /budget alone prints caps plus how to set steps, tokens, usd, or daily.",
        )
    )
    return "\\n".join(lines)


SLASH_COMMAND_HELP = _format_slash_command_help()


def _slash_command_completer() -> Any:
    if Completer is None or Completion is None:
        return None

    class SlashCommandCompleter(Completer):
        def get_completions(self, document: Any, complete_event: Any) -> Any:
            before_cursor = document.text_before_cursor
            if not before_cursor.startswith("/") or any(ch.isspace() for ch in before_cursor):
                return
            prefix = before_cursor.lower()
            for command in SLASH_COMMANDS:
                if command.lower().startswith(prefix):
                    yield Completion(
                        command,
                        start_position=-len(before_cursor),
                        display=f"{command:<16}",
                        display_meta=SLASH_COMMAND_META[command],
                    )

    return SlashCommandCompleter()


def _make_chat_prompt(history_path: Path) -> tuple[Any, Any]:
    if (
        bool(getattr(sys.stdin, "isatty", lambda: False)())
        and PromptSession is not None
        and FileHistory is not None
    ):
        prompt_style = Style.from_dict({"prompt": "dim"}) if Style is not None and use_rich_ui() else None
        message: Any = "> "
        if use_rich_ui():
            message = [("class:prompt", "> ")]
        session = PromptSession(
            message,
            completer=_slash_command_completer(),
            complete_while_typing=True,
            history=FileHistory(str(history_path)),
            placeholder=CHAT_PLACEHOLDER if use_rich_ui() else None,
            style=prompt_style,
        )
        return session.prompt, lambda: None

    readline_history_enabled = False
    if readline is not None:
        readline.set_history_length(1000)
        try:
            readline.read_history_file(str(history_path))
        except OSError:
            pass
        readline_history_enabled = True

    def read_prompt() -> str:
        return input("> ")

    def save_history() -> None:
        if not readline_history_enabled:
            return
        try:
            readline.write_history_file(str(history_path))
        except OSError:
            pass

    return read_prompt, save_history


def _tool_calls_by_agent_type(events: list[dict[str, object]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for event in events:
        if event.get("kind") != "tool_call":
            continue
        agent_type = str(event.get("agent_type") or "parent")
        counts[agent_type] = counts.get(agent_type, 0) + 1
    return counts


def _print_finops(guard: BudgetGuard, recorder: TraceRecorder | None = None) -> None:
    """Per-agent-type FinOps breakdown (the pitch's live cost dashboard).

    Live values come from the BudgetGuard; the persistent store is the SQLite
    mirror at config.SQLITE_TRACE_DB for offline dashboard queries.
    """
    tool_counts = _tool_calls_by_agent_type(recorder.events) if recorder is not None else {}
    rows = sorted(
        set(guard.per_agent_type_tokens) | set(guard.per_agent_type_usd) | set(tool_counts),
        key=lambda t: guard.per_agent_type_usd.get(t, 0.0),
        reverse=True,
    )
    sys.stdout.write("FinOps - per-agent-type spend this session\\n")
    sys.stdout.write("prompts=model calls, tools=tool calls\\n")
    sys.stdout.write(f"{'agent_type':<12} {'in_tok':>10} {'out_tok':>10} {'total_tok':>10} {'prompts':>8} {'tools':>7} {'usd':>12}\\n")
    for agent_type in rows:
        input_tokens = guard.per_agent_type_input_tokens.get(agent_type, 0)
        output_tokens = guard.per_agent_type_output_tokens.get(agent_type, 0)
        tokens = guard.per_agent_type_tokens.get(agent_type, 0)
        model_calls = guard.per_agent_type_model_calls.get(agent_type, 0)
        tools = tool_counts.get(agent_type, 0)
        usd = guard.per_agent_type_usd.get(agent_type, 0.0)
        sys.stdout.write(f"{agent_type:<12} {input_tokens:>10} {output_tokens:>10} {tokens:>10} {model_calls:>8} {tools:>7} {usd:>12.6f}\\n")
    sys.stdout.write(
        f"{'TOTAL':<12} {guard.running_input_tokens:>10} {guard.running_output_tokens:>10} "
        f"{guard.running_tokens:>10} {guard.step_count:>8} {sum(tool_counts.values()):>7} {guard.running_usd:>12.6f}\\n"
    )
    if recorder is not None:
        user_prompts = sum(1 for event in recorder.events if event.get("kind") == "user_prompt")
        sys.stdout.write(f"user_prompts {user_prompts}\\n")
        parallel_lines = parallel_finops_batch_lines(recorder.events)
        if parallel_lines:
            sys.stdout.write("\\n".join(parallel_lines) + "\\n")


def _print_approvals(policy: ApprovalPolicy, recorder: TraceRecorder) -> None:
    approvals = [event for event in recorder.events if event.get("kind") == "approval"]
    sys.stdout.write("Approvals - session history\\n")
    if approvals:
        sys.stdout.write(f"{'#':>4} {'tool':<16} {'decision':<18} {'scope':<18} summary\\n")
        for event in approvals:
            scope = str(event.get("scope_key") or "-")
            summary = str(event.get("args_summary") or "")
            sys.stdout.write(
                f"{int(event.get('event_idx') or 0):>4} "
                f"{str(event.get('tool') or ''):<16} "
                f"{str(event.get('decision') or ''):<18} "
                f"{scope:<18} {summary}\\n"
            )
    else:
        sys.stdout.write("  (no approvals this session)\\n")

    cached = policy.cache.listing()
    sys.stdout.write("Cached approval scopes\\n")
    if cached:
        for tool, scope in cached:
            sys.stdout.write(f"  {tool}  {scope}\\n")
    else:
        sys.stdout.write("  (no reusable scopes)\\n")


def _format_compact_number(value: object) -> str:
    number = float(value or 0)
    if number >= 1_000_000:
        return f"{number / 1_000_000:.1f}m"
    if number >= 1_000:
        return f"{number / 1_000:.1f}k"
    return str(int(number))


def _bar(used: int, total: int, width: int = 10) -> str:
    if total <= 0:
        return "-" * width
    filled = max(0, min(width, round((used / total) * width)))
    return "#" * filled + "-" * (width - filled)


def _short_model(model: object) -> str:
    text = str(model or "")
    for prefix in ("openrouter/anthropic/", "openrouter/"):
        if text.startswith(prefix):
            return text[len(prefix):]
    return text


def _latest_parent_llm_start(events: list[dict[str, object]]) -> dict[str, object] | None:
    for event in reversed(events):
        if event.get("kind") == "llm_start" and event.get("agent_id") == "parent":
            return event
    return None


def _latest_run_state(events: list[dict[str, object]], *, since_event_idx: int = 0) -> str:
    for event in reversed(events[since_event_idx:]):
        kind = event.get("kind")
        if kind == "run_end":
            final_status = str(event.get("final_status") or "done")
            if final_status == "tool_error":
                return "tool_error (turn failed)"
            return final_status
        if kind == "budget_event":
            return str(event.get("budget_reason") or "budget")
    return "ready"


def _tool_error_count(events: list[dict[str, object]]) -> int:
    return sum(
        1
        for event in events
        if event.get("kind") == "tool_result" and event.get("status") != "ok"
    )


def clarify_tool_error(tool: str, message: str) -> str:
    """Expand terse tool refusals for CLI display (trace keeps the same text)."""
    text = str(message or "").strip()
    if not text:
        return text
    if "denylist" in text and "sensitive path" in text:
        match = re.search(r"'([^']+)'", text)
        if match:
            refreshed = tools.validate_sensitive_path(match.group(1))
            if refreshed:
                return refreshed
    if text.startswith("refused unsafe command:"):
        return "run_bash blocked:" + text[len("refused unsafe command:") :]
    if text.startswith("approval denied:"):
        return f"{tool} denied by approval policy:" + text[len("approval denied:") :]
    if text == "approval aborted by user":
        return f"{tool} cancelled - approval prompt returned abort"
    if text.startswith("path ") and "escapes the workspace root" in text:
        return text.replace("path ", "blocked path ", 1)
    if "No module named pytest" in text:
        return (
            "run_tests: pytest is not installed in the agent venv; "
            "reinstall the package with pytest in runtime dependencies."
        )
    return text


def _format_chat_statusline(
    recorder: TraceRecorder,
    guard: BudgetGuard,
    *,
    live_model: bool,
    since_event_idx: int = 0,
    width: int | None = None,
    force_state: str | None = None,
) -> str:
    status = build_session_status(
        root=recorder.root,
        recorder=recorder,
        guard=guard,
        live_model=live_model,
        since_event_idx=since_event_idx,
        force_state=force_state,
    )
    return format_statusline_compact(status, width=width)


def _chat_statusline_color(line: str, *, use_color: bool) -> str:
    if not use_color:
        return line
    lowered = line.lower()
    has_tool_errors = "tool errs " in lowered and "tool errs 0" not in lowered and "/ 0 session" not in lowered
    if any(marker in lowered for marker in ("tool_error", "model_error", "aborted")) or has_tool_errors:
        color = "\\x1b[31m"
    elif "!usd" in lowered or "exceeds cap" in lowered or "(next ~$" in lowered:
        color = "\\x1b[31m"
    elif any(marker in lowered for marker in ("warn_", "cap")):
        color = "\\x1b[33m"
    else:
        color = "\\x1b[32m"
    return f"{color}{line}\\x1b[0m"


def _print_chat_statusline(
    recorder: TraceRecorder,
    guard: BudgetGuard,
    *,
    live_model: bool,
    since_event_idx: int = 0,
) -> None:
    if not live_model:
        return
    line = _format_chat_statusline(
        recorder, guard, live_model=live_model, since_event_idx=since_event_idx
    )
    use_color = bool(getattr(sys.stderr, "isatty", lambda: False)()) and not os.environ.get("NO_COLOR")
    line = _chat_statusline_color(line, use_color=use_color)
    sys.stderr.write(line + "\\n")
    sys.stderr.flush()


def _tool_summary(call: dict[str, Any]) -> str:
    name = str(call.get("name") or call.get("tool") or "")
    args = call.get("args") or call.get("input") or {}
    if not isinstance(args, dict):
        return name
    if name in {"read_file", "read_file_range", "write_file", "edit_file"}:
        return f"{name} {args.get('path') or args.get('rel_path') or ''}".strip()
    if name == "run_bash":
        command = str(args.get("command") or "")
        return f"run_bash {sanitize_summary_text(command, limit=120)}"
    if name == "spawn_subagent":
        return f"spawn_subagent {sanitize_summary_text(str(args.get('question') or ''), limit=120)}"
    if name == "spawn_subagents":
        requests = args.get("requests") or []
        count = len(requests) if isinstance(requests, list) else "?"
        return f"spawn_subagents {count} requests"
    return name


def _format_progress_event(event: dict[str, object]) -> str | None:
    kind = event.get("kind")
    agent = str(event.get("agent_id") or "parent")
    if kind == "llm_start":
        return (
            f"[llm] {agent} step {event.get('step_idx')} -> {_short_model(event.get('model'))} "
            f"in~{event.get('tokens_in')} max_out={event.get('max_tokens')}"
        )
    if kind == "assistant_step":
        provider = event.get("openrouter_provider")
        provider_part = f" provider={provider}" if provider else ""
        line = (
            f"[llm] {agent} step {event.get('step_idx')} done "
            f"in={event.get('tokens_in')} out={event.get('tokens_out')} "
            f"usd={float(event.get('cost_usd') or 0):.6f} stop={event.get('stop_reason')}"
            f"{provider_part}"
        )
        tool_calls = event.get("tool_calls") or []
        if isinstance(tool_calls, list) and tool_calls:
            summaries = [_tool_summary(call) for call in tool_calls if isinstance(call, dict)]
            if summaries:
                line += " tools=" + " | ".join(summaries)
        return line
    if kind == "tool_result":
        line = (
            f"[tool] {agent} {event.get('tool')} {event.get('status')} "
            f"tokens={event.get('tokens')} {event.get('latency_ms')}ms"
        )
        tool_name = str(event.get("tool") or "")
        if event.get("status") != "ok":
            detail = clarify_tool_error(tool_name, str(event.get("result_full") or "")).replace("\\n", " ")
            if detail:
                line += f": {detail[:220]}"
        elif tool_name == "spawn_subagent":
            try:
                outcome = json.loads(str(event.get("result_full") or ""))
            except json.JSONDecodeError:
                outcome = None
            if isinstance(outcome, dict) and outcome.get("status") == "tool_error":
                child = outcome.get("agent_id") or "sub-agent"
                payload = clarify_tool_error(
                    tool_name, str(outcome.get("payload") or "sub-agent failed")
                ).replace("\\n", " ")
                line += f" (sub-agent {child} failed: {payload[:160]})"
        return line
    if kind == "approval":
        return f"[approval] {event.get('tool')} decision={event.get('decision')} scope={event.get('scope_key')}"
    if kind == "subagent_spawn":
        return f"[agent] spawn {event.get('child_agent_id')} {_short_model(event.get('model'))}"
    if kind == "subagent_return":
        child = event.get("child_agent_id")
        line = (
            f"[agent] return {child} tokens={event.get('child_total_tokens')} "
            f"usd={event.get('child_total_cost_usd')}"
        )
        child_status = str(event.get("status") or "ok")
        if child_status != "ok":
            summary = clarify_tool_error(
                "subagent", str(event.get("summary") or child_status)
            ).replace("\\n", " ")
            line += f" status={child_status}: {summary[:180]}"
        return line
    if kind == "compaction":
        return f"[context] compacted tool result {event.get('before_tokens')} -> {event.get('after_tokens')} tokens"
    if kind == "context_compaction":
        reason = event.get("reason") or "auto"
        return (
            f"[context] {reason}-compact {event.get('before_tokens')} -> {event.get('after_tokens')} "
            f"tokens ({event.get('percent_reduced')}% reduced); full history in trace"
        )
    if kind == "budget_event":
        reason = event.get("budget_reason")
        details = event.get("details") or {}
        if reason == "warn_expensive_provider" and isinstance(details, dict):
            slug = details.get("openrouter_provider")
            if slug:
                return f"[budget] {reason} provider={slug} model={details.get('model_id')}"
        return f"[budget] {reason}"
    if kind == "model_error":
        retry = " retryable" if event.get("retryable") else ""
        line = f"[llm] {agent} step {event.get('step_idx')} failed{retry}: {event.get('message')}"
        detail = event.get("provider_detail")
        if detail:
            line += f" | provider_detail: {detail}"
        return line
    if kind == "egress_blocked":
        return f"[network] blocked host={event.get('host')}"
    if kind == "run_end":
        final_status = str(event.get("final_status") or "done")
        line = f"[run] {final_status} tokens={event.get('total_tokens')} usd={event.get('total_cost_usd')}"
        if final_status == "tool_error":
            line += " - a tool was blocked or failed; see [tool] lines above"
        elif final_status not in {"ok", "done"}:
            line += f" - run ended with status {final_status}"
        return line
    return None


def _verbose_chat_progress_enabled() -> bool:
    return os.environ.get("VG_CHAT_VERBOSE_PROGRESS") == "1"


def _should_print_compact_progress_event(event: dict[str, object]) -> bool:
    kind = event.get("kind")
    agent_id = str(event.get("agent_id") or "parent")
    agent_type = str(event.get("agent_type") or "")
    is_parent = agent_id == "parent"

    if kind in {"llm_start", "assistant_step"}:
        return is_parent
    if kind in {"approval", "budget_event", "model_error", "egress_blocked", "run_end"}:
        return True
    if kind in {"compaction", "context_compaction"}:
        return True
    if kind == "tool_result":
        if event.get("status") != "ok":
            return True
        tool = str(event.get("tool") or "")
        return tool in WRITE_EDIT_TOOLS
    if kind == "subagent_spawn":
        return agent_type in {"coder", "reviewer"}
    if kind == "subagent_return":
        child_status = str(event.get("status") or "ok")
        return child_status != "ok" or agent_type in {"coder", "reviewer"}
    return False


def _progress_event_color(event: dict[str, object], *, use_color: bool) -> str:
    if not use_color:
        return ""
    kind = event.get("kind")
    if kind == "tool_result" and event.get("status") != "ok":
        return "\\x1b[31m"
    if kind == "run_end" and event.get("final_status") not in {None, "ok"}:
        return "\\x1b[31m"
    if kind in {"model_error", "egress_blocked"}:
        return "\\x1b[31m"
    if kind == "budget_event":
        return "\\x1b[33m"
    if kind == "approval":
        return "\\x1b[36m"
    if kind in {"subagent_spawn", "subagent_return"}:
        return "\\x1b[35m"
    if kind == "compaction":
        return "\\x1b[34m"
    return "\\x1b[90m"


def _make_progress_sink(
    stream: object | None = None,
    *,
    on_parent_status: Any = None,
    turn_state: dict[str, Any] | None = None,
    workspace_root: Path | None = None,
    recorder: TraceRecorder | None = None,
    rich_chat: bool = False,
) -> "callable":
    fh = stream if stream is not None else sys.stderr
    use_color = bool(getattr(fh, "isatty", lambda: False)()) and not os.environ.get("NO_COLOR")
    compact_progress = rich_chat and not _verbose_chat_progress_enabled()
    reset = "\\x1b[0m" if use_color else ""
    state = turn_state if turn_state is not None else {}
    pending_calls: dict[str, dict[str, object]] = {}
    write_priors: dict[str, str] = state.setdefault("write_priors", {})

    def sink(event: dict[str, object]) -> None:
        with progress_stderr_lock:
            _progress_sink_event(
                event,
                fh=fh,
                use_color=use_color,
                reset=reset,
                state=state,
                pending_calls=pending_calls,
                write_priors=write_priors,
                on_parent_status=on_parent_status,
                workspace_root=workspace_root,
                recorder=recorder,
                compact_progress=compact_progress,
            )

    return sink


def _progress_sink_event(
    event: dict[str, object],
    *,
    fh: object,
    use_color: bool,
    reset: str,
    state: dict[str, Any],
    pending_calls: dict[str, dict[str, object]],
    write_priors: dict[str, str],
    on_parent_status: Any,
    workspace_root: Path | None,
    recorder: TraceRecorder | None,
    compact_progress: bool,
) -> None:
    kind = event.get("kind")
    if kind == "statusline":
        return
    if kind == "user_prompt":
        state["turn"] = int(state.get("turn", 0)) + 1
        if recorder is not None:
            state["turn_list_start"] = len(recorder.events) - 1
        pending_calls.clear()
        state["progress_diff_paths"] = set()
        if use_color:
            fh.write(f"\\n\\x1b[90m── turn {state['turn']} ──\\x1b[0m\\n")
        else:
            fh.write(f"\\n── turn {state['turn']} ──\\n")
    if kind == "tool_call":
        tool = str(event.get("tool") or "")
        tool_use_id = str(event.get("tool_use_id") or "")
        if tool in WRITE_EDIT_TOOLS and tool_use_id:
            pending_calls[tool_use_id] = event
            if tool == "write_file" and workspace_root is not None:
                prior = capture_write_prior(workspace_root, event)
                if prior is not None:
                    write_priors[tool_use_id] = prior
    banner = format_compaction_banner(event)
    if banner:
        fh.write(f"{banner}\\n")
    line = _format_progress_event(event)
    should_print_line = line is not None and (
        not compact_progress or _should_print_compact_progress_event(event)
    )
    if should_print_line:
        color = _progress_event_color(event, use_color=use_color)
        prefix = "  " if kind in {"subagent_spawn", "subagent_return"} else ""
        fh.write(f"{color}{prefix}{line}{reset}\\n")
        fh.flush()
    if kind == "tool_result":
        tool = str(event.get("tool") or "")
        tool_use_id = str(event.get("tool_use_id") or "")
        if (
            tool == "spawn_subagents"
            and event.get("status") == "ok"
            and event.get("agent_id") == "parent"
            and recorder is not None
        ):
            tool_result_idx = len(recorder.events) - 1
            summary = parallel_subagent_summary_for_tool_result(
                recorder.events, tool_result_idx
            )
            if summary is not None:
                spawn_payload: list[dict[str, object]] | None = None
                try:
                    parsed = json.loads(str(event.get("result_full") or ""))
                except json.JSONDecodeError:
                    parsed = None
                if isinstance(parsed, list):
                    spawn_payload = [item for item in parsed if isinstance(item, dict)]
                parallel_color = "\\x1b[35m" if use_color else ""
                for parallel_line in format_parallel_progress_lines(summary, spawn_payload=spawn_payload):
                    fh.write(f"{parallel_color}{parallel_line}{reset}\\n")
                fh.flush()
        if tool in WRITE_EDIT_TOOLS and event.get("status") == "ok":
            call = pending_calls.pop(tool_use_id, None)
            if call is not None:
                prior = write_priors.get(tool_use_id)
                diff_path = write_progress_diff_lines(
                    fh, call, prior, use_color=use_color
                )
                if diff_path:
                    state.setdefault("progress_diff_paths", set()).add(diff_path)
    if kind == "assistant_step" and event.get("agent_id") == "parent" and on_parent_status:
        on_parent_status()
    elif kind == "run_end" and on_parent_status:
        on_parent_status()


def _latest_parent_answer(events: list[dict[str, object]], start_idx: int = 0) -> str:
    for event in reversed(events[start_idx:]):
        if event.get("kind") != "assistant_step" or event.get("agent_id") != "parent":
            continue
        tool_calls = event.get("tool_calls") or []
        text = str(event.get("assistant_text") or "").strip()
        if not tool_calls and text:
            return text
    return ""


ACK_PROMPTS = {"y", "yes", "ok", "okay", "sure", "go", "go ahead", "proceed"}
LITERAL_OUTPUT_PROMPT_MARKERS = (
    "pwd",
    "ls",
    "list",
    "read",
    "show",
    "print",
    "display",
    "contents",
    "content",
    "cat",
)
LITERAL_OUTPUT_TOOLS = {"read_file", "read_file_range", "run_bash"}


def _is_ack_prompt(prompt: str) -> bool:
    return prompt.strip().lower() in ACK_PROMPTS


def _wants_literal_tool_output(prompt: str) -> bool:
    lower = prompt.strip().lower()
    if not lower:
        return False
    if lower in {"pwd", "ls", "ls -l", "dir"}:
        return True
    return any(marker in lower for marker in LITERAL_OUTPUT_PROMPT_MARKERS)


def _parent_tool_calls(events: list[dict[str, object]], start_idx: int) -> dict[str, dict[str, object]]:
    calls: dict[str, dict[str, object]] = {}
    for event in events[start_idx:]:
        if event.get("kind") != "tool_call" or event.get("agent_id") != "parent":
            continue
        tool_use_id = str(event.get("tool_use_id") or "")
        if tool_use_id:
            calls[tool_use_id] = event
    return calls


def _literal_tool_outputs(
    events: list[dict[str, object]],
    start_idx: int,
    prompt: str,
    answer: str,
    *,
    trace_path: Path | None = None,
) -> list[str]:
    if not _wants_literal_tool_output(prompt):
        return []
    calls = _parent_tool_calls(events, start_idx)
    compaction_by_tool: dict[str, dict[str, object]] = {}
    for event in events[start_idx:]:
        if event.get("kind") == "compaction":
            compaction_by_tool[str(event.get("tool_use_id") or "")] = event
    outputs: list[str] = []
    answer_text = answer.strip()
    for event in events[start_idx:]:
        if event.get("kind") != "tool_result" or event.get("agent_id") != "parent":
            continue
        if event.get("tool") not in LITERAL_OUTPUT_TOOLS:
            continue
        content = clarify_tool_error(str(event.get("tool") or ""), str(event.get("result_full") or "")).strip()
        if not content or (answer_text and content in answer_text):
            continue
        tool_use_id = str(event.get("tool_use_id") or "")
        call = calls.get(tool_use_id, {})
        args = call.get("args") or {}
        path = str(args.get("path") or "") if isinstance(args, dict) else ""
        command = str(call.get("command") or "").strip() if isinstance(call, dict) else ""
        body = format_literal_tool_body(
            content,
            tool=str(event.get("tool") or ""),
            path=path,
            compaction_event=compaction_by_tool.get(tool_use_id),
            event_idx=int(event.get("event_idx") or 0),
            trace_path=trace_path,
        )
        label = "Tool output" if event.get("status") == "ok" else "Blocked"
        if command:
            title = f"{label} ({command}):"
        elif path:
            title = f"{label} ({path}):"
        else:
            title = f"{label} ({event.get('tool')}):"
        outputs.append(f"{title}\\n{body}")
    return outputs


def _turn_subagent_failure_notices(events: list[dict[str, object]], start_idx: int) -> list[str]:
    notices: list[str] = []
    for event in events[start_idx:]:
        if event.get("kind") != "subagent_return":
            continue
        child_status = str(event.get("status") or "ok")
        if child_status == "ok":
            continue
        child = event.get("child_agent_id") or "sub-agent"
        summary = clarify_tool_error("subagent", str(event.get("summary") or child_status))
        notices.append(f"Sub-agent {child} failed: {summary}")
    return notices


def _latest_model_error(events: list[dict[str, object]]) -> dict[str, object] | None:
    for event in reversed(events):
        if event.get("kind") == "model_error":
            return event
    return None


def _latest_run_end_status(events: list[dict[str, object]]) -> str | None:
    for event in reversed(events):
        if event.get("kind") == "run_end":
            return str(event.get("final_status") or "")
    return None


def _exit_code_for_final_status(status: str | None) -> int:
    if status == "aborted":
        return 3
    if status == "model_error":
        return 75
    return 0


def _apply_model_overrides(args: argparse.Namespace) -> None:
    if getattr(args, "parent_model", None):
        config.PARENT_MODEL_ID = normalize_model_id(args.parent_model)
    if getattr(args, "subagent_model", None):
        sub_id = normalize_model_id(args.subagent_model)
        config.EXPLORER_MODEL_ID = sub_id
        config.COMPACTOR_MODEL_ID = sub_id
    _refresh_subagent_model_ids()


def _chat_ui_kwargs(
    root: Path,
    recorder: TraceRecorder,
    guard: BudgetGuard,
    args: argparse.Namespace,
    *,
    since_event_idx: int = 0,
) -> dict[str, Any]:
    return {
        "root": root,
        "recorder": recorder,
        "guard": guard,
        "live_model": bool(args.live_model),
        "since_event_idx": since_event_idx,
    }


def _report_parent_session_status(
    root: Path,
    recorder: TraceRecorder,
    guard: BudgetGuard,
    args: argparse.Namespace,
    *,
    since_event_idx: int,
    force_state: str | None = None,
) -> None:
    status = build_session_status(
        root=root,
        recorder=recorder,
        guard=guard,
        live_model=bool(args.live_model),
        since_event_idx=since_event_idx,
        force_state=force_state,
    )
    emit_session_statusline(recorder, status)
    if use_rich_ui():
        refresh_chat_status_bar(
            root=root,
            recorder=recorder,
            guard=guard,
            live_model=bool(args.live_model),
            since_event_idx=since_event_idx,
            force_state=force_state,
            force=force_state != "running",
        )
    elif bool(getattr(sys.stderr, "isatty", lambda: False)()):
        line = _chat_statusline_color(
            format_statusline_compact(status),
            use_color=not os.environ.get("NO_COLOR"),
        )
        sys.stderr.write(line + "\\n")
        sys.stderr.flush()


def _guard_overrides(args: argparse.Namespace) -> dict[str, object]:
    """Per-run budget overrides from CLI or post-loader config."""
    overrides: dict[str, object] = {}
    if getattr(args, "max_usd", None) is not None:
        overrides["max_usd"] = args.max_usd
    else:
        overrides["max_usd"] = config.MAX_USD_PER_RUN
    if getattr(args, "max_tokens", None) is not None:
        overrides["max_tokens"] = args.max_tokens
    else:
        overrides["max_tokens"] = config.MAX_TOKENS_PER_RUN
    return overrides


def _chat_loop(root: Path, args: argparse.Namespace) -> int:
    guard = BudgetGuard.for_workspace(root, **_guard_overrides(args))
    turn_state: dict[str, Any] = {"turn": 0}
    ui_since = 0

    def on_parent_status() -> None:
        _report_parent_session_status(
            root,
            recorder,
            guard,
            args,
            since_event_idx=turn_state.get("since_event_idx", ui_since),
            force_state=turn_state.get("force_state"),
        )

    recorder = TraceRecorder(root, redact=not args.no_redact, event_sink=None)
    recorder.event_sink = _make_progress_sink(
        on_parent_status=on_parent_status,
        turn_state=turn_state,
        workspace_root=root,
        recorder=recorder,
        rich_chat=use_rich_ui(),
    )
    policy = _make_policy(args, workspace_root=root)
    history_path = root / ".vg_chat_history"
    read_prompt, save_history = _make_chat_prompt(history_path)
    if use_rich_ui():
        print_chat_dashboard_cleared(**_chat_ui_kwargs(root, recorder, guard, args, since_event_idx=ui_since))
    else:
        sys.stderr.write("VG Agent chat mode. Type /help for commands.\\n")
    conversation: list[dict[str, Any]] = []
    last_intent_prompt = ""
    try:
        while True:
            try:
                render_input_top_rule()
                prompt = read_prompt().strip()
            except KeyboardInterrupt:
                recorder.emit("budget_event", budget_reason="user_abort", details={})
                sys.stderr.write("\\n")
                break
            except EOFError:
                sys.stderr.write("\\n")
                break
            if not prompt:
                continue
            if prompt in {"/exit", "/quit"}:
                break
            if prompt.startswith("/budget"):
                _handle_budget_slash(prompt, guard, recorder)
                continue
            if prompt == "/status":
                if use_rich_ui():
                    reset_dashboard_mode()
                    print_chat_dashboard_cleared(**_chat_ui_kwargs(root, recorder, guard, args, since_event_idx=ui_since), compact=False)
                _print_chat_status_report(recorder, guard, args, since_event_idx=ui_since)
                continue
            if prompt == "/approvals":
                _print_approvals(policy, recorder)
                continue
            if prompt == "/reset":
                policy.cache.clear()
                guard = BudgetGuard.for_workspace(root, **_guard_overrides(args))
                conversation.clear()
                last_intent_prompt = ""
                ui_since = len(recorder.events)
                reset_dashboard_mode()
                recorder.emit("session_reset")
                if use_rich_ui():
                    print_chat_dashboard_cleared(**_chat_ui_kwargs(root, recorder, guard, args, since_event_idx=ui_since), compact=False)
                continue
            if prompt == "/new":
                policy.cache.clear()
                guard = BudgetGuard.for_workspace(root, **_guard_overrides(args))
                conversation.clear()
                last_intent_prompt = ""
                ui_since = 0
                reset_dashboard_mode()
                turn_state["turn"] = 0
                recorder = TraceRecorder(root, redact=not args.no_redact, event_sink=None)
                recorder.event_sink = _make_progress_sink(
                    on_parent_status=on_parent_status,
                    turn_state=turn_state,
                    workspace_root=root,
                    recorder=recorder,
                    rich_chat=use_rich_ui(),
                )
                recorder.emit("session_new")
                if use_rich_ui():
                    print_chat_dashboard_cleared(
                        **_chat_ui_kwargs(root, recorder, guard, args, since_event_idx=ui_since),
                        show_trace_path=True,
                    )
                continue
            if prompt == "/finops":
                _print_finops(guard, recorder)
                continue
            if prompt.startswith("/review"):
                parts = prompt.split()
                turn_index: int | None = None
                if len(parts) > 1:
                    try:
                        turn_index = int(parts[1])
                    except ValueError:
                        sys.stdout.write(f"Invalid turn index: {parts[1]!r}\\n")
                        continue
                review_text = format_turn_review(
                    recorder.events,
                    turn_index=turn_index,
                    trace_path=recorder.path,
                    tool_summary_fn=lambda name, args: _tool_summary({"name": name, "args": args}),
                )
                sys.stdout.write(review_text)
                continue
            if prompt.startswith("/show-context"):
                parts = prompt.split()
                if len(parts) == 1 or (len(parts) == 2 and parts[1].lower() == "overview"):
                    sys.stdout.write(format_show_context_overview(recorder.events))
                else:
                    try:
                        step = int(parts[1])
                    except ValueError:
                        sys.stdout.write(f"Invalid step index: {parts[1]!r}\\n")
                        continue
                    sys.stdout.write(
                        json.dumps(show_context(recorder.events, step), indent=2, ensure_ascii=False) + "\\n"
                    )
                continue
            if prompt == "/compact" or prompt.startswith("/compact "):
                skip_reason = conversation_compact_skip_reason(
                    conversation, config.PARENT_MODEL_ID
                )
                if skip_reason is not None:
                    sys.stdout.write(
                        format_manual_compact_skip_warning(
                            skip_reason, conversation, config.PARENT_MODEL_ID
                        )
                        + "\\n"
                    )
                    continue
                try:
                    compact_client = LiveModelClient.from_env(recorder=recorder)
                except MissingOpenRouterKey as exc:
                    sys.stderr.write(f"error: {exc}\\n")
                    continue
                compact_event = compact_conversation(
                    recorder,
                    conversation,
                    config.PARENT_MODEL_ID,
                    guard,
                    client=compact_client,
                    reason="manual",
                    deterministic=False,
                )
                if compact_event is None:
                    sys.stdout.write(
                        format_manual_compact_skip_warning(
                            "no_foldable_head", conversation, config.PARENT_MODEL_ID
                        )
                        + "\\n"
                    )
                else:
                    banner = format_compaction_banner(compact_event)
                    if banner:
                        sys.stdout.write(banner + "\\n")
                continue
            if prompt == "/help":
                sys.stdout.write(SLASH_COMMAND_HELP + "\\n")
                continue
            render_input_bottom_and_footer(
                **_chat_ui_kwargs(root, recorder, guard, args, since_event_idx=ui_since),
                show_status=False,
            )
            start_idx = len(recorder.events)
            turn_state["since_event_idx"] = start_idx
            turn_state["write_priors"] = {}
            turn_state["progress_diff_paths"] = set()
            turn_state["force_state"] = "running"
            _report_parent_session_status(
                root, recorder, guard, args, since_event_idx=start_idx, force_state="running"
            )
            literal_prompt = last_intent_prompt if _is_ack_prompt(prompt) and last_intent_prompt else prompt
            try:
                client = LiveModelClient.from_env(recorder=recorder)
            except MissingOpenRouterKey as exc:
                sys.stderr.write(f"error: {exc}\\n")
                return 2
            try:
                run_live_task(root, prompt, recorder, client=client, guard=guard, policy=policy, history=conversation)
            except KeyboardInterrupt:
                recorder.emit("budget_event", budget_reason="user_abort", details={})
                if not any(
                    e.get("kind") == "run_end"
                    and int(e.get("event_idx", -1)) >= start_idx
                    for e in recorder.events
                ):
                    recorder.emit(
                        "run_end",
                        final_status="aborted",
                        total_cost_usd=round(guard.running_usd, 6),
                        total_tokens=guard.running_tokens,
                        duration_s=0.0,
                    )
                sys.stderr.write("\\n")
                break
            turn_state["force_state"] = None
            answer = _latest_parent_answer(recorder.events, start_idx)
            literal_outputs = _literal_tool_outputs(
                recorder.events,
                start_idx,
                literal_prompt,
                answer,
                trace_path=recorder.path,
            )
            print_turn_output(
                answer=answer,
                literal_outputs=literal_outputs,
                events=recorder.events,
                start_idx=start_idx,
                workspace_root=root,
                pending_priors=turn_state.get("write_priors"),
                skip_change_paths=turn_state.get("progress_diff_paths"),
            )
            for notice in _turn_subagent_failure_notices(recorder.events, start_idx):
                sys.stderr.write(notice + "\\n")
            mark_turn_completed()
            refresh_chat_status_bar(
                **_chat_ui_kwargs(root, recorder, guard, args, since_event_idx=start_idx),
                force=True,
            )
            if not _is_ack_prompt(prompt):
                last_intent_prompt = prompt
    finally:
        save_history()
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="vg_agent")
    parser.add_argument("--task")
    parser.add_argument("--trace", action="store_true")
    parser.add_argument("--show-context", type=int)
    parser.add_argument("--seed-fixture", action="store_true")
    # The agent always runs against the live OpenRouter model; --live-model is
    # accepted as a no-op alias for backwards compatibility with older docs.
    parser.add_argument("--live-model", action="store_true")
    parser.add_argument("--parent-model")
    parser.add_argument("--subagent-model")
    parser.add_argument("--chat", action="store_true")
    parser.add_argument("--require-approval", choices=["off", "writes", "all"], default=None)
    parser.add_argument("--yes", action="store_true")
    parser.add_argument("--no-step-extend-prompt", action="store_true")
    parser.add_argument("--no-redact", action="store_true")
    parser.add_argument("--budget", action="store_true")
    parser.add_argument("--finops", action="store_true")
    parser.add_argument("--max-usd", type=float)
    parser.add_argument("--max-tokens", type=int)
    args = parser.parse_args(argv)
    args.live_model = True

    if args.no_redact:
        sys.stderr.write("warning: --no-redact disables trace secret redaction.\\n")

    root = resolve_workspace_root()
    apply_runtime_settings(workspace_root=root, cli=args)
    if args.require_approval is None:
        args.require_approval = config.REQUIRE_APPROVAL_DEFAULT
    _apply_model_overrides(args)
    missing_pricing = validate_configured_models(strict=strict_model_pricing_enabled())
    if missing_pricing and (args.chat or args.task):
        sys.stderr.write(format_missing_pricing_warning(missing_pricing) + "\\n")
    if args.seed_fixture:
        write_fixture(root)
        print(f"seeded fixture at {root}")
        return 0

    if args.chat:
        return _chat_loop(root, args)

    if not args.task:
        parser.error("--task, --chat, or --seed-fixture is required")

    recorder = TraceRecorder(
        root,
        redact=not args.no_redact,
        event_sink=_make_progress_sink() if args.live_model else None,
    )
    policy = _make_policy(args)
    try:
        client = LiveModelClient.from_env(recorder=recorder)
    except MissingOpenRouterKey as exc:
        parser.exit(2, f"error: {exc}\\n")
    guard = BudgetGuard.for_workspace(root, **_guard_overrides(args))
    try:
        run_live_task(root, args.task, recorder, client=client, guard=guard, policy=policy)
    except KeyboardInterrupt:
        recorder.emit("budget_event", budget_reason="user_abort", details={})
        recorder.emit(
            "run_end",
            final_status="aborted",
            total_cost_usd=round(guard.running_usd, 6),
            total_tokens=guard.running_tokens,
            duration_s=0.0,
        )
    answer = _latest_parent_answer(recorder.events)
    if answer:
        print(answer)
    for output in _literal_tool_outputs(
        recorder.events, 0, args.task, answer, trace_path=recorder.path
    ):
        print(output)
    if args.trace:
        print(render_tree(recorder.events))
        print(f"trace: {recorder.path}")
    if args.show_context is not None:
        print(json.dumps(show_context(recorder.events, args.show_context), indent=2, ensure_ascii=False))
    if guard is not None and args.budget:
        _print_budget(guard)
    if guard is not None and args.finops:
        _print_finops(guard, recorder)
    return _exit_code_for_final_status(_latest_run_end_status(recorder.events))


if __name__ == "__main__":
    raise SystemExit(main())
''',
}


EXTRA_SOURCE_GENERATED_FILES = ["sqlite_store.py", "chat_ui.py", "workspace_paths.py"]


def write_generated(src_dir: Path, digest: str, cfg: dict[str, str], prompts: dict[str, str], clean: bool) -> None:
    extra_files: dict[str, str] = {}
    source_dir = ROOT / "src" / "vg_agent"
    for rel_path in EXTRA_SOURCE_GENERATED_FILES:
        source_path = source_dir / rel_path
        if source_path.exists():
            extra_files[rel_path] = source_path.read_text(encoding="utf-8")
    if clean and src_dir.exists():
        shutil.rmtree(src_dir)
    src_dir.mkdir(parents=True, exist_ok=True)
    for rel_path, text in {**GENERATED_FILES, **extra_files}.items():
        path = src_dir / rel_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(render(text, digest, cfg, prompts), encoding="utf-8", newline="\n")


def write_fixture(fixture_dir: Path, clean: bool) -> None:
    if clean and fixture_dir.exists():
        shutil.rmtree(fixture_dir)
    import sys

    src_parent = str((ROOT / "src").resolve())
    if src_parent not in sys.path:
        sys.path.insert(0, src_parent)
    from vg_agent.demo_fixture import write_fixture as generated_write_fixture

    generated_write_fixture(fixture_dir)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--src-dir", default=str(ROOT / "src" / "vg_agent"))
    parser.add_argument("--fixture-dir", default=str(ROOT / "fixtures" / "demo_repo"))
    parser.add_argument("--clean", action="store_true")
    parser.add_argument("--no-fixture", action="store_true")
    args = parser.parse_args()

    cfg = read_config()
    cfg.update(read_context_windows())
    slug_parts = [part.strip() for part in cfg["EXPENSIVE_OPENROUTER_PROVIDER_SLUGS"].split(",") if part.strip()]
    cfg["EXPENSIVE_OPENROUTER_PROVIDER_SLUGS_TUPLE"] = repr(tuple(slug_parts))
    prompts = read_prompts()
    digest = spec_digest()
    src_dir = Path(args.src_dir)
    write_generated(src_dir, digest, cfg, prompts, args.clean)
    if not args.no_fixture:
        write_fixture(Path(args.fixture_dir), args.clean)
    print(f"generated {src_dir} from specs digest {digest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
