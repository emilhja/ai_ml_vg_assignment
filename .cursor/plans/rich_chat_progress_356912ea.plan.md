---
name: rich chat progress
overview: Make `vg-agent --chat` keep the richer terminal experience throughout a run by replacing the verbose mid-turn log stream with a compact Rich-friendly progress view in TTY chat, while keeping full event detail in traces and non-TTY/task output unchanged.
todos:
  - id: spec-progress-policy
    content: Update chat/observability specs to define compact Rich TTY progress and verbose escape hatch.
    status: completed
  - id: progress-filter
    content: Implement compact/verbose progress filtering in the generated `__main__.py` template.
    status: completed
  - id: status-polish
    content: Tighten status bar refresh output only if needed after progress filtering.
    status: completed
  - id: tests
    content: Add tests for suppressed child noise, retained parallel rollup, retained errors/diffs, and verbose mode.
    status: completed
  - id: regen-verify
    content: Regenerate generated files and run focused plus full pytest verification.
    status: completed
isProject: false
---

# Rich Chat Progress Fix

## Target Behavior
- In Rich TTY `--chat`, keep the polished start/end UI but make the middle of a turn compact: parent step summaries, approvals, errors, compaction notices, successful edit diffs, and one parallel batch rollup.
- Suppress routine sub-agent internals (`explorer/coder [llm]`, read-only `[tool]`, spawn/return spam) from the terminal by default. They stay in JSONL and can be restored with a verbose flag/env var.
- Leave `--task`, non-TTY chat, trace JSONL, and `/review` detail behavior unchanged.

## Files To Change
- Update spec first: [`specs/16_chat_ui.md`](c:/Users/emil_/vscode/vg_assignment/specs/16_chat_ui.md) should replace “Progress stream unchanged” with a Rich TTY progress policy and document `VG_CHAT_VERBOSE_PROGRESS=1`.
- Cross-link observability: [`specs/60_observability.md`](c:/Users/emil_/vscode/vg_assignment/specs/60_observability.md) should clarify that full progress remains the non-TTY / verbose stream, while Rich chat may collapse presentation only.
- Implement in generator template: [`scripts/generate_project.py`](c:/Users/emil_/vscode/vg_assignment/scripts/generate_project.py), around `_format_progress_event()` / `_progress_sink_event()`, because `src/vg_agent/__main__.py` is generated.
- Keep UI helpers aligned: [`src/vg_agent/chat_ui.py`](c:/Users/emil_/vscode/vg_assignment/src/vg_agent/chat_ui.py) is preserved by the generator and already owns Rich status/approval rendering.
- Add focused tests in [`tests/test_vg_agent.py`](c:/Users/emil_/vscode/vg_assignment/tests/test_vg_agent.py).

## Implementation Shape
- Add a presentation gate in the progress sink, for example `VG_CHAT_VERBOSE_PROGRESS=1` or non-Rich mode means current behavior; Rich TTY default means compact behavior.
- For compact Rich mode:
  - Print `── turn N ──` once.
  - Print parent `llm_start` / parent `assistant_step` in shortened form.
  - Print approval decisions, budget/model/network errors, failed tool results, compaction banners, final `[run]` summary, and parent tool failures.
  - Keep successful `edit_file` / `write_file` inline diffs because they are useful and already deduped from end-of-turn `Changes`.
  - For `spawn_subagents`, print only the existing `[parallel]` summary and child snippets, not every explorer model/tool line.
  - For `spawn_subagent` Coder, print a single spawn/return summary, plus only write diffs/errors from the child.
- Consider a small status-bar polish in `refresh_chat_status_bar()` after the progress filter is in place: avoid repeating the hint/secondary line during throttled running refreshes unless the state changed. This is secondary to reducing the raw progress flood.

## Existing Evidence
The current template formats every agent event directly:

```570:592:src/vg_agent/__main__.py

def _format_progress_event(event: dict[str, object]) -> str | None:
    kind = event.get("kind")
    agent = str(event.get("agent_id") or "parent")
    if kind == "llm_start":
        return (
            f"[llm] {agent} step {event.get('step_idx')} -> {_short_model(event.get('model'))} "
            f"in~{event.get('tokens_in')} max_out={event.get('max_tokens')}"
        )
```

And `specs/16_chat_ui.md` currently says Rich progress is unchanged from observability, which explains why the beginning/end look richer while the middle still looks like logs.

## Verification
- Regenerate after source edits: `python scripts/generate_project.py --clean`.
- Run focused tests first: `uv run pytest tests/test_vg_agent.py -k "progress_sink or chat_ui or approval"`.
- Run full suite: `uv run pytest`.
- Manually replay the pasted `spawn_subagents -> Coder` prompt in `--chat`: confirm the terminal shows compact parent progress, one parallel rollup, Rich approval panels, useful edit diffs, and no routine explorer/Coder read/model spam.
- If evaluating through Docker, rebuild before judging: `docker compose build vg-agent`.