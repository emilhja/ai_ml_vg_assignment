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
        elif kind == "context_compaction":
            context.append({
                "role": "meta",
                "kind": "context_compaction",
                "content": (
                    f"Conversation compacted {event.get('before_tokens')} -> {event.get('after_tokens')} "
                    f"tokens ({event.get('percent_reduced')}% reduced, reason={event.get('reason')}). "
                    f"{event.get('summary')}"
                ),
                "trace_pointer": event.get("trace_pointer"),
            })
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


def _parent_assistant_positions(events: list[dict[str, object]]) -> list[tuple[int, int]]:
    """Return (step_idx, event_index) for each parent assistant_step, sorted by step."""
    positions: list[tuple[int, int]] = []
    for index, event in enumerate(events):
        if event.get("kind") == "assistant_step" and event.get("agent_id") == "parent":
            positions.append((int(event.get("step_idx") or 0), index))
    return sorted(positions, key=lambda pair: pair[0])


def _turn_start_before_event_index(events: list[dict[str, object]], event_index: int) -> int:
    for index in range(event_index, -1, -1):
        if events[index].get("kind") == "user_prompt":
            return index
    return 0


def _event_slice_through_parent_step(events: list[dict[str, object]], step_idx: int) -> tuple[int, int]:
    """List slice [start, end) covering the turn through completion of parent step ``step_idx``."""
    positions = _parent_assistant_positions(events)
    target = next((index for step, index in positions if step == step_idx), None)
    if target is None:
        return 0, len(events)
    turn_start = _turn_start_before_event_index(events, target)
    next_assistant = next((index for step, index in positions if step > step_idx), len(events))
    return turn_start, next_assistant


def _tool_names_from_assistant_event(event: dict[str, object]) -> list[str]:
    names: list[str] = []
    for call in event.get("tool_calls") or []:
        if isinstance(call, dict):
            names.append(str(call.get("name") or call.get("tool") or "tool"))
    return names


def show_context_overview(events: list[dict[str, object]]) -> list[dict[str, object]]:
    """Per parent-step summary for ``/show-context`` without a step index."""
    rows: list[dict[str, object]] = []
    for step_idx, event_index in _parent_assistant_positions(events):
        context = show_context(events, step_idx)
        tool_calls = _tool_names_from_assistant_event(events[event_index])
        compacted = sum(1 for item in context if item.get("compacted"))
        tool_results = sum(1 for item in context if item.get("role") == "tool")
        parallel_note: str | None = None
        if "spawn_subagents" in tool_calls:
            start, end = _event_slice_through_parent_step(events, step_idx)
            summary = parallel_subagent_summary(events, since_event_idx=start, before_event_idx=end)
            if summary is not None:
                overlap = "yes" if summary.overlap else "no"
                parallel_note = f"{len(summary.returns)} parallel sub-agents (overlap {overlap})"
        elif "spawn_subagent" in tool_calls:
            parallel_note = "1 sub-agent"
        rows.append(
            {
                "step_idx": step_idx,
                "context_messages": len(context),
                "tool_calls": tool_calls,
                "tool_results_visible": tool_results,
                "compacted_results": compacted,
                "parallel": parallel_note,
            }
        )
    return rows


def format_show_context_overview(events: list[dict[str, object]]) -> str:
    rows = show_context_overview(events)
    if not rows:
        return "No parent steps yet. Run a task first.\n"
    lines = [
        "Parent context overview — use /show-context N for full JSON at step N",
        f"{'step':>4}  {'ctx':>4}  {'tools':>5}  {'results':>7}  {'compact':>7}  notes",
        "-" * 72,
    ]
    for row in rows:
        step = int(row["step_idx"])
        tools = row["tool_calls"]
        tool_count = len(tools) if isinstance(tools, list) else 0
        tool_label = ", ".join(tools) if isinstance(tools, list) and tools else "-"
        if tool_count > 3:
            tool_label = ", ".join(tools[:3]) + f", +{tool_count - 3} more"
        notes: list[str] = [tool_label]
        parallel = row.get("parallel")
        if parallel:
            notes.append(str(parallel))
        lines.append(
            f"{step:>4}  {int(row['context_messages']):>4}  {tool_count:>5}  "
            f"{int(row['tool_results_visible']):>7}  {int(row['compacted_results']):>7}  "
            + " · ".join(notes)
        )
    lines.append("")
    return "\n".join(lines) + "\n"


def _parse_iso_timestamp(value: object) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None


def _intervals_overlap(
    a_start: datetime,
    a_end: datetime,
    b_start: datetime,
    b_end: datetime,
) -> bool:
    return a_start <= b_end and b_start <= a_end


def _duration_seconds(started_at: object, ended_at: object) -> float | None:
    start = _parse_iso_timestamp(started_at)
    end = _parse_iso_timestamp(ended_at)
    if start is None or end is None:
        return None
    return max(0.0, (end - start).total_seconds())


@dataclass(frozen=True)
class SubagentReturnInfo:
    child_agent_id: str
    agent_type: str
    question: str
    started_at: str
    ended_at: str
    status: str
    payload_snippet: str
    duration_sec: float | None


