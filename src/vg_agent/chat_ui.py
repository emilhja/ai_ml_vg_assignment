"""Interactive TTY chat presentation for ``vg-agent --chat``."""

from __future__ import annotations

import difflib
import json
import os
import re
import sys
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

DIFF_MAX_LINES = 40
DIFF_CONTEXT_LINES = 3
_DIFF_PANEL_STYLE = "on black"
_WRITE_EDIT_TOOLS = frozenset({"edit_file", "write_file"})
WRITE_EDIT_TOOLS = _WRITE_EDIT_TOOLS

from . import config, tools
from .budget import BudgetGuard, format_usd_display
from .runtime_settings import models_missing_local_pricing
from .trace import TraceRecorder, latest_spawn_subagents_batch_summary, show_context

CHAT_PLACEHOLDER = 'Try "read data/sample.log and summarise auth/"'

_WELCOME_BORDER = "rgb(224,122,95)"
_PRODUCT_LABEL = "vg-agent"

_compact_dashboard = False
_STATUS_THROTTLE_S = float(os.environ.get("VG_CHAT_STATUS_THROTTLE_S", "0.75"))
_last_status_bar_refresh = 0.0
_rich_chat_latched = False
progress_stderr_lock = threading.RLock()

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


def latch_rich_chat_session() -> None:
    """Keep Rich approval panels for the rest of a --chat session once TTY UI started."""
    global _rich_chat_latched
    if use_rich_ui():
        _rich_chat_latched = True


def reset_rich_chat_latch() -> None:
    global _rich_chat_latched
    _rich_chat_latched = False


def use_rich_approval_ui() -> bool:
    """Rich approval chrome; latched chat sessions only require stdin TTY."""
    if os.environ.get("NO_COLOR"):
        return False
    if _rich_chat_latched:
        return bool(getattr(sys.stdin, "isatty", lambda: False)())
    return use_rich_ui()


def sanitize_summary_text(text: str, *, limit: int | None = None) -> str:
    flat = str(text).replace("\r", "").replace("\n", " ↵ ")
    if limit is not None:
        return flat[:limit]
    return flat


def format_approval_panel_summary(request: Any) -> str:
    summary = sanitize_summary_text(request.summary)
    if request.tool in {"spawn_subagent", "spawn_subagents"} and len(summary) > 500:
        return summary[:500] + "…"
    return summary


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
    reset_rich_chat_latch()


def clear_chat_screen(*, scrollback: bool = True) -> None:
    """Clear the TTY before a full dashboard refresh; no-op when disabled or non-TTY."""
    if os.environ.get("VG_CHAT_NO_CLEAR"):
        return
    if not use_rich_ui():
        return
    console = _console()
    console.clear()
    if scrollback:
        try:
            console.file.write("\033[3J")
            console.file.flush()
        except (AttributeError, OSError):
            pass


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


def _parent_tool_error_count(events: list[dict[str, object]], *, since_event_idx: int = 0) -> int:
    return sum(
        1
        for event in events[since_event_idx:]
        if event.get("kind") == "tool_result"
        and event.get("status") != "ok"
        and event.get("agent_id") == "parent"
    )


