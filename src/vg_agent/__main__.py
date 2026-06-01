"""Generated CLI."""

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
    prompt_approval,
    refresh_chat_status_bar,
    render_input_bottom_and_footer,
    render_input_top_rule,
    render_progress_file_diff,
    reset_dashboard_mode,
    use_rich_ui,
    _console,
)
from .agent import (
    BUDGET_CAP_TOOL,
    ApprovalOutcome,
    ApprovalPolicy,
    ApprovalRequest,
    compact_conversation,
    run_live_task,
)
from .live_model_client import LiveModelClient, MissingOpenRouterKey
from .budget import BudgetGuard, format_usd_display
from .demo_fixture import write_fixture
from .workspace_paths import resolve_workspace_root
from .trace import (
    TraceRecorder,
    format_parallel_progress_lines,
    format_show_context_overview,
    format_turn_review,
    parallel_finops_batch_lines,
    parallel_subagent_summary,
    render_tree,
    show_context,
)


def _stdin_prompt(stream: object | None = None, *, workspace_root: Path | None = None) -> "callable":
    fh = stream if stream is not None else sys.stdin

    def ask(request: ApprovalRequest) -> ApprovalOutcome:
        if use_rich_ui():
            return prompt_approval(request, input_stream=fh, workspace_root=workspace_root)
        if request.tool == BUDGET_CAP_TOOL and isinstance(request.args, dict):
            sys.stderr.write(format_budget_cap_approval_text(request.path, request.args) + "\n")
        elif request.tool == BUDGET_CAP_TOOL:
            sys.stderr.write(f"[approval] budget {request.path}  {request.summary}\n")
        else:
            sys.stderr.write(f"[approval] {request.tool}  {request.summary}\n")
        if request.tool == BUDGET_CAP_TOOL:
            sys.stderr.write("  1) yes  2) yes (this cap)  3) yes (always)  4) no  5) abort\n> ")
        else:
            sys.stderr.write("  1) yes  2) yes (this folder)  3) yes (always)  4) no  5) abort\n> ")
        sys.stderr.flush()
        line = fh.readline().strip()
        if not line:
            return ApprovalOutcome(decision="denied", reason="no input")
        choice = line.split()[0]
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
        f"steps {guard.step_count}/{guard.max_steps}  "
        f"tokens {guard.running_tokens}/{guard.max_tokens}  "
        f"usd {format_usd_number(guard.running_usd)}/{format_usd_number(guard.max_usd)}  "
        f"daily_remaining {format_usd_number(guard.daily_remaining_usd)}\n"
    )


