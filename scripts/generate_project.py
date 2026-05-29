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
        "CLAUDE_SONNET_4_6_INPUT_PER_MTOK",
        "CLAUDE_SONNET_4_6_OUTPUT_PER_MTOK",
        "CLAUDE_HAIKU_4_5_INPUT_PER_MTOK",
        "CLAUDE_HAIKU_4_5_OUTPUT_PER_MTOK",
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


def read_prompts() -> dict[str, str]:
    text = (ROOT / "PROMPTS.md").read_text(encoding="utf-8")
    sections: dict[str, str] = {}
    section_titles = {
        "PARENT_SYSTEM_PROMPT": "## Parent system prompt",
        "GRILLING_SYSTEM_PROMPT": "## Grilling system prompt",
        "EXPLORER_SYSTEM_PROMPT": "## Explorer system prompt",
        "CODER_SYSTEM_PROMPT": "## Coder system prompt",
        "REVIEWER_SYSTEM_PROMPT": "## Reviewer system prompt",
        "COMPACTION_SYSTEM_PROMPT": "## Compaction system prompt",
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
    "openrouter/anthropic/claude-haiku-4.5": {"input": __CLAUDE_HAIKU_4_5_INPUT_PER_MTOK__, "output": __CLAUDE_HAIKU_4_5_OUTPUT_PER_MTOK__},
    "openrouter/anthropic/claude-sonnet-4.6": {"input": __CLAUDE_SONNET_4_6_INPUT_PER_MTOK__, "output": __CLAUDE_SONNET_4_6_OUTPUT_PER_MTOK__},
}
UNKNOWN_MODEL_ESTIMATE_USD_PER_MTOK = {"input": __UNKNOWN_MODEL_INPUT_ESTIMATE_PER_MTOK__, "output": __UNKNOWN_MODEL_OUTPUT_ESTIMATE_PER_MTOK__}

MAX_PARENT_STEPS = 15
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

OPENROUTER_ENDPOINT_HOST = "__OPENROUTER_ENDPOINT_HOST__"
MAX_TOOL_RESULT_BYTES = 1_048_576
DAILY_SPEND_FILE = ".vg_daily_spend.json"
APPROVALS_FILE = ".vg_approvals.json"
REQUIRE_APPROVAL_DEFAULT = "off"
SQLITE_TRACE_DB = "traces/vg_agent.sqlite3"
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

    def before_model_call(self, model: str, worst_input_tokens: int, worst_output_tokens: int) -> BudgetDecision:
        with self.lock:
            if self.step_count >= self.max_steps:
                return BudgetDecision(False, "step_cap", {"steps": self.step_count, "max_steps": self.max_steps})
            if self.running_tokens + worst_input_tokens + worst_output_tokens > self.max_tokens:
                return BudgetDecision(False, "token_cap", {"tokens": self.running_tokens, "max_tokens": self.max_tokens})
            worst_cost = self.estimate_cost(model, worst_input_tokens, worst_output_tokens)
            if self.running_usd + worst_cost > self.max_usd:
                return BudgetDecision(False, "usd_cap", {"running_usd": self.running_usd, "worst_next_usd": worst_cost})
            if self.running_usd + worst_cost > self.daily_remaining_usd:
                return BudgetDecision(False, "daily_cap", {"running_usd": self.running_usd, "daily_remaining_usd": self.daily_remaining_usd})
            return BudgetDecision(True)

    def record_model_call(self, model: str, input_tokens: int, output_tokens: int, cost_usd: float | None = None, agent_type: str = "parent") -> float:
        with self.lock:
            self.step_count += 1
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
            if "warn_steps" not in self.warned and self.max_steps > 0 and self.step_count >= config.WARN_STEP_FRACTION * self.max_steps:
                self.warned.add("warn_steps")
                out.append(BudgetDecision(True, "warn_steps", {"step_count": self.step_count, "max_steps": self.max_steps, "crossed_at_step": self.step_count}))
            return out

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

    def extend_cap(self, reason: str, *, once: bool) -> None:
        """Raise a hard cap after interactive approval."""
        with self.lock:
            if reason == "step_cap":
                self.max_steps = (self.step_count + 1) if once else (self.max_steps + max(5, self.max_steps // 4))
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
        with contextlib.redirect_stdout(stdout_filter), contextlib.redirect_stderr(stderr_filter):
            try:
                response = litellm.completion(
                    model=model,
                    messages=_to_litellm_messages(system_prompt, messages),
                    tools=_to_litellm_tools(tools) if tools else None,
                    max_tokens=max_tokens,
                    api_key=self.api_key,
                    api_base=self.endpoint,
                    extra_headers=_openrouter_headers(),
                )
            except Exception as exc:
                if _is_rate_limit_error(exc):
                    raise LiveModelRateLimitError(_rate_limit_message(model)) from exc
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
    )


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
import time
from pathlib import Path


SAFE_COMMANDS = {"grep", "rg", "find", "ls", "pwd", "cat", "head", "tail", "wc", "rm"}
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
    if candidate.is_absolute() or token.startswith("~"):
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
    if normalized[0] == "rm":
        return _validate_rm_tokens(tokens)
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
    target = rm_delete_target(command)
    if target is None:
        return None
    try:
        path = resolve_workspace_path(root, target)
    except ValueError as exc:
        return str(exc)
    if not path.exists():
        return f"rm target {target!r} does not exist"
    if not path.is_file():
        return "rm may delete only regular files"
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
    completed = subprocess.run(["bash", "-c", command], cwd=root, text=True, capture_output=True, timeout=30)
    content = completed.stdout + completed.stderr
    status = "ok" if completed.returncode == 0 else "error"
    return _result(tool_use_id, "run_bash", content, status, started)
''',
    "trace.py": '''"""Generated JSONL trace and replay helpers."""

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
            lines.append(f"{prefix}{event['event_idx']:03d} {event['agent_id']} assistant step {event.get('step_idx')} model={event.get('model')}")
        elif kind == "tool_result":
            lines.append(f"{prefix}{event['event_idx']:03d} {event['agent_id']} tool_result {event.get('tool')} tokens={event.get('tokens')} status={event.get('status')}")
        elif kind == "compaction":
            lines.append(f"{prefix}{event['event_idx']:03d} compacted {event.get('before_tokens')} -> {event.get('after_tokens')} tokens (tool_use {event.get('tool_use_id')})")
        elif kind == "budget_event":
            lines.append(f"{prefix}{event['event_idx']:03d} budget_event {event.get('budget_reason')}")
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
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass, field
from typing import Any, Callable
from pathlib import Path

from . import config, tools
from .live_model_client import LiveModelClient, LiveModelError, ModelTurn, ToolCall
from .budget import BudgetGuard
from .trace import TraceRecorder, compacted_marker, now_iso


PARENT_SYSTEM_PROMPT = __PARENT_SYSTEM_PROMPT_LITERAL__

GRILLING_SYSTEM_PROMPT = __GRILLING_SYSTEM_PROMPT_LITERAL__

EXPLORER_SYSTEM_PROMPT = __EXPLORER_SYSTEM_PROMPT_LITERAL__

CODER_SYSTEM_PROMPT = __CODER_SYSTEM_PROMPT_LITERAL__

REVIEWER_SYSTEM_PROMPT = __REVIEWER_SYSTEM_PROMPT_LITERAL__

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
    "coder": {"read_file", "read_file_range", "run_bash", "write_file", "edit_file"},
    "reviewer": {"read_file", "read_file_range", "run_bash"},
}


