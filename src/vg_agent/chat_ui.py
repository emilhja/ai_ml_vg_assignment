"""Interactive TTY chat presentation for ``vg-agent --chat``."""

from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from . import config, tools
from .budget import BudgetGuard
from .trace import TraceRecorder, show_context

CHAT_PLACEHOLDER = 'Try "read data/sample.log and summarise auth/"'

_WELCOME_BORDER = "rgb(224,122,95)"
_PRODUCT_LABEL = "vg-agent"

MODEL_CONTEXT_WINDOWS: dict[str, int] = {
    "openrouter/google/gemini-2.0-flash-001": 1_048_576,
    "openrouter/anthropic/claude-haiku-4.5": 200_000,
    "openrouter/anthropic/claude-sonnet-4.6": 200_000,
}

_compact_dashboard = False

try:
    from prompt_toolkit import PromptSession
except ImportError:  # pragma: no cover
    PromptSession = None  # type: ignore[misc, assignment]


def use_rich_ui() -> bool:
    if os.environ.get("NO_COLOR"):
        return False
    stdin_tty = bool(getattr(sys.stdin, "isatty", lambda: False)())
    stderr_tty = bool(getattr(sys.stderr, "isatty", lambda: False)())
    return stdin_tty and stderr_tty


def use_emoji() -> bool:
    if os.environ.get("NO_EMOJI"):
        return False
    return use_rich_ui()


def mark_turn_completed() -> None:
    global _compact_dashboard
    _compact_dashboard = True


def reset_dashboard_mode() -> None:
    global _compact_dashboard
    _compact_dashboard = False


def short_cwd(path: Path) -> str:
    resolved = path.resolve()
    home = Path.home().resolve()
    try:
        rel = resolved.relative_to(home)
        suffix = rel.as_posix()
        return "~" if not suffix else f"~/{suffix}"
    except ValueError:
        return resolved.as_posix()


def _console() -> Any:
    from rich.console import Console

    return Console(stderr=True, highlight=False)


def _format_compact_number(value: object) -> str:
    number = float(value or 0)
    if number >= 1_000_000:
        return f"{number / 1_000_000:.1f}m"
    if number >= 1_000:
        return f"{number / 1_000:.1f}k"
    return str(int(number))


def _short_model(model: object) -> str:
    text = str(model or "")
    for prefix in ("openrouter/anthropic/", "openrouter/"):
        if text.startswith(prefix):
            return text[len(prefix) :]
    return text


def _bar(used: int, total: int, width: int = 10) -> str:
    if total <= 0:
        return "-" * width
    filled = max(0, min(width, round((used / total) * width)))
    return "#" * filled + "-" * (width - filled)


def _latest_parent_llm_start(events: list[dict[str, object]]) -> dict[str, object] | None:
    for event in reversed(events):
        if event.get("kind") == "llm_start" and event.get("agent_id") == "parent":
            return event
    return None


def _latest_parent_step_idx(events: list[dict[str, object]]) -> int:
    step = 0
    for event in events:
        if event.get("kind") == "assistant_step" and event.get("agent_id") == "parent":
            step = max(step, int(event.get("step_idx") or 0))
    return step


def estimate_parent_ctx_tokens(events: list[dict[str, object]]) -> int:
    has_parent_steps = any(
        event.get("kind") == "assistant_step" and event.get("agent_id") == "parent"
        for event in events
    )
    if not has_parent_steps:
        latest_llm = _latest_parent_llm_start(events)
        return int((latest_llm or {}).get("tokens_in") or 0)
    step_idx = _latest_parent_step_idx(events)
    ctx = show_context(events, step_idx)
    return tools.estimate_tokens(json.dumps(ctx, sort_keys=True, ensure_ascii=False))


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