def _subagent_failure_count(events: list[dict[str, object]], *, since_event_idx: int = 0) -> int:
    return sum(
        1
        for event in events[since_event_idx:]
        if event.get("kind") == "subagent_return" and event.get("status") != "ok"
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
    turn_parent_errors = _parent_tool_error_count(events, since_event_idx=since_event_idx)
    subagent_failures = _subagent_failure_count(events, since_event_idx=since_event_idx)
    if (
        turn_parent_errors > 0
        or subagent_failures > 0
        or "tool_error" in lowered
        or "model_error" in lowered
        or "aborted" in lowered
        or "error" in lowered
    ):
        if status in {"ok", "done"} and subagent_failures > 0 and turn_parent_errors == 0:
            return "\u2717", "partial", "red"
        label = status if status != "ready" else "error"
        return "\u2717", label, "red"
    if any(marker in lowered for marker in ("warn", "cap", "budget")):
        return "\u26a0", "warn", "yellow"
    if status in {"ready", "ok", "done"}:
        display = "ready" if status == "ready" else status
        return "\u2713", display, "green"
    return "\u2713", status, "green"


def file_preview_lines() -> int:
    try:
        return max(1, int(os.environ.get("VG_CHAT_FILE_PREVIEW_LINES", "30")))
    except ValueError:
        return 30


def format_literal_tool_body(
    content: str,
    *,
    tool: str,
    path: str = "",
    compaction_event: dict[str, object] | None = None,
    event_idx: int | None = None,
    trace_path: Path | str | None = None,
) -> str:
    """Compaction banner, tail preview for large reads, or passthrough."""
    if compaction_event is not None:
        banner = format_compaction_banner(compaction_event)
        if banner:
            return banner
        from .trace import compacted_marker

        return compacted_marker(compaction_event)
    if tool not in {"read_file", "read_file_range"}:
        return content
    lines = content.splitlines()
    max_lines = file_preview_lines()
    if len(lines) <= max_lines:
        return content
    tail = lines[-max_lines:]
    skipped = len(lines) - max_lines
    header_parts: list[str] = []
    if path:
        header_parts.append(path)
    header_parts.append(f"{len(lines)} lines, {len(content.encode('utf-8'))} bytes")
    if event_idx is not None:
        header_parts.append(f"event {event_idx}")
    if trace_path:
        header_parts.append(f"trace: {trace_path}")
    header = " — ".join(header_parts)
    start_line = len(lines) - max_lines + 1
    hint = f"read_file_range {path} {start_line} {len(lines)}" if path else ""
    footer = f"… {skipped} earlier lines (full payload in trace)"
    if hint:
        footer += f" · {hint}"
    return f"{header}\n" + "\n".join(tail) + f"\n{footer}"


def _latest_turn_parallel_hint(events: list[dict[str, object]]) -> str | None:
    prompt_positions = [
        index for index, event in enumerate(events) if event.get("kind") == "user_prompt"
    ]
    if not prompt_positions:
        return None
    start = prompt_positions[-1]
    summary = latest_spawn_subagents_batch_summary(events, since_event_idx=start)
    if summary is None or not summary.overlap:
        return None
    explorer_count = sum(1 for item in summary.returns if item.agent_type == "explorer")
    count = explorer_count if explorer_count >= 2 else len(summary.returns)
    label = "parallel explorers" if explorer_count == len(summary.returns) else "parallel sub-agents"
    return f"last turn: {count} {label} (overlap confirmed)"


def _secondary_notice(events: list[dict[str, object]], *, since_event_idx: int) -> str | None:
    status = _latest_run_state(events, since_event_idx=since_event_idx)
    turn_errors = _tool_error_count(events[since_event_idx:])
    if status in {"ready", "ok"} and turn_errors == 0:
        parallel_hint = _latest_turn_parallel_hint(events)
        return parallel_hint
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
    usd_projected: float | None = None
    usd_would_exceed: bool = False
    usd_warn: bool = False
    model_priced: bool = True

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
    ctx_window = config.CONTEXT_WINDOW_TOKENS.get(model_id)
    ctx_pct = (ctx_tokens / ctx_window * 100) if ctx_window else None
    icon, status_label, status_style = _status_token(
        recorder.events, since_event_idx=since_event_idx, force_state=force_state
    )
    workspace_name = root.resolve().name or str(root)
    approval_events = sum(1 for event in recorder.events if event.get("kind") == "approval")
    session_tool_errors = _tool_error_count(recorder.events)
    turn_tool_errors = _tool_error_count(recorder.events[since_event_idx:])
    model_priced = model_id in config.PRICING_USD_PER_MTOK
    if model_priced:
        usd_projected = _estimate_next_step_usd(guard, model_id=model_id, ctx_tokens=ctx_tokens)
        usd_would_exceed, usd_warn = _usd_budget_flags(
            guard.running_usd, guard.max_usd, projected_usd=usd_projected
        )
    else:
        usd_projected = None
        usd_would_exceed = False
        _, usd_warn = _usd_budget_flags(
            guard.running_usd, guard.max_usd, projected_usd=None
        )
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
        usd_projected=usd_projected,
        usd_would_exceed=usd_would_exceed,
        usd_warn=usd_warn,
        model_priced=model_priced,
    )


def _format_usd(value: float) -> str:
    """Format a USD amount; delegates to :func:`format_usd_display` in ``budget``."""
    return format_usd_display(value)


