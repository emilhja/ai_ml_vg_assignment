"""Generated JSONL trace and rendering helpers."""

from __future__ import annotations

import json
import re
import sys
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable
from uuid import uuid4

from .sqlite_store import SQLiteTraceStore


REDACTION_PATTERNS = [
    ("openrouter_key", re.compile(r"sk-or-v1-[A-Za-z0-9_\-]+")),
    ("aws_key_id", re.compile(r"AKIA[0-9A-Z]{16}")),
    ("bearer_token", re.compile(r"(?i)bearer\s+[a-z0-9._\-]+")),
]


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _redact(content: str) -> tuple[str, list[tuple[str, int]]]:
    summary: list[tuple[str, int]] = []
    redacted = content
    for name, pattern in REDACTION_PATTERNS:
        redacted, count = pattern.subn("***REDACTED***", redacted)
        if count:
            summary.append((name, count))
    return redacted, summary


def _redact_event_fields(event: dict[str, Any]) -> tuple[dict[str, Any], list[tuple[str, int]]]:
    summary: list[tuple[str, int]] = []
    redacted: dict[str, Any] = {}
    for key, value in event.items():
        if isinstance(value, str):
            new_value, hits = _redact(value)
            if hits:
                summary.extend(hits)
            redacted[key] = new_value
        else:
            redacted[key] = value
    return redacted, summary


@dataclass
class TraceRecorder:
    root: Path
    run_id: str = field(default_factory=lambda: uuid4().hex[:12])
    session_id: str | None = None
    events: list[dict[str, object]] = field(default_factory=list)
    redact: bool = True
    event_sink: Callable[[dict[str, object]], None] | None = None
    sqlite_enabled: bool = True

    def __post_init__(self) -> None:
        self.trace_dir = self.root / "traces"
        self.trace_dir.mkdir(parents=True, exist_ok=True)
        self.path = self.trace_dir / f"{self.run_id}.jsonl"
        if self.session_id is None:
            self.session_id = self.run_id
        self.turn_counter = 0
        self.current_turn_id: str | None = None
        # Reentrant lock: parallel sub-agents (spawn_subagents) emit concurrently,
        # and emit() re-enters via _emit_redaction.
        self._lock = threading.RLock()
        self.sqlite_store: SQLiteTraceStore | None = None
        if self.sqlite_enabled:
            try:
                self.sqlite_store = SQLiteTraceStore(self.root, redaction_enabled=self.redact)
            except Exception as exc:  # pragma: no cover - best-effort mirror
                sys.stderr.write(f"warning: sqlite trace disabled: {exc}\n")

    def emit(self, kind: str, agent_id: str = "parent", parent_id: str | None = None, agent_type: str = "parent", **fields: object) -> dict[str, object]:
        with self._lock:
            if kind == "user_prompt":
                self.turn_counter += 1
                self.current_turn_id = f"{self.session_id}:turn:{self.turn_counter}"
                fields.setdefault("turn_id", self.current_turn_id)
                fields.setdefault("turn_index", self.turn_counter)
            elif self.current_turn_id is not None:
                fields.setdefault("turn_id", self.current_turn_id)
                fields.setdefault("turn_index", self.turn_counter)
            event: dict[str, object] = {
                "run_id": self.run_id,
                "session_id": self.session_id,
                "event_idx": len(self.events),
                "timestamp_iso": now_iso(),
                "agent_id": agent_id,
                "agent_type": agent_type,
                "parent_id": parent_id,
                "kind": kind,
            }
            event.update(fields)
            redaction_summary: list[tuple[str, int]] = []
            if self.redact:
                event, redaction_summary = _redact_event_fields(event)
            self.events.append(event)
            with self.path.open("a", encoding="utf-8", newline="\n") as fh:
                fh.write(json.dumps(event, ensure_ascii=False, sort_keys=True) + "\n")
            if self.sqlite_store is not None:
                try:
                    self.sqlite_store.record_event(event)
                except Exception as exc:  # pragma: no cover - JSONL remains canonical
                    sys.stderr.write(f"warning: sqlite trace write failed: {exc}\n")
                    self.sqlite_store = None
            if self.event_sink is not None:
                self.event_sink(event)
            if redaction_summary and kind != "redaction":
                self._emit_redaction(int(event["event_idx"]), redaction_summary)
            return event

    def _emit_redaction(self, original_event_idx: int, summary: list[tuple[str, int]]) -> None:
        for pattern_name, count in summary:
            self.emit(
                "redaction",
                original_event_idx=original_event_idx,
                pattern=pattern_name,
                count=count,
            )


def load_trace(path: Path) -> list[dict[str, object]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def render_tree(events: list[dict[str, object]]) -> str:
    lines: list[str] = []
    for event in events:
        prefix = "  " if event.get("parent_id") else ""
        kind = event["kind"]
        if kind == "llm_start":
            lines.append(f"{prefix}{event['event_idx']:03d} {event['agent_id']} llm_start step {event.get('step_idx')} model={event.get('model')}")
        elif kind == "assistant_step":
            lines.append(f"{prefix}{event['event_idx']:03d} {event['agent_id']} assistant step {event.get('step_idx')} model={event.get('model')}")
        elif kind == "tool_result":
            lines.append(f"{prefix}{event['event_idx']:03d} {event['agent_id']} tool_result {event.get('tool')} tokens={event.get('tokens')} status={event.get('status')}")
        elif kind == "compaction":
            lines.append(f"{prefix}{event['event_idx']:03d} compacted {event.get('before_tokens')} -> {event.get('after_tokens')} tokens (tool_use {event.get('tool_use_id')})")
        elif kind == "budget_event":
            lines.append(f"{prefix}{event['event_idx']:03d} budget_event {event.get('budget_reason')}")
        elif kind == "approval":
            lines.append(f"{prefix}{event['event_idx']:03d} approval {event.get('tool')} decision={event.get('decision')} scope={event.get('scope_key')}")
        elif kind == "model_error":
            lines.append(f"{prefix}{event['event_idx']:03d} {event['agent_id']} model_error {event.get('error_type')} retryable={event.get('retryable')}")
        elif kind == "egress_blocked":
            lines.append(f"{prefix}{event['event_idx']:03d} egress_blocked host={event.get('host')!r}")
        elif kind == "redaction":
            lines.append(f"{prefix}{event['event_idx']:03d} redaction {event.get('pattern')} count={event.get('count')} orig_idx={event.get('original_event_idx')}")
        elif kind == "session_reset":
            lines.append(f"{prefix}{event['event_idx']:03d} session_reset")
        elif kind == "session_new":
            lines.append(f"{prefix}{event['event_idx']:03d} session_new")
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
            if int(event.get("step_idx") or 0) > step_idx:
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
        elif kind == "approval":
            context.append({
                "role": "meta",
                "kind": "approval",
                "tool": event.get("tool"),
                "decision": event.get("decision"),
                "scope_key": event.get("scope_key"),
            })
        elif kind == "redaction":
            context.append({
                "role": "meta",
                "kind": "redaction",
                "pattern": event.get("pattern"),
                "count": event.get("count"),
            })
        elif kind == "egress_blocked":
            context.append({
                "role": "meta",
                "kind": "egress_blocked",
                "host": event.get("host"),
            })
        elif kind == "model_error":
            context.append({
                "role": "meta",
                "kind": "model_error",
                "message": event.get("message"),
                "retryable": event.get("retryable"),
            })
    return context