def _status_token(
    events: list[dict[str, object]],
    *,
    since_event_idx: int,
    force_state: str | None = None,
) -> tuple[str, str, str]:
    if force_state == "running":
        return "\u2026", "running", "yellow"
    status = _latest_run_state(events, since_event_idx=since_event_idx)
    lowered = status.lower()
    turn_errors = _tool_error_count(events[since_event_idx:])
    if (
        turn_errors > 0
        or "tool_error" in lowered
        or "model_error" in lowered
        or "aborted" in lowered
        or "error" in lowered
    ):
        label = status if status != "ready" else "error"
        return "\u2717", label, "red"
    if any(marker in lowered for marker in ("warn", "cap", "budget")):
        return "\u26a0", "warn", "yellow"
    if status in {"ready", "ok", "done"}:
        display = "ready" if status == "ready" else status
        return "\u2713", display, "green"
    return "\u2713", status, "green"


def _secondary_notice(events: list[dict[str, object]], *, since_event_idx: int) -> str | None:
    status = _latest_run_state(events, since_event_idx=since_event_idx)
    turn_errors = _tool_error_count(events[since_event_idx:])
    if status in {"ready", "ok"} and turn_errors == 0:
        return None
    reason = status
    if turn_errors > 0 and status in {"ready", "ok", "done"}:
        reason = f"{turn_errors} tool error(s)"
    return f"!! {reason} \u2014 see progress above"


@dataclass(frozen=True)
class SessionStatus:
    mode: str
    model: str
    model_id: str
    ctx_tokens: int
    ctx_window: int | None
    ctx_pct: float | None
    running_tokens: int
    max_tokens: int
    token_bar: str
    steps: int
    max_steps: int
    running_usd: float
    max_usd: float
    approvals: int
    tool_errors_turn: int
    tool_errors_session: int
    status_icon: str
    status_label: str
    status_style: str
    workspace_name: str

    def ctx_display(self) -> str:
        compact = _format_compact_number(self.ctx_tokens)
        if self.ctx_window and self.ctx_pct is not None:
            return f"ctx {compact}/{_format_compact_number(self.ctx_window)} ({self.ctx_pct:.0f}%)"
        return f"ctx {compact} in"


def build_session_status(
    *,
    root: Path,
    recorder: TraceRecorder,
    guard: BudgetGuard,
    live_model: bool,
    since_event_idx: int = 0,
    force_state: str | None = None,
) -> SessionStatus:
    mode = "live" if live_model else "deterministic"
    latest_llm = _latest_parent_llm_start(recorder.events)
    model_id = str((latest_llm or {}).get("model") or config.PARENT_MODEL_ID)
    model = _short_model(model_id)
    ctx_tokens = estimate_parent_ctx_tokens(recorder.events)
    ctx_window = MODEL_CONTEXT_WINDOWS.get(model_id)
    ctx_pct = (ctx_tokens / ctx_window * 100) if ctx_window else None
    icon, status_label, status_style = _status_token(
        recorder.events, since_event_idx=since_event_idx, force_state=force_state
    )
    workspace_name = root.resolve().name or str(root)
    approval_events = sum(1 for event in recorder.events if event.get("kind") == "approval")
    session_tool_errors = _tool_error_count(recorder.events)
    turn_tool_errors = _tool_error_count(recorder.events[since_event_idx:])
    return SessionStatus(
        mode=mode,
        model=model,
        model_id=model_id,
        ctx_tokens=ctx_tokens,
        ctx_window=ctx_window,
        ctx_pct=ctx_pct,
        running_tokens=guard.running_tokens,
        max_tokens=guard.max_tokens,
        token_bar=_bar(guard.running_tokens, guard.max_tokens),
        steps=guard.step_count,
        max_steps=guard.max_steps,
        running_usd=guard.running_usd,
        max_usd=guard.max_usd,
        approvals=approval_events,
        tool_errors_turn=turn_tool_errors,
        tool_errors_session=session_tool_errors,
        status_icon=icon,
        status_label=status_label,
        status_style=status_style,
        workspace_name=workspace_name,
    )


