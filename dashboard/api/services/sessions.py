"""Session listing and detail queries."""

from __future__ import annotations

import json
from pathlib import Path

from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from ..config import jsonl_path_for_session
from ..db import get_engine
from ..metadata import load_all_display_names, set_display_name
from ..paths import all_traces_dirs, find_jsonl_path, mtime_iso
from .session_agent_types import bulk_agent_types
from .session_compaction_tags import bulk_compaction_flags
from .session_tags import bulk_subagent_flags
from .trace_backfill import ensure_session_mirrored
from ..models import EventRow, RunRow, SessionRow, TurnRow
from ..schemas import (
    EventItem,
    RunSummary,
    SessionDetailResponse,
    SessionSummary,
    TurnSummary,
)


def _prompt_snippet(db: Session, session_id: str) -> str | None:
    row = db.execute(
        select(TurnRow.prompt)
        .where(TurnRow.session_id == session_id)
        .order_by(desc(TurnRow.turn_index))
        .limit(1)
    ).scalar_one_or_none()
    if not row:
        return None
    text = str(row)
    return text[:120] + ("…" if len(text) > 120 else "")


def session_to_summary(
    row: SessionRow,
    db: Session,
    *,
    display_names: dict[str, str] | None = None,
) -> SessionSummary:
    name = None
    if display_names is not None:
        name = display_names.get(row.session_id)
    return SessionSummary(
        session_id=row.session_id,
        display_name=name,
        first_seen_at=row.first_seen_at,
        last_seen_at=row.last_seen_at,
        status=row.status,
        run_count=int(row.run_count or 0),
        total_turns=int(row.total_turns or 0),
        total_tokens=int(row.total_tokens or 0),
        total_cost_usd=float(row.total_cost_usd or 0.0),
        last_prompt_snippet=_prompt_snippet(db, row.session_id),
    )


def _quick_jsonl_summary(
    session_id: str,
    path: Path,
    *,
    display_names: dict[str, str] | None = None,
) -> SessionSummary:
    """Fast index row for history lists — does not read the whole file."""
    last_seen = mtime_iso(path)
    first_seen = last_seen
    last_prompt: str | None = None
    try:
        with path.open(encoding="utf-8") as handle:
            for _ in range(30):
                line = handle.readline()
                if not line:
                    break
                line = line.strip()
                if not line:
                    continue
                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if not isinstance(event, dict):
                    continue
                ts = event.get("timestamp_iso")
                if isinstance(ts, str):
                    first_seen = ts
                if event.get("kind") == "user_prompt":
                    prompt = str(event.get("prompt") or "")
                    if prompt:
                        last_prompt = prompt
                break
    except OSError:
        pass
    snippet = None
    if last_prompt:
        snippet = last_prompt[:120] + ("…" if len(last_prompt) > 120 else "")
    return SessionSummary(
        session_id=session_id,
        display_name=display_names.get(session_id) if display_names else None,
        first_seen_at=first_seen,
        last_seen_at=last_seen,
        status="jsonl_only",
        run_count=1,
        total_turns=0,
        total_tokens=0,
        total_cost_usd=0.0,
        last_prompt_snippet=snippet,
    )


def _summarize_jsonl_session(
    session_id: str,
    *,
    display_names: dict[str, str] | None = None,
) -> SessionSummary | None:
    """Full parse of JSONL for session detail (can be slow on large traces)."""
    path = find_jsonl_path(session_id)
    if path is None:
        return None
    first_seen: str | None = None
    last_seen: str | None = None
    last_prompt: str | None = None
    turns = 0
    status = "jsonl_only"
    total_tokens = 0
    total_cost = 0.0
    try:
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
            ts = event.get("timestamp_iso")
            if isinstance(ts, str):
                if first_seen is None:
                    first_seen = ts
                last_seen = ts
            kind = event.get("kind")
            if kind == "user_prompt":
                turns += 1
                prompt = str(event.get("prompt") or "")
                if prompt:
                    last_prompt = prompt
            elif kind == "run_end":
                status = str(event.get("final_status") or status)
            elif kind == "assistant_step":
                total_tokens += int(event.get("tokens_in") or 0) + int(event.get("tokens_out") or 0)
                total_cost += float(event.get("cost_usd") or event.get("usd") or 0.0)
    except OSError:
        return None
    if first_seen is None:
        try:
            mtime = path.stat().st_mtime
            from datetime import datetime, timezone

            iso = datetime.fromtimestamp(mtime, tz=timezone.utc).isoformat()
            first_seen = last_seen = iso
        except OSError:
            first_seen = last_seen = None
    snippet = None
    if last_prompt:
        snippet = last_prompt[:120] + ("…" if len(last_prompt) > 120 else "")
    return SessionSummary(
        session_id=session_id,
        display_name=display_names.get(session_id) if display_names else None,
        first_seen_at=first_seen,
        last_seen_at=last_seen,
        status=status,
        run_count=1,
        total_turns=turns,
        total_tokens=total_tokens,
        total_cost_usd=round(total_cost, 6),
        last_prompt_snippet=snippet,
    )


