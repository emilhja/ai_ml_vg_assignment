"""Generated CLI."""

from __future__ import annotations

import argparse
import json
import os
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
    from prompt_toolkit.completion import WordCompleter
    from prompt_toolkit.history import FileHistory
except ImportError:  # pragma: no cover - dependency is optional at runtime fallback level
    PromptSession = None
    WordCompleter = None
    FileHistory = None

from . import config
from .agent import ApprovalOutcome, ApprovalPolicy, ApprovalRequest, run_live_task, run_task
from .live_model_client import LiveModelClient, MissingOpenRouterKey
from .budget import BudgetGuard
from .demo_fixture import write_fixture
from .trace import TraceRecorder, load_trace, render_tree, show_context


def _stdin_prompt(stream: object | None = None) -> "callable":
    fh = stream if stream is not None else sys.stdin

    def ask(request: ApprovalRequest) -> ApprovalOutcome:
        sys.stderr.write(f"[approval] {request.tool}  {request.summary}\n")
        sys.stderr.write("  1) yes  2) yes (this folder)  3) yes (always)  4) no  5) abort\n> ")
        sys.stderr.flush()
        line = fh.readline().strip()
        if not line:
            return ApprovalOutcome(decision="denied", reason="no input")
        choice = line.split()[0]
        if choice == "1":
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
        if choice == "3":
            return ApprovalOutcome(decision="approved_always", scope_key="*", reason="user yes-always")
        if choice == "5":
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
        f"daily_remaining {guard.daily_remaining_usd:.6f}\n"
    )


SLASH_COMMANDS = (
    "/exit",
    "/quit",
    "/budget",
    "/status",
    "/finops",
    "/approvals",
    "/reset",
    "/show-context",
    "/help",
)
SLASH_COMMAND_HELP = " ".join((*SLASH_COMMANDS[:-2], "/show-context N", SLASH_COMMANDS[-1]))


def _slash_command_completer() -> Any:
    if WordCompleter is None:
        return None
    return WordCompleter(list(SLASH_COMMANDS), ignore_case=True, match_middle=False, WORD=True)


