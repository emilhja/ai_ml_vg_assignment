"""Generated JSONL trace and replay helpers."""

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
        with self.path.open("a", encoding="utf-8", newline="\n") as fh:
            fh.write(json.dumps(event, ensure_ascii=False, sort_keys=True) + "\n")
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
    return "\n".join(lines)


def compacted_marker(event: dict[str, object]) -> str:
    return (
        f"[COMPACTED tool_result for tool_use_id={event['tool_use_id']}]\n"
        f"Summary (<=300 tokens): {event['summary']}\n"
        f"Original size: {event['before_tokens']} tokens. Trace pointer: {event['run_id']}:event:{event['original_event_idx']}.\n"
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