@dataclass(frozen=True)
class ParallelSubagentSummary:
    returns: tuple[SubagentReturnInfo, ...]
    overlap: bool


def _spawn_questions_by_child(events: list[dict[str, object]]) -> dict[str, str]:
    questions: dict[str, str] = {}
    for event in events:
        if event.get("kind") != "subagent_spawn":
            continue
        child = str(event.get("child_agent_id") or "")
        if child:
            questions[child] = str(event.get("question") or "")[:60]
    return questions


def parallel_subagent_summary(
    events: list[dict[str, object]],
    *,
    since_event_idx: int = 0,
    before_event_idx: int | None = None,
) -> ParallelSubagentSummary | None:
    """Summarise subagent_return rows in an event slice; overlap from started_at/ended_at."""
    end = before_event_idx if before_event_idx is not None else len(events)
    slice_events = events[since_event_idx:end]
    questions = _spawn_questions_by_child(events[:end])
    returns: list[SubagentReturnInfo] = []
    for event in slice_events:
        if event.get("kind") != "subagent_return":
            continue
        child = str(event.get("child_agent_id") or "")
        payload = str(event.get("summary") or "")
        returns.append(
            SubagentReturnInfo(
                child_agent_id=child,
                agent_type=str(event.get("agent_type") or "explorer"),
                question=questions.get(child, ""),
                started_at=str(event.get("started_at") or ""),
                ended_at=str(event.get("ended_at") or ""),
                status=str(event.get("status") or "ok"),
                payload_snippet=payload[:120],
                duration_sec=_duration_seconds(event.get("started_at"), event.get("ended_at")),
            )
        )
    if len(returns) < 2:
        return None
    intervals: list[tuple[datetime, datetime]] = []
    for item in returns:
        start = _parse_iso_timestamp(item.started_at)
        end = _parse_iso_timestamp(item.ended_at)
        if start is not None and end is not None:
            intervals.append((start, end))
    overlap = False
    for index, (a_start, a_end) in enumerate(intervals):
        for b_start, b_end in intervals[index + 1 :]:
            if _intervals_overlap(a_start, a_end, b_start, b_end):
                overlap = True
                break
        if overlap:
            break
    return ParallelSubagentSummary(returns=tuple(returns), overlap=overlap)


def format_parallel_progress_lines(
    summary: ParallelSubagentSummary,
    *,
    spawn_payload: list[dict[str, object]] | None = None,
) -> list[str]:
    """stderr lines after spawn_subagents tool_result."""
    durations = [item.duration_sec for item in summary.returns if item.duration_sec is not None]
    dur_text = ""
    if durations:
        parts = [f"{value:.1f}s" for value in durations[:4]]
        dur_text = f" · {' / '.join(parts)}"
    overlap_label = "yes" if summary.overlap else "no"
    types = {item.agent_type for item in summary.returns}
    type_label = next(iter(types)) if len(types) == 1 else "mixed"
    header = (
        f"[parallel] {len(summary.returns)} {type_label} finished "
        f"({'concurrently' if summary.overlap else 'sequentially'}) "
        f"(overlap {overlap_label}{dur_text})"
    )
    lines = [header]
    payload_by_child: dict[str, str] = {}
    if spawn_payload:
        for entry in spawn_payload:
            if isinstance(entry, dict):
                child = str(entry.get("agent_id") or "")
                payload_by_child[child] = str(entry.get("payload") or "")[:60]
    for item in summary.returns:
        snippet = payload_by_child.get(item.child_agent_id) or item.question or item.payload_snippet
        child_short = item.child_agent_id.split(".")[-1] if "." in item.child_agent_id else item.child_agent_id
        lines.append(f"  · {child_short}: {snippet}")
    return lines


def parallel_finops_batch_lines(events: list[dict[str, object]]) -> list[str]:
    """Short parallel-batch summary for /finops."""
    prompt_positions = [
        index for index, event in enumerate(events) if event.get("kind") == "user_prompt"
    ]
    if not prompt_positions:
        return []
    batches: list[str] = []
    batch_num = 0
    for turn_num, start in enumerate(prompt_positions, start=1):
        end = prompt_positions[turn_num] if turn_num < len(prompt_positions) else len(events)
        turn_events = events[start:end]
        has_spawn = any(
            event.get("kind") == "tool_result"
            and event.get("tool") == "spawn_subagents"
            and event.get("status") == "ok"
            and event.get("agent_id") == "parent"
            for event in turn_events
        )
        if not has_spawn:
            continue
        summary = parallel_subagent_summary(events, since_event_idx=start, before_event_idx=end)
        if summary is None:
            continue
        batch_num += 1
        overlap_label = "overlapping wall-clock" if summary.overlap else "no overlap detected"
        batches.append(
            f"  turn {turn_num}: spawn_subagents · {len(summary.returns)} sub-agents · {overlap_label}"
        )
    if not batches:
        return []
    return [f"Parallel batches this session: {batch_num}", *batches]