def _engine_optional():
    try:
        from ..metadata import ensure_metadata_table

        engine = get_engine()
        ensure_metadata_table(engine)
        return engine
    except RuntimeError:
        return None


def _discover_jsonl_session_ids() -> list[str]:
    ids: set[str] = set()
    for directory in all_traces_dirs():
        if not directory.is_dir():
            continue
        for path in directory.glob("*.jsonl"):
            if path.stem and path.stat().st_size > 0:
                ids.add(path.stem)
    return sorted(ids)


def list_sessions(
    db: Session | None,
    *,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[SessionSummary], int]:
    """Merge SQLite sessions with JSONL files not mirrored to the DB."""
    by_id: dict[str, SessionSummary] = {}
    display_names = load_all_display_names(_engine_optional())

    if db is not None:
        try:
            rows = db.scalars(select(SessionRow).order_by(desc(SessionRow.last_seen_at))).all()
        except Exception:
            rows = []
        for row in rows:
            by_id[row.session_id] = session_to_summary(row, db, display_names=display_names)

    for session_id in _discover_jsonl_session_ids():
        if session_id in by_id:
            continue
        if db is not None:
            ensure_session_mirrored(db, session_id)
            row = get_session(db, session_id)
            if row is not None:
                by_id[session_id] = session_to_summary(row, db, display_names=display_names)
                continue
        path = find_jsonl_path(session_id)
        if path is not None:
            by_id[session_id] = _quick_jsonl_summary(
                session_id, path, display_names=display_names
            )

    merged = sorted(
        by_id.values(),
        key=lambda item: item.last_seen_at or item.first_seen_at or "",
        reverse=True,
    )
    session_ids = [item.session_id for item in merged]
    try:
        flags_by_id = bulk_subagent_flags(db, session_ids)
        compaction_by_id = bulk_compaction_flags(db, session_ids)
        agent_types_by_id = bulk_agent_types(db, session_ids)
    except Exception:
        from ..db import mark_sqlite_unusable
        from .session_compaction_tags import CompactionFlags
        from .session_tags import SubagentFlags

        mark_sqlite_unusable()
        flags_by_id = {sid: SubagentFlags() for sid in session_ids}
        compaction_by_id = {sid: CompactionFlags() for sid in session_ids}
        agent_types_by_id = {sid: [] for sid in session_ids}
    enriched: list[SessionSummary] = []
    for item in merged:
        flags = flags_by_id.get(item.session_id)
        compaction = compaction_by_id.get(item.session_id)
        agent_types = agent_types_by_id.get(item.session_id)
        updates: dict[str, object] = {}
        if flags is not None:
            updates.update(
                {
                    "has_subagents": flags.has_subagents,
                    "has_parallel_subagents": flags.has_parallel_subagents,
                    "has_sequential_subagents": flags.has_sequential_subagents,
                }
            )
        if compaction is not None:
            updates.update(
                {
                    "has_tool_compaction": compaction.has_tool_compaction,
                    "has_context_compaction_auto": compaction.has_context_compaction_auto,
                    "has_context_compaction_manual": compaction.has_context_compaction_manual,
                }
            )
        if agent_types is not None:
            updates["agent_types_present"] = agent_types
        enriched.append(item.model_copy(update=updates) if updates else item)
    total = len(enriched)
    page = enriched[offset : offset + limit]
    return page, total


def get_session(db: Session, session_id: str) -> SessionRow | None:
    return db.get(SessionRow, session_id)


def session_exists(db: Session | None, session_id: str) -> bool:
    if db is not None and get_session(db, session_id) is not None:
        return True
    return find_jsonl_path(session_id) is not None


def rename_session_display_name(
    db: Session | None,
    session_id: str,
    display_name: str | None,
) -> SessionSummary | None:
    if not session_exists(db, session_id):
        return None
    engine = _engine_optional()
    set_display_name(engine, session_id, display_name)
    names = load_all_display_names(engine)
    if db is not None:
        row = get_session(db, session_id)
        if row is not None:
            return session_to_summary(row, db, display_names=names)
    return _summarize_jsonl_session(session_id, display_names=names)


