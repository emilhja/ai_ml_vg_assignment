"""Per-session sub-agent usage tags for history filters."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from vg_agent.trace import parallel_subagent_summary

from ..models import SubagentRow, ToolCallRow
from ..paths import find_jsonl_path


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


def _turn_overlap_from_subagent_rows(rows: list[SubagentRow]) -> bool:
    if len(rows) < 2:
        return False
    intervals: list[tuple[datetime, datetime]] = []
    for row in rows:
        start = _parse_iso(row.started_at)
        end = _parse_iso(row.ended_at)
        if start is not None and end is not None:
            intervals.append((start, end))
    if len(intervals) < 2:
        return False
    for i, (a_start, a_end) in enumerate(intervals):
        for b_start, b_end in intervals[i + 1 :]:
            if _intervals_overlap(a_start, a_end, b_start, b_end):
                return True
    return False


def _flags_from_turn_events(events: list[dict]) -> SubagentFlags:
    if not events:
        return SubagentFlags()
    has_subagents = any(
        e.get("kind") in {"subagent_spawn", "subagent_return"}
        or e.get("tool") in {"spawn_subagent", "spawn_subagents"}
        for e in events
    )
    if not has_subagents:
        return SubagentFlags()

    has_parallel = False
    has_sequential = False
    boundaries = [0]
    for idx, event in enumerate(events):
        if event.get("kind") == "user_prompt" and idx > 0:
            boundaries.append(idx)
    boundaries.append(len(events))

    for turn_start in range(len(boundaries) - 1):
        start = boundaries[turn_start]
        end = boundaries[turn_start + 1]
        turn_events = events[start:end]
        summary = parallel_subagent_summary(turn_events, since_event_idx=0, before_event_idx=len(turn_events))
        if summary is None:
            if any(e.get("kind") == "subagent_return" for e in turn_events):
                has_sequential = True
            continue
        if summary.overlap:
            has_parallel = True
        else:
            has_sequential = True

    if has_subagents and not has_parallel:
        has_sequential = True

    return SubagentFlags(
        has_subagents=has_subagents,
        has_parallel_subagents=has_parallel,
        has_sequential_subagents=has_sequential,
    )


def subagent_flags_from_db(db: Session, session_id: str) -> SubagentFlags:
    sub_rows = db.scalars(
        select(SubagentRow).where(SubagentRow.session_id == session_id)
    ).all()
    if not sub_rows:
        spawn_tools = db.scalars(
            select(ToolCallRow.tool)
            .where(ToolCallRow.session_id == session_id)
            .where(ToolCallRow.tool.in_(("spawn_subagent", "spawn_subagents")))
        ).all()
        if not spawn_tools:
            return SubagentFlags()
        has_parallel = "spawn_subagents" in spawn_tools
        has_sequential = "spawn_subagent" in spawn_tools or not has_parallel
        return SubagentFlags(
            has_subagents=True,
            has_parallel_subagents=has_parallel,
            has_sequential_subagents=has_sequential,
        )

    by_turn: dict[str | None, list[SubagentRow]] = {}
    for row in sub_rows:
        key = row.turn_id
        by_turn.setdefault(key, []).append(row)

    has_parallel = any(_turn_overlap_from_subagent_rows(rows) for rows in by_turn.values() if len(rows) >= 2)
    has_sequential = len(sub_rows) == 1 or any(
        len(rows) >= 2 and not _turn_overlap_from_subagent_rows(rows) for rows in by_turn.values()
    )
    if not has_sequential:
        singles = db.scalars(
            select(ToolCallRow.tool)
            .where(ToolCallRow.session_id == session_id)
            .where(ToolCallRow.tool == "spawn_subagent")
            .limit(1)
        ).first()
        if singles is not None:
            has_sequential = True

    return SubagentFlags(
        has_subagents=True,
        has_parallel_subagents=has_parallel,
        has_sequential_subagents=has_sequential or not has_parallel,
    )


def subagent_flags_from_jsonl(session_id: str) -> SubagentFlags:
    path = find_jsonl_path(session_id)
    if path is None:
        return SubagentFlags()
    try:
        events: list[dict] = []
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                raw = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(raw, dict):
                events.append(raw)
    except OSError:
        return SubagentFlags()
    return _flags_from_turn_events(events)


def bulk_subagent_flags(db: Session | None, session_ids: list[str]) -> dict[str, SubagentFlags]:
    result: dict[str, SubagentFlags] = {sid: SubagentFlags() for sid in session_ids}
    if db is not None:
        for sid in session_ids:
            result[sid] = subagent_flags_from_db(db, sid)
        return result
    for sid in session_ids:
        result[sid] = subagent_flags_from_jsonl(sid)
    return result