def _turn_event_bounds(events: list[dict[str, object]], turn_index: int) -> tuple[int, int] | None:
    """Return (start_list_index, end_list_index) for 1-based user_prompt turn_index."""
    prompt_positions = [
        index for index, event in enumerate(events) if event.get("kind") == "user_prompt"
    ]
    if turn_index < 1 or turn_index > len(prompt_positions):
        return None
    start = prompt_positions[turn_index - 1]
    end = prompt_positions[turn_index] if turn_index < len(prompt_positions) else len(events)
    return start, end


def format_turn_review(
    events: list[dict[str, object]],
    *,
    turn_index: int | None = None,
    trace_path: Path | str | None = None,
    tool_summary_fn: Any | None = None,
) -> str:
    """Human-readable recap of one chat turn for /review."""
    prompt_positions = [
        index for index, event in enumerate(events) if event.get("kind") == "user_prompt"
    ]
    if not prompt_positions:
        return "No turns recorded yet.\n"
    chosen = turn_index if turn_index is not None else len(prompt_positions)
    bounds = _turn_event_bounds(events, chosen)
    if bounds is None:
        return f"Turn {chosen} not found ({len(prompt_positions)} turn(s) in session).\n"
    start, end = bounds
    turn_events = events[start:end]
    lines: list[str] = [f"=== Turn {chosen} review ===", ""]
    user_prompt = next((event for event in turn_events if event.get("kind") == "user_prompt"), None)
    if user_prompt:
        lines.extend(["Prompt:", str(user_prompt.get("prompt") or ""), ""])
    lines.append("Parent plan:")
    plan_found = False
    for event in turn_events:
        if event.get("kind") != "assistant_step" or event.get("agent_id") != "parent":
            continue
        tool_calls = event.get("tool_calls") or []
        if not isinstance(tool_calls, list):
            continue
        for call in tool_calls:
            if not isinstance(call, dict):
                continue
            name = str(call.get("name") or call.get("tool") or "tool")
            args = call.get("args") or {}
            if tool_summary_fn is not None:
                summary = tool_summary_fn(name, args if isinstance(args, dict) else {})
            else:
                summary = name
            lines.append(f"  - {summary}")
            plan_found = True
    if not plan_found:
        lines.append("  (no tool calls)")
    lines.append("")
    summary = parallel_subagent_summary(events, since_event_idx=start, before_event_idx=end)
    lines.append("Parallel:")
    if summary is None:
        lines.append("  (no parallel sub-agent batch)")
    else:
        lines.append(
            f"  {len(summary.returns)} sub-agents · overlap {'yes' if summary.overlap else 'no'}"
        )
        for item in summary.returns:
            dur = f"{item.duration_sec:.1f}s" if item.duration_sec is not None else "?"
            lines.append(
                f"  · {item.child_agent_id} ({item.agent_type}, {dur}): "
                f"{item.payload_snippet or item.question}"
            )
    lines.append("")
    compactions = [event for event in turn_events if event.get("kind") == "compaction"]
    context_compactions = [event for event in turn_events if event.get("kind") == "context_compaction"]
    lines.append("Context engineering:")
    if not compactions and not context_compactions:
        lines.append("  (no compaction events)")
    else:
        for event in compactions:
            summary = str(event.get("summary") or "").strip()
            if len(summary) > 80:
                summary = summary[:80] + "…"
            lines.append(
                f"  - tool_result compacted {event.get('before_tokens')} -> {event.get('after_tokens')} tokens "
                f"(trace event {event.get('original_event_idx')}, model={event.get('compactor_model')}, "
                f"fallback={event.get('compactor_fallback')})"
            )
            if summary:
                lines.append(f"    summary: {summary}")
        for event in context_compactions:
            summary = str(event.get("summary") or "").strip()
            if len(summary) > 80:
                summary = summary[:80] + "…"
            lines.append(
                f"  - conversation compacted {event.get('before_tokens')} -> {event.get('after_tokens')} tokens "
                f"(reason={event.get('reason')}, {event.get('percent_reduced')}% reduced)"
            )
            if summary:
                lines.append(f"    summary: {summary}")
    lines.append("")
    answer = ""
    for event in reversed(turn_events):
        if event.get("kind") != "assistant_step" or event.get("agent_id") != "parent":
            continue
        tool_calls = event.get("tool_calls") or []
        text = str(event.get("assistant_text") or "").strip()
        if not tool_calls and text:
            answer = text
            break
    lines.append("Answer:")
    if not answer:
        lines.append("  (no final parent text)")
    elif len(answer) > 2048:
        lines.append(answer[:2048])
        lines.append(f"  … truncated ({len(answer)} chars; full text in trace)")
    else:
        lines.append(answer)
    lines.append("")
    if trace_path:
        lines.append(f"trace: {trace_path}")
    parent_steps = [
        int(event.get("step_idx") or 0)
        for event in turn_events
        if event.get("kind") == "assistant_step" and event.get("agent_id") == "parent"
    ]
    if parent_steps:
        lines.append(f"Tip: /show-context {max(parent_steps)} for parent-visible context at final step.")
    lines.append("")
    return "\n".join(lines)
