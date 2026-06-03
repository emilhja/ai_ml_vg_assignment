"""Per-session sub-agent usage tags for history filters."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from vg_agent.trace import (
    iter_spawn_subagents_batch_summaries,
    spawn_subagents_child_ids,
)

from ..models import SubagentRow, ToolCallRow
from ..paths import find_jsonl_path
from .jsonl_io import read_jsonl_events


@dataclass(frozen=True)
class SubagentFlags:
    has_subagents: bool = False
    has_parallel_subagents: bool = False
    has_sequential_subagents: bool = False


def _parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _intervals_overlap(
    a_start: datetime,
    a_end: datetime,
    b_start: datetime,
    b_end: datetime,
) -> bool:
    return a_start < b_end and b_start < a_end


def _lane_key(event: dict) -> str:
    agent_id = str(event.get("agent_id") or "")
    if agent_id == "parent":
        return "parent"
    if event.get("kind") in {"subagent_spawn", "subagent_return"}:
        return str(event.get("child_agent_id") or agent_id or "subagent")
    return agent_id or "unknown"


def _batch_child_ids_from_turn(turn_events: list[dict]) -> set[str] | None:
    """Child ids from the latest spawn_subagents tool_result in a turn, if any."""
    for event in reversed(turn_events):
        if (
            event.get("kind") == "tool_result"
            and event.get("tool") == "spawn_subagents"
            and event.get("status") == "ok"
            and event.get("agent_id") == "parent"
        ):
            child_ids = spawn_subagents_child_ids(event)
            if len(child_ids) >= 2:
                return child_ids
            return None
    return None


def _inflight_spawn_batch_lane_ids(turn_events: list[dict]) -> set[str]:
    """Lane ids for an in-flight spawn_subagents batch (tool_result not landed yet)."""
    has_spawn_tool = any(
        event.get("kind") == "tool_call" and event.get("tool") == "spawn_subagents"
        for event in turn_events
    )
    if not has_spawn_tool or _batch_child_ids_from_turn(turn_events):
        return set()
    lane_ids: set[str] = set()
    for event in turn_events:
        if event.get("kind") != "subagent_spawn":
            continue
        lane = _lane_key(event)
        if lane != "parent":
            lane_ids.add(lane)
    return lane_ids


def _lane_timestamp_overlap(turn_events: list[dict], lane_ids: set[str] | None = None) -> bool:
    """2+ lanes (optionally filtered) with overlapping timestamp_iso ranges."""
    lanes: dict[str, list[dict]] = {}
    for event in turn_events:
        key = _lane_key(event)
        if key == "parent":
            continue
        if lane_ids is not None and key not in lane_ids:
            continue
        lanes.setdefault(key, []).append(event)
    if len(lanes) < 2:
        return False

    ranges: list[tuple[datetime, datetime]] = []
    for lane_events in lanes.values():
        timestamps = [
            parsed
            for event in lane_events
            if event.get("timestamp_iso")
            for parsed in [_parse_iso(str(event.get("timestamp_iso")))]
            if parsed is not None
        ]
        if not timestamps:
            continue
        ranges.append((min(timestamps), max(timestamps)))
    if len(ranges) < 2:
        return False

    for i, (a_start, a_end) in enumerate(ranges):
        for b_start, b_end in ranges[i + 1 :]:
            if _intervals_overlap(a_start, a_end, b_start, b_end):
                return True
    return False


def _turn_has_parallel_spawn_batch(turn_events: list[dict]) -> bool:
    batch_ids = _batch_child_ids_from_turn(turn_events)
    if batch_ids is not None:
        return True
    return len(_inflight_spawn_batch_lane_ids(turn_events)) >= 2


def _turn_has_subagent_activity(turn_events: list[dict]) -> bool:
    return any(
        event.get("kind") in {"subagent_spawn", "subagent_return"}
        or event.get("tool") in {"spawn_subagent", "spawn_subagents"}
        for event in turn_events
    )


def _classify_turn(turn_events: list[dict]) -> tuple[bool, bool]:
    """Return (is_parallel, is_sequential) for one user-prompt turn."""
    if not _turn_has_subagent_activity(turn_events):
        return False, False

    batch_summaries = iter_spawn_subagents_batch_summaries(
        turn_events,
        since_event_idx=0,
        before_event_idx=len(turn_events),
    )
    if batch_summaries:
        if any(summary.overlap for summary in batch_summaries):
            return True, False
        return False, True

    batch_child_ids = _batch_child_ids_from_turn(turn_events)
    if batch_child_ids and _lane_timestamp_overlap(turn_events, batch_child_ids):
        return True, False

    inflight = _inflight_spawn_batch_lane_ids(turn_events)
    if len(inflight) >= 2 and _lane_timestamp_overlap(turn_events, inflight):
        return True, False

    if _turn_has_subagent_activity(turn_events):
        return False, True

    return False, False


def _turn_boundaries(events: list[dict]) -> list[tuple[int, int]]:
    boundaries = [0]
    for idx, event in enumerate(events):
        if event.get("kind") == "user_prompt" and idx > 0:
            boundaries.append(idx)
    boundaries.append(len(events))
    return [
        (boundaries[i], boundaries[i + 1]) for i in range(len(boundaries) - 1)
    ]


def _flags_from_turn_events(events: list[dict]) -> SubagentFlags:
    if not events:
        return SubagentFlags()

    has_subagents = any(_turn_has_subagent_activity(events[start:end]) for start, end in _turn_boundaries(events))
    if not has_subagents:
        has_subagents = _turn_has_subagent_activity(events)
    if not has_subagents:
        return SubagentFlags()

    has_parallel = False
    has_sequential = False
    for start, end in _turn_boundaries(events):
        is_parallel, is_sequential = _classify_turn(events[start:end])
        has_parallel = has_parallel or is_parallel
        has_sequential = has_sequential or is_sequential

    return SubagentFlags(
        has_subagents=True,
        has_parallel_subagents=has_parallel,
        has_sequential_subagents=has_sequential,
    )


def subagent_flags_from_db(db: Session, session_id: str) -> SubagentFlags:
    try:
        return _subagent_flags_from_db(db, session_id)
    except Exception:
        if find_jsonl_path(session_id) is not None:
            return subagent_flags_from_jsonl(session_id)
        return SubagentFlags()


def _subagent_flags_from_db(db: Session, session_id: str) -> SubagentFlags:
    if find_jsonl_path(session_id) is not None:
        return subagent_flags_from_jsonl(session_id)

    sub_rows = db.scalars(
        select(SubagentRow).where(SubagentRow.session_id == session_id)
    ).all()
    if not sub_rows:
        spawn_tools = {
            str(tool)
            for tool in db.scalars(
                select(ToolCallRow.tool)
                .where(ToolCallRow.session_id == session_id)
                .where(ToolCallRow.tool.in_(("spawn_subagent", "spawn_subagents")))
            ).all()
        }
        if not spawn_tools:
            return SubagentFlags()
        return SubagentFlags(
            has_subagents=True,
            has_parallel_subagents=False,
            has_sequential_subagents=bool(spawn_tools),
        )

    by_turn: dict[str | None, list[SubagentRow]] = {}
    for row in sub_rows:
        key = row.turn_id
        by_turn.setdefault(key, []).append(row)

    has_parallel = False
    has_sequential = False
    for rows in by_turn.values():
        if not rows:
            continue
        started_ends = [
            (_parse_iso(row.started_at), _parse_iso(row.ended_at))
            for row in rows
        ]
        intervals = [(s, e) for s, e in started_ends if s is not None and e is not None]
        if len(intervals) >= 2:
            overlap = False
            for i, (a_start, a_end) in enumerate(intervals):
                for b_start, b_end in intervals[i + 1 :]:
                    if _intervals_overlap(a_start, a_end, b_start, b_end):
                        overlap = True
                        break
                if overlap:
                    break
            if overlap and len(rows) == 2:
                has_parallel = True
            elif len(rows) >= 2:
                has_sequential = True
            else:
                has_sequential = True
        elif rows:
            has_sequential = True

    if not has_sequential:
        single_spawn = db.scalars(
            select(ToolCallRow.tool)
            .where(ToolCallRow.session_id == session_id)
            .where(ToolCallRow.tool == "spawn_subagent")
            .limit(1)
        ).first()
        if single_spawn is not None:
            has_sequential = True

    return SubagentFlags(
        has_subagents=True,
        has_parallel_subagents=has_parallel,
        has_sequential_subagents=has_sequential,
    )


def subagent_flags_from_jsonl(session_id: str) -> SubagentFlags:
    path = find_jsonl_path(session_id)
    if path is None:
        return SubagentFlags()
    return _flags_from_turn_events(read_jsonl_events(path))


def bulk_subagent_flags(db: Session | None, session_ids: list[str]) -> dict[str, SubagentFlags]:
    result: dict[str, SubagentFlags] = {sid: SubagentFlags() for sid in session_ids}
    for sid in session_ids:
        if find_jsonl_path(sid) is not None:
            result[sid] = subagent_flags_from_jsonl(sid)
        elif db is not None:
            result[sid] = subagent_flags_from_db(db, sid)
    return result
