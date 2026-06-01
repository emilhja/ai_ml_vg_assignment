"""JSONL tailing and SSE event generation."""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import jsonl_path_for_session
from ..models import EventRow
from ..schemas import EventItem
from .sessions import event_row_to_item, grouping_fields_from_dict, load_events_from_jsonl


POLL_INTERVAL_SEC = 0.5


def tail_jsonl_new_events(path: Path, *, from_event_idx: int) -> list[dict]:
    if not path.is_file():
        return []
    events: list[dict] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(event, dict):
            continue
        idx = int(event.get("event_idx", -1))
        if idx > from_event_idx:
            events.append(event)
    return events


def dict_to_event_item(event: dict) -> EventItem:
    grouping = grouping_fields_from_dict(event)
    return EventItem(
        run_id=str(event.get("run_id") or ""),
        session_id=str(event.get("session_id")) if event.get("session_id") else None,
        event_idx=int(event.get("event_idx", 0)),
        kind=str(event.get("kind") or ""),
        timestamp_iso=str(event.get("timestamp_iso")) if event.get("timestamp_iso") else None,
        turn_id=grouping["turn_id"],
        turn_index=grouping["turn_index"],
        agent_id=str(event.get("agent_id")) if event.get("agent_id") else None,
        agent_type=str(event.get("agent_type")) if event.get("agent_type") else None,
        parent_id=grouping["parent_id"],
        child_agent_id=grouping["child_agent_id"],
        tool=str(event.get("tool")) if event.get("tool") else None,
        status=str(event.get("status")) if event.get("status") else None,
        tokens_in=int(event["tokens_in"]) if event.get("tokens_in") is not None else None,
        tokens_out=int(event["tokens_out"]) if event.get("tokens_out") is not None else None,
        cost_usd=float(event["cost_usd"]) if event.get("cost_usd") is not None else None,
        latency_ms=int(event["latency_ms"]) if event.get("latency_ms") is not None else None,
        payload=event,
    )


def fetch_sqlite_events_after(db: Session, session_id: str, from_event_idx: int) -> list[EventItem]:
    rows = db.scalars(
        select(EventRow)
        .where(EventRow.session_id == session_id)
        .where(EventRow.event_idx > from_event_idx)
        .order_by(EventRow.event_idx)
    ).all()
    return [event_row_to_item(row) for row in rows]


def latest_statusline_from_events(events: list[dict]) -> dict | None:
    for event in reversed(events):
        if event.get("kind") == "statusline":
            return event
    return None


async def sse_session_stream(
    db_factory,
    session_id: str,
    *,
    start_from: int = -1,
    max_ticks: int | None = None,
) -> AsyncIterator[tuple[str, dict]]:
    cursor = start_from
    jsonl_path = jsonl_path_for_session(session_id)
    all_cached: list[dict] = load_events_from_jsonl(session_id) if jsonl_path.is_file() else []
    ticks = 0

    while True:
        if max_ticks is not None and ticks >= max_ticks:
            return
        ticks += 1
        new_items: list[EventItem] = []
        jsonl_new = tail_jsonl_new_events(jsonl_path, from_event_idx=cursor)
        if jsonl_new:
            all_cached.extend(jsonl_new)
            for event in jsonl_new:
                new_items.append(dict_to_event_item(event))
                cursor = max(cursor, int(event.get("event_idx", cursor)))
        else:
            from ..config import schema_ready

            sqlite_new: list[EventItem] = []
            if schema_ready():
                with db_factory() as db:
                    sqlite_new = fetch_sqlite_events_after(db, session_id, cursor)
            for item in sqlite_new:
                new_items.append(item)
                cursor = max(cursor, item.event_idx)

        if new_items:
            yield "events", {"items": [item.model_dump() for item in new_items]}

        statusline = latest_statusline_from_events(all_cached)
        if statusline:
            yield "statusline", statusline

        for event in reversed(all_cached):
            if event.get("kind") == "run_end":
                yield "run_end", {
                    "final_status": event.get("final_status"),
                    "event_idx": event.get("event_idx"),
                }
                break

        yield "heartbeat", {}
        await asyncio.sleep(POLL_INTERVAL_SEC)