def _normalise_agent_type(value: object) -> str:
    text = str(value or "explorer").strip().lower()
    return text if text in config.SUBAGENT_TYPES else "explorer"


GATED_WRITES = {"write_file", "edit_file", "run_bash", "spawn_subagent", "spawn_subagents"}
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


def _args_summary(tool: str, args: dict[str, Any]) -> str:
    if tool in {"read_file", "read_file_range", "write_file", "edit_file"}:
        path = args.get("path") or args.get("rel_path") or ""
        if tool == "edit_file":
            old = str(args.get("old") or "")
            new = str(args.get("new") or "")
            return f"{path}  - {old[:40]!r} -> + {new[:40]!r}"
        return str(path)
    if tool == "run_bash":
        return str(args.get("command") or "")
    if tool == "spawn_subagent":
        return str(args.get("question") or "")[:120]
    if tool == "spawn_subagents":
        requests = args.get("requests") or []
        if isinstance(requests, list):
            return f"{len(requests)} sub-agent requests"
        return "parallel sub-agent requests"
    return json.dumps(args, sort_keys=True, ensure_ascii=False)[:160]


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
        "description": "Run one simple inspection command through bash, or exactly `rm <relative-file>` for approved single-file deletion. For top-level folder listings use `find . -maxdepth 1 -type d`. No pipes, redirection, shell control, Python, pytest, package managers, network tools, command chains, rm flags, globs, or directory deletion.",
        "input_schema": {"type": "object", "properties": {"command": {"type": "string"}}, "required": ["command"]},
    },
}