def format_statusline_compact(status: SessionStatus, *, width: int | None = None) -> str:
    err_segment = (
        f"tool errs {status.tool_errors_turn} turn / {status.tool_errors_session} session"
        if status.tool_errors_turn != status.tool_errors_session
        else f"tool errs {status.tool_errors_session}"
    )
    line = (
        f"[{status.mode}] {status.model} | {status.ctx_display()} | "
        f"run {status.token_bar} {_format_compact_number(status.running_tokens)}/"
        f"{_format_compact_number(status.max_tokens)} tok | "
        f"steps {status.steps}/{status.max_steps} | "
        f"usd ${status.running_usd:.4f}/${status.max_usd:.2f} | "
        f"approvals {status.approvals} | {err_segment} | {status.status_label}"
    )
    if width is None:
        import shutil

        width = shutil.get_terminal_size((120, 20)).columns
    if width > 20 and len(line) > width:
        return line[: max(0, width - 3)] + "..."
    return line


def emit_session_statusline(
    recorder: TraceRecorder,
    status: SessionStatus,
    *,
    width: int | None = None,
) -> None:
    text = format_statusline_compact(status, width=width)
    recorder.emit(
        "statusline",
        text=text,
        mode=status.mode,
        model=status.model_id,
        ctx_tokens=status.ctx_tokens,
        ctx_window=status.ctx_window,
        steps=status.steps,
        max_steps=status.max_steps,
        running_tokens=status.running_tokens,
        max_tokens=status.max_tokens,
        running_usd=status.running_usd,
        max_usd=status.max_usd,
    )


def build_status_bar_text(
    *,
    root: Path,
    recorder: TraceRecorder,
    guard: BudgetGuard,
    live_model: bool,
    since_event_idx: int = 0,
    force_state: str | None = None,
) -> str:
    status = build_session_status(
        root=root,
        recorder=recorder,
        guard=guard,
        live_model=live_model,
        since_event_idx=since_event_idx,
        force_state=force_state,
    )
    if use_emoji():
        folder = "\U0001f4c1"
        robot = "\U0001f916"
        coin = "\U0001f4b5"
        chart = "\U0001f4ca"
    else:
        folder = "dir:"
        robot = "mdl:"
        coin = "usd:"
        chart = "stp:"
    return (
        f"{folder} {status.workspace_name} | {robot} {status.model} | {status.mode} | "
        f"{status.ctx_display()} | "
        f"{coin} ${status.running_usd:.4f}/${status.max_usd:.2f} | "
        f"{chart} {status.steps}/{status.max_steps} steps | "
        f"{status.status_icon} {status.status_label}"
    )


def _write_status_bar(
    console: Any,
    *,
    root: Path,
    recorder: TraceRecorder,
    guard: BudgetGuard,
    live_model: bool,
    since_event_idx: int,
    force_state: str | None = None,
) -> None:
    status = build_session_status(
        root=root,
        recorder=recorder,
        guard=guard,
        live_model=live_model,
        since_event_idx=since_event_idx,
        force_state=force_state,
    )
    if use_emoji():
        folder = "\U0001f4c1"
        robot = "\U0001f916"
        coin = "\U0001f4b5"
        chart = "\U0001f4ca"
    else:
        folder = "dir:"
        robot = "mdl:"
        coin = "usd:"
        chart = "stp:"
    status_part = f"[{status.status_style}]{status.status_icon} {status.status_label}[/{status.status_style}]"
    line = (
        f"{folder} {status.workspace_name} | {robot} {status.model} | {status.mode} | "
        f"{status.ctx_display()} | "
        f"{coin} ${status.running_usd:.4f}/${status.max_usd:.2f} | "
        f"{chart} {status.steps}/{status.max_steps} steps | {status_part}"
    )
    console.print(line)


def _write_hint(console: Any) -> None:
    console.print("[dim]/help for commands \u00b7 /status to refresh session[/dim]")


