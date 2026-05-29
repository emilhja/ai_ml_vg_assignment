"""Interactive TTY chat presentation for ``vg-agent --chat``."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

from . import config
from .budget import BudgetGuard
from .trace import TraceRecorder

CHAT_PLACEHOLDER = 'Try "read data/sample.log and summarise auth/"'

_WELCOME_BORDER = "rgb(224,122,95)"
_PRODUCT_LABEL = "vg-agent"


def use_rich_ui() -> bool:
    if os.environ.get("NO_COLOR"):
        return False
    stdin_tty = bool(getattr(sys.stdin, "isatty", lambda: False)())
    stderr_tty = bool(getattr(sys.stderr, "isatty", lambda: False)())
    return stdin_tty and stderr_tty


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


def _status_token(events: list[dict[str, object]], *, since_event_idx: int) -> tuple[str, str, str]:
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


def build_status_bar_text(
    *,
    root: Path,
    recorder: TraceRecorder,
    guard: BudgetGuard,
    live_model: bool,
    since_event_idx: int = 0,
) -> str:
    mode = "live" if live_model else "deterministic"
    latest_llm = _latest_parent_llm_start(recorder.events)
    model = _short_model((latest_llm or {}).get("model") or config.PARENT_MODEL_ID)
    context_tokens = int((latest_llm or {}).get("tokens_in") or 0)
    icon, status_label, _style = _status_token(recorder.events, since_event_idx=since_event_idx)
    workspace_name = root.resolve().name or str(root)
    segments = [
        f"\U0001f4c1 {workspace_name}",
        f"\U0001f916 {model}",
        mode,
        f"ctx {_format_compact_number(context_tokens)} in",
        f"\U0001f4b5 ${guard.running_usd:.4f}/${guard.max_usd:.2f}",
        f"\U0001f4ca {guard.step_count}/{guard.max_steps} steps",
        f"{icon} {status_label}",
    ]
    return " | ".join(segments)


def _write_status_bar(
    console: Any,
    *,
    root: Path,
    recorder: TraceRecorder,
    guard: BudgetGuard,
    live_model: bool,
    since_event_idx: int,
) -> None:
    mode = "live" if live_model else "deterministic"
    latest_llm = _latest_parent_llm_start(recorder.events)
    model = _short_model((latest_llm or {}).get("model") or config.PARENT_MODEL_ID)
    context_tokens = int((latest_llm or {}).get("tokens_in") or 0)
    icon, status_label, status_style = _status_token(recorder.events, since_event_idx=since_event_idx)
    workspace_name = root.resolve().name or str(root)
    status_part = f"[{status_style}]{icon} {status_label}[/{status_style}]"
    line = (
        f"\U0001f4c1 {workspace_name} | \U0001f916 {model} | {mode} | "
        f"ctx {_format_compact_number(context_tokens)} in | "
        f"\U0001f4b5 ${guard.running_usd:.4f}/${guard.max_usd:.2f} | "
        f"\U0001f4ca {guard.step_count}/{guard.max_steps} steps | {status_part}"
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
) -> None:
    if not use_rich_ui():
        return
    console = _console()
    console.print(f"[dim]{_PRODUCT_LABEL}[/dim]")
    from rich.panel import Panel
    from rich.text import Text

    welcome = Text()
    welcome.append("* ", style=f"bold {_WELCOME_BORDER}")
    welcome.append("Welcome to VG Agent!", style="bold white")
    welcome.append("\n")
    welcome.append("/help for commands \u00b7 /status for your current setup", style="italic dim")
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


def refresh_chat_status_bar(
    *,
    root: Path,
    recorder: TraceRecorder,
    guard: BudgetGuard,
    live_model: bool,
    since_event_idx: int = 0,
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
    )
    _write_hint(console)
    _write_secondary(console, recorder.events, since_event_idx=since_event_idx)
