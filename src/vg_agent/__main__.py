"""Generated CLI."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import config
from .agent import ApprovalOutcome, ApprovalPolicy, ApprovalRequest, run_live_task, run_task
from .anthropic_client import AnthropicClient, MissingAnthropicKey
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
            elif request.tool == "spawn_subagent":
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


def _chat_loop(root: Path, args: argparse.Namespace) -> int:
    recorder = TraceRecorder(root, redact=not args.no_redact)
    policy = _make_policy(args)
    guard = BudgetGuard.for_workspace(root)
    sys.stderr.write("VG Agent chat mode. Type /help for commands.\n")
    while True:
        sys.stderr.write("vg> ")
        sys.stderr.flush()
        try:
            line = sys.stdin.readline()
        except KeyboardInterrupt:
            recorder.emit("budget_event", budget_reason="user_abort", details={})
            break
        if not line:
            break
        prompt = line.strip()
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
        if args.live_model:
            try:
                client = AnthropicClient.from_env()
            except MissingAnthropicKey as exc:
                sys.stderr.write(f"error: {exc}\n")
                return 2
            run_live_task(root, prompt, recorder, client=client, guard=guard, policy=policy)
        else:
            run_task(root, prompt, recorder, policy=policy)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="vg_agent")
    parser.add_argument("--task")
    parser.add_argument("--trace", action="store_true")
    parser.add_argument("--replay")
    parser.add_argument("--show-context", type=int)
    parser.add_argument("--seed-fixture", action="store_true")
    parser.add_argument("--live-model", action="store_true")
    parser.add_argument("--chat", action="store_true")
    parser.add_argument("--require-approval", choices=["off", "writes", "all"], default=config.REQUIRE_APPROVAL_DEFAULT)
    parser.add_argument("--yes", action="store_true")
    parser.add_argument("--no-redact", action="store_true")
    args = parser.parse_args(argv)

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

    recorder = TraceRecorder(root, redact=not args.no_redact)
    policy = _make_policy(args)
    if args.live_model:
        try:
            client = AnthropicClient.from_env()
        except MissingAnthropicKey as exc:
            parser.exit(2, f"error: {exc}\n")
        run_live_task(root, args.task, recorder, client=client, policy=policy)
    else:
        run_task(root, args.task, recorder, policy=policy)
    if args.trace:
        print(render_tree(recorder.events))
        print(f"trace: {recorder.path}")
    if args.show_context is not None:
        print(json.dumps(show_context(recorder.events, args.show_context), indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