def session_detail_from_jsonl(session_id: str) -> SessionDetailResponse | None:
    names = load_all_display_names(_engine_optional())
    summary = _summarize_jsonl_session(session_id, display_names=names)
    events = load_events_from_jsonl(session_id)
    if summary is None or not events:
        return None
    run_id = str(events[0].get("run_id") or session_id)
    turns: list[TurnSummary] = []
    turn_index = 0
    for event in events:
        if event.get("kind") != "user_prompt":
            continue
        turn_index += 1
        turns.append(
            TurnSummary(
                turn_id=str(event.get("turn_id") or f"{session_id}:turn:{turn_index}"),
                run_id=run_id,
                turn_index=turn_index,
                prompt=str(event.get("prompt") or ""),
                status="ok",
                duration_ms=None,
                total_tokens=0,
                total_cost_usd=0.0,
                total_tool_calls=0,
                error_type=None,
            )
        )
    return SessionDetailResponse(
        session=summary,
        runs=[
            RunSummary(
                run_id=run_id,
                session_id=session_id,
                started_at=summary.first_seen_at,
                ended_at=summary.last_seen_at,
                duration_ms=None,
                final_status=summary.status,
                total_tokens=summary.total_tokens,
                total_cost_usd=summary.total_cost_usd,
            )
        ],
        turns=turns,
        jsonl_path=str(jsonl_path_for_session(session_id)),
    )


def session_detail(db: Session | None, session_id: str) -> SessionDetailResponse | None:
    if db is not None:
        if get_session(db, session_id) is None:
            ensure_session_mirrored(db, session_id)
        row = get_session(db, session_id)
        if row is not None:
            return _session_detail_from_sqlite(db, session_id, row)
    return session_detail_from_jsonl(session_id)


def _session_detail_from_sqlite(
    db: Session, session_id: str, row: SessionRow
) -> SessionDetailResponse:
    display_names = load_all_display_names(_engine_optional())
    runs = db.scalars(
        select(RunRow).where(RunRow.session_id == session_id).order_by(RunRow.started_at)
    ).all()
    turns = db.scalars(
        select(TurnRow).where(TurnRow.session_id == session_id).order_by(TurnRow.turn_index)
    ).all()
    return SessionDetailResponse(
        session=session_to_summary(row, db, display_names=display_names),
        runs=[
            RunSummary(
                run_id=r.run_id,
                session_id=r.session_id,
                started_at=r.started_at,
                ended_at=r.ended_at,
                duration_ms=r.duration_ms,
                final_status=r.final_status,
                total_tokens=int(r.total_tokens or 0),
                total_cost_usd=float(r.total_cost_usd or 0.0),
            )
            for r in runs
        ],
        turns=[
            TurnSummary(
                turn_id=t.turn_id,
                run_id=t.run_id,
                turn_index=t.turn_index,
                prompt=t.prompt,
                status=t.status,
                duration_ms=t.duration_ms,
                total_tokens=int(t.total_tokens or 0),
                total_cost_usd=float(t.total_cost_usd or 0.0),
                total_tool_calls=int(t.total_tool_calls or 0),
                error_type=t.error_type,
            )
            for t in turns
        ],
        jsonl_path=str(jsonl_path_for_session(session_id)),
    )


def grouping_fields_from_dict(event: dict) -> dict[str, str | int | None]:
    kind = str(event.get("kind") or "")
    child_agent_id: str | None = None
    if kind in {"subagent_spawn", "subagent_return"}:
        raw = event.get("child_agent_id") or event.get("agent_id")
        child_agent_id = str(raw) if raw else None
    turn_id = event.get("turn_id")
    turn_index = event.get("turn_index")
    parent_id = event.get("parent_id")
    return {
        "turn_id": str(turn_id) if turn_id is not None else None,
        "turn_index": int(turn_index) if turn_index is not None else None,
        "parent_id": str(parent_id) if parent_id is not None else None,
        "child_agent_id": child_agent_id,
    }


def merge_run_events_dicts(sqlite_events: list[dict], jsonl_events: list[dict]) -> list[dict]:
    """Merge run events by event_idx; JSONL wins on conflict (audit source)."""
    by_idx: dict[int, dict] = {}
    for event in sqlite_events:
        idx = int(event.get("event_idx", -1))
        if idx >= 0:
            by_idx[idx] = event
    for event in jsonl_events:
        idx = int(event.get("event_idx", -1))
        if idx >= 0:
            by_idx[idx] = event
    return [by_idx[i] for i in sorted(by_idx)]


def merge_event_items(sqlite_items: list[EventItem], jsonl_events: list[dict]) -> list[EventItem]:
    """Merge EventItem rows with JSONL dicts; JSONL wins on conflict."""
    from ..services.tail import dict_to_event_item

    by_idx: dict[int, EventItem] = {item.event_idx: item for item in sqlite_items}
    for event in jsonl_events:
        idx = int(event.get("event_idx", -1))
        if idx >= 0:
            by_idx[idx] = dict_to_event_item(event)
    return [by_idx[i] for i in sorted(by_idx)]