_SUBAGENT_REQUEST_SCHEMA = {
    "type": "object",
    "properties": {
        "type": {"type": "string", "enum": list(config.SUBAGENT_TYPES)},
        "question": {"type": "string"},
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
    *SPAWN_TOOL_SCHEMAS,
]


def _subagent_tool_schemas(agent_type: str) -> list[dict[str, Any]]:
    names = SUBAGENT_TOOL_NAMES.get(agent_type, set())
    return [FILE_TOOL_SCHEMAS[name] for name in FILE_TOOL_SCHEMAS if name in names]


EXPLORER_TOOL_SCHEMAS = _subagent_tool_schemas("explorer")


def _compact_if_needed(recorder: TraceRecorder, event: dict[str, object], deterministic: bool = False) -> dict[str, object] | None:
    tokens = int(event["tokens"])
    if tokens <= config.K_COMPACT:
        return None
    full = str(event["result_full"])
    if deterministic:
        summary = (
            "Large deterministic sample.log read for the compaction demo. "
            f"It contains {full.count(chr(10))} log lines of health-check traffic; "
            "the full content remains in the JSONL trace."
        )
    else:
        lines = full.splitlines()
        summary = (
            f"Large {event['tool']} result with {len(lines)} lines and {event['bytes']} bytes. "
            "The full content remains in the JSONL trace; use read_file_range or re-run "
            "a targeted read to retrieve specific lines."
        )
    return recorder.emit(
        "compaction",
        tool_use_id=event["tool_use_id"],
        before_tokens=tokens,
        after_tokens=tools.estimate_tokens(summary),
        summary=summary,
        original_event_idx=event["event_idx"],
        original_sha256=hashlib.sha256(full.encode("utf-8")).hexdigest(),
    )


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
    if reason == "step_cap":
        return f"{reason} steps {details.get('steps')}/{details.get('max_steps')}"
    if reason == "token_cap":
        return f"{reason} tokens {details.get('tokens')}/{details.get('max_tokens')}"
    if reason == "usd_cap":
        return f"{reason} usd {details.get('running_usd')}/{details.get('max_usd', config.MAX_USD_PER_RUN)}"
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
    recorder.emit(
        "model_error",
        agent_id=agent_id,
        parent_id=parent_id,
        agent_type=agent_type,
        model=model,
        model_id=model,
        step_idx=step_idx,
        error_type=type(exc).__name__,
        message=str(exc),
        retryable=getattr(exc, "retryable", False),
    )
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
    if tool_name == "write_file":
        return tools.write_file(root, path, str(args.get("content") or ""), call.tool_use_id)
    if tool_name == "edit_file":
        return tools.edit_file(root, path, str(args.get("old") or ""), str(args.get("new") or ""), call.tool_use_id)
    if tool_name == "spawn_subagent":
        child_type = _normalise_agent_type(args.get("type"))
        question = str(args.get("question") or "")
        outcome = _spawn_one(root, child_type, question, recorder, client, guard, started, policy)
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
) -> tuple[str, str]:
    """Run one typed sub-agent loop. Returns (summary, status)."""
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

    for local_step in range(1, config.MAX_SUBAGENT_STEPS + 1):
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
            break
        if not isinstance(turn, ModelTurn):
            turn = ModelTurn(**turn)
        turn.tool_calls = [_normalise_tool_call(c) for c in turn.tool_calls]
        model_id = turn.model_id or model
        input_tokens = turn.input_tokens or expected_in
        output_tokens = turn.output_tokens or tools.estimate_tokens(turn.assistant_text + json.dumps([asdict(c) for c in turn.tool_calls], sort_keys=True))
        cost = guard.record_model_call(model_id, input_tokens, output_tokens, cost_usd=turn.cost_usd, agent_type=agent_type)
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
        )
        messages.append({"role": "assistant", "content": _assistant_content(turn)})
        if not turn.tool_calls:
            final_summary = turn.assistant_text[:2048]
            break
        tool_blocks: list[dict[str, Any]] = []
        had_error = False
        for c in turn.tool_calls:
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
            if result["status"] != "ok":
                final_summary = str(result["result_full"])[:2048]
                status = "tool_error"
                had_error = True
                break
        messages.append({"role": "user", "content": tool_blocks})
        if had_error:
            break

    if not final_summary:
        final_summary = f"{agent_type} stopped before producing a final summary."
    return final_summary, status


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
    summary, status = _run_live_subagent(root, agent_type, question, recorder, client, guard, child_id, started, policy, review_slice)
    ended_at = now_iso()
    recorder.emit(
        "subagent_return",
        agent_id=child_id,
        parent_id="parent",
        agent_type=agent_type,
        child_agent_id=child_id,
        status=status,
        summary=summary,
        started_at=run_started_at,
        ended_at=ended_at,
        child_total_cost_usd=round(guard.running_usd - cost_before, 6),
        child_total_tokens=guard.running_tokens - tok_before,
    )
    return {"agent_id": child_id, "agent_type": agent_type, "status": status, "payload": summary}


