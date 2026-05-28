# 12 Sub-Agent Pipeline

Sub-agents are typed. The parent never writes files directly; it spawns the
right type for each step.

## Types and tool surfaces

| Type | Read tools | Write tools | May spawn | Model |
|---|---|---|---|---|
| `grilling` | none | none | no | `GRILLING_MODEL_ID` |
| `explorer` | `read_file`, `read_file_range`, `run_bash` (read-only allowlist) | none | no | `EXPLORER_MODEL_ID` |
| `coder` | Explorer's tools | `write_file`, `edit_file` | no | `CODER_MODEL_ID` |
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
4. **Reviewer** — optional. Invoked after Coder when the parent wants a second
   pass; required when the Coder edit touches >1 file or the parent's
   confidence is low.

The parent decides each transition autonomously (VG.9). The pipeline is a
guideline encoded in the parent system prompt, not a fixed Python switch.

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
- Each parallel sub-agent receives its own `BudgetGuard` slice equal to
  `remaining_budget / len(requests)`. If any slice exceeds, the remaining
  in-flight sub-agents are cancelled and one
  `budget_event{reason:"parallel_aborted", offender_agent_id:"…"}` is emitted.
- `subagent_spawn` and `subagent_return` events carry `started_at` and
  `ended_at` (UTC ISO-8601). Overlap is observable directly from the trace.

## Failure modes

Every `subagent_return` has a `status` field. The parent must branch on it.

| Status | Cause | Parent behavior |
|---|---|---|
| `ok` | normal return ≤2 KB | use payload |
| `timeout` | wall-clock exceeded `TOOL_TIMEOUT` | retry once with reduced scope, then yield with error |
| `oversize` | return >2 KB after one retry instruction | use truncated payload, mark in final answer |
| `tool_error` | a tool inside the sub-agent failed | parent reads `reason`, decides retry vs. yield |
| `conflict` | Coder write-path conflict | serialise: re-spawn after the prior Coder returns |
| `parallel_aborted` | budget slice exceeded | yield with `run_end{final_status:"aborted"}` |

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
