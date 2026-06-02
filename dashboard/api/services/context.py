"""Parent context and parallel summaries via vg_agent.trace."""

from __future__ import annotations

from vg_agent.trace import iter_spawn_subagents_batch_summaries, show_context

from ..schemas import (
    ContextMessage,
    ContextResponse,
    ParallelResponse,
    ParallelReturnItem,
    ParallelTurnItem,
)
from .sessions import load_events_for_run


def _turn_bounds(events: list[dict]) -> list[tuple[int, int]]:
    positions = [i for i, event in enumerate(events) if event.get("kind") == "user_prompt"]
    bounds: list[tuple[int, int]] = []
    for idx, start in enumerate(positions):
        end = positions[idx + 1] if idx + 1 < len(positions) else len(events)
        bounds.append((start, end))
    return bounds


def _compaction_by_tool_use_id(events: list[dict]) -> dict[str, dict]:
    by_tool: dict[str, dict] = {}
    for event in events:
        if event.get("kind") != "compaction":
            continue
        tool_use_id = str(event.get("tool_use_id") or "")
        if tool_use_id:
            by_tool[tool_use_id] = event
    return by_tool


def build_context_response(run_id: str, events: list[dict], step_idx: int) -> ContextResponse:
    messages_raw = show_context(events, step_idx)
    compaction_by_tool = _compaction_by_tool_use_id(events)
    messages: list[ContextMessage] = []
    for item in messages_raw:
        role = str(item.get("role") or "meta")
        tool_use_id = str(item.get("tool_use_id")) if item.get("tool_use_id") else None
        compacted = bool(item.get("compacted")) if item.get("compacted") else None
        before_tokens: int | None = None
        after_tokens: int | None = None
        if compacted and tool_use_id:
            comp = compaction_by_tool.get(tool_use_id)
            if comp is not None:
                if comp.get("before_tokens") is not None:
                    before_tokens = int(comp["before_tokens"])
                if comp.get("after_tokens") is not None:
                    after_tokens = int(comp["after_tokens"])
        msg = ContextMessage(
            role=role,
            content=str(item.get("content")) if item.get("content") is not None else None,
            kind=str(item.get("kind")) if item.get("kind") else None,
            step_idx=int(item["step_idx"]) if item.get("step_idx") is not None else None,
            tool=str(item.get("tool")) if item.get("tool") else None,
            tool_use_id=tool_use_id,
            compacted=compacted,
            compaction_before_tokens=before_tokens,
            compaction_after_tokens=after_tokens,
            tool_calls=item.get("tool_calls") if isinstance(item.get("tool_calls"), list) else None,
        )
        messages.append(msg)
    return ContextResponse(run_id=run_id, step_idx=step_idx, messages=messages)


def build_parallel_response(run_id: str, events: list[dict]) -> ParallelResponse:
    bounds = _turn_bounds(events)
    turns: list[ParallelTurnItem] = []
    for turn_index, (start, end) in enumerate(bounds, start=1):
        batch_summaries = iter_spawn_subagents_batch_summaries(
            events, since_event_idx=start, before_event_idx=end
        )
        for summary in batch_summaries:
            turns.append(
                ParallelTurnItem(
                    turn_index=turn_index,
                    overlap=summary.overlap,
                    returns=[
                        ParallelReturnItem(
                            child_agent_id=item.child_agent_id,
                            agent_type=item.agent_type,
                            question=item.question,
                            duration_sec=item.duration_sec,
                            status=item.status,
                            payload_snippet=item.payload_snippet,
                        )
                        for item in summary.returns
                    ],
                )
            )
    return ParallelResponse(run_id=run_id, turns=turns)


def max_parent_step(events: list[dict]) -> int:
    max_step = 0
    for event in events:
        if event.get("agent_id") != "parent":
            continue
        if event.get("kind") != "assistant_step":
            continue
        max_step = max(max_step, int(event.get("step_idx") or 0))
    return max_step


def steps_with_compacted_context(events: list[dict]) -> list[int]:
    """Parent step indices where show_context includes at least one compacted tool result."""
    if not events:
        return []
    max_step = max_parent_step(events)
    steps: list[int] = []
    for step_idx in range(max_step + 1):
        messages = show_context(events, step_idx)
        if any(item.get("compacted") for item in messages):
            steps.append(step_idx)
    return steps