def _spawn_many(
    root: Path,
    raw_requests: list[Any],
    recorder: TraceRecorder,
    client: Any,
    guard: BudgetGuard,
    started: float,
    policy: ApprovalPolicy,
) -> list[dict[str, object]]:
    parsed: list[tuple[str, str]] = []
    for raw in raw_requests:
        if isinstance(raw, dict):
            parsed.append((_normalise_agent_type(raw.get("type")), str(raw.get("question") or "")))
    accepted = parsed[: config.MAX_PARALLEL_SUBAGENTS]
    overflow = parsed[config.MAX_PARALLEL_SUBAGENTS :]

    # Coders never run concurrently with another Coder (overlapping write paths):
    # the runtime serialises them and reports `conflict` for the second.
    runnable: list[tuple[int, str, str, str]] = []  # (slot, child_id, type, question)
    conflicts: list[dict[str, object]] = []
    seen_coder = False
    for slot, (atype, question) in enumerate(accepted):
        child_id = _next_child_id(recorder, atype) + f".{slot}"
        if atype == "coder" and seen_coder:
            conflicts.append({"agent_id": child_id, "agent_type": atype, "status": "conflict", "payload": "serialised: another Coder in the same batch holds the write lock", "slot": slot})
            continue
        if atype == "coder":
            seen_coder = True
        runnable.append((slot, child_id, atype, question))

    results_by_slot: dict[int, dict[str, object]] = {}
    barrier = threading.Barrier(len(runnable)) if len(runnable) > 1 else None
    if runnable:
        with ThreadPoolExecutor(max_workers=len(runnable)) as pool:
            futures = {
                pool.submit(_spawn_one, root, atype, question, recorder, client, guard, started, policy, None, child_id, barrier): slot
                for (slot, child_id, atype, question) in runnable
            }
            for future, slot in futures.items():
                out = future.result()
                out["slot"] = slot
                results_by_slot[slot] = out
    for conflict in conflicts:
        results_by_slot[int(conflict["slot"])] = conflict

    summaries = [results_by_slot[slot] for slot in sorted(results_by_slot)]
    for slot, (atype, question) in enumerate(overflow, start=len(accepted)):
        summaries.append({"agent_id": f"{atype}-overflow-{slot}", "agent_type": atype, "status": "tool_error", "payload": "parallel cap exceeded"})
    for entry in summaries:
        entry.pop("slot", None)
    return summaries


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

    while True:
        if _wall_clock_exceeded(started, guard):
            timeout = type("Decision", (), {"budget_reason": "timeout", "details": {"timeout_s": config.WALL_CLOCK_TIMEOUT}})()
            if not _handle_budget_cap(policy=policy, recorder=recorder, guard=guard, decision=timeout, started=started):
                return recorder
            continue
        expected_in = _estimate_message_tokens(PARENT_SYSTEM_PROMPT, messages)
        decision = guard.before_model_call(config.PARENT_MODEL_ID, expected_in, 4096)
        if not decision.allowed:
            if not _handle_budget_cap(policy=policy, recorder=recorder, guard=guard, decision=decision, started=started):
                return recorder
            continue
        recorder.emit(
            "llm_start",
            model=config.PARENT_MODEL_ID,
            model_id=config.PARENT_MODEL_ID,
            step_idx=guard.step_count + 1,
            tokens_in=expected_in,
            max_tokens=4096,
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
                max_tokens=4096,
            )
        except LiveModelError as exc:
            _record_model_error(
                recorder,
                guard,
                exc,
                started,
                model=config.PARENT_MODEL_ID,
                step_idx=guard.step_count + 1,
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
        step_idx = guard.step_count
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
            event = recorder.emit("tool_result", **result)
            content = str(result["result_full"])
            compaction = _compact_if_needed(recorder, event, deterministic=False)
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
                recorder.emit(
                    "run_end",
                    final_status="tool_error",
                    total_cost_usd=round(guard.running_usd, 6),
                    total_tokens=guard.running_tokens,
                    duration_s=round(time.perf_counter() - started, 3),
                )
                return recorder
        messages.append({"role": "user", "content": tool_blocks})


def _explore_auth(root: Path, recorder: TraceRecorder, policy: ApprovalPolicy | None = None) -> str:
    if policy is not None and "spawn_subagent" in policy.gated_tools():
        spawn_call = ToolCall("parent-spawn-explorer", "spawn_subagent", {"question": "inspect auth/"})
        outcome = policy.check(_request_for(spawn_call))
        _emit_approval(recorder, spawn_call, outcome)
        if outcome.decision in {"denied", "aborted"}:
            return f"approval denied: {outcome.reason}"
    child_id = "explorer-1"
    recorder.emit("subagent_spawn", child_agent_id=child_id, question="inspect auth/", model=config.EXPLORER_MODEL_ID)
    recorder.emit(
        "assistant_step",
        agent_id=child_id,
        parent_id="parent",
        model=config.EXPLORER_MODEL_ID,
        model_id=config.EXPLORER_MODEL_ID,
        step_idx=1,
        tokens_in=600,
        tokens_out=80,
        cost_usd=0.0008,
        assistant_text="Inspect auth/session.py and auth/middleware.py.",
        tool_calls=[
            {"tool_use_id": "child-read-session", "name": "read_file", "args": {"path": "auth/session.py"}},
            {"tool_use_id": "child-read-middleware", "name": "read_file", "args": {"path": "auth/middleware.py"}},
        ],
        stop_reason="tool_use",
    )
    _emit_tool_call(recorder, ToolCall("child-read-session", "read_file", {"path": "auth/session.py"}), agent_id=child_id, parent_id="parent")
    session = tools.read_file(root, "auth/session.py", "child-read-session")
    recorder.emit("tool_result", agent_id=child_id, parent_id="parent", **session)
    _emit_tool_call(recorder, ToolCall("child-read-middleware", "read_file", {"path": "auth/middleware.py"}), agent_id=child_id, parent_id="parent")
    middleware = tools.read_file(root, "auth/middleware.py", "child-read-middleware")
    recorder.emit("tool_result", agent_id=child_id, parent_id="parent", **middleware)
    summary = (
        "Auth is handled in auth/session.py and auth/middleware.py: session.py "
        "issues token strings, validates the token shape and shared secret, and "
        "loads a session dict; middleware.py wraps protected handlers with "
        "require_auth and raises AuthError when request.token fails validation."
    )
    recorder.emit(
        "subagent_return",
        child_agent_id=child_id,
        summary=summary,
        child_total_cost_usd=0.001,
        child_total_tokens=int(session["tokens"]) + int(middleware["tokens"]),
    )
    return summary


def run_task(
    root: Path,
    task: str,
    recorder: TraceRecorder | None = None,
    policy: ApprovalPolicy | None = None,
) -> TraceRecorder:
    recorder = recorder or TraceRecorder(root)
    guard = BudgetGuard()
    policy = policy or ApprovalPolicy()
    task_lower = task.lower()
    recorder.emit("user_prompt", prompt=task)

    if "rename" in task_lower and "foo" in task_lower and "bar" in task_lower:
        cost = guard.record_model_call(config.PARENT_MODEL_ID, 500, 80)
        recorder.emit(
            "assistant_step",
            model=config.PARENT_MODEL_ID,
            model_id=config.PARENT_MODEL_ID,
            step_idx=1,
            tokens_in=500,
            tokens_out=80,
            cost_usd=cost,
            assistant_text="I will replace foo with bar in app.py.",
            tool_calls=[{"tool_use_id": "parent-edit-app", "name": "edit_file", "args": {"path": "app.py"}}],
            stop_reason="tool_use",
        )
        edit_call = ToolCall("parent-edit-app", "edit_file", {"path": "app.py", "old": "foo", "new": "bar"})
        _emit_tool_call(recorder, edit_call)
        if edit_call.name in policy.gated_tools():
            outcome = policy.check(_request_for(edit_call))
            _emit_approval(recorder, edit_call, outcome)
            if outcome.decision in {"denied", "aborted"}:
                deny_result = _result("parent-edit-app", "edit_file", f"approval denied: {outcome.reason}", "error", time.perf_counter())
                recorder.emit("tool_result", **deny_result)
                recorder.emit(
                    "run_end",
                    final_status="tool_error",
                    total_cost_usd=round(guard.running_usd, 6),
                    total_tokens=guard.running_tokens,
                    duration_s=0.1,
                )
                return recorder
        result = tools.edit_file(root, "app.py", "foo", "bar", "parent-edit-app")
        recorder.emit("tool_result", **result)
        cost = guard.record_model_call(config.PARENT_MODEL_ID, 350, 60)
        recorder.emit(
            "assistant_step",
            model=config.PARENT_MODEL_ID,
            model_id=config.PARENT_MODEL_ID,
            step_idx=2,
            tokens_in=350,
            tokens_out=60,
            cost_usd=cost,
            assistant_text="Renamed foo to bar in app.py.",
            tool_calls=[],
            stop_reason="end_turn",
        )
        recorder.emit("run_end", final_status="ok", total_cost_usd=round(guard.running_usd, 6), total_tokens=guard.running_tokens, duration_s=0.1)
        return recorder

    if "__vg_sentinel_never_present__" in task_lower or "don't stop" in task_lower or "dont stop" in task_lower:
        for step in range(1, 4):
            cost = guard.record_model_call(config.PARENT_MODEL_ID, 700, 80)
            recorder.emit(
                "assistant_step",
                model=config.PARENT_MODEL_ID,
                model_id=config.PARENT_MODEL_ID,
                step_idx=step,
                tokens_in=700,
                tokens_out=80,
                cost_usd=cost,
                assistant_text="Searching for the sentinel.",
                tool_calls=[{"tool_use_id": f"search-{step}", "name": "run_bash", "args": {"command": "grep -R __VG_SENTINEL_NEVER_PRESENT__ ."}}],
                stop_reason="tool_use",
            )
            _emit_tool_call(recorder, ToolCall(f"search-{step}", "run_bash", {"command": "grep -R __VG_SENTINEL_NEVER_PRESENT__ ."}))
            decision = guard.record_tool_signature("run_bash", "grep -R __VG_SENTINEL_NEVER_PRESENT__ .")
            recorder.emit(
                "tool_result",
                tool_use_id=f"search-{step}",
                tool="run_bash",
                result_full="",
                bytes=0,
                tokens=1,
                latency_ms=1,
                status="ok",
            )
            if not decision.allowed:
                recorder.emit("budget_event", budget_reason=decision.budget_reason, details=decision.details)
                recorder.emit("run_end", final_status="aborted", total_cost_usd=round(guard.running_usd, 6), total_tokens=guard.running_tokens, duration_s=0.1)
                return recorder

    cost = guard.record_model_call(config.PARENT_MODEL_ID, 900, 90)
    recorder.emit(
        "assistant_step",
        model=config.PARENT_MODEL_ID,
        model_id=config.PARENT_MODEL_ID,
        step_idx=1,
        tokens_in=900,
        tokens_out=90,
        cost_usd=cost,
        assistant_text="I will read the deterministic large log before delegating auth inspection.",
        tool_calls=[{"tool_use_id": "parent-read-sample-log", "name": "read_file", "args": {"path": "data/sample.log"}}],
        stop_reason="tool_use",
    )
    _emit_tool_call(recorder, ToolCall("parent-read-sample-log", "read_file", {"path": "data/sample.log"}))
    log_result = tools.read_file(root, "data/sample.log", "parent-read-sample-log")
    log_event = recorder.emit("tool_result", **log_result)
    _compact_if_needed(recorder, log_event, deterministic=True)

    cost = guard.record_model_call(config.PARENT_MODEL_ID, 1000, 120)
    recorder.emit(
        "assistant_step",
        model=config.PARENT_MODEL_ID,
        model_id=config.PARENT_MODEL_ID,
        step_idx=2,
        tokens_in=1000,
        tokens_out=120,
        cost_usd=cost,
        assistant_text="The large parent result is compacted. I will spawn Explorer for auth/.",
        tool_calls=[{"tool_use_id": "parent-spawn-explorer", "name": "spawn_subagent", "args": {"question": "inspect auth/"}}],
        stop_reason="tool_use",
    )
    _emit_tool_call(recorder, ToolCall("parent-spawn-explorer", "spawn_subagent", {"question": "inspect auth/"}))
    summary = _explore_auth(root, recorder, policy)
    recorder.emit(
        "tool_result",
        tool_use_id="parent-spawn-explorer",
        tool="spawn_subagent",
        result_full=summary,
        bytes=len(summary.encode("utf-8")),
        tokens=tools.estimate_tokens(summary),
        latency_ms=1,
        status="ok",
    )

    cost = guard.record_model_call(config.PARENT_MODEL_ID, 900, 100)
    recorder.emit(
        "assistant_step",
        model=config.PARENT_MODEL_ID,
        model_id=config.PARENT_MODEL_ID,
        step_idx=3,
        tokens_in=900,
        tokens_out=100,
        cost_usd=cost,
        assistant_text=summary,
        tool_calls=[],
        stop_reason="end_turn",
    )
    recorder.emit("run_end", final_status="ok", total_cost_usd=round(guard.running_usd, 6), total_tokens=guard.running_tokens, duration_s=0.2)
    return recorder
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
    build_session_status,
    emit_session_statusline,
    format_compaction_banner,
    format_statusline_compact,
    mark_turn_completed,
    print_chat_dashboard,
    print_turn_output,
    prompt_approval,
    refresh_chat_status_bar,
    render_input_bottom_and_footer,
    render_input_top_rule,
    reset_dashboard_mode,
    use_rich_ui,
)
from .agent import BUDGET_CAP_TOOL, ApprovalOutcome, ApprovalPolicy, ApprovalRequest, run_live_task, run_task
from .live_model_client import LiveModelClient, MissingOpenRouterKey
from .budget import BudgetGuard
from .demo_fixture import write_fixture
from .trace import TraceRecorder, load_trace, render_tree, show_context