def _print_budget_set_hint() -> None:
    sys.stdout.write(
        "Set caps: /budget steps N   /budget tokens N   /budget usd N   /budget daily N\n"
        "  (combine: /budget steps 50 tokens 100000 usd 2 daily 4)\n"
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
        sys.stdout.write(err + "\n")
        return
    if not caps:
        _print_budget(guard)
        _print_budget_set_hint()
        return
    msg = guard.configure_caps(**caps)  # type: ignore[arg-type]
    if msg:
        sys.stdout.write(msg + "\n")
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
    line = _format_chat_statusline(
        recorder,
        guard,
        live_model=bool(args.live_model),
        since_event_idx=since_event_idx,
    )
    sys.stdout.write(line + "\n")
    _print_budget(guard)
    sys.stdout.write(f"trace: {recorder.path}\n")
    final_status = _latest_run_end_status(recorder.events)
    if final_status:
        sys.stdout.write(f"last_run: {final_status}\n")


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
    return "\n".join(lines)


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
    sys.stdout.write("FinOps - per-agent-type spend this session\n")
    sys.stdout.write("prompts=model calls, tools=tool calls\n")
    sys.stdout.write(f"{'agent_type':<12} {'in_tok':>10} {'out_tok':>10} {'total_tok':>10} {'prompts':>8} {'tools':>7} {'usd':>12}\n")
    for agent_type in rows:
        input_tokens = guard.per_agent_type_input_tokens.get(agent_type, 0)
        output_tokens = guard.per_agent_type_output_tokens.get(agent_type, 0)
        tokens = guard.per_agent_type_tokens.get(agent_type, 0)
        model_calls = guard.per_agent_type_model_calls.get(agent_type, 0)
        tools = tool_counts.get(agent_type, 0)
        usd = guard.per_agent_type_usd.get(agent_type, 0.0)
        sys.stdout.write(f"{agent_type:<12} {input_tokens:>10} {output_tokens:>10} {tokens:>10} {model_calls:>8} {tools:>7} {usd:>12.6f}\n")
    sys.stdout.write(
        f"{'TOTAL':<12} {guard.running_input_tokens:>10} {guard.running_output_tokens:>10} "
        f"{guard.running_tokens:>10} {guard.step_count:>8} {sum(tool_counts.values()):>7} {guard.running_usd:>12.6f}\n"
    )
    if recorder is not None:
        user_prompts = sum(1 for event in recorder.events if event.get("kind") == "user_prompt")
        sys.stdout.write(f"user_prompts {user_prompts}\n")
        parallel_lines = parallel_finops_batch_lines(recorder.events)
        if parallel_lines:
            sys.stdout.write("\n".join(parallel_lines) + "\n")


def _print_approvals(policy: ApprovalPolicy, recorder: TraceRecorder) -> None:
    approvals = [event for event in recorder.events if event.get("kind") == "approval"]
    sys.stdout.write("Approvals - session history\n")
    if approvals:
        sys.stdout.write(f"{'#':>4} {'tool':<16} {'decision':<18} {'scope':<18} summary\n")
        for event in approvals:
            scope = str(event.get("scope_key") or "-")
            summary = str(event.get("args_summary") or "")
            sys.stdout.write(
                f"{int(event.get('event_idx') or 0):>4} "
                f"{str(event.get('tool') or ''):<16} "
                f"{str(event.get('decision') or ''):<18} "
                f"{scope:<18} {summary}\n"
            )
    else:
        sys.stdout.write("  (no approvals this session)\n")

    cached = policy.cache.listing()
    sys.stdout.write("Cached approval scopes\n")
    if cached:
        for tool, scope in cached:
            sys.stdout.write(f"  {tool}  {scope}\n")
    else:
        sys.stdout.write("  (no reusable scopes)\n")


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
        color = "\x1b[31m"
    elif "!usd" in lowered or "exceeds cap" in lowered or "(next ~$" in lowered:
        color = "\x1b[31m"
    elif any(marker in lowered for marker in ("warn_", "cap")):
        color = "\x1b[33m"
    else:
        color = "\x1b[32m"
    return f"{color}{line}\x1b[0m"


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
    sys.stderr.write(line + "\n")
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
            detail = clarify_tool_error(tool_name, str(event.get("result_full") or "")).replace("\n", " ")
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
                ).replace("\n", " ")
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
            ).replace("\n", " ")
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
        return "\x1b[31m"
    if kind == "run_end" and event.get("final_status") not in {None, "ok"}:
        return "\x1b[31m"
    if kind in {"model_error", "egress_blocked"}:
        return "\x1b[31m"
    if kind == "budget_event":
        return "\x1b[33m"
    if kind == "approval":
        return "\x1b[36m"
    if kind in {"subagent_spawn", "subagent_return"}:
        return "\x1b[35m"
    if kind == "compaction":
        return "\x1b[34m"
    return "\x1b[90m"


def _make_progress_sink(
    stream: object | None = None,
    *,
    on_parent_status: Any = None,
    turn_state: dict[str, Any] | None = None,
    workspace_root: Path | None = None,
    recorder: TraceRecorder | None = None,
) -> "callable":
    fh = stream if stream is not None else sys.stderr
    use_color = bool(getattr(fh, "isatty", lambda: False)()) and not os.environ.get("NO_COLOR")
    reset = "\x1b[0m" if use_color else ""
    state = turn_state if turn_state is not None else {}
    pending_calls: dict[str, dict[str, object]] = {}
    write_priors: dict[str, str] = state.setdefault("write_priors", {})

    def sink(event: dict[str, object]) -> None:
        kind = event.get("kind")
        if kind == "statusline":
            return
        if kind == "user_prompt":
            state["turn"] = int(state.get("turn", 0)) + 1
            if recorder is not None:
                state["turn_list_start"] = len(recorder.events) - 1
            pending_calls.clear()
            if use_color:
                fh.write(f"\n\x1b[90m── turn {state['turn']} ──\x1b[0m\n")
            else:
                fh.write(f"\n── turn {state['turn']} ──\n")
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
            fh.write(f"{banner}\n")
        line = _format_progress_event(event)
        if line is not None:
            color = _progress_event_color(event, use_color=use_color)
            prefix = "  " if kind in {"subagent_spawn", "subagent_return"} else ""
            fh.write(f"{color}{prefix}{line}{reset}\n")
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
                since = int(state.get("turn_list_start", 0))
                summary = parallel_subagent_summary(recorder.events, since_event_idx=since)
                if summary is not None:
                    spawn_payload: list[dict[str, object]] | None = None
                    try:
                        parsed = json.loads(str(event.get("result_full") or ""))
                    except json.JSONDecodeError:
                        parsed = None
                    if isinstance(parsed, list):
                        spawn_payload = [item for item in parsed if isinstance(item, dict)]
                    parallel_color = "\x1b[35m" if use_color else ""
                    for parallel_line in format_parallel_progress_lines(summary, spawn_payload=spawn_payload):
                        fh.write(f"{parallel_color}{parallel_line}{reset}\n")
                    fh.flush()
            if tool in WRITE_EDIT_TOOLS and event.get("status") == "ok":
                call = pending_calls.pop(tool_use_id, None)
                if call is not None:
                    prior = write_priors.get(tool_use_id)
                    if use_rich_ui():
                        render_progress_file_diff(
                            _console(), call_event=call, prior_content=prior
                        )
                    else:
                        for diff_line in progress_diff_lines(call, prior):
                            fh.write(f"  {diff_line}\n")
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
        outputs.append(f"{title}\n{body}")
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


