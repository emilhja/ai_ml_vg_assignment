"""Generated CLI."""

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
            parser.exit(2, f"error: {exc}\n")
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
