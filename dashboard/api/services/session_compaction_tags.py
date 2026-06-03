"""Per-session compaction tags for history filters."""

from __future__ import annotations

import json
from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models import CompactionRow, EventRow
from ..paths import find_jsonl_path
from .jsonl_io import read_jsonl_events


@dataclass(frozen=True)
class CompactionFlags:
    has_tool_compaction: bool = False
    has_context_compaction_auto: bool = False
    has_context_compaction_manual: bool = False


def _flags_from_events(events: list[dict]) -> CompactionFlags:
    has_tool = False
    has_auto = False
    has_manual = False
    for event in events:
        kind = event.get("kind")
        if kind == "compaction" and event.get("agent_id") == "parent":
            has_tool = True
        elif kind == "context_compaction":
            reason = str(event.get("reason") or "").lower()
            if reason == "manual":
                has_manual = True
            else:
                has_auto = True
    return CompactionFlags(
        has_tool_compaction=has_tool,
        has_context_compaction_auto=has_auto,
        has_context_compaction_manual=has_manual,
    )


def compaction_flags_from_jsonl(session_id: str) -> CompactionFlags:
    path = find_jsonl_path(session_id)
    if path is None:
        return CompactionFlags()
    return _flags_from_events(read_jsonl_events(path))


def compaction_flags_from_db(db: Session, session_id: str) -> CompactionFlags:
    compaction_count = db.scalar(
        select(func.count())
        .select_from(CompactionRow)
        .where(CompactionRow.session_id == session_id)
    )
    has_tool = bool(compaction_count and int(compaction_count) > 0)
    if not has_tool:
        event_count = db.scalar(
            select(func.count())
            .select_from(EventRow)
            .where(EventRow.session_id == session_id)
            .where(EventRow.kind == "compaction")
        )
        has_tool = bool(event_count and int(event_count) > 0)

    has_auto = False
    has_manual = False
    for payload_raw in db.scalars(
        select(EventRow.payload_json)
        .where(EventRow.session_id == session_id)
        .where(EventRow.kind == "context_compaction")
    ).all():
        if not payload_raw:
            continue
        try:
            data = json.loads(payload_raw)
        except json.JSONDecodeError:
            continue
        if not isinstance(data, dict):
            continue
        reason = str(data.get("reason") or "").lower()
        if reason == "manual":
            has_manual = True
        else:
            has_auto = True

    return CompactionFlags(
        has_tool_compaction=has_tool,
        has_context_compaction_auto=has_auto,
        has_context_compaction_manual=has_manual,
    )


def bulk_compaction_flags(db: Session | None, session_ids: list[str]) -> dict[str, CompactionFlags]:
    result: dict[str, CompactionFlags] = {sid: CompactionFlags() for sid in session_ids}
    for sid in session_ids:
        if find_jsonl_path(sid) is not None:
            result[sid] = compaction_flags_from_jsonl(sid)
        elif db is not None:
            result[sid] = compaction_flags_from_db(db, sid)
    return result
