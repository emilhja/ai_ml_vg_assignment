"""Statistics rollups from SQLite."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from vg_agent import config as agent_config

from ..config import daily_spend_path
from ..runtime_config import ensure_runtime_config
from ..models import ModelCallRow, RunRow, SubagentRow, ToolCallRow, TurnRow
from ..schemas import (
    ConfiguredModelItem,
    DailyFinOpsResponse,
    DailySeriesPoint,
    ExpensiveTurnItem,
    ModelRoleBreakdown,
    ModelStatsItem,
    PromptLeaderboardItem,
    StatsBreakdownItem,
    StatsResponse,
    ToolErrorGroup,
    ToolErrorOccurrence,
    ToolErrorsDrillResponse,
    ToolUsageItem,
)
from .session_agent_types import KNOWN_AGENT_TYPES

_PROMPT_SNIPPET_LEN = 120
_OCCURRENCES_PER_TOOL = 5
_STALE_MODEL_DAYS = 7


def _utc_today_start(now: datetime | None = None) -> datetime:
    """UTC midnight for the calendar day containing *now* (default: current time)."""
    now = now or datetime.now(timezone.utc)
    return now.replace(hour=0, minute=0, second=0, microsecond=0)


def _range_start(range_key: str) -> datetime:
    """Inclusive UTC calendar windows aligned with the *Today* filter."""
    today_start = _utc_today_start()
    if range_key == "today":
        return today_start
    if range_key == "7d":
        return today_start - timedelta(days=6)
    if range_key == "30d":
        return today_start - timedelta(days=29)
    return today_start - timedelta(days=6)


def _day_keys_in_range(start: datetime) -> list[str]:
    """Every UTC date from *start*'s calendar day through today (inclusive)."""
    end = datetime.now(timezone.utc).date()
    day = start.date()
    keys: list[str] = []
    while day <= end:
        keys.append(day.isoformat())
        day += timedelta(days=1)
    return keys


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


def _agent_role(agent_id: str | None, subagent_types: dict[str, str]) -> str:
    aid = (agent_id or "").strip()
    if not aid or aid == "parent":
        return "parent"
    if aid == "compactor":
        return "compactor"
    if aid in subagent_types:
        return subagent_types[aid]
    if "-" in aid:
        prefix = aid.split("-", 1)[0]
        if prefix in KNOWN_AGENT_TYPES:
            return prefix
    return aid


def _subagent_type_by_child_id(db: Session) -> dict[str, str]:
    mapping: dict[str, str] = {}
    for row in db.scalars(select(SubagentRow)).all():
        agent_type = (row.agent_type or "").strip()
        if not agent_type or not row.subagent_id:
            continue
        if ":" in row.subagent_id:
            child_id = row.subagent_id.rsplit(":", 1)[-1]
            mapping[child_id] = agent_type
    return mapping


def _model_pricing(model_id: str) -> tuple[float | None, float | None]:
    entry = agent_config.PRICING_USD_PER_MTOK.get(model_id)
    if not entry:
        return None, None
    return float(entry.get("input", 0)), float(entry.get("output", 0))


def _configured_role_map() -> dict[str, list[str]]:
    role_models: list[tuple[str, str]] = [
        ("parent", agent_config.PARENT_MODEL_ID),
        ("grilling", agent_config.GRILLING_MODEL_ID),
        ("explorer", agent_config.EXPLORER_MODEL_ID),
        ("coder", agent_config.CODER_MODEL_ID),
        ("reviewer", agent_config.REVIEWER_MODEL_ID),
        ("compactor", agent_config.COMPACTOR_MODEL_ID),
    ]
    by_model: dict[str, list[str]] = {}
    for role, model_id in role_models:
        by_model.setdefault(model_id, []).append(role)
    return by_model


def _build_configured_models() -> list[ConfiguredModelItem]:
    items: list[ConfiguredModelItem] = []
    for role, model_id in [
        ("parent", agent_config.PARENT_MODEL_ID),
        ("grilling", agent_config.GRILLING_MODEL_ID),
        ("explorer", agent_config.EXPLORER_MODEL_ID),
        ("coder", agent_config.CODER_MODEL_ID),
        ("reviewer", agent_config.REVIEWER_MODEL_ID),
        ("compactor", agent_config.COMPACTOR_MODEL_ID),
    ]:
        price_in, price_out = _model_pricing(model_id)
        items.append(
            ConfiguredModelItem(
                role=role,
                model_id=model_id,
                price_input_per_mtok=price_in,
                price_output_per_mtok=price_out,
                has_known_pricing=price_in is not None and price_out is not None,
            )
        )
    return items


