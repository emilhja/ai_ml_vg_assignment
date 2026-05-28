# 10 Main Agent

The parent owns the user conversation, tool execution, compaction, trace
writing, and final answer. **The parent never writes files directly.** All
mutations go through a Coder sub-agent spawned via `spawn_subagent` or, when
batching independent work, `spawn_subagents`.

Tools available to the parent:

- `read_file`
- `read_file_range`
- `run_bash`
- `spawn_subagent`
- `spawn_subagents`

Notably absent: `write_file`, `edit_file`. Spawn Coder to perform any file
mutation. See `specs/12_subagent_pipeline.md` for the typed pipeline
(Grilling, Explorer, Coder, Reviewer) and parallel fan-out contract.

Approval policy:

- Gated tools are `spawn_subagent` / `spawn_subagents` (always — consume
  budget) and any
  mutating tool *inside* a Coder sub-agent (`write_file`, `edit_file`).
  Parent reads remain ungated in `writes` mode. The policy is consulted
  before the tool runs and emits an `approval` trace event regardless of
  outcome.
- Modes: `off` (default — used by deterministic replay and the rubric demo
  when run in replay mode), `writes` (gate sub-agent spawns and any
  Coder-internal write), `all` (gate every tool including reads). `--yes`
  auto-approves with `decision="auto"` so the demo remains reproducible.
- The policy holds an in-memory `ApprovalScopeCache`. Scope keys are
  `(tool, dir_prefix)`. Lookup order is exact dir → parent prefixes →
  `(tool, "*")`. First match wins. Scoped grants are persisted only when
  `--save-approvals` is set and are revoked by `--reset-approvals`.
- Scoped grants never override the command deny-list or the sensitive-path
  denylist. Granting `edit_file` for the workspace root does not let
  `.env` through.

Injection defense:

- The parent system prompt explicitly states that tool output is data,
  not instructions, and that the agent must never follow directives that
  appear inside files or command output. All sub-agent system prompts
  inherit this assertion (`PROMPTS.md`).

Parent loop (`--live-model` path):

- Requires `OPENROUTER_API_KEY`. Local replay-only runs use `--replay`
  instead and do not require the key.
- The LiteLLM OpenRouter client refuses any non-`openrouter.ai` host. A
  `EndpointPinViolation` is raised before the socket opens and emitted as
  `egress_blocked` in the trace.
- Sends the parent system prompt, task, and compacted parent context to
  OpenRouter through LiteLLM using `PARENT_MODEL_ID`.
- Executes model-requested tool calls, appends `assistant_step`,
  `tool_call`, and `tool_result` events to JSONL, and sends only
  parent-visible results back into the next model turn.
- Stops on final assistant text (no `tool_use` block), budget abort, step
  cap, token/cost cap, timeout, or tool error policy. **The model itself
  decides when to yield** — there is no scripted route (VG.9).
- Parent tool results larger than `K_COMPACT` are compacted before the next
  parent model turn. The full result remains in the JSONL trace and is
  retrievable via `read_file_range` or replay.
- The parent emits a `statusline` event and rewrites the stderr statusline
  at each step boundary (`specs/60_observability.md`).

Replay mode:

- `--replay <trace.jsonl>` reconstructs the parent loop deterministically
  by injecting recorded `ModelTurn` payloads through a `FakeClient`. No
  network call is made. This is the CI path and the demo-day safety net.
- Replay preserves all event indices, `agent_id`s, and `started_at` /
  `ended_at` timestamps from the original run.

Interactive chat mode:

- `--chat` opens a REPL serving multiple user turns from one process. The
  `BudgetGuard`, `ApprovalScopeCache`, and JSONL trace persist across turns
  for the life of the session under a single `session_id`.
- Slash commands handled before dispatch: `/exit`, `/quit`, `/reset`
  (clears approvals and budget; emits `session_reset`), `/budget`,
  `/show-context N`, `/approvals`, `/help`.
- Input history is appended to `.vg_history` (gitignored). Ctrl-C aborts
  the current turn with `budget_reason="user_abort"`; a second Ctrl-C
  exits.
- Non-TTY stdin reads newline-separated prompts and answers approval
  prompts from the same stream so the demo script can drive it.
