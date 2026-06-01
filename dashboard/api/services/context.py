"""Parent context and parallel summaries via vg_agent.trace."""

from __future__ import annotations

from vg_agent.trace import parallel_subagent_summary, show_context

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


def build_context_response(run_id: str, events: list[dict], step_idx: int) -> ContextResponse:
    messages_raw = show_context(events, step_idx)
    messages: list[ContextMessage] = []
    for item in messages_raw:
        role = str(item.get("role") or "meta")
        msg = ContextMessage(
            role=role,
            content=str(item.get("content")) if item.get("content") is not None else None,
            kind=str(item.get("kind")) if item.get("kind") else None,
            step_idx=int(item["step_idx"]) if item.get("step_idx") is not None else None,
            tool=str(item.get("tool")) if item.get("tool") else None,
            tool_use_id=str(item.get("tool_use_id")) if item.get("tool_use_id") else None,
            compacted=bool(item.get("compacted")) if item.get("compacted") else None,
            tool_calls=item.get("tool_calls") if isinstance(item.get("tool_calls"), list) else None,
        )
        messages.append(msg)
    return ContextResponse(run_id=run_id, step_idx=step_idx, messages=messages)


def build_parallel_response(run_id: str, events: list[dict]) -> ParallelResponse:
    bounds = _turn_bounds(events)
    turns: list[ParallelTurnItem] = []
    for turn_index, (start, end) in enumerate(bounds, start=1):
        summary = parallel_subagent_summary(events, since_event_idx=start, before_event_idx=end)
        if summary is None:
            continue
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
