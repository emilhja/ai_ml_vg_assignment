# 12 Sub-Agent Pipeline

Sub-agents are typed. The parent never writes files directly; it spawns the
right type for each step.

## Types and tool surfaces

| Type | Read tools | Write tools | May spawn | Model |
|---|---|---|---|---|
| `grilling` | none | none | no | `GRILLING_MODEL_ID` |
| `explorer` | `read_file`, `read_file_range`, `run_bash` (read-only allowlist) | none | no | `EXPLORER_MODEL_ID` |
| `coder` | Explorer's tools plus `run_tests` | `write_file`, `edit_file` | no | `CODER_MODEL_ID` |
| `reviewer` | Explorer's tools, plus the JSONL slice of the Coder run under review | none | no | `REVIEWER_MODEL_ID` |

- `MAX_SUBAGENT_DEPTH = 1` applies to every type. No sub-agent may call
  `spawn_subagent` or `spawn_subagents`.
- Coder is the **only** mutation path in the system. The parent's tool surface
  does not include `write_file` or `edit_file`.
- Coder is always gated by the approval policy in `writes` and `all` modes.
- Reviewer never modifies files; a FAIL verdict surfaces to the parent, which
  decides whether to spawn another Coder cycle or yield to the user.

## Sequential pipeline (default order)

For a given user turn the parent decides per step which type to spawn:

1. **Grilling** — invoked when the task is ambiguous. Heuristic: task length
   < 30 tokens, OR no concrete file paths/identifiers, OR contains
   high-ambiguity words (`make it better`, `find all`, `everything`, `the
   bug`). `--no-grill` bypasses this step.
   - Grilling returns either `{questions: [...]}` (parent surfaces to user, no
     further spawns this turn) or `{refined_task: "..."}` (parent continues).
2. **Explorer** — bounded repository inspection. Sequential by default. See
   parallel fan-out below.
3. **Coder** — invoked when the refined task requires a file mutation.
   Coder must call `write_file` or `edit_file` successfully at least once
   before returning; a read-only exit is reported as
   `subagent_return{status:"tool_error"}`.
4. **Reviewer** — invoked **after every successful Coder** on fix/review tasks
   (not before Coder; Reviewer verifies Coder output, not pre-fix exploration).
   Optional only for trivial single-line edits the parent is confident about.

**Reviewer is a regression / integration guard, not a general code-quality
auditor.** Its mandate follows from its wiring: it is read-only and receives
only the JSONL slice of the Coder run (see below), so it answers *"did this
edit break or correctly integrate with pre-existing code?"* — not *"is this new
code well written?"*. Two consequences:

- **Greenfield creation — a brand-new file with no existing callers — does not
  require a Reviewer.** There is nothing to regress against, and every spawn
  costs tokens/$, so on this (common) case the parent instructs the Coder to
  finish with a single `python3 -m py_compile <new file>` self-check and yield.
  This is a deliberate cost/scope tradeoff, not a missing step: greenfield
  *correctness* is the Coder's own responsibility, covered by that self-check.
- **`py_compile` is a syntax gate, not a behavior gate.** It confirms the file
  parses; it cannot catch logic bugs. Greenfield logic errors therefore have no
  Reviewer safety net by design. If behavior-level coverage is wanted on new
  code, the right mechanism is a Coder-authored smoke/`test_*.py` (which *does*
  trigger a Reviewer, since tests count as a reviewable artifact) — not
  widening Reviewer's mandate to greenfield.

The parent decides each transition autonomously (VG.9). The pipeline is a
guideline encoded in the parent system prompt, not a fixed Python switch.

### Reviewer JSONL slice (runtime)

When the parent spawns `type:"reviewer"`, the runtime automatically attaches
the JSONL trace slice for the Coder run under review:

- `SubagentRequest` may include optional `review_agent_id` (e.g. `"coder-2"`).
  When omitted, the runtime uses the most recent `coder-*` child in the
  current run trace.
- `_build_review_slice(recorder, coder_agent_id)` serialises events where
  `agent_id == coder_agent_id`, capped at ~8 KB, and injects them into the
  Reviewer's first user message.
- Reviewer must call at least one read tool (`read_file`, `read_file_range`,
  or allowlisted `run_bash`) before returning; text-only exits are
  `tool_error`.
- Reviewer final message must start with `PASS:` or `FAIL:`. If the reviewer
  runs out of budget/steps or otherwise stops before producing a verdict, the
  runtime returns a deterministic `FAIL:` with a short reason (and marks the
  sub-agent status as `tool_error`).
- Spawning `reviewer` without a prior Coder in the current run trace returns
  `tool_error` with guidance to use Explorer for read-only review.

### Coder test guard

When the spawn `question` mentions `test_*.py`, pytest, or tests, Coder must
successfully `read_file` or `read_file_range` an implementation `.py` (non-test)
before `write_file` on a test file. Violations are `tool_error`.

### Coder empty-turn hardening

Some live providers occasionally return an empty Coder step (`assistant_text`
blank and no `tool_calls`) even for explicit write instructions. Runtime must:

- detect this as an `empty_turn` condition (not a normal completion),
- retry Coder locally with a deterministic nudge that explicitly requires
  `write_file` or `edit_file`,
- cap retries (bounded, no infinite loop),
- emit trace diagnostics so this failure mode is visible during review.

If retries are exhausted, Coder returns `tool_error` with a deterministic reason
indicating repeated empty turns.

### Verify loop (fix + test)

