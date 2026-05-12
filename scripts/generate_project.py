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
        "EXPLORER_MODEL_ID",
        "COMPACTOR_MODEL_ID",
        "CLAUDE_SONNET_4_6_INPUT_PER_MTOK",
        "CLAUDE_SONNET_4_6_OUTPUT_PER_MTOK",
        "CLAUDE_HAIKU_4_5_INPUT_PER_MTOK",
        "CLAUDE_HAIKU_4_5_OUTPUT_PER_MTOK",
    ]
    values: dict[str, str] = {}
    for key in keys:
        match = re.search(rf"^{key}:\s*([^\n]+)$", text, flags=re.MULTILINE)
        if not match:
            raise SystemExit(f"missing {key} in MODEL_CONFIG.md")
        values[key] = match.group(1).strip()
    return values


def spec_digest() -> str:
    h = hashlib.sha256()
    for path in SOURCE_INPUTS:
        h.update(path.name.encode("utf-8"))
        h.update(b"\0")
        h.update(path.read_bytes())
        h.update(b"\0")
    return h.hexdigest()


def render(text: str, digest: str, cfg: dict[str, str]) -> str:
    for key, value in cfg.items():
        text = text.replace(f"__{key}__", value)
    return text.replace("__SPEC_DIGEST__", digest)


