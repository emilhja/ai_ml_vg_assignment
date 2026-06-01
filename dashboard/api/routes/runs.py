from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import schema_ready
from ..db import get_db
from ..models import (
    ApprovalRow,
    CompactionRow,
    EventRow,
    ModelCallRow,
    RedactionRow,
    RunRow,
    SubagentRow,
    ToolCallRow,
    TurnRow,
)
from ..schemas import (
    ApprovalItem,
    BudgetEventItem,
    CompactionItem,
    ContextResponse,
    ModelCallItem,
    ParallelResponse,
    RedactionItem,
    SafetyResponse,
    SubagentItem,
    TimelineResponse,
    ToolCallItem,
    TurnSummary,
)
from ..services.context import (
    build_context_response,
    build_parallel_response,
    max_parent_step,
    steps_with_compacted_context,
)
from ..services.sessions import load_events_for_run

router = APIRouter(prefix="/runs", tags=["runs"])


def _db_dep():
    if not schema_ready():
        yield None
        return
    with get_db() as db:
        yield db


def _get_run(db: Session | None, run_id: str) -> RunRow | None:
    if db is None:
        return None
    return db.get(RunRow, run_id)


@router.get("/{run_id}/timeline", response_model=TimelineResponse)
def run_timeline(run_id: str, db: Session | None = Depends(_db_dep)) -> TimelineResponse:
    run = _get_run(db, run_id)
    events = load_events_for_run(db, run_id)
    if run is None and not events:
        raise HTTPException(status_code=404, detail="run not found")
    session_id = (run.session_id if run is not None else None) or (
        str(events[0].get("session_id")) if events else None
    )

    turn_summaries: list[TurnSummary]
    if db is not None and run is not None:
        turn_rows = db.scalars(
            select(TurnRow).where(TurnRow.run_id == run_id).order_by(TurnRow.turn_index)
        ).all()
        turn_summaries = [
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
            for t in turn_rows
        ]
        models = db.scalars(select(ModelCallRow).where(ModelCallRow.run_id == run_id)).all()
        tools = db.scalars(select(ToolCallRow).where(ToolCallRow.run_id == run_id)).all()
        subs = db.scalars(select(SubagentRow).where(SubagentRow.run_id == run_id)).all()
    else:
        turn_summaries = []
        turn_index = 0
        for event in events:
            if event.get("kind") != "user_prompt":
                continue
            turn_index += 1
            turn_summaries.append(
                TurnSummary(
                    turn_id=str(event.get("turn_id") or f"{run_id}:turn:{turn_index}"),
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
        models = []
        tools = []
        subs = []

    return TimelineResponse(
        run_id=run_id,
        session_id=session_id,
        turns=turn_summaries,
        model_calls=[
            ModelCallItem(
                model_call_id=m.model_call_id,
                agent_id=m.agent_id,
                step_idx=m.step_idx,
                model_id=m.model_id,
                tokens_in=m.tokens_in,
                tokens_out=m.tokens_out,
                cost_usd=m.cost_usd,
                latency_ms=m.latency_ms,
                status=m.status,
                started_at=m.started_at,
                ended_at=m.ended_at,
            )
            for m in models
        ],
        tool_calls=[
            ToolCallItem(
                tool_call_id=t.tool_call_id,
                agent_id=t.agent_id,
                tool=t.tool,
                args_summary=t.args_summary,
                target_path=t.target_path,
                latency_ms=t.latency_ms,
                status=t.status,
                error_type=t.error_type,
                error_message=t.error_message,
                started_at=t.started_at,
                ended_at=t.ended_at,
            )
            for t in tools
        ],
        subagents=[
            SubagentItem(
                subagent_id=s.subagent_id,
                agent_type=s.agent_type,
                question=s.question,
                started_at=s.started_at,
                ended_at=s.ended_at,
                duration_ms=s.duration_ms,
                status=s.status,
                total_tokens=s.total_tokens,
            )
            for s in subs
        ],
    )


@router.get("/{run_id}/context", response_model=ContextResponse)
def run_context(
    run_id: str,
    step_idx: int = Query(0, ge=0),
    db: Session | None = Depends(_db_dep),
) -> ContextResponse:
    events = load_events_for_run(db, run_id)
    if not events:
        raise HTTPException(status_code=404, detail="no events for run")
    max_step = max_parent_step(events)
    if step_idx > max_step:
        step_idx = max_step
    return build_context_response(run_id, events, step_idx)


@router.get("/{run_id}/context/max-step")
def run_context_max_step(run_id: str, db: Session | None = Depends(_db_dep)) -> dict[str, object]:
    events = load_events_for_run(db, run_id)
    if not events:
        raise HTTPException(status_code=404, detail="no events for run")
    return {
        "max_step_idx": max_parent_step(events),
        "compaction_steps": steps_with_compacted_context(events),
    }


@router.get("/{run_id}/parallel", response_model=ParallelResponse)
def run_parallel(run_id: str, db: Session | None = Depends(_db_dep)) -> ParallelResponse:
    events = load_events_for_run(db, run_id)
    if not events:
        return ParallelResponse(run_id=run_id, turns=[])
    return build_parallel_response(run_id, events)


@router.get("/{run_id}/safety", response_model=SafetyResponse)
def run_safety(run_id: str, db: Session | None = Depends(_db_dep)) -> SafetyResponse:
    approvals: list = []
    compactions: list = []
    redactions: list = []
    budget_events: list[BudgetEventItem] = []

    if db is not None:
        approvals = db.scalars(select(ApprovalRow).where(ApprovalRow.run_id == run_id)).all()
        compactions = db.scalars(select(CompactionRow).where(CompactionRow.run_id == run_id)).all()
        redactions = db.scalars(select(RedactionRow).where(RedactionRow.run_id == run_id)).all()
        budget_rows = db.scalars(
            select(EventRow).where(EventRow.run_id == run_id).where(EventRow.kind == "budget_event")
        ).all()
        for row in budget_rows:
            reason = None
            try:
                payload = json.loads(row.payload_json)
                reason = str(payload.get("budget_reason") or "")
            except json.JSONDecodeError:
                pass
            budget_events.append(
                BudgetEventItem(
                    event_idx=int(row.event_idx),
                    budget_reason=reason,
                    timestamp_iso=row.timestamp_iso,
                )
            )

    if not approvals and not compactions and not redactions and not budget_events:
        for event in load_events_for_run(db, run_id):
            kind = event.get("kind")
            idx = int(event.get("event_idx") or 0)
            if kind == "approval":
                approvals.append(event)
            elif kind == "compaction":
                compactions.append(event)
            elif kind == "redaction":
                redactions.append(event)
            elif kind == "budget_event":
                budget_events.append(
                    BudgetEventItem(
                        event_idx=idx,
                        budget_reason=str(event.get("budget_reason") or ""),
                        timestamp_iso=str(event.get("timestamp_iso") or ""),
                    )
                )
    def _approval_items() -> list[ApprovalItem]:
        items: list[ApprovalItem] = []
        for a in approvals:
            if isinstance(a, ApprovalItem):
                items.append(a)
            elif hasattr(a, "approval_id"):
                items.append(
                    ApprovalItem(
                        approval_id=a.approval_id,
                        tool=a.tool,
                        decision=a.decision,
                        args_summary=a.args_summary,
                        timestamp_iso=a.timestamp_iso,
                    )
                )
            elif isinstance(a, dict):
                items.append(
                    ApprovalItem(
                        approval_id=str(a.get("approval_id") or a.get("event_idx") or ""),
                        tool=str(a.get("tool")) if a.get("tool") else None,
                        decision=str(a.get("decision")) if a.get("decision") else None,
                        args_summary=None,
                        timestamp_iso=str(a.get("timestamp_iso")) if a.get("timestamp_iso") else None,
                    )
                )
        return items

    def _compaction_items() -> list[CompactionItem]:
        items: list[CompactionItem] = []
        for c in compactions:
            if hasattr(c, "compaction_id"):
                items.append(
                    CompactionItem(
                        compaction_id=c.compaction_id,
                        event_idx=c.event_idx,
                        original_event_idx=c.original_event_idx,
                        before_tokens=c.before_tokens,
                        after_tokens=c.after_tokens,
                        summary=c.summary,
                    )
                )
            elif isinstance(c, dict):
                items.append(
                    CompactionItem(
                        compaction_id=str(c.get("compaction_id") or c.get("event_idx") or ""),
                        event_idx=int(c["event_idx"]) if c.get("event_idx") is not None else None,
                        original_event_idx=int(c["original_event_idx"])
                        if c.get("original_event_idx") is not None
                        else None,
                        before_tokens=int(c["before_tokens"]) if c.get("before_tokens") is not None else None,
                        after_tokens=int(c["after_tokens"]) if c.get("after_tokens") is not None else None,
                        summary=str(c.get("summary")) if c.get("summary") else None,
                    )
                )
        return items

    def _redaction_items() -> list[RedactionItem]:
        items: list[RedactionItem] = []
        for r in redactions:
            if hasattr(r, "redaction_id"):
                items.append(
                    RedactionItem(
                        redaction_id=r.redaction_id,
                        event_idx=r.event_idx,
                        pattern=r.pattern,
                        count=r.count,
                    )
                )
            elif isinstance(r, dict):
                items.append(
                    RedactionItem(
                        redaction_id=str(r.get("redaction_id") or r.get("event_idx") or ""),
                        event_idx=int(r["event_idx"]) if r.get("event_idx") is not None else None,
                        pattern=str(r.get("pattern")) if r.get("pattern") else None,
                        count=int(r["count"]) if r.get("count") is not None else None,
                    )
                )
        return items

    return SafetyResponse(
        run_id=run_id,
        approvals=_approval_items(),
        compactions=_compaction_items(),
        redactions=_redaction_items(),
        budget_events=budget_events,
    )