def _max_ts(a: str | None, b: str | None) -> str | None:
    if not a:
        return b
    if not b:
        return a
    return a if a >= b else b


def _avg_latency(latencies: list[int]) -> float | None:
    if not latencies:
        return None
    return round(sum(latencies) / len(latencies), 1)


def _accumulate_model_stats(
    model_rows: list[ModelCallRow],
    start: datetime,
    subagent_types: dict[str, str],
) -> tuple[list[ModelStatsItem], list[StatsBreakdownItem]]:
    configured_by_model = _configured_role_map()
    last_used_all_time: dict[str, str | None] = {}
    range_buckets: dict[str, dict[str, object]] = {}
    all_time_models: set[str] = set()

    for row in model_rows:
        model_id = row.model_id or "unknown"
        all_time_models.add(model_id)
        last_used_all_time[model_id] = _max_ts(last_used_all_time.get(model_id), row.started_at)

        if not _in_range(row.started_at, start):
            continue

        role = _agent_role(row.agent_id, subagent_types)
        bucket = range_buckets.setdefault(
            model_id,
            {
                "call_count": 0,
                "tokens_in": 0,
                "tokens_out": 0,
                "cost_usd": 0.0,
                "error_count": 0,
                "latencies": [],
                "last_used_at": None,
                "sample_session_id": None,
                "roles": {},
            },
        )
        bucket["call_count"] = int(bucket["call_count"]) + 1
        bucket["tokens_in"] = int(bucket["tokens_in"]) + int(row.tokens_in or 0)
        bucket["tokens_out"] = int(bucket["tokens_out"]) + int(row.tokens_out or 0)
        bucket["cost_usd"] = float(bucket["cost_usd"]) + float(row.cost_usd or 0.0)
        if row.status not in {None, "ok"}:
            bucket["error_count"] = int(bucket["error_count"]) + 1
        if row.latency_ms is not None:
            cast_latencies = bucket["latencies"]
            assert isinstance(cast_latencies, list)
            cast_latencies.append(int(row.latency_ms))
        prev_last = str(bucket["last_used_at"]) if bucket["last_used_at"] else None
        bucket["last_used_at"] = _max_ts(prev_last, row.started_at)
        if row.started_at and (prev_last is None or (row.started_at or "") >= prev_last):
            bucket["sample_session_id"] = row.session_id

        roles = bucket["roles"]
        assert isinstance(roles, dict)
        role_bucket = roles.setdefault(
            role,
            {"call_count": 0, "tokens_in": 0, "tokens_out": 0, "cost_usd": 0.0, "latencies": []},
        )
        role_bucket["call_count"] = int(role_bucket["call_count"]) + 1
        role_bucket["tokens_in"] = int(role_bucket["tokens_in"]) + int(row.tokens_in or 0)
        role_bucket["tokens_out"] = int(role_bucket["tokens_out"]) + int(row.tokens_out or 0)
        role_bucket["cost_usd"] = float(role_bucket["cost_usd"]) + float(row.cost_usd or 0.0)
        if row.latency_ms is not None:
            cast_role_lat = role_bucket["latencies"]
            assert isinstance(cast_role_lat, list)
            cast_role_lat.append(int(row.latency_ms))

    by_agent_role: dict[str, StatsBreakdownItem] = {}
    for model_id, bucket in range_buckets.items():
        roles = bucket["roles"]
        assert isinstance(roles, dict)
        for role, role_bucket in roles.items():
            item = by_agent_role.setdefault(role, StatsBreakdownItem(label=role))
            item.count += int(role_bucket["call_count"])
            item.tokens += int(role_bucket["tokens_in"]) + int(role_bucket["tokens_out"])
            item.cost_usd += float(role_bucket["cost_usd"])

    models_in_range: list[ModelStatsItem] = []
    for model_id, bucket in range_buckets.items():
        price_in, price_out = _model_pricing(model_id)
        roles = bucket["roles"]
        assert isinstance(roles, dict)
        by_role = [
            ModelRoleBreakdown(
                agent_role=role,
                call_count=int(rb["call_count"]),
                tokens_in=int(rb["tokens_in"]),
                tokens_out=int(rb["tokens_out"]),
                cost_usd=round(float(rb["cost_usd"]), 6),
                avg_latency_ms=_avg_latency(rb["latencies"]),
            )
            for role, rb in sorted(roles.items(), key=lambda x: -float(x[1]["cost_usd"]))
        ]
        latencies = bucket["latencies"]
        assert isinstance(latencies, list)
        models_in_range.append(
            ModelStatsItem(
                model_id=model_id,
                call_count=int(bucket["call_count"]),
                tokens_in=int(bucket["tokens_in"]),
                tokens_out=int(bucket["tokens_out"]),
                cost_usd=round(float(bucket["cost_usd"]), 6),
                avg_latency_ms=_avg_latency(latencies),
                last_used_at=str(bucket["last_used_at"]) if bucket["last_used_at"] else None,
                last_used_at_all_time=last_used_all_time.get(model_id),
                active_in_range=True,
                price_input_per_mtok=price_in,
                price_output_per_mtok=price_out,
                configured_roles=configured_by_model.get(model_id, []),
                by_role=by_role,
                sample_session_id=str(bucket["sample_session_id"])
                if bucket.get("sample_session_id")
                else None,
                error_count=int(bucket["error_count"]),
            )
        )

    for model_id in all_time_models:
        if model_id in range_buckets:
            continue
        price_in, price_out = _model_pricing(model_id)
        models_in_range.append(
            ModelStatsItem(
                model_id=model_id,
                call_count=0,
                active_in_range=False,
                last_used_at=None,
                last_used_at_all_time=last_used_all_time.get(model_id),
                price_input_per_mtok=price_in,
                price_output_per_mtok=price_out,
                configured_roles=configured_by_model.get(model_id, []),
            )
        )

    models_in_range.sort(key=lambda m: (-m.cost_usd, m.last_used_at_all_time or ""))
    return models_in_range, sorted(by_agent_role.values(), key=lambda p: -p.cost_usd)


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
    ensure_runtime_config()
    start = _range_start(range_key)
    runs = db.scalars(select(RunRow)).all()
    filtered_runs = [r for r in runs if _in_range(r.started_at, start)]

    total_tokens = sum(int(r.total_tokens or 0) for r in filtered_runs)
    total_cost = sum(float(r.total_cost_usd or 0.0) for r in filtered_runs)
    turns = db.scalars(select(TurnRow).where(TurnRow.turn_id.isnot(None))).all()
    filtered_turns = [
        t
        for t in turns
        if t is not None and t.started_at is not None and _in_range(t.started_at, start)
    ]
    errors = sum(1 for t in filtered_turns if t.status not in {None, "ok", "running"})
    error_rate = (errors / len(filtered_turns)) if filtered_turns else 0.0

    by_day: dict[str, DailySeriesPoint] = {}
    for day_key in _day_keys_in_range(start):
        by_day[day_key] = DailySeriesPoint(date=day_key)
    for run in filtered_runs:
        day = (run.started_at or "")[:10] or "unknown"
        if day not in by_day:
            continue
        point = by_day[day]
        point.runs += 1
        point.tokens += int(run.total_tokens or 0)
        point.cost_usd += float(run.total_cost_usd or 0.0)

    model_rows = db.scalars(select(ModelCallRow)).all()
    subagent_types = _subagent_type_by_child_id(db)
    models, by_agent_role = _accumulate_model_stats(model_rows, start, subagent_types)
    configured_models = _build_configured_models()

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
        by_agent_role=by_agent_role[:20],
        by_model=sorted(by_model.values(), key=lambda p: -p.cost_usd)[:20],
        models=models,
        configured_models=configured_models,
        tool_errors=sorted(tool_errors.values(), key=lambda p: -p.count)[:20],
        by_tool=by_tool,
        top_user_prompts=top_user_prompts,
        top_subagent_questions=top_subagent_questions,
        top_expensive_turns=top_expensive_turns,
        tool_error_groups=sorted(error_groups_map.values(), key=lambda g: -g.count),
    )


def daily_finops() -> DailyFinOpsResponse:
    ensure_runtime_config()
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
