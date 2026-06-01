"""Pydantic response models for the dashboard API."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    ok: bool
    workspace_root: str
    sqlite_path: str
    traces_dir: str
    sqlite_exists: bool
    schema_ready: bool
    traces_dirs: list[str] = Field(default_factory=list)
    hint: str | None = None


class SessionRenameRequest(BaseModel):
    display_name: str | None = None


class SessionSummary(BaseModel):
    session_id: str
    display_name: str | None = None
    first_seen_at: str | None = None
    last_seen_at: str | None = None
    status: str | None = None
    run_count: int = 0
    total_turns: int = 0
    total_tokens: int = 0
    total_cost_usd: float = 0.0
    last_prompt_snippet: str | None = None
    has_subagents: bool = False
    has_parallel_subagents: bool = False
    has_sequential_subagents: bool = False
    has_tool_compaction: bool = False
    has_context_compaction_auto: bool = False
    has_context_compaction_manual: bool = False
    agent_types_present: list[str] = Field(default_factory=list)


class SessionListResponse(BaseModel):
    items: list[SessionSummary]
    total: int


class RunSummary(BaseModel):
    run_id: str
    session_id: str | None = None
    started_at: str | None = None
    ended_at: str | None = None
    duration_ms: int | None = None
    final_status: str | None = None
    total_tokens: int = 0
    total_cost_usd: float = 0.0


class TurnSummary(BaseModel):
    turn_id: str
    run_id: str | None = None
    turn_index: int | None = None
    prompt: str | None = None
    status: str | None = None
    duration_ms: int | None = None
    total_tokens: int = 0
    total_cost_usd: float = 0.0
    total_tool_calls: int = 0
    error_type: str | None = None


class SessionDetailResponse(BaseModel):
    session: SessionSummary
    runs: list[RunSummary]
    turns: list[TurnSummary]
    jsonl_path: str


class EventItem(BaseModel):
    run_id: str
    session_id: str | None = None
    event_idx: int
    kind: str
    timestamp_iso: str | None = None
    turn_id: str | None = None
    turn_index: int | None = None
    agent_id: str | None = None
    agent_type: str | None = None
    parent_id: str | None = None
    child_agent_id: str | None = None
    tool: str | None = None
    status: str | None = None
    tokens_in: int | None = None
    tokens_out: int | None = None
    cost_usd: float | None = None
    latency_ms: int | None = None
    payload: dict[str, Any] = Field(default_factory=dict)


class EventListResponse(BaseModel):
    items: list[EventItem]
    has_more: bool = False
    next_from_event_idx: int | None = None


class ActiveSessionResponse(BaseModel):
    session_id: str | None = None
    session: SessionDetailResponse | None = None
    recent_events: list[EventItem] = Field(default_factory=list)


class ModelCallItem(BaseModel):
    model_call_id: str
    agent_id: str | None = None
    step_idx: int | None = None
    model_id: str | None = None
    tokens_in: int | None = None
    tokens_out: int | None = None
    cost_usd: float | None = None
    latency_ms: int | None = None
    status: str | None = None
    started_at: str | None = None
    ended_at: str | None = None


class ToolCallItem(BaseModel):
    tool_call_id: str
    agent_id: str | None = None
    tool: str | None = None
    args_summary: str | None = None
    target_path: str | None = None
    latency_ms: int | None = None
    status: str | None = None
    error_type: str | None = None
    error_message: str | None = None
    started_at: str | None = None
    ended_at: str | None = None


class SubagentItem(BaseModel):
    subagent_id: str
    agent_type: str | None = None
    question: str | None = None
    started_at: str | None = None
    ended_at: str | None = None
    duration_ms: int | None = None
    status: str | None = None
    total_tokens: int | None = None


class TimelineResponse(BaseModel):
    run_id: str
    session_id: str | None = None
    turns: list[TurnSummary]
    model_calls: list[ModelCallItem]
    tool_calls: list[ToolCallItem]
    subagents: list[SubagentItem]


class ContextMessage(BaseModel):
    role: str
    content: str | None = None
    kind: str | None = None
    step_idx: int | None = None
    tool: str | None = None
    tool_use_id: str | None = None
    compacted: bool | None = None
    compaction_before_tokens: int | None = None
    compaction_after_tokens: int | None = None
    tool_calls: list[dict[str, Any]] | None = None


class ContextResponse(BaseModel):
    run_id: str
    step_idx: int
    messages: list[ContextMessage]


class ParallelReturnItem(BaseModel):
    child_agent_id: str
    agent_type: str
    question: str
    duration_sec: float | None = None
    status: str
    payload_snippet: str


class ParallelTurnItem(BaseModel):
    turn_index: int
    overlap: bool
    returns: list[ParallelReturnItem]


class ParallelResponse(BaseModel):
    run_id: str
    turns: list[ParallelTurnItem]


class ApprovalItem(BaseModel):
    approval_id: str
    tool: str | None = None
    decision: str | None = None
    args_summary: str | None = None
    timestamp_iso: str | None = None


class CompactionItem(BaseModel):
    compaction_id: str
    event_idx: int | None = None
    original_event_idx: int | None = None
    before_tokens: int | None = None
    after_tokens: int | None = None
    summary: str | None = None


class RedactionItem(BaseModel):
    redaction_id: str
    event_idx: int | None = None
    pattern: str | None = None
    count: int | None = None


class BudgetEventItem(BaseModel):
    event_idx: int
    budget_reason: str | None = None
    timestamp_iso: str | None = None


class SafetyResponse(BaseModel):
    run_id: str
    approvals: list[ApprovalItem]
    compactions: list[CompactionItem]
    redactions: list[RedactionItem]
    budget_events: list[BudgetEventItem]


class DailySeriesPoint(BaseModel):
    date: str
    tokens: int = 0
    cost_usd: float = 0.0
    runs: int = 0


class StatsBreakdownItem(BaseModel):
    label: str
    tokens: int = 0
    cost_usd: float = 0.0
    count: int = 0


class ToolUsageItem(BaseModel):
    tool: str
    count: int
    error_count: int = 0
    avg_latency_ms: float | None = None


class PromptLeaderboardItem(BaseModel):
    label: str
    count: int
    sample_session_id: str | None = None


class ExpensiveTurnItem(BaseModel):
    turn_id: str
    session_id: str
    run_id: str
    turn_index: int | None = None
    prompt_snippet: str
    total_cost_usd: float
    total_tokens: int
    started_at: str | None = None


class ToolErrorOccurrence(BaseModel):
    tool_call_id: str
    session_id: str
    run_id: str
    turn_id: str | None = None
    error_type: str | None = None
    error_message: str | None = None
    started_at: str | None = None


class ToolErrorGroup(BaseModel):
    tool: str
    count: int
    occurrences: list[ToolErrorOccurrence] = Field(default_factory=list)


class ToolErrorsDrillResponse(BaseModel):
    tool: str
    range: str
    total: int
    items: list[ToolErrorOccurrence] = Field(default_factory=list)


class ModelRoleBreakdown(BaseModel):
    agent_role: str
    call_count: int = 0
    tokens_in: int = 0
    tokens_out: int = 0
    cost_usd: float = 0.0
    avg_latency_ms: float | None = None


class ModelStatsItem(BaseModel):
    model_id: str
    call_count: int = 0
    tokens_in: int = 0
    tokens_out: int = 0
    cost_usd: float = 0.0
    avg_latency_ms: float | None = None
    last_used_at: str | None = None
    last_used_at_all_time: str | None = None
    active_in_range: bool = False
    price_input_per_mtok: float | None = None
    price_output_per_mtok: float | None = None
    configured_roles: list[str] = Field(default_factory=list)
    by_role: list[ModelRoleBreakdown] = Field(default_factory=list)
    sample_session_id: str | None = None
    error_count: int = 0


class ConfiguredModelItem(BaseModel):
    role: str
    model_id: str
    price_input_per_mtok: float | None = None
    price_output_per_mtok: float | None = None
    has_known_pricing: bool = True


class StatsResponse(BaseModel):
    range: str
    total_runs: int = 0
    total_turns: int = 0
    total_tokens: int = 0
    total_cost_usd: float = 0.0
    error_rate: float = 0.0
    by_day: list[DailySeriesPoint] = Field(default_factory=list)
    by_agent_type: list[StatsBreakdownItem] = Field(default_factory=list)
    by_agent_role: list[StatsBreakdownItem] = Field(default_factory=list)
    by_model: list[StatsBreakdownItem] = Field(default_factory=list)
    models: list[ModelStatsItem] = Field(default_factory=list)
    configured_models: list[ConfiguredModelItem] = Field(default_factory=list)
    tool_errors: list[StatsBreakdownItem] = Field(default_factory=list)
    by_tool: list[ToolUsageItem] = Field(default_factory=list)
    top_user_prompts: list[PromptLeaderboardItem] = Field(default_factory=list)
    top_subagent_questions: list[PromptLeaderboardItem] = Field(default_factory=list)
    top_expensive_turns: list[ExpensiveTurnItem] = Field(default_factory=list)
    tool_error_groups: list[ToolErrorGroup] = Field(default_factory=list)


class DailyFinOpsResponse(BaseModel):
    today_spent_usd: float
    daily_cap_usd: float
    remaining_usd: float
    history: dict[str, float] = Field(default_factory=dict)
