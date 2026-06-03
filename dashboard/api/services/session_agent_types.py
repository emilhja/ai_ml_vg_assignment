"""Per-session agent_type tags for history filters and badges."""

from __future__ import annotations

import json

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import EventRow, SubagentRow
from ..paths import find_jsonl_path
from .jsonl_io import read_jsonl_events

KNOWN_AGENT_TYPES: tuple[str, ...] = (
    "parent",
    "explorer",
    "grilling",
    "coder",
    "reviewer",
    "compactor",
)


def _is_parent_agent(event: dict) -> bool:
    agent_id = str(event.get("agent_id") or "")
    if agent_id == "parent":
        return True
    if not agent_id and (
        event.get("agent_type") == "parent" or not event.get("parent_id")
    ):
        return True
    return False


def _event_agent_type(event: dict) -> str | None:
    raw = event.get("agent_type")
    if isinstance(raw, str) and raw:
        return raw
    payload = event.get("payload")
    if isinstance(payload, dict):
        p = payload.get("agent_type")
        if isinstance(p, str) and p:
            return p
    return None


def _match_agent_type(event: dict, agent_type: str) -> bool:
    if agent_type == "parent":
        return _is_parent_agent(event)
    if agent_type == "compactor":
        return (
            _event_agent_type(event) == "compactor"
            or event.get("kind") == "context_compaction"
        )
    return _event_agent_type(event) == agent_type


def _types_from_events(events: list[dict]) -> list[str]:
    found: set[str] = set()
    for event in events:
        for agent_type in KNOWN_AGENT_TYPES:
            if _match_agent_type(event, agent_type):
                found.add(agent_type)
    return [t for t in KNOWN_AGENT_TYPES if t in found]


def agent_types_from_jsonl(session_id: str) -> list[str]:
    path = find_jsonl_path(session_id)
    if path is None:
        return []
    return _types_from_events(read_jsonl_events(path))


def agent_types_from_db(db: Session, session_id: str) -> list[str]:
    found: set[str] = set()

    for row in db.scalars(
        select(EventRow).where(EventRow.session_id == session_id)
    ).all():
        event: dict = {
            "agent_id": row.agent_id,
            "agent_type": row.agent_type,
            "parent_id": row.parent_id,
            "kind": row.kind,
        }
        if row.payload_json:
            try:
                payload = json.loads(row.payload_json)
                if isinstance(payload, dict):
                    event["payload"] = payload
                    if not event.get("agent_type") and isinstance(
                        payload.get("agent_type"), str
                    ):
                        event["agent_type"] = payload["agent_type"]
            except json.JSONDecodeError:
                pass
        for agent_type in KNOWN_AGENT_TYPES:
            if _match_agent_type(event, agent_type):
                found.add(agent_type)

    for row in db.scalars(
        select(SubagentRow.agent_type).where(SubagentRow.session_id == session_id)
    ).all():
        if row and str(row) in KNOWN_AGENT_TYPES:
            found.add(str(row))

    return [t for t in KNOWN_AGENT_TYPES if t in found]


def bulk_agent_types(db: Session | None, session_ids: list[str]) -> dict[str, list[str]]:
    result: dict[str, list[str]] = {sid: [] for sid in session_ids}
    for sid in session_ids:
        if find_jsonl_path(sid) is not None:
            result[sid] = agent_types_from_jsonl(sid)
        elif db is not None:
            result[sid] = agent_types_from_db(db, sid)
    return result