def _stdin_prompt(stream: object | None = None) -> "callable":
    fh = stream if stream is not None else sys.stdin

    def ask(request: ApprovalRequest) -> ApprovalOutcome:
        if use_rich_ui():
            return prompt_approval(request, input_stream=fh)
        if request.tool == BUDGET_CAP_TOOL:
            sys.stderr.write(f"[approval] budget {request.path}  {request.summary}\\n")
        else:
            sys.stderr.write(f"[approval] {request.tool}  {request.summary}\\n")
        if request.tool == BUDGET_CAP_TOOL:
            sys.stderr.write("  1) yes  2) yes (this cap)  3) yes (always)  4) no  5) abort\\n> ")
        else:
            sys.stderr.write("  1) yes  2) yes (this folder)  3) yes (always)  4) no  5) abort\\n> ")
        sys.stderr.flush()
        line = fh.readline().strip()
        if not line:
            return ApprovalOutcome(decision="denied", reason="no input")
        choice = line.split()[0]
        if choice in {"1", "y", "yes"}:
            return ApprovalOutcome(decision="approved", reason="user yes")
        if choice == "2":
            path = request.path or ""
            normalized = path.replace("\\\\", "/")
            parent = "/".join(normalized.split("/")[:-1])
            if request.tool == "run_bash" and not request.path:
                command = str(request.args.get("command") or "")
                head = command.strip().split()[0] if command.strip() else ""
                scope = f"cmd:{head}" if head else "*"
            elif request.tool in {"spawn_subagent", "spawn_subagents"}:
                scope = "*"
            else:
                scope = parent
            return ApprovalOutcome(decision="approved_scoped", scope_key=scope, reason="user yes-folder")
        if choice in {"3", "a", "always"}:
            return ApprovalOutcome(decision="approved_always", scope_key="*", reason="user yes-always")
        if choice in {"5", "abort"}:
            return ApprovalOutcome(decision="aborted", reason="user abort")
        return ApprovalOutcome(decision="denied", reason="user no")

    return ask


