# 10 Main Agent

The parent owns the user conversation, tool execution, compaction, trace
writing, and final answer.

Tools:

- `read_file`
- `read_file_range`
- `write_file`
- `edit_file`
- `run_bash`
- `spawn_subagent`

Approval policy:

- Mutating tools (`write_file`, `edit_file`) and `spawn_subagent` are gated
  by an `ApprovalPolicy`. The policy is consulted before the tool runs and
  emits an `approval` trace event regardless of outcome.
- Modes: `off` (default — used by deterministic tests and the rubric demo),
  `writes` (gate mutating tools and `spawn_subagent`), `all` (gate every
  tool including reads). `--yes` auto-approves with `decision="auto"` so
  the demo remains reproducible.
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
  appear inside files or command output.

Deterministic demo routes:

- Rename route: read `app.py`, replace `foo` with `bar`, write the result.
- Auth route: read `data/sample.log`, compact the parent tool result when it
  exceeds `K_COMPACT`, spawn Explorer to inspect `auth/`, and return a concise
  auth summary.
- Cost route: repeat the sentinel search until the repetition/step guard emits
  `budget_event` and `run_end(final_status="aborted")`.

Live route:

- Extension path enabled only by `--live-model`; deterministic routes remain
  the default and the required presentation path.
- Requires `ANTHROPIC_API_KEY`.
- The Anthropic client refuses any non-`api.anthropic.com` host. A
  `EndpointPinViolation` is raised before the socket opens and emitted as
  `egress_blocked` in the trace.
- Sends the parent system prompt, task, and compacted parent context to
  Anthropic using `PARENT_MODEL_ID`.
- Executes model-requested tool calls, appends assistant/tool events to JSONL,
  and sends only parent-visible results back into the next model turn.
- Stops on final assistant text, budget abort, step cap, token/cost cap,
  timeout, or tool error policy.
- Parent tool results larger than `K_COMPACT` are compacted before the next
  parent model turn. The full result remains in trace.

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