After Reviewer `PASS:` and when tests exist, the parent calls
`run_tests("<path>")` — never `run_bash pytest`. On `run_tests` failure, the
parent receives the error as a **soft tool result** (the turn continues so
the parent can re-spawn Coder with the traceback). Hard `run_end{final_status:
"tool_error"}` is reserved for approval abort, budget deny, and non-recoverable
tool blocks.

`subagent_return` events for Coder include `writes_ok` and `reads_ok` counts
so the parent can detect empty Coder returns.

## Parallel fan-out

The parent has two spawn tools:

- `spawn_subagent(request: SubagentRequest) -> SubagentReturn` for one
  sub-agent.
- `spawn_subagents(requests: list[SubagentRequest]) -> list[SubagentReturn]`
  for two or more sub-agents.

`spawn_subagents` runs requests concurrently and awaits all returns before
the next parent model turn.

**Parallel is the default for independent work.** When the parent
identifies ≥2 independent inspection targets (different files, different
directories, or otherwise non-overlapping questions) in a single turn, it
MUST call `spawn_subagents` once with all of them rather than issuing
serial `spawn_subagent` calls. The parent system prompt encodes this
expectation. Tests assert that a task naming ≥2 distinct paths produces
overlapping `subagent_spawn` events in the trace.

- Implementation may use `asyncio.gather` or
  `concurrent.futures.ThreadPoolExecutor`; the trace contract is what matters.
- `MAX_PARALLEL_SUBAGENTS = 4`.
- Mixed types are allowed in one call (e.g., two Explorers + one Reviewer).
- Coder may not be invoked in parallel with another Coder targeting the same
  workspace — the runtime serialises Coders by detecting overlapping write
  paths and returning `subagent_return{status:"conflict"}` for the second.
- Each parallel sub-agent receives its own budget slice equal to
  `remaining_run_budget / len(requests)` (USD and tokens from the shared
  parent `BudgetGuard`). If any child exceeds its slice, the runtime sets a
  batch abort flag, cancels remaining in-flight peers at the next safe
  checkpoint, and emits one
  `budget_event{budget_reason:"parallel_aborted", offender_agent_id:"…"}`.
  Cancelled children return `subagent_return{status:"parallel_aborted"}`.
- `subagent_spawn` and `subagent_return` events carry `started_at` and
  `ended_at` (UTC ISO-8601). Overlap is observable directly from the trace.

### Near-cap finalization (parent step reserve)

- `FINAL_STEP_RESERVE = 1`: when `parent_step_count >= max_steps - 1`, the
  parent must not call `spawn_subagent` or `spawn_subagents` (reserved for
  synthesis / user-facing completion). The runtime blocks these tools with a
  soft `tool_result` payload (`near_cap_blocked`) so the parent can finalize
  instead of burning the last step on new sub-agent work.
- This is independent of the proactive `step_extend` offer at 14/15.

### Parallel failure recovery

- When `spawn_subagents` returns one or more non-`ok` Coder entries with an
  actionable `failure_reason` (`invalid_path_kind`, `no_write`,
  `no_terminal_summary`, blocked-shell reasons, generic `tool_error`), the
  runtime performs a **bounded same-turn constrained retry** for each failed
  Coder (max **2** retries per parent tool call) before the parent sees the
  payload. Each retry emits `budget_event{budget_reason:"coder_constrained_retry"}`.
- If retries are exhausted, the parent receives the failed payload plus
  explicit recovery hints; it must not launch another parallel batch on the
  final reserved step.

## Failure modes

Every `subagent_return` has a `status` field. The parent must branch on it.

| Status | Cause | Parent behavior |
|---|---|---|
| `ok` | normal return ≤2 KB | use payload |
| `timeout` | wall-clock exceeded `TOOL_TIMEOUT` | retry once with reduced scope, then yield with error |
| `oversize` | return >2 KB after one retry instruction | use truncated payload, mark in final answer |
| `tool_error` | a tool inside the sub-agent failed and the sub-agent exhausted `MAX_SUBAGENT_STEPS` without completing | sub-agent may retry within `MAX_SUBAGENT_STEPS` after a tool error; parent reads `reason`, decides retry vs. yield |
| `conflict` | Coder write-path conflict | serialise: re-spawn after the prior Coder returns |
| `parallel_aborted` | budget slice exceeded in a parallel batch | parent reads offender id; do not re-spawn in parallel on the reserved final step |
| `near_cap_blocked` | parent at `max_steps - FINAL_STEP_RESERVE` tried to spawn | parent must synthesize and answer; no new spawns this turn |

Sub-agent terminal summaries use structured reasons, e.g.
`coder exited without summary (reason=no_terminal_summary)`, not a generic
"stopped before producing a final summary" string.

A failed sub-agent return is **never** silently dropped. Tests assert that
every non-`ok` status produces either a follow-up `subagent_spawn` or a
`run_end` within two parent steps.

## Sub-agent context isolation (preserved from `11_subagent_explorer.md`)

- Parent context receives only the `subagent_return.payload` string (≤2 KB).
  Intermediate `assistant_step`, `tool_call`, `tool_result` events from the
  sub-agent stay in the JSONL trace under that sub-agent's `agent_id` and are
  filtered out of `show_context`.
- `agent_id == "parent"` filter in `show_context` is unchanged; `agent_type`
  is a new field but does not affect context filtering.

## Consumption assertion

For every `subagent_return{status:"ok"}` event, at least one subsequent
parent `assistant_step` within the same turn must reference content
obtainable only from that return. Tests check this by string-matching a known
sentinel from the sub-agent return in the parent's next message.