def _make_chat_prompt(history_path: Path) -> tuple[Any, Any]:
    if (
        bool(getattr(sys.stdin, "isatty", lambda: False)())
        and PromptSession is not None
        and FileHistory is not None
    ):
        session = PromptSession(
            "vg> ",
            completer=_slash_command_completer(),
            complete_while_typing=True,
            history=FileHistory(str(history_path)),
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
        return input("vg> ")

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


def _latest_run_state(events: list[dict[str, object]]) -> str:
    for event in reversed(events):
        kind = event.get("kind")
        if kind == "run_end":
            return str(event.get("final_status") or "done")
        if kind == "budget_event":
            return str(event.get("budget_reason") or "budget")
    return "ready"


def _format_chat_statusline(
    recorder: TraceRecorder,
    guard: BudgetGuard,
    *,
    live_model: bool,
    width: int | None = None,
) -> str:
    mode = "live" if live_model else "deterministic"
    latest_llm = _latest_parent_llm_start(recorder.events)
    model = _short_model((latest_llm or {}).get("model") or config.PARENT_MODEL_ID)
    context_tokens = int((latest_llm or {}).get("tokens_in") or 0)
    status = _latest_run_state(recorder.events)
    approval_events = sum(1 for event in recorder.events if event.get("kind") == "approval")
    token_bar = _bar(guard.running_tokens, guard.max_tokens)
    line = (
        f"[{mode}] {model} | ctx {_format_compact_number(context_tokens)} in | "
        f"run {token_bar} {_format_compact_number(guard.running_tokens)}/{_format_compact_number(guard.max_tokens)} tok | "
        f"steps {guard.step_count}/{guard.max_steps} | "
        f"usd ${guard.running_usd:.4f}/${guard.max_usd:.2f} | "
        f"approvals {approval_events} | {status}"
    )
    if width is None:
        width = shutil.get_terminal_size((120, 20)).columns
    if width > 20 and len(line) > width:
        return line[: max(0, width - 3)] + "..."
    return line


def _chat_statusline_color(line: str, *, use_color: bool) -> str:
    if not use_color:
        return line
    return f"\x1b[32m{line}\x1b[0m"


def _print_chat_statusline(recorder: TraceRecorder, guard: BudgetGuard, *, live_model: bool) -> None:
    if not live_model:
        return
    line = _format_chat_statusline(recorder, guard, live_model=live_model)
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
        return (
            f"[tool] {agent} {event.get('tool')} {event.get('status')} "
            f"tokens={event.get('tokens')} {event.get('latency_ms')}ms"
        )
    if kind == "approval":
        return f"[approval] {event.get('tool')} decision={event.get('decision')} scope={event.get('scope_key')}"
    if kind == "subagent_spawn":
        return f"[agent] spawn {event.get('child_agent_id')} {_short_model(event.get('model'))}"
    if kind == "subagent_return":
        return f"[agent] return {event.get('child_agent_id')} tokens={event.get('child_total_tokens')} usd={event.get('child_total_cost_usd')}"
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
        return f"[run] {event.get('final_status')} tokens={event.get('total_tokens')} usd={event.get('total_cost_usd')}"
    return None


def _make_progress_sink(stream: object | None = None) -> "callable":
    fh = stream if stream is not None else sys.stderr
    use_color = bool(getattr(fh, "isatty", lambda: False)()) and not os.environ.get("NO_COLOR")
    grey = "\x1b[90m" if use_color else ""
    reset = "\x1b[0m" if use_color else ""

    def sink(event: dict[str, object]) -> None:
        line = _format_progress_event(event)
        if line is None:
            return
        fh.write(f"{grey}{line}{reset}\n")
        fh.flush()

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
        if event.get("status") != "ok" or event.get("tool") not in LITERAL_OUTPUT_TOOLS:
            continue
        content = str(event.get("result_full") or "").strip()
        if not content or (answer_text and content in answer_text):
            continue
        call = calls.get(str(event.get("tool_use_id") or ""), {})
        command = str(call.get("command") or "").strip()
        title = f"Tool output ({command}):" if command else f"Tool output ({event.get('tool')}):"
        outputs.append(f"{title}\n{content}")
    return outputs


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


def _chat_loop(root: Path, args: argparse.Namespace) -> int:
    recorder = TraceRecorder(root, redact=not args.no_redact, event_sink=_make_progress_sink())
    policy = _make_policy(args)
    guard = BudgetGuard.for_workspace(root)
    history_path = root / ".vg_chat_history"
    read_prompt, save_history = _make_chat_prompt(history_path)
    sys.stderr.write("VG Agent chat mode. Type /help for commands.\n")
    conversation: list[dict[str, Any]] = []
    last_intent_prompt = ""
    try:
        while True:
            try:
                _print_chat_statusline(recorder, guard, live_model=bool(args.live_model))
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
            if prompt == "/budget":
                _print_budget(guard)
                continue
            if prompt == "/status":
                line = _format_chat_statusline(recorder, guard, live_model=bool(args.live_model))
                use_color = bool(getattr(sys.stdout, "isatty", lambda: False)()) and bool(args.live_model) and not os.environ.get("NO_COLOR")
                sys.stdout.write(_chat_statusline_color(line, use_color=use_color) + "\n")
                continue
            if prompt == "/approvals":
                _print_approvals(policy, recorder)
                continue
            if prompt == "/reset":
                policy.cache.clear()
                guard = BudgetGuard.for_workspace(root)
                conversation.clear()
                recorder.emit("session_reset")
                continue
            if prompt == "/finops":
                _print_finops(guard, recorder)
                continue
            if prompt.startswith("/show-context"):
                parts = prompt.split()
                step = int(parts[1]) if len(parts) > 1 else 0
                sys.stdout.write(json.dumps(show_context(recorder.events, step), indent=2, ensure_ascii=False) + "\n")
                continue
            if prompt == "/help":
                sys.stdout.write(SLASH_COMMAND_HELP + "\n")
                continue
            start_idx = len(recorder.events)
            literal_prompt = last_intent_prompt if _is_ack_prompt(prompt) and last_intent_prompt else prompt
            if args.live_model:
                try:
                    client = LiveModelClient.from_env(recorder=recorder)
                except MissingOpenRouterKey as exc:
                    sys.stderr.write(f"error: {exc}\n")
                    return 2
                run_live_task(root, prompt, recorder, client=client, guard=guard, policy=policy, history=conversation)
            else:
                run_task(root, prompt, recorder, policy=policy)
            answer = _latest_parent_answer(recorder.events, start_idx)
            if answer:
                sys.stdout.write(answer + "\n")
            literal_outputs = _literal_tool_outputs(recorder.events, start_idx, literal_prompt, answer)
            for output in literal_outputs:
                sys.stdout.write(output + "\n")
            if answer or literal_outputs:
                sys.stdout.flush()
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
        sys.stderr.write("warning: --no-redact disables trace secret redaction.\n")

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
            parser.exit(2, f"error: {exc}\n")
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