def _jsonl_events_for_run(run_id: str) -> list[dict]:
    direct = load_events_from_jsonl(run_id)
    if direct:
        return direct
    for session_id in _discover_jsonl_session_ids():
        events = load_events_from_jsonl(session_id)
        if not events:
            continue
        if str(events[0].get("run_id") or session_id) == run_id:
            return events
    return []


def event_row_to_item(row: EventRow) -> EventItem:
    payload: dict = {}
    try:
        payload = json.loads(row.payload_json)
    except json.JSONDecodeError:
        payload = {}
    grouping = grouping_fields_from_dict(payload)
    if row.turn_id:
        grouping["turn_id"] = row.turn_id
    if row.parent_id:
        grouping["parent_id"] = row.parent_id
    return EventItem(
        run_id=row.run_id,
        session_id=row.session_id,
        event_idx=int(row.event_idx),
        kind=row.kind,
        timestamp_iso=row.timestamp_iso,
        turn_id=grouping["turn_id"],
        turn_index=grouping["turn_index"],
        agent_id=row.agent_id,
        agent_type=payload.get("agent_type") if isinstance(payload.get("agent_type"), str) else None,
        parent_id=grouping["parent_id"],
        child_agent_id=grouping["child_agent_id"],
        tool=row.tool,
        status=row.status,
        tokens_in=row.tokens_in,
        tokens_out=row.tokens_out,
        cost_usd=row.cost_usd,
        latency_ms=row.latency_ms,
        payload=payload,
    )


def list_events(
    db: Session | None,
    session_id: str,
    *,
    from_event_idx: int = -1,
    limit: int = 100,
) -> tuple[list[EventItem], bool]:
    from ..services.tail import dict_to_event_item

    jsonl_raw = load_events_from_jsonl(session_id)
    sqlite_items: list[EventItem] = []
    if db is not None:
        rows = db.scalars(
            select(EventRow)
            .where(EventRow.session_id == session_id)
            .where(EventRow.event_idx > from_event_idx)
            .order_by(EventRow.event_idx)
        ).all()
        sqlite_items = [event_row_to_item(row) for row in rows]

    if sqlite_items and jsonl_raw:
        merged = merge_event_items(sqlite_items, jsonl_raw)
    elif sqlite_items:
        merged = sqlite_items
    elif jsonl_raw:
        merged = [dict_to_event_item(event) for event in jsonl_raw]
    else:
        return [], False

    filtered = [item for item in merged if item.event_idx > from_event_idx]
    filtered.sort(key=lambda item: item.event_idx)
    has_more = len(filtered) > limit
    page = filtered[:limit]
    return page, has_more


def _parse_ts(value: str | None) -> float:
    if not value:
        return 0.0
    try:
        from datetime import datetime

        return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return 0.0


def detect_active_session_id(db: Session | None, override: str | None) -> str | None:
    if override:
        return override
    candidates: list[tuple[float, str]] = []
    if db is not None:
        try:
            rows = db.execute(
                select(SessionRow.session_id, SessionRow.last_seen_at).where(
                    SessionRow.status == "running"
                )
            ).all()
        except Exception:
            rows = []
        for session_id, last_seen in rows:
            score = _parse_ts(str(last_seen) if last_seen else None)
            candidates.append((score, str(session_id)))
    for directory in all_traces_dirs():
        if not directory.is_dir():
            continue
        for path in directory.glob("*.jsonl"):
            if path.stat().st_size <= 0:
                continue
            try:
                candidates.append((path.stat().st_mtime, path.stem))
            except OSError:
                continue
    if not candidates:
        return None
    candidates.sort(key=lambda item: item[0], reverse=True)
    return candidates[0][1]


def load_events_for_run(db: Session | None, run_id: str) -> list[dict]:
    jsonl_events = _jsonl_events_for_run(run_id)
    sqlite_events: list[dict] = []
    if db is not None:
        rows = db.scalars(
            select(EventRow).where(EventRow.run_id == run_id).order_by(EventRow.event_idx)
        ).all()
        for row in rows:
            try:
                payload = json.loads(row.payload_json)
            except json.JSONDecodeError:
                payload = {}
            if isinstance(payload, dict):
                sqlite_events.append(payload)

    if sqlite_events or jsonl_events:
        return merge_run_events_dicts(sqlite_events, jsonl_events)
    return []


def load_events_from_jsonl(session_id: str) -> list[dict]:
    path = jsonl_path_for_session(session_id)
    if not path.is_file():
        return []
    events: list[dict] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(item, dict):
            events.append(item)
    return events