GENERATED_FILES: dict[str, str] = {
    "__init__.py": '''"""Generated VG agent runtime."""

SPEC_DIGEST = "__SPEC_DIGEST__"

__all__ = ["SPEC_DIGEST"]
''',
    "config.py": '''"""Generated runtime constants from MODEL_CONFIG.md."""

SPEC_DIGEST = "__SPEC_DIGEST__"

PARENT_MODEL_ID = "__PARENT_MODEL_ID__"
EXPLORER_MODEL_ID = "__EXPLORER_MODEL_ID__"
COMPACTOR_MODEL_ID = "__COMPACTOR_MODEL_ID__"

PRICING_USD_PER_MTOK = {
    PARENT_MODEL_ID: {"input": __CLAUDE_SONNET_4_6_INPUT_PER_MTOK__, "output": __CLAUDE_SONNET_4_6_OUTPUT_PER_MTOK__},
    EXPLORER_MODEL_ID: {"input": __CLAUDE_HAIKU_4_5_INPUT_PER_MTOK__, "output": __CLAUDE_HAIKU_4_5_OUTPUT_PER_MTOK__},
    COMPACTOR_MODEL_ID: {"input": __CLAUDE_HAIKU_4_5_INPUT_PER_MTOK__, "output": __CLAUDE_HAIKU_4_5_OUTPUT_PER_MTOK__},
}

MAX_PARENT_STEPS = 15
MAX_SUBAGENT_STEPS = 8
MAX_SUBAGENT_DEPTH = 1
MAX_CONCURRENT_SUBAGENTS = 2
MAX_TOKENS_PER_RUN = 80_000
MAX_USD_PER_RUN = 0.50
MAX_USD_PER_DAY = 5.00
WALL_CLOCK_TIMEOUT = 120
TOOL_TIMEOUT = 30
K_COMPACT = 4000
''',
    "budget.py": '''"""Generated budget guard."""

from __future__ import annotations

from dataclasses import dataclass, field

from . import config


@dataclass
class BudgetDecision:
    allowed: bool
    budget_reason: str | None = None
    details: dict[str, object] = field(default_factory=dict)


@dataclass
class BudgetGuard:
    max_steps: int = config.MAX_PARENT_STEPS
    max_tokens: int = config.MAX_TOKENS_PER_RUN
    max_usd: float = config.MAX_USD_PER_RUN
    daily_remaining_usd: float = config.MAX_USD_PER_DAY
    running_tokens: int = 0
    running_usd: float = 0.0
    step_count: int = 0
    last_tool_signature: tuple[str, str] | None = None
    repeat_count: int = 0

    def estimate_cost(self, model: str, input_tokens: int, output_tokens: int) -> float:
        price = config.PRICING_USD_PER_MTOK[model]
        return (input_tokens / 1_000_000) * price["input"] + (output_tokens / 1_000_000) * price["output"]

    def before_model_call(self, model: str, worst_input_tokens: int, worst_output_tokens: int) -> BudgetDecision:
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

    def record_model_call(self, model: str, input_tokens: int, output_tokens: int) -> float:
        self.step_count += 1
        self.running_tokens += input_tokens + output_tokens
        cost = self.estimate_cost(model, input_tokens, output_tokens)
        self.running_usd += cost
        return cost

    def record_tool_signature(self, tool: str, args_key: str) -> BudgetDecision:
        signature = (tool, args_key)
        if signature == self.last_tool_signature:
            self.repeat_count += 1
        else:
            self.last_tool_signature = signature
            self.repeat_count = 1
        if self.repeat_count >= 3:
            return BudgetDecision(False, "repetition_abort", {"tool": tool, "args_key": args_key, "repeat_count": self.repeat_count})
        return BudgetDecision(True)
''',
    "anthropic_client.py": '''"""Generated Anthropic Messages API client."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Any


class MissingAnthropicKey(RuntimeError):
    pass


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


class AnthropicClient:
    endpoint = "https://api.anthropic.com/v1/messages"

    def __init__(self, api_key: str, endpoint: str | None = None) -> None:
        self.api_key = api_key
        if endpoint is not None:
            self.endpoint = endpoint

    @classmethod
    def from_env(cls) -> "AnthropicClient":
        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            raise MissingAnthropicKey("ANTHROPIC_API_KEY is required when --live-model is used")
        return cls(api_key)

    def complete(
        self,
        *,
        model: str,
        system_prompt: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        max_tokens: int = 4096,
    ) -> ModelTurn:
        payload = {
            "model": model,
            "system": system_prompt,
            "messages": messages,
            "tools": tools,
            "max_tokens": max_tokens,
        }
        data = json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(
            self.endpoint,
            data=data,
            headers={
                "content-type": "application/json",
                "x-api-key": self.api_key,
                "anthropic-version": "2023-06-01",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                parsed = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"Anthropic API error {exc.code}: {body}") from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(f"Anthropic API request failed: {exc.reason}") from exc

        content = parsed.get("content", [])
        text_parts: list[str] = []
        tool_calls: list[ToolCall] = []
        raw_content: list[dict[str, Any]] = []
        for block in content:
            if not isinstance(block, dict):
                continue
            raw_content.append(block)
            if block.get("type") == "text":
                text_parts.append(str(block.get("text", "")))
            elif block.get("type") == "tool_use":
                tool_calls.append(
                    ToolCall(
                        tool_use_id=str(block.get("id", "")),
                        name=str(block.get("name", "")),
                        args=dict(block.get("input") or {}),
                    )
                )
        usage = parsed.get("usage") or {}
        return ModelTurn(
            assistant_text="\\n".join(part for part in text_parts if part),
            tool_calls=tool_calls,
            stop_reason=str(parsed.get("stop_reason") or ("tool_use" if tool_calls else "end_turn")),
            input_tokens=int(usage.get("input_tokens") or 0),
            output_tokens=int(usage.get("output_tokens") or 0),
            raw_content=raw_content,
        )
''',
    "tools.py": '''"""Generated local tools."""

from __future__ import annotations

import shlex
import subprocess
import time
from pathlib import Path


SAFE_COMMANDS = {"grep", "rg", "find", "ls", "pwd", "cat", "sed", "head", "tail", "wc"}
DESTRUCTIVE_TOKENS = {
    "rm", "del", "erase", "rmdir", "remove-item", "ri", "rd",
    "mv", "move", "cp", "copy", "chmod", "chown", "mkfs", "dd",
    "curl", "wget", "pip", "npm", "pnpm", "yarn", "uv", "python",
    "powershell", "pwsh", "cmd",
}
SHELL_CONTROL_MARKERS = [";", "&&", "||", "|", ">", "<", "`", "$("]


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
    if normalized[0] not in SAFE_COMMANDS:
        return f"command {normalized[0]!r} is not in the read-only allowlist"
    for token in normalized:
        if token in DESTRUCTIVE_TOKENS:
            return f"destructive token {token!r} is not allowed"
    for token in tokens[1:]:
        path_error = _path_token_error(token)
        if path_error:
            return path_error
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
    try:
        path = resolve_workspace_path(root, rel_path)
        content = path.read_text(encoding="utf-8")
        return _result(tool_use_id, "read_file", content, "ok", started)
    except (OSError, ValueError) as exc:
        return _result(tool_use_id, "read_file", str(exc), "error", started)


def read_file_range(root: Path, rel_path: str, start_line: int, end_line: int, tool_use_id: str) -> dict[str, object]:
    started = time.perf_counter()
    try:
        path = resolve_workspace_path(root, rel_path)
        lines = path.read_text(encoding="utf-8").splitlines()
        content = "\\n".join(lines[max(0, int(start_line) - 1):int(end_line)])
        return _result(tool_use_id, "read_file_range", content, "ok", started)
    except (OSError, ValueError) as exc:
        return _result(tool_use_id, "read_file_range", str(exc), "error", started)


def write_file(root: Path, rel_path: str, content: str, tool_use_id: str) -> dict[str, object]:
    started = time.perf_counter()
    try:
        path = resolve_workspace_path(root, rel_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8", newline="\\n")
        return _result(tool_use_id, "write_file", f"wrote {rel_path}", "ok", started)
    except (OSError, ValueError) as exc:
        return _result(tool_use_id, "write_file", str(exc), "error", started)


def edit_file(root: Path, rel_path: str, old: str, new: str, tool_use_id: str) -> dict[str, object]:
    started = time.perf_counter()
    try:
        path = resolve_workspace_path(root, rel_path)
        content = path.read_text(encoding="utf-8")
        if old not in content:
            return _result(tool_use_id, "edit_file", f"old text not found in {rel_path}", "error", started)
        path.write_text(content.replace(old, new), encoding="utf-8", newline="\\n")
        return _result(tool_use_id, "edit_file", f"edited {rel_path}", "ok", started)
    except (OSError, ValueError) as exc:
        return _result(tool_use_id, "edit_file", str(exc), "error", started)


def run_bash(root: Path, command: str, tool_use_id: str) -> dict[str, object]:
    started = time.perf_counter()
    safety_error = validate_shell_command(command)
    if safety_error:
        return _result(tool_use_id, "run_bash", f"refused unsafe command: {safety_error}", "error", started)
    completed = subprocess.run(["bash", "-c", command], cwd=root, text=True, capture_output=True, timeout=30)
    content = completed.stdout + completed.stderr
    status = "ok" if completed.returncode == 0 else "error"
    return _result(tool_use_id, "run_bash", content, status, started)
''',
    "trace.py": '''"""Generated JSONL trace and replay helpers."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class TraceRecorder:
    root: Path
    run_id: str = field(default_factory=lambda: uuid4().hex[:12])
    events: list[dict[str, object]] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.trace_dir = self.root / "traces"
        self.trace_dir.mkdir(parents=True, exist_ok=True)
        self.path = self.trace_dir / f"{self.run_id}.jsonl"

    def emit(self, kind: str, agent_id: str = "parent", parent_id: str | None = None, **fields: object) -> dict[str, object]:
        event = {
            "run_id": self.run_id,
            "event_idx": len(self.events),
            "timestamp_iso": now_iso(),
            "agent_id": agent_id,
            "parent_id": parent_id,
            "kind": kind,
        }
        event.update(fields)
        self.events.append(event)
        with self.path.open("a", encoding="utf-8", newline="\\n") as fh:
            fh.write(json.dumps(event, ensure_ascii=False, sort_keys=True) + "\\n")
        return event


def load_trace(path: Path) -> list[dict[str, object]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def render_tree(events: list[dict[str, object]]) -> str:
    lines: list[str] = []
    for event in events:
        prefix = "  " if event.get("parent_id") else ""
        kind = event["kind"]
        if kind == "assistant_step":
            lines.append(f"{prefix}{event['event_idx']:03d} {event['agent_id']} assistant step {event.get('step_idx')} model={event.get('model')}")
        elif kind == "tool_result":
            lines.append(f"{prefix}{event['event_idx']:03d} {event['agent_id']} tool_result {event.get('tool')} tokens={event.get('tokens')} status={event.get('status')}")
        elif kind == "compaction":
            lines.append(f"{prefix}{event['event_idx']:03d} compacted {event.get('before_tokens')} -> {event.get('after_tokens')} tokens (tool_use {event.get('tool_use_id')})")
        elif kind == "budget_event":
            lines.append(f"{prefix}{event['event_idx']:03d} budget_event {event.get('budget_reason')}")
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
            if int(event["step_idx"]) > step_idx:
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
import time
from dataclasses import asdict
from typing import Any
from pathlib import Path

from . import config, tools
from .anthropic_client import AnthropicClient, ModelTurn, ToolCall
from .budget import BudgetGuard
from .trace import TraceRecorder, compacted_marker


PARENT_SYSTEM_PROMPT = (
    "You are the parent coding agent. Use tools deliberately, keep a concise working "
    "context, and spawn Explorer only for bounded repository inspection. You may use "
    "`read_file`, `read_file_range`, `write_file`, `edit_file`, `run_bash`, and "
    "`spawn_subagent`. Prefer targeted reads before edits, explain final changes "
    "concisely, and stop when the task is complete."
)

EXPLORER_SYSTEM_PROMPT = (
    "You are Explorer, a read-only sub-agent. Inspect only the requested area, keep "
    "all intermediate tool calls in your private context, and return one summary of "
    "at most 2 KB. Never spawn another sub-agent, never edit files, and answer only "
    "the bounded question from the parent."
)

PARENT_TOOL_SCHEMAS: list[dict[str, Any]] = [
    {
        "name": "read_file",
        "description": "Read a UTF-8 text file under the workspace root.",
        "input_schema": {"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]},
    },
    {
        "name": "read_file_range",
        "description": "Read an inclusive 1-based line range from a UTF-8 text file under the workspace root.",
        "input_schema": {
            "type": "object",
            "properties": {"path": {"type": "string"}, "start_line": {"type": "integer"}, "end_line": {"type": "integer"}},
            "required": ["path", "start_line", "end_line"],
        },
    },
    {
        "name": "write_file",
        "description": "Write a UTF-8 text file under the workspace root.",
        "input_schema": {"type": "object", "properties": {"path": {"type": "string"}, "content": {"type": "string"}}, "required": ["path", "content"]},
    },
    {
        "name": "edit_file",
        "description": "Replace exact text in a UTF-8 text file under the workspace root.",
        "input_schema": {
            "type": "object",
            "properties": {"path": {"type": "string"}, "old": {"type": "string"}, "new": {"type": "string"}},
            "required": ["path", "old", "new"],
        },
    },
    {
        "name": "run_bash",
        "description": "Run one simple read-only inspection command through bash.",
        "input_schema": {"type": "object", "properties": {"command": {"type": "string"}}, "required": ["command"]},
    },
    {
        "name": "spawn_subagent",
        "description": "Ask Explorer a bounded read-only repository-inspection question.",
        "input_schema": {"type": "object", "properties": {"question": {"type": "string"}}, "required": ["question"]},
    },
]

EXPLORER_TOOL_SCHEMAS = [schema for schema in PARENT_TOOL_SCHEMAS if schema["name"] in {"read_file", "read_file_range", "run_bash"}]


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


def _execute_live_tool(
    *,
    root: Path,
    call: ToolCall,
    recorder: TraceRecorder,
    client: Any,
    guard: BudgetGuard,
    read_only: bool,
    allow_spawn: bool,
    started: float,
) -> dict[str, object]:
    tool_name = call.name
    args = call.args
    tool_started = time.perf_counter()
    path = str(args.get("path") or args.get("rel_path") or "")

    if tool_name == "read_file":
        return tools.read_file(root, path, call.tool_use_id)
    if tool_name == "read_file_range":
        return tools.read_file_range(root, path, int(args.get("start_line", 1)), int(args.get("end_line", 1)), call.tool_use_id)
    if tool_name == "run_bash":
        command = str(args.get("command") or "")
        repeat = guard.record_tool_signature("run_bash", command)
        if not repeat.allowed:
            recorder.emit("budget_event", budget_reason=repeat.budget_reason, details=repeat.details)
            return _result(call.tool_use_id, "run_bash", f"budget abort: {repeat.budget_reason}", "error", tool_started)
        return tools.run_bash(root, command, call.tool_use_id)
    if tool_name == "write_file":
        if read_only:
            return _result(call.tool_use_id, tool_name, "Explorer is read-only and cannot write files", "error", tool_started)
        return tools.write_file(root, path, str(args.get("content") or ""), call.tool_use_id)
    if tool_name == "edit_file":
        if read_only:
            return _result(call.tool_use_id, tool_name, "Explorer is read-only and cannot edit files", "error", tool_started)
        return tools.edit_file(root, path, str(args.get("old") or ""), str(args.get("new") or ""), call.tool_use_id)
    if tool_name == "spawn_subagent":
        if not allow_spawn:
            return _result(call.tool_use_id, tool_name, "Explorer cannot spawn sub-agents", "error", tool_started)
        question = str(args.get("question") or "")
        child_id = f"explorer-{sum(1 for event in recorder.events if event.get('kind') == 'subagent_spawn') + 1}"
        recorder.emit("subagent_spawn", child_agent_id=child_id, question=question, model=config.EXPLORER_MODEL_ID)
        summary = _run_live_explorer(root, question, recorder, client, guard, child_id, started)
        return _result(call.tool_use_id, "spawn_subagent", summary, "ok", tool_started)
    return _result(call.tool_use_id, tool_name, f"unknown tool {tool_name!r}", "error", tool_started)


def _run_live_explorer(
    root: Path,
    question: str,
    recorder: TraceRecorder,
    client: Any,
    guard: BudgetGuard,
    child_id: str,
    started: float,
) -> str:
    messages: list[dict[str, Any]] = [{"role": "user", "content": question}]
    child_cost_before = guard.running_usd
    child_tokens_before = guard.running_tokens
    final_summary = ""

    for local_step in range(1, config.MAX_SUBAGENT_STEPS + 1):
        if time.perf_counter() - started > config.WALL_CLOCK_TIMEOUT:
            recorder.emit("budget_event", agent_id=child_id, parent_id="parent", budget_reason="timeout", details={"timeout_s": config.WALL_CLOCK_TIMEOUT})
            break
        expected_in = _estimate_message_tokens(EXPLORER_SYSTEM_PROMPT, messages)
        decision = guard.before_model_call(config.EXPLORER_MODEL_ID, expected_in, 2048)
        if not decision.allowed:
            recorder.emit("budget_event", agent_id=child_id, parent_id="parent", budget_reason=decision.budget_reason, details=decision.details)
            break
        turn = client.complete(
            model=config.EXPLORER_MODEL_ID,
            system_prompt=EXPLORER_SYSTEM_PROMPT,
            messages=messages,
            tools=EXPLORER_TOOL_SCHEMAS,
            max_tokens=2048,
        )
        if not isinstance(turn, ModelTurn):
            turn = ModelTurn(**turn)
        turn.tool_calls = [_normalise_tool_call(call) for call in turn.tool_calls]
        input_tokens = turn.input_tokens or expected_in
        output_tokens = turn.output_tokens or tools.estimate_tokens(turn.assistant_text + json.dumps([asdict(c) for c in turn.tool_calls], sort_keys=True))
        cost = guard.record_model_call(config.EXPLORER_MODEL_ID, input_tokens, output_tokens)
        recorder.emit(
            "assistant_step",
            agent_id=child_id,
            parent_id="parent",
            model=config.EXPLORER_MODEL_ID,
            step_idx=local_step,
            tokens_in=input_tokens,
            tokens_out=output_tokens,
            cost_usd=cost,
            assistant_text=turn.assistant_text,
            tool_calls=[_tool_call_trace(call) for call in turn.tool_calls],
            stop_reason=turn.stop_reason,
        )
        messages.append({"role": "assistant", "content": _assistant_content(turn)})
        if not turn.tool_calls:
            final_summary = turn.assistant_text[:2048]
            break
        tool_blocks: list[dict[str, Any]] = []
        for call in turn.tool_calls:
            result = _execute_live_tool(
                root=root,
                call=call,
                recorder=recorder,
                client=client,
                guard=guard,
                read_only=True,
                allow_spawn=False,
                started=started,
            )
            recorder.emit("tool_result", agent_id=child_id, parent_id="parent", **result)
            tool_blocks.append({"type": "tool_result", "tool_use_id": call.tool_use_id, "content": str(result["result_full"]), "is_error": result["status"] != "ok"})
            if result["status"] != "ok":
                final_summary = str(result["result_full"])[:2048]
                break
        messages.append({"role": "user", "content": tool_blocks})
        if final_summary and any(block.get("is_error") for block in tool_blocks):
            break

    if not final_summary:
        final_summary = "Explorer stopped before producing a final summary."
    recorder.emit(
        "subagent_return",
        child_agent_id=child_id,
        summary=final_summary,
        child_total_cost_usd=round(guard.running_usd - child_cost_before, 6),
        child_total_tokens=guard.running_tokens - child_tokens_before,
    )
    return final_summary


def run_live_task(
    root: Path,
    task: str,
    recorder: TraceRecorder | None = None,
    client: Any | None = None,
    guard: BudgetGuard | None = None,
) -> TraceRecorder:
    recorder = recorder or TraceRecorder(root)
    client = client or AnthropicClient.from_env()
    guard = guard or BudgetGuard()
    started = time.perf_counter()
    messages: list[dict[str, Any]] = [{"role": "user", "content": task}]
    recorder.emit("user_prompt", prompt=task, live_model=True)

    while True:
        if time.perf_counter() - started > config.WALL_CLOCK_TIMEOUT:
            decision = type("Decision", (), {"budget_reason": "timeout", "details": {"timeout_s": config.WALL_CLOCK_TIMEOUT}})()
            _record_budget_abort(recorder, guard, decision, started)
            return recorder
        expected_in = _estimate_message_tokens(PARENT_SYSTEM_PROMPT, messages)
        decision = guard.before_model_call(config.PARENT_MODEL_ID, expected_in, 4096)
        if not decision.allowed:
            _record_budget_abort(recorder, guard, decision, started)
            return recorder
        turn = client.complete(
            model=config.PARENT_MODEL_ID,
            system_prompt=PARENT_SYSTEM_PROMPT,
            messages=messages,
            tools=PARENT_TOOL_SCHEMAS,
            max_tokens=4096,
        )
        if not isinstance(turn, ModelTurn):
            turn = ModelTurn(**turn)
        turn.tool_calls = [_normalise_tool_call(call) for call in turn.tool_calls]
        input_tokens = turn.input_tokens or expected_in
        output_tokens = turn.output_tokens or tools.estimate_tokens(turn.assistant_text + json.dumps([asdict(c) for c in turn.tool_calls], sort_keys=True))
        cost = guard.record_model_call(config.PARENT_MODEL_ID, input_tokens, output_tokens)
        step_idx = guard.step_count
        recorder.emit(
            "assistant_step",
            model=config.PARENT_MODEL_ID,
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
                read_only=False,
                allow_spawn=True,
                started=started,
            )
            event = recorder.emit("tool_result", **result)
            content = str(result["result_full"])
            compaction = _compact_if_needed(recorder, event, deterministic=False)
            if compaction is not None:
                content = compacted_marker(compaction)
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


def _explore_auth(root: Path, recorder: TraceRecorder) -> str:
    child_id = "explorer-1"
    recorder.emit("subagent_spawn", child_agent_id=child_id, question="inspect auth/", model=config.EXPLORER_MODEL_ID)
    recorder.emit(
        "assistant_step",
        agent_id=child_id,
        parent_id="parent",
        model=config.EXPLORER_MODEL_ID,
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
    session = tools.read_file(root, "auth/session.py", "child-read-session")
    recorder.emit("tool_result", agent_id=child_id, parent_id="parent", **session)
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


def run_task(root: Path, task: str, recorder: TraceRecorder | None = None) -> TraceRecorder:
    recorder = recorder or TraceRecorder(root)
    guard = BudgetGuard()
    task_lower = task.lower()
    recorder.emit("user_prompt", prompt=task)

    if "rename" in task_lower and "foo" in task_lower and "bar" in task_lower:
        cost = guard.record_model_call(config.PARENT_MODEL_ID, 500, 80)
        recorder.emit(
            "assistant_step",
            model=config.PARENT_MODEL_ID,
            step_idx=1,
            tokens_in=500,
            tokens_out=80,
            cost_usd=cost,
            assistant_text="I will replace foo with bar in app.py.",
            tool_calls=[{"tool_use_id": "parent-edit-app", "name": "edit_file", "args": {"path": "app.py"}}],
            stop_reason="tool_use",
        )
        result = tools.edit_file(root, "app.py", "foo", "bar", "parent-edit-app")
        recorder.emit("tool_result", **result)
        cost = guard.record_model_call(config.PARENT_MODEL_ID, 350, 60)
        recorder.emit(
            "assistant_step",
            model=config.PARENT_MODEL_ID,
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
                step_idx=step,
                tokens_in=700,
                tokens_out=80,
                cost_usd=cost,
                assistant_text="Searching for the sentinel.",
                tool_calls=[{"tool_use_id": f"search-{step}", "name": "run_bash", "args": {"command": "grep -R __VG_SENTINEL_NEVER_PRESENT__ ."}}],
                stop_reason="tool_use",
            )
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
        step_idx=1,
        tokens_in=900,
        tokens_out=90,
        cost_usd=cost,
        assistant_text="I will read the deterministic large log before delegating auth inspection.",
        tool_calls=[{"tool_use_id": "parent-read-sample-log", "name": "read_file", "args": {"path": "data/sample.log"}}],
        stop_reason="tool_use",
    )
    log_result = tools.read_file(root, "data/sample.log", "parent-read-sample-log")
    log_event = recorder.emit("tool_result", **log_result)
    _compact_if_needed(recorder, log_event, deterministic=True)

    cost = guard.record_model_call(config.PARENT_MODEL_ID, 1000, 120)
    recorder.emit(
        "assistant_step",
        model=config.PARENT_MODEL_ID,
        step_idx=2,
        tokens_in=1000,
        tokens_out=120,
        cost_usd=cost,
        assistant_text="The large parent result is compacted. I will spawn Explorer for auth/.",
        tool_calls=[{"tool_use_id": "parent-spawn-explorer", "name": "spawn_subagent", "args": {"question": "inspect auth/"}}],
        stop_reason="tool_use",
    )
    summary = _explore_auth(root, recorder)
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
from pathlib import Path

from .agent import run_live_task, run_task
from .anthropic_client import AnthropicClient, MissingAnthropicKey
from .demo_fixture import write_fixture
from .trace import TraceRecorder, load_trace, render_tree, show_context


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="vg_agent")
    parser.add_argument("--task")
    parser.add_argument("--trace", action="store_true")
    parser.add_argument("--replay")
    parser.add_argument("--show-context", type=int)
    parser.add_argument("--seed-fixture", action="store_true")
    parser.add_argument("--live-model", action="store_true")
    args = parser.parse_args(argv)

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

    if not args.task:
        parser.error("--task, --replay, or --seed-fixture is required")

    recorder = TraceRecorder(root)
    if args.live_model:
        try:
            client = AnthropicClient.from_env()
        except MissingAnthropicKey as exc:
            parser.exit(2, f"error: {exc}\\n")
        run_live_task(root, args.task, recorder, client=client)
    else:
        run_task(root, args.task, recorder)
    if args.trace:
        print(render_tree(recorder.events))
        print(f"trace: {recorder.path}")
    if args.show_context is not None:
        print(json.dumps(show_context(recorder.events, args.show_context), indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
''',
}


def write_generated(src_dir: Path, digest: str, cfg: dict[str, str], clean: bool) -> None:
    if clean and src_dir.exists():
        shutil.rmtree(src_dir)
    src_dir.mkdir(parents=True, exist_ok=True)
    for rel_path, text in GENERATED_FILES.items():
        path = src_dir / rel_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(render(text, digest, cfg), encoding="utf-8", newline="\n")


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
    digest = spec_digest()
    src_dir = Path(args.src_dir)
    write_generated(src_dir, digest, cfg, args.clean)
    if not args.no_fixture:
        write_fixture(Path(args.fixture_dir), args.clean)
    print(f"generated {src_dir} from specs digest {digest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