def _write_secondary(console: Any, events: list[dict[str, object]], *, since_event_idx: int) -> None:
    notice = _secondary_notice(events, since_event_idx=since_event_idx)
    if notice:
        console.print(f"[yellow]{notice}[/yellow]")


def print_chat_dashboard(
    *,
    root: Path,
    recorder: TraceRecorder,
    guard: BudgetGuard,
    live_model: bool,
    since_event_idx: int = 0,
    compact: bool | None = None,
) -> None:
    if not use_rich_ui():
        return
    use_compact = _compact_dashboard if compact is None else compact
    console = _console()
    console.print(f"[dim]{_PRODUCT_LABEL}[/dim]")
    if not use_compact:
        from rich.panel import Panel
        from rich.text import Text

        welcome = Text()
        welcome.append("* ", style=f"bold {_WELCOME_BORDER}")
        welcome.append("Welcome to VG Agent!", style="bold white")
        welcome.append("\n")
        welcome.append(f"cwd: {short_cwd(root)}", style="dim")
        console.print(Panel(welcome, border_style=_WELCOME_BORDER, padding=(0, 1)))
    _write_status_bar(
        console,
        root=root,
        recorder=recorder,
        guard=guard,
        live_model=live_model,
        since_event_idx=since_event_idx,
    )
    _write_hint(console)
    _write_secondary(console, recorder.events, since_event_idx=since_event_idx)


def render_input_top_rule() -> None:
    if not use_rich_ui():
        return
    from rich.rule import Rule

    _console().print(Rule(style="dim"))


def render_input_bottom_and_footer(
    *,
    root: Path,
    recorder: TraceRecorder,
    guard: BudgetGuard,
    live_model: bool,
    since_event_idx: int = 0,
) -> None:
    if not use_rich_ui():
        return
    from rich.rule import Rule

    console = _console()
    console.print(Rule(style="dim"))
    _write_status_bar(
        console,
        root=root,
        recorder=recorder,
        guard=guard,
        live_model=live_model,
        since_event_idx=since_event_idx,
    )
    _write_hint(console)
    _write_secondary(console, recorder.events, since_event_idx=since_event_idx)


def _lines_already_in_answer(answer: str, content: str) -> bool:
    answer_lines = {line.strip() for line in answer.splitlines() if line.strip()}
    content_lines = [line.strip() for line in content.splitlines() if line.strip()]
    if not content_lines:
        return True
    return all(line in answer_lines for line in content_lines)


def _render_directory_tree(text: str) -> Any | None:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if not lines or not all(line.startswith("./") or line in {".", "./"} for line in lines[:20]):
        return None
    from rich.tree import Tree

    root = Tree(".")
    nodes: dict[str, Any] = {".": root}
    for line in lines:
        path = line.removeprefix("./")
        if not path or path == ".":
            continue
        parts = path.split("/")
        parent_key = "."
        for index, part in enumerate(parts):
            key = "/".join(parts[: index + 1])
            if key not in nodes:
                parent = nodes[parent_key]
                nodes[key] = parent.add(part)
            parent_key = key
    return root


def print_turn_output(*, answer: str, literal_outputs: list[str]) -> bool:
    """Frame agent answer + literal tool outputs. Returns True if anything printed."""
    answer_text = answer.strip()
    filtered_outputs: list[str] = []
    for output in literal_outputs:
        if not output:
            continue
        body = output.split(":", 1)[-1].strip() if output.startswith(("Tool output", "Blocked", "Tool error")) else output
        if answer_text and _lines_already_in_answer(answer_text, body):
            continue
        filtered_outputs.append(output)
    if not answer_text and not filtered_outputs:
        return False
    if use_rich_ui():
        from rich.console import Console
        from rich.panel import Panel
        from rich.rule import Rule
        from rich.syntax import Syntax

        console = Console(file=sys.stdout, highlight=False)
        console.print(Rule(style="dim"))
        if answer_text:
            console.print(Panel(answer_text, title="Response", border_style="dim"))
        for output in filtered_outputs:
            if "\n" in output:
                title, _, body = output.partition(":\n")
                tree = _render_directory_tree(body)
                if tree is not None:
                    console.print(Panel(tree, title=title or "Tool output", border_style="dim"))
                elif len(body) > 80 and "\n" in body:
                    console.print(Panel(Syntax(body, "text", word_wrap=True), title=title or "Tool output", border_style="dim"))
                else:
                    console.print(Panel(body, title=title or "Tool output", border_style="dim"))
            else:
                console.print(output)
        console.print(Rule(style="dim"))
    else:
        parts: list[str] = []
        if answer_text:
            parts.append(answer_text)
        parts.extend(filtered_outputs)
        sys.stdout.write("\n".join(parts) + "\n")
    sys.stdout.flush()
    return True


