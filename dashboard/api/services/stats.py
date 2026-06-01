"""Statistics rollups from SQLite."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from vg_agent import config as agent_config

from ..config import daily_spend_path
from ..models import ModelCallRow, RunRow, SubagentRow, ToolCallRow, TurnRow
from ..schemas import (
    DailyFinOpsResponse,
    DailySeriesPoint,
    ExpensiveTurnItem,
    PromptLeaderboardItem,
    StatsBreakdownItem,
    StatsResponse,
    ToolErrorGroup,
    ToolErrorOccurrence,
    ToolErrorsDrillResponse,
    ToolUsageItem,
)

_PROMPT_SNIPPET_LEN = 120
_OCCURRENCES_PER_TOOL = 5


def _range_start(range_key: str) -> datetime:
    now = datetime.now(timezone.utc)
    if range_key == "today":
        return now.replace(hour=0, minute=0, second=0, microsecond=0)
    if range_key == "7d":
        return now - timedelta(days=7)
    if range_key == "30d":
        return now - timedelta(days=30)
    return now - timedelta(days=7)


def _parse_ts(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _in_range(started_at: str | None, start: datetime) -> bool:
    return (_parse_ts(started_at) or datetime.min.replace(tzinfo=timezone.utc)) >= start


def _prompt_snippet(text: str, max_len: int = _PROMPT_SNIPPET_LEN) -> str:
    stripped = text.strip()
    if len(stripped) <= max_len:
        return stripped
    return stripped[: max_len - 1] + "…"


def _group_prompts(
    rows: list[tuple[str, str | None]],
) -> list[PromptLeaderboardItem]:
    """Group (text, session_id) pairs by normalized prompt text."""
    groups: dict[str, dict[str, object]] = {}
    for text, session_id in rows:
        if not text.strip():
            continue
        key = text.strip().lower()
        entry = groups.setdefault(
            key,
            {"count": 0, "label": text, "sample_session_id": session_id},
        )
        entry["count"] = int(entry["count"]) + 1
        if len(text) > len(str(entry["label"])):
            entry["label"] = text
        if session_id and not entry.get("sample_session_id"):
            entry["sample_session_id"] = session_id

    items = [
        PromptLeaderboardItem(
            label=_prompt_snippet(str(g["label"])),
            count=int(g["count"]),
            sample_session_id=str(g["sample_session_id"]) if g.get("sample_session_id") else None,
        )
        for g in groups.values()
    ]
    return sorted(items, key=lambda p: -p.count)[:10]


def _tool_error_occurrence(row: ToolCallRow) -> ToolErrorOccurrence:
    return ToolErrorOccurrence(
        tool_call_id=row.tool_call_id,
        session_id=row.session_id or "",
        run_id=row.run_id or "",
        turn_id=row.turn_id,
        error_type=row.error_type,
        error_message=row.error_message,
        started_at=row.started_at,
    )


def _failed_tool_rows(db: Session, start: datetime) -> list[ToolCallRow]:
    rows = db.scalars(select(ToolCallRow).where(ToolCallRow.status != "ok")).all()
    return [r for r in rows if _in_range(r.started_at, start)]


def compute_tool_errors_drill(
    db: Session,
    range_key: str,
    tool: str,
    *,
    limit: int = 50,
    offset: int = 0,
) -> ToolErrorsDrillResponse:
    start = _range_start(range_key)
    rows = [r for r in _failed_tool_rows(db, start) if (r.tool or "unknown") == tool]
    rows.sort(key=lambda r: r.started_at or "", reverse=True)
    total = len(rows)
    page = rows[offset : offset + limit]
    return ToolErrorsDrillResponse(
        tool=tool,
        range=range_key,
        total=total,
        items=[_tool_error_occurrence(r) for r in page],
    )


def compute_stats(db: Session, range_key: str) -> StatsResponse:
    start = _range_start(range_key)
    runs = db.scalars(select(RunRow)).all()
    filtered_runs = [r for r in runs if _in_range(r.started_at, start)]

    total_tokens = sum(int(r.total_tokens or 0) for r in filtered_runs)
    total_cost = sum(float(r.total_cost_usd or 0.0) for r in filtered_runs)
    turns = db.scalars(select(TurnRow)).all()
    filtered_turns = [t for t in turns if t.started_at is not None and _in_range(t.started_at, start)]
    errors = sum(1 for t in filtered_turns if t.status not in {None, "ok", "running"})
    error_rate = (errors / len(filtered_turns)) if filtered_turns else 0.0

    by_day: dict[str, DailySeriesPoint] = {}
    for run in filtered_runs:
        day = (run.started_at or "")[:10] or "unknown"
        point = by_day.setdefault(day, DailySeriesPoint(date=day))
        point.runs += 1
        point.tokens += int(run.total_tokens or 0)
        point.cost_usd += float(run.total_cost_usd or 0.0)

    model_rows = db.scalars(select(ModelCallRow)).all()
    by_model: dict[str, StatsBreakdownItem] = {}
    for row in model_rows:
        if not _in_range(row.started_at, start):
            continue
        label = row.model_id or "unknown"
        item = by_model.setdefault(label, StatsBreakdownItem(label=label))
        item.count += 1
        item.tokens += int(row.tokens_in or 0) + int(row.tokens_out or 0)
        item.cost_usd += float(row.cost_usd or 0.0)

    by_agent: dict[str, StatsBreakdownItem] = {}
    for row in model_rows:
        if not _in_range(row.started_at, start):
            continue
        agent = row.agent_id or "parent"
        item = by_agent.setdefault(agent, StatsBreakdownItem(label=agent))
        item.count += 1
        item.tokens += int(row.tokens_in or 0) + int(row.tokens_out or 0)
        item.cost_usd += float(row.cost_usd or 0.0)

    all_tool_rows = db.scalars(select(ToolCallRow)).all()
    tool_usage: dict[str, dict[str, object]] = {}
    for row in all_tool_rows:
        if not _in_range(row.started_at, start):
            continue
        tool = row.tool or "unknown"
        bucket = tool_usage.setdefault(
            tool,
            {"count": 0, "error_count": 0, "latencies": []},
        )
        bucket["count"] = int(bucket["count"]) + 1
        if row.status != "ok":
            bucket["error_count"] = int(bucket["error_count"]) + 1
        if row.latency_ms is not None:
            cast_latencies = bucket["latencies"]
            assert isinstance(cast_latencies, list)
            cast_latencies.append(int(row.latency_ms))

    by_tool: list[ToolUsageItem] = []
    for tool, bucket in tool_usage.items():
        latencies = bucket["latencies"]
        assert isinstance(latencies, list)
        avg_latency: float | None = None
        if latencies:
            avg_latency = round(sum(latencies) / len(latencies), 1)
        by_tool.append(
            ToolUsageItem(
                tool=tool,
                count=int(bucket["count"]),
                error_count=int(bucket["error_count"]),
                avg_latency_ms=avg_latency,
            )
        )
    by_tool.sort(key=lambda item: -item.count)
    by_tool = by_tool[:15]

    prompt_rows = [(t.prompt or "", t.session_id) for t in filtered_turns]
    top_user_prompts = _group_prompts(
        [(p, sid) for p, sid in prompt_rows if p],
    )

    subagent_rows = db.scalars(select(SubagentRow)).all()
    question_rows = [
        (s.question or "", s.session_id)
        for s in subagent_rows
        if _in_range(s.started_at, start) and (s.question or "").strip()
    ]
    top_subagent_questions = _group_prompts(question_rows)

    expensive_candidates = [
        ExpensiveTurnItem(
            turn_id=t.turn_id,
            session_id=t.session_id or "",
            run_id=t.run_id or "",
            turn_index=t.turn_index,
            prompt_snippet=_prompt_snippet(t.prompt or ""),
            total_cost_usd=float(t.total_cost_usd or 0.0),
            total_tokens=int(t.total_tokens or 0),
            started_at=t.started_at,
        )
        for t in filtered_turns
        if float(t.total_cost_usd or 0.0) > 0.0
    ]
    top_expensive_turns = sorted(
        expensive_candidates,
        key=lambda item: -item.total_cost_usd,
    )[:10]

    failed_tools = _failed_tool_rows(db, start)
    tool_errors: dict[str, StatsBreakdownItem] = {}
    error_groups_map: dict[str, ToolErrorGroup] = {}
    for row in failed_tools:
        label = row.tool or "unknown"
        item = tool_errors.setdefault(label, StatsBreakdownItem(label=label))
        item.count += 1

        group = error_groups_map.setdefault(label, ToolErrorGroup(tool=label, count=0))
        group.count += 1
        if len(group.occurrences) < _OCCURRENCES_PER_TOOL:
            group.occurrences.append(_tool_error_occurrence(row))

    return StatsResponse(
        range=range_key,
        total_runs=len(filtered_runs),
        total_turns=len(filtered_turns),
        total_tokens=total_tokens,
        total_cost_usd=round(total_cost, 6),
        error_rate=round(error_rate, 4),
        by_day=sorted(by_day.values(), key=lambda p: p.date),
        by_agent_type=sorted(by_agent.values(), key=lambda p: -p.tokens)[:20],
        by_model=sorted(by_model.values(), key=lambda p: -p.cost_usd)[:20],
        tool_errors=sorted(tool_errors.values(), key=lambda p: -p.count)[:20],
        by_tool=by_tool,
        top_user_prompts=top_user_prompts,
        top_subagent_questions=top_subagent_questions,
        top_expensive_turns=top_expensive_turns,
        tool_error_groups=sorted(error_groups_map.values(), key=lambda g: -g.count),
    )


def daily_finops() -> DailyFinOpsResponse:
    path = daily_spend_path()
    history: dict[str, float] = {}
    if path.is_file():
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(payload, dict):
                history = {str(k): float(v) for k, v in payload.items()}
        except (OSError, ValueError, json.JSONDecodeError):
            history = {}
    today_key = datetime.now(timezone.utc).date().isoformat()
    today_spent = float(history.get(today_key, 0.0))
    cap = float(agent_config.MAX_USD_PER_DAY)
    return DailyFinOpsResponse(
        today_spent_usd=today_spent,
        daily_cap_usd=cap,
        remaining_usd=max(0.0, cap - today_spent),
        history=history,
    )