def _exit_code_for_final_status(status: str | None) -> int:
    if status == "aborted":
        return 3
    if status == "model_error":
        return 75
    return 0


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
        sys.stderr.write(line + "\n")
        sys.stderr.flush()


def _guard_overrides(args: argparse.Namespace) -> dict[str, object]:
    """Per-run budget overrides from the CLI (unset flags fall back to config)."""
    overrides: dict[str, object] = {}
    if getattr(args, "max_usd", None) is not None:
        overrides["max_usd"] = args.max_usd
    if getattr(args, "max_tokens", None) is not None:
        overrides["max_tokens"] = args.max_tokens
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
    )
    policy = _make_policy(args, workspace_root=root)
    history_path = root / ".vg_chat_history"
    read_prompt, save_history = _make_chat_prompt(history_path)
    if use_rich_ui():
        print_chat_dashboard_cleared(**_chat_ui_kwargs(root, recorder, guard, args, since_event_idx=ui_since))
    else:
        sys.stderr.write("VG Agent chat mode. Type /help for commands.\n")
    conversation: list[dict[str, Any]] = []
    last_intent_prompt = ""
    try:
        while True:
            try:
                render_input_top_rule()
                prompt = read_prompt().strip()
            except KeyboardInterrupt:
                recorder.emit("budget_event", budget_reason="user_abort", details={})
                sys.stderr.write("\n")
                break
            except EOFError:
                sys.stderr.write("\n")
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
                        sys.stdout.write(f"Invalid turn index: {parts[1]!r}\n")
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
                        sys.stdout.write(f"Invalid step index: {parts[1]!r}\n")
                        continue
                    sys.stdout.write(
                        json.dumps(show_context(recorder.events, step), indent=2, ensure_ascii=False) + "\n"
                    )
                continue
            if prompt == "/compact" or prompt.startswith("/compact "):
                if not conversation:
                    sys.stdout.write("No conversation history to compact yet.\n")
                    continue
                try:
                    compact_client = LiveModelClient.from_env(recorder=recorder)
                except MissingOpenRouterKey as exc:
                    sys.stderr.write(f"error: {exc}\n")
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
                    sys.stdout.write("Nothing to fold (history too short).\n")
                else:
                    banner = format_compaction_banner(compact_event)
                    if banner:
                        sys.stdout.write(banner + "\n")
                continue
            if prompt == "/help":
                sys.stdout.write(SLASH_COMMAND_HELP + "\n")
                continue
            render_input_bottom_and_footer(**_chat_ui_kwargs(root, recorder, guard, args, since_event_idx=ui_since))
            start_idx = len(recorder.events)
            turn_state["since_event_idx"] = start_idx
            turn_state["write_priors"] = {}
            turn_state["force_state"] = "running"
            _report_parent_session_status(
                root, recorder, guard, args, since_event_idx=start_idx, force_state="running"
            )
            literal_prompt = last_intent_prompt if _is_ack_prompt(prompt) and last_intent_prompt else prompt
            try:
                client = LiveModelClient.from_env(recorder=recorder)
            except MissingOpenRouterKey as exc:
                sys.stderr.write(f"error: {exc}\n")
                return 2
            run_live_task(root, prompt, recorder, client=client, guard=guard, policy=policy, history=conversation)
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
            )
            for notice in _turn_subagent_failure_notices(recorder.events, start_idx):
                sys.stderr.write(notice + "\n")
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
    parser.add_argument("--show-context", type=int)
    parser.add_argument("--seed-fixture", action="store_true")
    # The agent always runs against the live OpenRouter model; --live-model is
    # accepted as a no-op alias for backwards compatibility with older docs.
    parser.add_argument("--live-model", action="store_true")
    parser.add_argument("--parent-model")
    parser.add_argument("--subagent-model")
    parser.add_argument("--chat", action="store_true")
    parser.add_argument("--require-approval", choices=["off", "writes", "all"], default=config.REQUIRE_APPROVAL_DEFAULT)
    parser.add_argument("--yes", action="store_true")
    parser.add_argument("--no-step-extend-prompt", action="store_true")
    parser.add_argument("--no-redact", action="store_true")
    parser.add_argument("--budget", action="store_true")
    parser.add_argument("--finops", action="store_true")
    parser.add_argument("--max-usd", type=float)
    parser.add_argument("--max-tokens", type=int)
    args = parser.parse_args(argv)
    args.live_model = True
    _apply_model_overrides(args)

    if args.no_redact:
        sys.stderr.write("warning: --no-redact disables trace secret redaction.\n")

    root = resolve_workspace_root()
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
        parser.exit(2, f"error: {exc}\n")
    guard = BudgetGuard.for_workspace(root, **_guard_overrides(args))
    run_live_task(root, args.task, recorder, client=client, guard=guard, policy=policy)
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