def _budget_warn_prefix() -> str:
    if use_emoji():
        return "\u26a0\ufe0f "
    return "! "


def _estimate_next_step_usd(
    guard: BudgetGuard,
    *,
    model_id: str,
    ctx_tokens: int,
    worst_output_tokens: int = 4096,
) -> float:
    worst_in = max(ctx_tokens, 512)
    return guard.running_usd + guard.estimate_cost(model_id, worst_in, worst_output_tokens)


def _usd_budget_flags(
    running_usd: float,
    max_usd: float,
    *,
    projected_usd: float | None,
) -> tuple[bool, bool]:
    """Return (would_exceed_on_next_step, in_warn_band)."""
    if max_usd <= 0:
        return False, False
    would_exceed = projected_usd is not None and projected_usd > max_usd + 1e-12
    at_cap = running_usd >= max_usd
    warn_band = running_usd >= config.WARN_USD_FRACTION * max_usd
    return would_exceed or at_cap, warn_band and not would_exceed and not at_cap


def _budget_rich_style(running_usd: float, max_usd: float, *, projected_usd: float | None) -> str:
    """Rich style for the USD segment: red when over/near cap, yellow at warn threshold."""
    would_exceed, warn_only = _usd_budget_flags(running_usd, max_usd, projected_usd=projected_usd)
    if would_exceed:
        return "bold red"
    if warn_only:
        return "yellow"
    return ""


