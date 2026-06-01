"""SQLAlchemy ORM mappings for the existing sqlite_store schema."""

from __future__ import annotations

from sqlalchemy import Float, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class SessionRow(Base):
    __tablename__ = "sessions"

    session_id: Mapped[str] = mapped_column(String, primary_key=True)
    first_seen_at: Mapped[str | None] = mapped_column(String, nullable=True)
    last_seen_at: Mapped[str | None] = mapped_column(String, nullable=True)
    run_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    total_turns: Mapped[int | None] = mapped_column(Integer, nullable=True)
    total_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    total_cost_usd: Mapped[float | None] = mapped_column(Float, nullable=True)
    status: Mapped[str | None] = mapped_column(String, nullable=True)
    redaction_enabled: Mapped[int | None] = mapped_column(Integer, nullable=True)


class RunRow(Base):
    __tablename__ = "runs"

    run_id: Mapped[str] = mapped_column(String, primary_key=True)
    session_id: Mapped[str | None] = mapped_column(String, nullable=True)
    started_at: Mapped[str | None] = mapped_column(String, nullable=True)
    ended_at: Mapped[str | None] = mapped_column(String, nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    final_status: Mapped[str | None] = mapped_column(String, nullable=True)
    total_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    total_cost_usd: Mapped[float | None] = mapped_column(Float, nullable=True)


class TurnRow(Base):
    __tablename__ = "turns"

    turn_id: Mapped[str] = mapped_column(String, primary_key=True)
    run_id: Mapped[str | None] = mapped_column(String, nullable=True)
    session_id: Mapped[str | None] = mapped_column(String, nullable=True)
    turn_index: Mapped[int | None] = mapped_column(Integer, nullable=True)
    prompt: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[str | None] = mapped_column(String, nullable=True)
    ended_at: Mapped[str | None] = mapped_column(String, nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[str | None] = mapped_column(String, nullable=True)
    error_type: Mapped[str | None] = mapped_column(String, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    total_model_calls: Mapped[int | None] = mapped_column(Integer, nullable=True)
    total_tool_calls: Mapped[int | None] = mapped_column(Integer, nullable=True)
    total_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    total_cost_usd: Mapped[float | None] = mapped_column(Float, nullable=True)


class EventRow(Base):
    __tablename__ = "events"

    run_id: Mapped[str] = mapped_column(String, primary_key=True)
    event_idx: Mapped[int] = mapped_column(Integer, primary_key=True)
    session_id: Mapped[str | None] = mapped_column(String, nullable=True)
    turn_id: Mapped[str | None] = mapped_column(String, nullable=True)
    timestamp_iso: Mapped[str | None] = mapped_column(String, nullable=True)
    agent_id: Mapped[str | None] = mapped_column(String, nullable=True)
    parent_id: Mapped[str | None] = mapped_column(String, nullable=True)
    kind: Mapped[str] = mapped_column(String)
    model_id: Mapped[str | None] = mapped_column(String, nullable=True)
    tool: Mapped[str | None] = mapped_column(String, nullable=True)
    status: Mapped[str | None] = mapped_column(String, nullable=True)
    tokens_in: Mapped[int | None] = mapped_column(Integer, nullable=True)
    tokens_out: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cost_usd: Mapped[float | None] = mapped_column(Float, nullable=True)
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    payload_json: Mapped[str] = mapped_column(Text)


class ModelCallRow(Base):
    __tablename__ = "model_calls"

    model_call_id: Mapped[str] = mapped_column(String, primary_key=True)
    run_id: Mapped[str | None] = mapped_column(String, nullable=True)
    session_id: Mapped[str | None] = mapped_column(String, nullable=True)
    turn_id: Mapped[str | None] = mapped_column(String, nullable=True)
    agent_id: Mapped[str | None] = mapped_column(String, nullable=True)
    step_idx: Mapped[int | None] = mapped_column(Integer, nullable=True)
    model_id: Mapped[str | None] = mapped_column(String, nullable=True)
    provider: Mapped[str | None] = mapped_column(String, nullable=True)
    tokens_in: Mapped[int | None] = mapped_column(Integer, nullable=True)
    tokens_out: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cost_usd: Mapped[float | None] = mapped_column(Float, nullable=True)
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[str | None] = mapped_column(String, nullable=True)
    started_at: Mapped[str | None] = mapped_column(String, nullable=True)
    ended_at: Mapped[str | None] = mapped_column(String, nullable=True)


class ToolCallRow(Base):
    __tablename__ = "tool_calls"

    tool_call_id: Mapped[str] = mapped_column(String, primary_key=True)
    run_id: Mapped[str | None] = mapped_column(String, nullable=True)
    session_id: Mapped[str | None] = mapped_column(String, nullable=True)
    turn_id: Mapped[str | None] = mapped_column(String, nullable=True)
    agent_id: Mapped[str | None] = mapped_column(String, nullable=True)
    tool: Mapped[str | None] = mapped_column(String, nullable=True)
    args_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    target_path: Mapped[str | None] = mapped_column(String, nullable=True)
    started_at: Mapped[str | None] = mapped_column(String, nullable=True)
    ended_at: Mapped[str | None] = mapped_column(String, nullable=True)
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[str | None] = mapped_column(String, nullable=True)
    error_type: Mapped[str | None] = mapped_column(String, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)


class SubagentRow(Base):
    __tablename__ = "subagents"

    subagent_id: Mapped[str] = mapped_column(String, primary_key=True)
    run_id: Mapped[str | None] = mapped_column(String, nullable=True)
    session_id: Mapped[str | None] = mapped_column(String, nullable=True)
    turn_id: Mapped[str | None] = mapped_column(String, nullable=True)
    agent_type: Mapped[str | None] = mapped_column(String, nullable=True)
    question: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[str | None] = mapped_column(String, nullable=True)
    ended_at: Mapped[str | None] = mapped_column(String, nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[str | None] = mapped_column(String, nullable=True)
    total_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    total_cost_usd: Mapped[float | None] = mapped_column(Float, nullable=True)


class ApprovalRow(Base):
    __tablename__ = "approvals"

    approval_id: Mapped[str] = mapped_column(String, primary_key=True)
    run_id: Mapped[str | None] = mapped_column(String, nullable=True)
    session_id: Mapped[str | None] = mapped_column(String, nullable=True)
    tool: Mapped[str | None] = mapped_column(String, nullable=True)
    decision: Mapped[str | None] = mapped_column(String, nullable=True)
    args_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    timestamp_iso: Mapped[str | None] = mapped_column(String, nullable=True)


class CompactionRow(Base):
    __tablename__ = "compactions"

    compaction_id: Mapped[str] = mapped_column(String, primary_key=True)
    run_id: Mapped[str | None] = mapped_column(String, nullable=True)
    session_id: Mapped[str | None] = mapped_column(String, nullable=True)
    event_idx: Mapped[int | None] = mapped_column(Integer, nullable=True)
    original_event_idx: Mapped[int | None] = mapped_column(Integer, nullable=True)
    before_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    after_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)


class RedactionRow(Base):
    __tablename__ = "redactions"

    redaction_id: Mapped[str] = mapped_column(String, primary_key=True)
    run_id: Mapped[str | None] = mapped_column(String, nullable=True)
    session_id: Mapped[str | None] = mapped_column(String, nullable=True)
    event_idx: Mapped[int | None] = mapped_column(Integer, nullable=True)
    pattern: Mapped[str | None] = mapped_column(String, nullable=True)
    count: Mapped[int | None] = mapped_column(Integer, nullable=True)
