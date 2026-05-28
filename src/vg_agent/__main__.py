"""Generated CLI."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

try:
    import readline  # enables arrow-key history in input() on POSIX
except ImportError:  # Windows host lacks GNU readline; chat mode requires a TTY anyway
    readline = None

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
            if request.tool == "run_bash":
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


def _short_model(model: object) -> str:
    text = str(model or "")
    for prefix in ("openrouter/anthropic/", "openrouter/"):
        if text.startswith(prefix):
            return text[len(prefix):]
    return text


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
    if readline is not None:
        readline.set_history_length(1000)
        try:
            readline.read_history_file(str(history_path))
        except OSError:
            pass
    sys.stderr.write("VG Agent chat mode. Type /help for commands.\n")
    try:
        while True:
            try:
                prompt = input("vg> ").strip()
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
            if prompt == "/approvals":
                for entry in policy.cache.listing():
                    sys.stdout.write(f"  {entry[0]}  {entry[1]}\n")
                continue
            if prompt == "/reset":
                policy.cache.clear()
                guard = BudgetGuard.for_workspace(root)
                recorder.emit("session_reset")
                continue
            if prompt.startswith("/show-context"):
                parts = prompt.split()
                step = int(parts[1]) if len(parts) > 1 else 0
                sys.stdout.write(json.dumps(show_context(recorder.events, step), indent=2, ensure_ascii=False) + "\n")
                continue
            if prompt == "/help":
                sys.stdout.write("/exit /quit /budget /approvals /reset /show-context N /help\n")
                continue
            start_idx = len(recorder.events)
            if args.live_model:
                try:
                    client = LiveModelClient.from_env(recorder=recorder)
                except MissingOpenRouterKey as exc:
                    sys.stderr.write(f"error: {exc}\n")
                    return 2
                run_live_task(root, prompt, recorder, client=client, guard=guard, policy=policy)
            else:
                run_task(root, prompt, recorder, policy=policy)
            answer = _latest_parent_answer(recorder.events, start_idx)
            if answer:
                sys.stdout.write(answer + "\n")
                sys.stdout.flush()
    finally:
        if readline is not None:
            try:
                readline.write_history_file(str(history_path))
            except OSError:
                pass
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
    if args.live_model:
        try:
            client = LiveModelClient.from_env(recorder=recorder)
        except MissingOpenRouterKey as exc:
            parser.exit(2, f"error: {exc}\n")
        run_live_task(root, args.task, recorder, client=client, policy=policy)
    else:
        run_task(root, args.task, recorder, policy=policy)
    answer = _latest_parent_answer(recorder.events)
    if answer:
        print(answer)
    if args.trace:
        print(render_tree(recorder.events))
        print(f"trace: {recorder.path}")
    if args.show_context is not None:
        print(json.dumps(show_context(recorder.events, args.show_context), indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