def format_budget_cap_approval_text(reason: str, details: dict[str, Any]) -> str:
    """Plain-text body for budget-cap approval (Rich and non-TTY)."""
    if reason in {"step_extend", "step_cap"}:
        steps = int(details.get("step_count") or details.get("steps") or 0)
        max_steps = int(details.get("max_steps") or 0)
        bump_once = steps + 1
        bump_scoped = max_steps + max(5, max_steps // 4) if max_steps else bump_once
        if reason == "step_extend":
            headline = f"Approaching step limit ({steps}/{max_steps}) — extend budget?"
        else:
            headline = f"Step cap reached ({steps}/{max_steps}) — extend to continue?"
        return (
            f"{headline}\n"
            f"  Parent steps used:   {steps}/{max_steps}\n"
            f"  1/y yes adds:        1 step (→ {bump_once} max)\n"
            f"  2 this cap adds:     {bump_scoped - max_steps} steps (→ {bump_scoped} max)\n"
            f"Approve to raise the step cap for this run, or n/abort to stop."
        )
    if reason == "token_cap":
        tokens = int(details.get("tokens") or details.get("running_tokens") or 0)
        max_tokens = int(details.get("max_tokens") or 0)
        bump = max(10_000, max_tokens // 4) if max_tokens > 0 else 0
        # Choices:
        # - `1/y yes` is a one-time bump: new max = running_tokens + bump
        # - `2/3` is "this cap"/"always": new max = max_tokens + bump
        new_max_once = tokens + bump
        new_max_scoped = max_tokens + bump
        return (
            f"Token cap reached ({tokens:,}/{max_tokens:,}).\n"
            f"  Bump:                ~{bump:,} tokens\n"
            f"  1/y (one-time) max: ~{new_max_once:,}\n"
            f"  2/3 (this cap) max: ~{new_max_scoped:,}\n"
            f"Approve to raise the token cap (1/y for one-time, 2 to cache for this cap type), or n/abort to stop."
        )
    if reason == "usd_cap":
        cap = float(details.get("max_usd") or 0.0)
        spent = float(details.get("running_usd") or 0.0)
        step_est = float(details.get("worst_next_usd") or 0.0)
        projected = spent + step_est
        prefix = _budget_warn_prefix().strip()
        headline = f"{prefix} Next step would exceed your USD cap" if prefix else "Next step would exceed your USD cap"
        return (
            f"{headline}\n"
            f"  Cap (--max-usd):     {_format_usd(cap)}\n"
            f"  Spent so far:        {_format_usd(spent)}\n"
            f"  This step (est.):    ~{_format_usd(step_est)}\n"
            f"  Total after step:    ~{_format_usd(projected)}  (> cap)\n"
            f"Approve to raise the cap for this run, or n/abort to stop."
        )
    if reason == "daily_cap":
        remaining = details.get("daily_remaining_usd")
        return (
            f"Daily USD cap would be exceeded (remaining {_format_usd(float(remaining or 0))}).\n"
            f"Approve to raise the daily allowance for this run, or n/abort to stop."
        )
    return f"Budget cap ({reason}). Approve to continue, or n/abort to stop."


def _steps_status_segment(status: SessionStatus, *, chart: str = "") -> str:
    prefix = "!" if status.max_steps > 0 and status.steps == status.max_steps - 1 else ""
    label = f"{chart} {status.steps}/{status.max_steps} steps".strip()
    return f"{prefix}{label}".strip() if prefix else label


def _usd_status_segment(
    status: SessionStatus,
    *,
    coin: str = "",
) -> str:
    prefix = _budget_warn_prefix() if (status.usd_would_exceed or status.usd_warn) else ""
    run = _format_usd(status.running_usd)
    cap = _format_usd(status.max_usd)
    segment = f"{prefix}{coin} {run}/{cap}".strip() if coin else f"{prefix}{run}/{cap}".strip()
    if status.usd_would_exceed and status.usd_projected is not None:
        segment += f" (next ~{_format_usd(status.usd_projected)})"
    elif not status.model_priced:
        segment += " (unpriced model)"
    return segment


def format_statusline_compact(status: SessionStatus, *, width: int | None = None) -> str:
    err_segment = (
        f"tool errs {status.tool_errors_turn} turn / {status.tool_errors_session} session"
        if status.tool_errors_turn != status.tool_errors_session
        else f"tool errs {status.tool_errors_session}"
    )
    usd_prefix = "!" if status.usd_would_exceed or status.usd_warn else ""
    usd_part = f"{usd_prefix}usd {_format_usd(status.running_usd)}/{_format_usd(status.max_usd)}"
    if status.usd_would_exceed and status.usd_projected is not None:
        usd_part += f" (next ~{_format_usd(status.usd_projected)})"
    elif not status.model_priced:
        usd_part += " (unpriced model)"
    line = (
        f"[{status.mode}] {status.model} | {status.ctx_display()} | "
        f"session {status.token_bar} {_format_compact_number(status.running_tokens)}/"
        f"{_format_compact_number(status.max_tokens)} tok | "
        f"{_steps_status_segment(status)} | "
        f"{usd_part} | "
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
        f"{_usd_status_segment(status, coin=coin)} | "
        f"{_steps_status_segment(status, chart=chart)} | "
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
    usd_plain = _usd_status_segment(status, coin=coin)
    budget_style = _budget_rich_style(
        status.running_usd, status.max_usd, projected_usd=status.usd_projected
    )
    usd_part = f"[{budget_style}]{usd_plain}[/{budget_style}]" if budget_style else usd_plain
    line = (
        f"{folder} {status.workspace_name} | {robot} {status.model} | {status.mode} | "
        f"{status.ctx_display()} | "
        f"{usd_part} | "
        f"{_steps_status_segment(status, chart=chart)} | {status_part}"
    )
    console.print(line)


def _write_hint(console: Any) -> None:
    console.print("[dim]/help for commands \u00b7 /status to refresh dashboard and print session summary[/dim]")


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
    latch_rich_chat_session()
    use_compact = _compact_dashboard if compact is None else compact
    console = _console()
    console.print(f"[dim]{_PRODUCT_LABEL}[/dim]")
    if not use_compact:
        from rich.panel import Panel
        from rich.text import Text

        welcome = Text()
        welcome.append("* ", style=f"bold {_WELCOME_BORDER}")
        welcome.append("Welcome to CodeSaver!", style="bold white")
        welcome.append("\n")
        welcome.append(f"cwd: {short_cwd(root)}", style="dim")
        missing = models_missing_local_pricing()
        if missing:
            short = [m.removeprefix("openrouter/") for m in missing]
            welcome.append("\n")
            welcome.append(
                f"Unpriced model(s) configured — see docs/PRICE.md: {', '.join(short)}",
                style="dim",
            )
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


def print_chat_dashboard_cleared(
    *,
    root: Path,
    recorder: TraceRecorder,
    guard: BudgetGuard,
    live_model: bool,
    since_event_idx: int = 0,
    compact: bool | None = None,
    show_trace_path: bool = False,
) -> None:
    """Clear the TTY, then print the session dashboard."""
    clear_chat_screen()
    print_chat_dashboard(
        root=root,
        recorder=recorder,
        guard=guard,
        live_model=live_model,
        since_event_idx=since_event_idx,
        compact=compact,
    )
    if show_trace_path and use_rich_ui():
        _console().print(f"[dim]trace: traces/{recorder.run_id}.jsonl[/dim]")


def format_response_bullets(text: str) -> str:
    """Prefix each line with a bullet when the response has multiple non-empty lines."""
    lines = [line for line in text.splitlines() if line.strip()]
    if len(lines) <= 1:
        return text
    out: list[str] = []
    for raw in text.splitlines():
        stripped = raw.strip()
        if not stripped:
            out.append("")
            continue
        if stripped.startswith(("- ", "* ", "• ")) or re.match(r"^\d+\.\s", stripped):
            out.append(raw)
            continue
        out.append(f"• {stripped}")
    return "\n".join(out)


def render_input_top_rule() -> None:
    if not use_rich_ui():
        return
    from rich.rule import Rule

    console = _console()
    console.print()
    console.print()
    console.print(Rule("input", style="dim"))


def render_input_bottom_and_footer(
    *,
    root: Path,
    recorder: TraceRecorder,
    guard: BudgetGuard,
    live_model: bool,
    since_event_idx: int = 0,
    show_status: bool = True,
) -> None:
    if not use_rich_ui():
        return
    from rich.rule import Rule

    console = _console()
    console.print(Rule(style="dim"))
    if show_status:
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


@dataclass(frozen=True)
class FileChange:
    path: str
    tool: str
    old: str
    new: str


def format_unified_diff(
    old: str,
    new: str,
    *,
    path: str,
    context: int = DIFF_CONTEXT_LINES,
    max_lines: int = DIFF_MAX_LINES,
) -> tuple[list[str], bool]:
    """Return unified diff lines and whether output was truncated."""
    fromfile = f"a/{path}" if path else "a/file"
    tofile = f"b/{path}" if path else "b/file"
    lines = list(
        difflib.unified_diff(
            old.splitlines(),
            new.splitlines(),
            fromfile=fromfile,
            tofile=tofile,
            lineterm="",
            n=context,
        )
    )
    if not lines and old != new:
        lines = [f"--- {fromfile}", f"+++ {tofile}", "@@", f"-{old}", f"+{new}"]
    truncated = len(lines) > max_lines
    if truncated:
        extra = len(lines) - max_lines
        lines = lines[:max_lines]
        lines.append(f"... {extra} more lines (full edit in trace)")
    return lines, truncated


def _diff_lines_plain(lines: list[str]) -> str:
    return "\n".join(lines)


def _diff_syntax(lines: list[str]) -> Any:
    """Black-background diff block matching read_file ``Syntax`` tool output."""
    from rich.syntax import Syntax

    return Syntax(
        "\n".join(lines),
        "diff",
        word_wrap=True,
        background_color="black",
    )


def _print_diff_panel(console: Any, lines: list[str], title: str, *, border_style: str = "dim") -> None:
    if not lines:
        return
    from rich.panel import Panel

    if os.environ.get("NO_COLOR"):
        body: Any = _diff_lines_plain(lines)
    else:
        body = _diff_syntax(lines)
    console.print(Panel(body, title=title, border_style=border_style, style=_DIFF_PANEL_STYLE))


def render_diff_to_console(
    console: Any,
    *,
    path: str,
    old: str,
    new: str,
    title: str,
    border_style: str = "dim",
) -> None:
    lines, _ = format_unified_diff(old, new, path=path)
    if not lines:
        return
    _print_diff_panel(console, lines, title, border_style=border_style)


def read_prior_workspace_file(workspace_root: Path, rel_path: str) -> str:
    try:
        return tools.resolve_workspace_path(workspace_root, rel_path).read_text(encoding="utf-8")
    except (OSError, ValueError):
        return ""


def old_new_for_write_request(workspace_root: Path, args: dict[str, Any]) -> tuple[str, str]:
    path = str(args.get("path") or args.get("rel_path") or "")
    new = str(args.get("content") or "")
    old = read_prior_workspace_file(workspace_root, path) if path else ""
    return old, new


def old_new_for_edit_request(args: dict[str, Any]) -> tuple[str, str]:
    return str(args.get("old") or ""), str(args.get("new") or "")


def _path_from_call(call: dict[str, object]) -> str:
    args = call.get("args")
    if not isinstance(args, dict):
        return str(call.get("path") or "")
    return str(args.get("path") or args.get("rel_path") or call.get("path") or "")


def _old_new_from_pending(call: dict[str, object], prior_content: str | None = None) -> tuple[str, str]:
    tool = str(call.get("tool") or "")
    args = call.get("args")
    if not isinstance(args, dict):
        return "", ""
    if tool == "edit_file":
        return old_new_for_edit_request(args)
    if tool == "write_file":
        new = str(args.get("content") or "")
        old = prior_content if prior_content is not None else ""
        return old, new
    return "", ""


def collect_file_changes(
    events: list[dict[str, object]],
    start_idx: int,
    *,
    workspace_root: Path,
    pending_priors: dict[str, str] | None = None,
) -> list[FileChange]:
    """Collect successful write/edit changes in event order; last per path wins."""
    calls: dict[str, dict[str, object]] = {}
    for event in events[start_idx:]:
        if event.get("kind") == "tool_call":
            tool_use_id = str(event.get("tool_use_id") or "")
            if tool_use_id:
                calls[tool_use_id] = event

    by_path: dict[str, FileChange] = {}
    priors = pending_priors or {}
    for event in events[start_idx:]:
        if event.get("kind") != "tool_result":
            continue
        tool = str(event.get("tool") or "")
        if tool not in WRITE_EDIT_TOOLS or event.get("status") != "ok":
            continue
        tool_use_id = str(event.get("tool_use_id") or "")
        call = calls.get(tool_use_id, {})
        path = _path_from_call(call)
        if not path:
            continue
        prior = priors.get(tool_use_id)
        old, new = _old_new_from_pending(call, prior)
        if tool == "write_file" and prior is None and not old:
            old = read_prior_workspace_file(workspace_root, path)
        by_path[path] = FileChange(path=path, tool=tool, old=old, new=new)
    return list(by_path.values())


def _render_changes_to_console(console: Any, changes: list[FileChange]) -> None:
    for change in changes:
        lines, _ = format_unified_diff(change.old, change.new, path=change.path)
        _print_diff_panel(console, lines, change.path)


def print_turn_changes(
    events: list[dict[str, object]],
    start_idx: int,
    workspace_root: Path,
    *,
    pending_priors: dict[str, str] | None = None,
) -> bool:
    changes = collect_file_changes(
        events, start_idx, workspace_root=workspace_root, pending_priors=pending_priors
    )
    if not changes:
        return False
    if use_rich_ui():
        from rich.console import Console

        console = Console(file=sys.stdout, highlight=False)
        _render_changes_to_console(console, changes)
    else:
        parts: list[str] = ["Changes:"]
        for change in changes:
            lines, _ = format_unified_diff(change.old, change.new, path=change.path)
            parts.append(f"--- {change.path} ---")
            parts.extend(lines)
        sys.stdout.write("\n".join(parts) + "\n")
    sys.stdout.flush()
    return True


def capture_write_prior(workspace_root: Path, call_event: dict[str, object]) -> str | None:
    if str(call_event.get("tool") or "") != "write_file":
        return None
    path = _path_from_call(call_event)
    if not path:
        return None
    try:
        resolved = tools.resolve_workspace_path(workspace_root, path)
        if resolved.is_file():
            return resolved.read_text(encoding="utf-8")
    except (OSError, ValueError):
        pass
    return ""


def progress_diff_lines(call_event: dict[str, object], prior_content: str | None = None) -> list[str]:
    path = _path_from_call(call_event)
    if str(call_event.get("tool") or "") not in WRITE_EDIT_TOOLS or not path:
        return []
    old, new = _old_new_from_pending(call_event, prior_content)
    lines, _ = format_unified_diff(old, new, path=path)
    return lines


def write_progress_diff_lines(
    fh: Any,
    call_event: dict[str, object],
    prior_content: str | None,
    *,
    use_color: bool = True,
) -> str | None:
    """Write unified-diff hunks inline on the progress stream (returns path if written)."""
    path = _path_from_call(call_event)
    lines = progress_diff_lines(call_event, prior_content)
    if not lines:
        return None
    reset = "\x1b[0m" if use_color else ""
    for raw in lines:
        line = f"  {raw}"
        if not use_color:
            fh.write(line + "\n")
            continue
        if raw.startswith("+") and not raw.startswith("+++"):
            fh.write(f"\x1b[32m{line}{reset}\n")
        elif raw.startswith("-") and not raw.startswith("---"):
            fh.write(f"\x1b[31m{line}{reset}\n")
        elif raw.startswith(("---", "+++", "@@")):
            fh.write(f"\x1b[90m{line}{reset}\n")
        else:
            fh.write(line + "\n")
    fh.flush()
    return path or None


def render_progress_file_diff(
    console: Any,
    *,
    call_event: dict[str, object],
    prior_content: str | None,
) -> None:
    path = _path_from_call(call_event)
    tool = str(call_event.get("tool") or "")
    if tool not in WRITE_EDIT_TOOLS or not path:
        return
    old, new = _old_new_from_pending(call_event, prior_content)
    render_diff_to_console(console, path=path, old=old, new=new, title=f"{tool} {path}")


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


def print_turn_output(
    *,
    answer: str,
    literal_outputs: list[str],
    events: list[dict[str, object]] | None = None,
    start_idx: int = 0,
    workspace_root: Path | None = None,
    pending_priors: dict[str, str] | None = None,
    skip_change_paths: set[str] | frozenset[str] | None = None,
) -> bool:
    """Print agent answer + literal tool outputs + optional Changes diffs. Returns True if anything printed."""
    answer_text = answer.strip()
    filtered_outputs: list[str] = []
    for output in literal_outputs:
        if not output:
            continue
        body = output.split(":", 1)[-1].strip() if output.startswith(("Tool output", "Blocked", "Tool error")) else output
        if answer_text and _lines_already_in_answer(answer_text, body):
            continue
        filtered_outputs.append(output)
    changes: list[FileChange] = []
    if events is not None and workspace_root is not None:
        changes = collect_file_changes(
            events, start_idx, workspace_root=workspace_root, pending_priors=pending_priors
        )
        if skip_change_paths:
            changes = [change for change in changes if change.path not in skip_change_paths]
    if not answer_text and not filtered_outputs and not changes:
        return False
    if use_rich_ui():
        from rich.console import Console
        from rich.panel import Panel
        from rich.syntax import Syntax

        console = Console(file=sys.stdout, highlight=False)
        if answer_text:
            console.print(format_response_bullets(answer_text))
        for output in filtered_outputs:
            if "\n" in output:
                title, _, body = output.partition(":\n")
                tree = _render_directory_tree(body)
                if tree is not None:
                    console.print(Panel(tree, title=title or "Tool output", border_style="dim"))
                elif len(body) > 80 and "\n" in body:
                    console.print(Panel(Syntax(body, "text", word_wrap=True), title=title or "Tool output", border_style="dim"))
                else:
                    console.print(f"{title or 'Tool output'}:\n{body}")
            else:
                console.print(output)
        if changes:
            console.print("[dim]Changes:[/dim]")
            for change in changes:
                lines, _ = format_unified_diff(change.old, change.new, path=change.path)
                if lines:
                    console.print(f"[dim]--- {change.path} ---[/dim]")
                    for raw in lines:
                        if raw.startswith("+") and not raw.startswith("+++"):
                            console.print(f"[green]{raw}[/green]")
                        elif raw.startswith("-") and not raw.startswith("---"):
                            console.print(f"[red]{raw}[/red]")
                        else:
                            console.print(f"[dim]{raw}[/dim]")
    else:
        parts: list[str] = []
        if answer_text:
            parts.append(format_response_bullets(answer_text))
        parts.extend(filtered_outputs)
        if changes:
            parts.append("Changes:")
            for change in changes:
                lines, _ = format_unified_diff(change.old, change.new, path=change.path)
                parts.append(f"--- {change.path} ---")
                parts.extend(lines)
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
    force: bool = False,
) -> None:
    global _last_status_bar_refresh
    if not use_rich_ui():
        return
    if not force and force_state == "running":
        now = time.monotonic()
        if now - _last_status_bar_refresh < _STATUS_THROTTLE_S:
            return
        _last_status_bar_refresh = now
    elif force_state != "running":
        _last_status_bar_refresh = 0.0
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
    if force_state == "running" and not force:
        return
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
        # `budget_cap` requests use `request.path` to carry the cap reason
        # (e.g. "step_cap", "token_cap"), not a filesystem path. Cache the
        # user's choice per cap reason so we don't re-prompt for the same
        # cap type repeatedly.
        if request.tool == "budget_cap":
            scope = str(path)
            return ApprovalOutcome(decision="approved_scoped", scope_key=scope, reason="user yes-folder")

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


def _read_approval_line(input_stream: object | None) -> str:
    fh = input_stream if input_stream is not None else sys.stdin
    if hasattr(fh, "readline"):
        line = fh.readline()
        return line.strip() if line else ""
    return input("> ").strip()


def _write_plain_approval_prompt(request: Any) -> None:
    from .agent import BUDGET_CAP_TOOL

    summary = format_approval_panel_summary(request)
    if request.tool == BUDGET_CAP_TOOL and isinstance(request.args, dict):
        sys.stderr.write(format_budget_cap_approval_text(str(request.path or "budget"), request.args) + "\n")
        sys.stderr.write("  1) yes  2) yes (this cap)  3) yes (always)  4) no  5) abort\n> ")
    elif request.tool == BUDGET_CAP_TOOL:
        sys.stderr.write(f"[approval] budget {request.path}  {summary}\n")
        sys.stderr.write("  1) yes  2) yes (this cap)  3) yes (always)  4) no  5) abort\n> ")
    else:
        sys.stderr.write(f"[approval] {request.tool}  {summary}\n")
        sys.stderr.write("  1) yes  2) yes (scoped)  3) yes (always)  4) no  5) abort\n> ")
    sys.stderr.flush()


def prompt_approval(
    request: Any,
    *,
    input_stream: object | None = None,
    workspace_root: Path | None = None,
) -> Any:
    from .agent import BUDGET_CAP_TOOL

    if use_rich_approval_ui():
        from rich.console import Group
        from rich.panel import Panel
        from rich.text import Text

        with progress_stderr_lock:
            console = _console()
            console.print()
            if request.tool == BUDGET_CAP_TOOL:
                warn = _budget_warn_prefix().strip()
                title = (
                    f"{warn} Budget cap — {request.path} (approval required)"
                    if warn
                    else f"Budget cap — {request.path} (approval required)"
                )
                options = "1/y yes  2 yes (this cap)  3/a always  4/n no  5 abort"
                border_style = "red"
            else:
                title = f"Approve {request.tool}"
                options = "1/y yes  2 yes (scoped)  3/a always  4/n no  5 abort"
                border_style = "cyan"
            panel_summary = format_approval_panel_summary(request)
            panel_body: Any
            if request.tool == BUDGET_CAP_TOOL and isinstance(request.args, dict):
                body_text = format_budget_cap_approval_text(str(request.path or "budget"), request.args)
                headline, _, remainder = body_text.partition("\n")
                panel_body = Group(
                    Text(headline + "\n", style="bold red"),
                    Text(remainder, style="white"),
                    Text(options, style="dim"),
                )
            elif request.tool in WRITE_EDIT_TOOLS and isinstance(request.args, dict) and workspace_root is not None:
                if request.tool == "edit_file":
                    old, new = old_new_for_edit_request(request.args)
                else:
                    old, new = old_new_for_write_request(workspace_root, request.args)
                path = str(request.path or request.args.get("path") or "")
                lines, _ = format_unified_diff(old, new, path=path)
                if lines and not os.environ.get("NO_COLOR"):
                    panel_body = Group(
                        Text(panel_summary),
                        Panel(_diff_syntax(lines), border_style="dim", style=_DIFF_PANEL_STYLE),
                        Text(options, style="dim"),
                    )
                elif lines:
                    panel_body = Group(
                        Text(panel_summary),
                        Text(_diff_lines_plain(lines)),
                        Text(options, style="dim"),
                    )
                else:
                    panel_body = Group(Text(panel_summary), Text(options, style="dim"))
            else:
                panel_body = Group(Text(panel_summary), Text(options, style="dim"))
            console.print(Panel(panel_body, title=title, border_style=border_style))
            sys.stderr.write("> ")
            sys.stderr.flush()
            line = _read_approval_line(input_stream)
            return _parse_approval_choice(line, request)

    with progress_stderr_lock:
        _write_plain_approval_prompt(request)
        line = _read_approval_line(input_stream)
        return _parse_approval_choice(line, request)
