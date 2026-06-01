from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from ..config import active_session_id_override, schema_ready
from ..db import get_db
from ..schemas import (
    ActiveSessionResponse,
    EventListResponse,
    SessionDetailResponse,
    SessionListResponse,
    SessionRenameRequest,
    SessionSummary,
)
from ..services.sessions import (
    detect_active_session_id,
    list_events,
    list_sessions,
    rename_session_display_name,
    session_detail,
)
from ..services.tail import sse_session_stream

router = APIRouter(prefix="/sessions", tags=["sessions"])


def _db_dep():
    if not schema_ready():
        yield None
        return
    with get_db() as db:
        yield db


@router.get("", response_model=SessionListResponse)
def get_sessions(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session | None = Depends(_db_dep),
) -> SessionListResponse:
    items, total = list_sessions(db, limit=limit, offset=offset)
    return SessionListResponse(items=items, total=total)


@router.get("/active", response_model=ActiveSessionResponse)
def get_active_session(db: Session | None = Depends(_db_dep)) -> ActiveSessionResponse:
    session_id = detect_active_session_id(db, active_session_id_override())
    if session_id is None:
        return ActiveSessionResponse(session_id=None)
    detail = session_detail(db, session_id) if db is not None else None
    events: list = []
    if db is not None:
        events, _ = list_events(db, session_id, from_event_idx=-1, limit=50)
    else:
        from ..services.sessions import load_events_from_jsonl
        from ..services.tail import dict_to_event_item

        raw = load_events_from_jsonl(session_id)[-50:]
        events = [dict_to_event_item(item) for item in raw]
    return ActiveSessionResponse(
        session_id=session_id,
        session=detail,
        recent_events=events,
    )


@router.get("/{session_id}", response_model=SessionDetailResponse)
def get_session(session_id: str, db: Session | None = Depends(_db_dep)) -> SessionDetailResponse:
    detail = session_detail(db, session_id)
    if detail is None:
        raise HTTPException(status_code=404, detail="session not found")
    return detail


@router.patch("/{session_id}", response_model=SessionSummary)
def patch_session(
    session_id: str,
    body: SessionRenameRequest,
    db: Session | None = Depends(_db_dep),
) -> SessionSummary:
    try:
        summary = rename_session_display_name(db, session_id, body.display_name)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if summary is None:
        raise HTTPException(status_code=404, detail="session not found")
    return summary


@router.get("/{session_id}/events", response_model=EventListResponse)
def get_session_events(
    session_id: str,
    from_event_idx: int = Query(-1),
    limit: int = Query(100, ge=1, le=500),
    db: Session | None = Depends(_db_dep),
) -> EventListResponse:
    items, has_more = list_events(db, session_id, from_event_idx=from_event_idx, limit=limit)
    next_idx = items[-1].event_idx if items else None
    return EventListResponse(items=items, has_more=has_more, next_from_event_idx=next_idx)


@router.get("/{session_id}/stream")
async def stream_session(session_id: str, request: Request) -> StreamingResponse:
    from_event_idx = int(request.query_params.get("from_event_idx", -1))
    last_event_id = request.headers.get("Last-Event-ID")
    if last_event_id and last_event_id.isdigit():
        from_event_idx = max(from_event_idx, int(last_event_id))

    max_ticks_param = request.query_params.get("max_ticks")
    max_ticks = int(max_ticks_param) if max_ticks_param and max_ticks_param.isdigit() else None

    async def event_generator():
        from ..db import get_db as db_ctx

        async for kind, payload in sse_session_stream(
            db_ctx,
            session_id,
            start_from=from_event_idx,
            max_ticks=max_ticks,
        ):
            event_id = ""
            if kind == "events" and payload.get("items"):
                event_id = str(payload["items"][-1].get("event_idx", ""))
            yield f"id: {event_id}\nevent: {kind}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
    )