def _make_policy(args: argparse.Namespace) -> ApprovalPolicy:
    mode = args.require_approval
    if mode == "off":
        return ApprovalPolicy(mode="off")
    return ApprovalPolicy(
        mode=mode,
        auto_yes=bool(args.yes),
        prompt=_stdin_prompt(),
    )


def _print_budget(guard: BudgetGuard) -> None:
    sys.stdout.write(
        f"steps {guard.step_count}/{guard.max_steps}  "
        f"tokens {guard.running_tokens}/{guard.max_tokens}  "
        f"usd {guard.running_usd:.6f}/{guard.max_usd}  "
        f"daily_remaining {guard.daily_remaining_usd:.6f}\\n"
    )


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
    "/help",
)
SLASH_COMMAND_USAGE = {
    "/show-context": "/show-context N",
}
SLASH_COMMAND_META = {
    "/exit": "End chat cleanly",
    "/quit": "Alias for /exit",
    "/budget": "Show steps, tokens, USD, and daily remaining",
    "/status": "Reprint session dashboard (TTY) or compact status + budget",
    "/finops": "Show per-agent token, tool, and cost table",
    "/approvals": "Show approval history and cached scopes",
    "/reset": "Clear approvals, budget, and chat history",
    "/new": "Start a fresh chat session and trace",
    "/show-context": "N: parent step index; default 0",
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
        return f"run_bash {command[:120]}"
    if name == "spawn_subagent":
        return f"spawn_subagent {str(args.get('question') or '')[:120]}"
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
        line = (
            f"[llm] {agent} step {event.get('step_idx')} done "
            f"in={event.get('tokens_in')} out={event.get('tokens_out')} "
            f"usd={float(event.get('cost_usd') or 0):.6f} stop={event.get('stop_reason')}"
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
        return f"[context] compacted {event.get('before_tokens')} -> {event.get('after_tokens')} tokens"
    if kind == "budget_event":
        return f"[budget] {event.get('budget_reason')}"
    if kind == "model_error":
        retry = " retryable" if event.get("retryable") else ""
        return f"[llm] {agent} step {event.get('step_idx')} failed{retry}: {event.get('message')}"
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
) -> "callable":
    fh = stream if stream is not None else sys.stderr
    use_color = bool(getattr(fh, "isatty", lambda: False)()) and not os.environ.get("NO_COLOR")
    reset = "\\x1b[0m" if use_color else ""
    state = turn_state if turn_state is not None else {}

    def sink(event: dict[str, object]) -> None:
        kind = event.get("kind")
        if kind == "statusline":
            return
        if kind == "user_prompt":
            state["turn"] = int(state.get("turn", 0)) + 1
            if use_color:
                fh.write(f"\\n\\x1b[90m── turn {state['turn']} ──\\x1b[0m\\n")
            else:
                fh.write(f"\\n── turn {state['turn']} ──\\n")
        banner = format_compaction_banner(event)
        if banner:
            fh.write(f"{banner}\\n")
        line = _format_progress_event(event)
        if line is not None:
            color = _progress_event_color(event, use_color=use_color)
            prefix = "  " if kind in {"subagent_spawn", "subagent_return"} else ""
            fh.write(f"{color}{prefix}{line}{reset}\\n")
            fh.flush()
        if kind == "assistant_step" and event.get("agent_id") == "parent" and on_parent_status:
            on_parent_status()
        elif kind == "run_end" and on_parent_status:
            on_parent_status()

    return sink


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


def _literal_tool_outputs(events: list[dict[str, object]], start_idx: int, prompt: str, answer: str) -> list[str]:
    if not _wants_literal_tool_output(prompt):
        return []
    calls = _parent_tool_calls(events, start_idx)
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
        call = calls.get(str(event.get("tool_use_id") or ""), {})
        command = str(call.get("command") or "").strip()
        label = "Tool output" if event.get("status") == "ok" else "Blocked"
        title = f"{label} ({command}):" if command else f"{label} ({event.get('tool')}):"
        outputs.append(f"{title}\\n{content}")
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


def _latest_run_end_status(events: list[dict[str, object]]) -> str | None:
    for event in reversed(events):
        if event.get("kind") == "run_end":
            return str(event.get("final_status") or "")
    return None


def _apply_model_overrides(args: argparse.Namespace) -> None:
    if getattr(args, "parent_model", None):
        config.PARENT_MODEL_ID = args.parent_model
    if getattr(args, "subagent_model", None):
        config.EXPLORER_MODEL_ID = args.subagent_model
        config.COMPACTOR_MODEL_ID = args.subagent_model




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
        )
    elif bool(getattr(sys.stderr, "isatty", lambda: False)()):
        line = _chat_statusline_color(
            format_statusline_compact(status),
            use_color=not os.environ.get("NO_COLOR"),
        )
        sys.stderr.write(line + "\\n")
        sys.stderr.flush()


