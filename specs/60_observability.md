# 60 Observability

The agent emits a live statusline to stderr and records every piece of data a
future FastAPI + Pydantic + React analysis frontend would need from the JSONL
trace alone. The frontend itself is **deferred** — this spec mandates the data
contract, statusline, machine-readable budget summary, and SQLite query mirror.

## Statusline

One line per parent step, rewritten in place on stderr (carriage return, no
newline). Format:

```
[step {step}/{max_steps}] tokens {tokens_used}/{tokens_cap} ({tokens_pct}%) · usd {usd_used:.3f}/{usd_cap:.3f} ({usd_pct}%) · agents {per_agent_breakdown} · tools {tool_call_count} · model {parent_model_short}
```

Concrete example:

```
[step 5/15] tokens 12340/80000 (15%) · usd 0.041/0.500 (8%) · agents parent=8.2k explorer=4.1k · tools 7 · model haiku-4.5
```

- `per_agent_breakdown` aggregates `tokens_in + tokens_out` per `agent_type`
  for the current run. Sub-agent slices show their type label, not their
  `agent_id`.
- When a warning threshold is crossed, the relevant section is highlighted
  with leading `!` (e.g., `!usd 0.41/0.50 (82%)`). Highlighting is the
  visible cue for VG.3's "budget warning" requirement.
- Live chat statuslines include the session tool-error count and use color in
  TTYs: green for normal state, yellow for budget/cap warnings, and red for
  error/abort states. The progress stream uses distinct colors for approvals,
  sub-agent activity, compaction, warnings, and failures; non-TTY output remains
  plain text. Rich TTY `--chat` may also print unified-diff panels for successful
  `edit_file` / `write_file` tools (`specs/16_chat_ui.md`); this is presentation
  only and does not add JSONL event kinds.
- Idle TTY chat (`specs/16_chat_ui.md`) does **not** repeat the compact
  statusline before every prompt. Instead a bottom status bar below the input
  shows session counters (updated during runs via throttled progress callbacks);
  `/status` reprints the full dashboard. Rich TTY chat does **not** also rewrite
  a `\r` compact statusline during runs — the bottom bar is the sole live HUD.
  The compact `format_statusline_compact` string is still emitted as trace
  `statusline` events during agent runs.
- `statusline` events include `ctx_tokens` from parent-visible `show_context`
  and, when configured, `ctx_window` / percentage of model context window.
- Statusline is also written as a `statusline` JSONL event at every parent
  step boundary so replays can reconstruct the user-visible UI.
- A non-TTY stderr (CI, piped) writes one line per step with a trailing
  newline instead of carriage return.

## Warning thresholds

Constants live in `specs/30_runtime_governance.md`:

- `WARN_USD_FRACTION = 0.8`
- `WARN_TOKEN_FRACTION = 0.8`
- `WARN_STEP_FRACTION = 0.8`

When `BudgetGuard` crosses a threshold for the first time in a run, it emits
a single `budget_event` with `reason ∈ {warn_usd, warn_tokens, warn_steps}`
and `crossed_at_step`. The event is **not** an abort. The hard caps remain
the only termination triggers.

## Per-event attribution

Every event the trace recorder writes must carry these fields (or
`null` where structurally inapplicable):

| Field | Applies to | Purpose |
|---|---|---|
| `agent_id` | all | UUID of the agent that produced the event (parent or sub-agent) |
| `agent_type` | all | `parent` \| `grilling` \| `explorer` \| `coder` \| `reviewer` |
| `parent_step_idx` | sub-agent events | parent step that spawned this sub-agent |
| `model_id` | `assistant_step` and any event tied to an OpenRouter request | exact model ID used |
| `tokens_in` / `tokens_out` | `assistant_step` | usage from the LiteLLM/OpenRouter response |
| `usd` | `assistant_step` | provider-returned cost or computed from `MODEL_CONFIG.md` pricing |
| `tool_call_index` | `tool_call`, `tool_result` | monotonically increasing per `agent_id` |
| `started_at` / `ended_at` | `subagent_spawn`, `subagent_return`, `tool_call` | ISO-8601 UTC; parallel overlap is computed from these |

`event_idx` (existing) remains the run-global monotonically increasing
identifier.

## BudgetGuard counters

`BudgetGuard` exposes:

- `total_tokens`, `total_usd`, `total_steps`.
- `per_agent_type_tokens` and `per_agent_type_usd` (dict keyed by `agent_type`).
- `remaining_*` derivations.
- `daily_remaining_usd` from `DailySpendLedger`.

Surfaced via:

- The statusline (each parent step).
- `--budget` CLI flag (one-shot summary at the end of a run, machine-readable
  JSON to stdout).
- `/budget` slash command in `--chat`.

## FinOps data contract (frontend deferred)

A future FastAPI + Pydantic + React frontend must be able to render the run
from JSONL alone, while normal dashboard queries should use the SQLite mirror.
Store rich structured data now; do not require the frontend for v1:

- Per-step timeline with per-agent token usage.
- Compaction events with `original_event_idx` and `original_sha256`.
- Approval events with decision + scope.
- Statusline strings (already in the trace as `statusline` events).
- Tool-call counts per agent / per type.
- Wall-clock overlaps for parallel sub-agents.
- Turn-level rows for prompt duration, model/tool counts, tokens, cost, status,
  and normalized failure reason.
- Model/tool rows for latency, token usage, cost, status, and error summaries.

## SQLite mirror

- Default path: `<workspace_root>/traces/vg_agent.sqlite3`.
- JSONL remains canonical for replay. SQLite mirrors the same redacted events
  and adds derived tables for dashboard queries.
- The mirror stores sessions, runs, turns, model calls, tool calls, sub-agents,
  approvals, redactions, and compactions.
- SQLite write failures must not abort agent execution; JSONL tracing continues.

A spec assertion in `40_demo_and_eval.md` checks that a representative trace
contains every field listed above at least once.

## Trace location

- Default: `<workspace_root>/traces/<run_id>.jsonl`.
- In `--chat` mode the path is `<workspace_root>/traces/<session_id>.jsonl`;
  multiple user turns append to the same file.
- The `traces/` directory is created with mode 0700 on POSIX. On Windows the
  directory is created with default ACL and the runtime logs a warning if it
  is world-readable.