def refresh_chat_status_bar(
    *,
    root: Path,
    recorder: TraceRecorder,
    guard: BudgetGuard,
    live_model: bool,
    since_event_idx: int = 0,
    force_state: str | None = None,
) -> None:
    if not use_rich_ui():
        return
    console = _console()
    _write_status_bar(
        console,
        root=root,
        recorder=recorder,
        guard=guard,
        live_model=live_model,
        since_event_idx=since_event_idx,
        force_state=force_state,
    )
    _write_hint(console)
    _write_secondary(console, recorder.events, since_event_idx=since_event_idx)


def format_compaction_banner(event: dict[str, object]) -> str | None:
    kind = event.get("kind")
    if kind == "compaction":
        before = event.get("before_tokens")
        after = event.get("after_tokens")
        return f"[context] compacted tool result {before} -> {after} tokens (full payload in trace)"
    if kind == "context_compaction":
        before = event.get("before_tokens")
        after = event.get("after_tokens")
        if before and after:
            try:
                pct = 100 - (int(after) / int(before) * 100)
            except (TypeError, ZeroDivisionError):
                pct = 0
            return (
                f"[context] conversation compacted {_format_compact_number(before)} -> "
                f"{_format_compact_number(after)} ({pct:.0f}% reduced); full history in trace"
            )
    return None


def _parse_approval_choice(line: str, request: Any) -> Any:
    from .agent import ApprovalOutcome

    if not line:
        return ApprovalOutcome(decision="denied", reason="no input")
    choice = line.strip().lower().split()[0]
    if choice in {"1", "y", "yes"}:
        return ApprovalOutcome(decision="approved", reason="user yes")
    if choice == "2":
        path = request.path or ""
        normalized = path.replace("\\", "/")
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


def prompt_approval(request: Any, *, input_stream: object | None = None) -> Any:
    from .agent import BUDGET_CAP_TOOL

    if use_rich_ui():
        from rich.panel import Panel

        console = _console()
        if request.tool == BUDGET_CAP_TOOL:
            title = f"Approve budget cap: {request.path}"
            options = "1/y yes  2 yes (this cap)  3/a always  4/n no  5 abort"
        else:
            title = f"Approve {request.tool}"
            options = "1/y yes  2 yes (scoped)  3/a always  4/n no  5 abort"
        console.print(Panel(f"{request.summary}\n[dim]{options}[/dim]", title=title, border_style="cyan"))
        if PromptSession is not None:
            session = PromptSession()
            line = session.prompt("> ")
            return _parse_approval_choice(line, request)
    if request.tool == BUDGET_CAP_TOOL:
        sys.stderr.write(f"[approval] budget {request.path}  {request.summary}\n")
        sys.stderr.write("  1) yes  2) yes (this cap)  3) yes (always)  4) no  5) abort\n> ")
    else:
        sys.stderr.write(f"[approval] {request.tool}  {request.summary}\n")
        sys.stderr.write("  1) yes  2) yes (this folder)  3) yes (always)  4) no  5) abort\n> ")
    sys.stderr.flush()
    fh = input_stream if input_stream is not None else sys.stdin
    line = fh.readline().strip()
    return _parse_approval_choice(line, request)