def _chat_loop(root: Path, args: argparse.Namespace) -> int:
    guard = BudgetGuard.for_workspace(root)
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

    recorder = TraceRecorder(
        root,
        redact=not args.no_redact,
        event_sink=_make_progress_sink(on_parent_status=on_parent_status, turn_state=turn_state),
    )
    policy = _make_policy(args)
    history_path = root / ".vg_chat_history"
    read_prompt, save_history = _make_chat_prompt(history_path)
    if use_rich_ui():
        print_chat_dashboard(**_chat_ui_kwargs(root, recorder, guard, args, since_event_idx=ui_since))
    else:
        sys.stderr.write("VG Agent chat mode. Type /help for commands.\\n")
    conversation: list[dict[str, Any]] = []
    last_intent_prompt = ""
    try:
        while True:
            try:
                render_input_top_rule()
                prompt = read_prompt().strip()
                render_input_bottom_and_footer(**_chat_ui_kwargs(root, recorder, guard, args, since_event_idx=ui_since))
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
            if prompt == "/budget":
                _print_budget(guard)
                continue
            if prompt == "/status":
                if use_rich_ui():
                    print_chat_dashboard(**_chat_ui_kwargs(root, recorder, guard, args, since_event_idx=ui_since), compact=False)
                else:
                    line = _format_chat_statusline(recorder, guard, live_model=bool(args.live_model))
                    sys.stdout.write(line + "\\n")
                    _print_budget(guard)
                continue
            if prompt == "/approvals":
                _print_approvals(policy, recorder)
                continue
            if prompt == "/reset":
                policy.cache.clear()
                guard = BudgetGuard.for_workspace(root)
                conversation.clear()
                last_intent_prompt = ""
                ui_since = len(recorder.events)
                reset_dashboard_mode()
                recorder.emit("session_reset")
                if use_rich_ui():
                    print_chat_dashboard(**_chat_ui_kwargs(root, recorder, guard, args, since_event_idx=ui_since), compact=False)
                continue
            if prompt == "/new":
                policy.cache.clear()
                guard = BudgetGuard.for_workspace(root)
                conversation.clear()
                last_intent_prompt = ""
                ui_since = 0
                reset_dashboard_mode()
                turn_state["turn"] = 0
                recorder = TraceRecorder(
                    root,
                    redact=not args.no_redact,
                    event_sink=_make_progress_sink(on_parent_status=on_parent_status, turn_state=turn_state),
                )
                recorder.emit("session_new")
                if use_rich_ui():
                    print_chat_dashboard(**_chat_ui_kwargs(root, recorder, guard, args, since_event_idx=ui_since))
                continue
            if prompt == "/finops":
                _print_finops(guard, recorder)
                continue
            if prompt.startswith("/show-context"):
                parts = prompt.split()
                step = int(parts[1]) if len(parts) > 1 else 0
                sys.stdout.write(json.dumps(show_context(recorder.events, step), indent=2, ensure_ascii=False) + "\\n")
                continue
            if prompt == "/help":
                sys.stdout.write(SLASH_COMMAND_HELP + "\\n")
                continue
            start_idx = len(recorder.events)
            turn_state["since_event_idx"] = start_idx
            turn_state["force_state"] = "running"
            _report_parent_session_status(
                root, recorder, guard, args, since_event_idx=start_idx, force_state="running"
            )
            literal_prompt = last_intent_prompt if _is_ack_prompt(prompt) and last_intent_prompt else prompt
            if args.live_model:
                try:
                    client = LiveModelClient.from_env(recorder=recorder)
                except MissingOpenRouterKey as exc:
                    sys.stderr.write(f"error: {exc}\\n")
                    return 2
                run_live_task(root, prompt, recorder, client=client, guard=guard, policy=policy, history=conversation)
            else:
                run_task(root, prompt, recorder, policy=policy)
            turn_state["force_state"] = None
            answer = _latest_parent_answer(recorder.events, start_idx)
            literal_outputs = _literal_tool_outputs(recorder.events, start_idx, literal_prompt, answer)
            print_turn_output(answer=answer, literal_outputs=literal_outputs)
            for notice in _turn_subagent_failure_notices(recorder.events, start_idx):
                sys.stderr.write(notice + "\\n")
            mark_turn_completed()
            refresh_chat_status_bar(**_chat_ui_kwargs(root, recorder, guard, args, since_event_idx=start_idx))
            if not _is_ack_prompt(prompt):
                last_intent_prompt = prompt
    finally:
        save_history()
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="vg_agent")
    parser.add_argument("--task")
    parser.add_argument("--trace", action="store_true")
    parser.add_argument("--replay")
    parser.add_argument("--show-context", type=int)
    parser.add_argument("--seed-fixture", action="store_true")
    parser.add_argument("--live-model", action="store_true")
    parser.add_argument("--parent-model")
    parser.add_argument("--subagent-model")
    parser.add_argument("--chat", action="store_true")
    parser.add_argument("--require-approval", choices=["off", "writes", "all"], default=config.REQUIRE_APPROVAL_DEFAULT)
    parser.add_argument("--yes", action="store_true")
    parser.add_argument("--no-redact", action="store_true")
    parser.add_argument("--budget", action="store_true")
    parser.add_argument("--finops", action="store_true")
    args = parser.parse_args(argv)
    _apply_model_overrides(args)

    if args.no_redact:
        sys.stderr.write("warning: --no-redact disables trace secret redaction.\\n")

    root = Path.cwd()
    if args.seed_fixture:
        write_fixture(root)
        print(f"seeded fixture at {root}")
        return 0

    if args.replay:
        events = load_trace(Path(args.replay))
        if args.trace:
            print(render_tree(events))
        if args.show_context is not None:
            print(json.dumps(show_context(events, args.show_context), indent=2, ensure_ascii=False))
        return 0

    if args.chat:
        return _chat_loop(root, args)

    if not args.task:
        parser.error("--task, --chat, --replay, or --seed-fixture is required")

    recorder = TraceRecorder(
        root,
        redact=not args.no_redact,
        event_sink=_make_progress_sink() if args.live_model else None,
    )
    policy = _make_policy(args)
    guard: BudgetGuard | None = None
    if args.live_model:
        try:
            client = LiveModelClient.from_env(recorder=recorder)
        except MissingOpenRouterKey as exc:
            parser.exit(2, f"error: {exc}\\n")
        guard = BudgetGuard.for_workspace(root)
        run_live_task(root, args.task, recorder, client=client, guard=guard, policy=policy)
    else:
        run_task(root, args.task, recorder, policy=policy)
    answer = _latest_parent_answer(recorder.events)
    if answer:
        print(answer)
    for output in _literal_tool_outputs(recorder.events, 0, args.task, answer):
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
    if _latest_run_end_status(recorder.events) == "model_error":
        return 75
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
''',
}


EXTRA_SOURCE_GENERATED_FILES = ["sqlite_store.py", "chat_ui.py"]


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
