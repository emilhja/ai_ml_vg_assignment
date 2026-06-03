# 30 Runtime Governance

Constants:

- `MAX_PARENT_STEPS = 15` (counts parent model turns only; sub-agent and compactor
  turns do not consume this cap)
- `FINAL_STEP_RESERVE = 1` (when `max_steps > 2` and
  `parent_step_count >= max_steps - 1`, block parent `spawn_subagent` /
  `spawn_subagents` so the last step is reserved for synthesis; returns soft
  `near_cap_blocked` payload)
- `MAX_PARALLEL_CODER_RETRIES_PER_CALL = 2` (bounded constrained retries after
  `spawn_subagents` when Coder children return actionable `tool_error`)
- `MAX_SUBAGENT_STEPS = 8`
- `MAX_REVIEWER_STEPS = 3` (Reviewer-only step cap; a verdict on one changed
  file needs ≤2 tool calls, so Reviewer is bounded tighter than other types to
  contain runaway token cost. On exhaustion the runtime still returns the
  deterministic `FAIL:` verdict, same as `MAX_SUBAGENT_STEPS`.)
- `MAX_SUBAGENT_DEPTH = 1`
- `MAX_PARALLEL_SUBAGENTS = 4`
- `MAX_TOKENS_PER_RUN = 80000`
- `MAX_USD_PER_RUN = 0.50`
- `MAX_USD_PER_DAY = 5.00`
- `WARN_USD_FRACTION = 0.8`
- `WARN_TOKEN_FRACTION = 0.8`
- `WARN_STEP_FRACTION = 0.8`
- `WALL_CLOCK_TIMEOUT = 120`
- `TOOL_TIMEOUT = 30`
- `K_COMPACT = 4000`
- `PARENT_MAX_OUTPUT_TOKENS = 4096` (per-turn output cap for the parent model loop; also the worst-case output used by the budget preflight; overridable via `VG_MAX_OUTPUT_TOKENS`)
- `COMPACTOR_MAX_OUTPUT_TOKENS = 400`
- `COMPACTOR_MAX_INPUT_CHARS = 120_000` (payload cap sent to compactor; remainder noted with trace pointer)
- `COMPACTOR_MAX_SUMMARY_TOKENS = 300`
- `COMPACT_KEEP_RECENT_TURNS = 4` (conversation compaction tail)
- `DEFAULT_CONTEXT_WINDOW = 128_000`
- `DEFAULT_COMPACT_FRACTION = 0.80`
- Per-model `CONTEXT_WINDOW_TOKENS` and `AUTO_COMPACT_FRACTION` from `CONTEXT_WINDOWS.md`
- `MAX_TOOL_RESULT_BYTES = 1_048_576`
- `DAILY_SPEND_FILE = ".vg_daily_spend.json"`
- `SQLITE_TRACE_DB = "traces/vg_agent.sqlite3"`
- `REQUIRE_APPROVAL_DEFAULT = "off"`
- `STEP_EXTEND_PROMPT_ON_LAST_STEP = true` (proactive step-budget offer; disable via `--no-step-extend-prompt`)
- `OPENROUTER_ENDPOINT_HOST = "openrouter.ai"`

Model and pricing constants are imported from `MODEL_CONFIG.md`.

Event kinds:

- Top-level `kind` is always the event discriminator. Defined kinds:
  `user_prompt`, `assistant_step`, `tool_call`, `tool_result`, `compaction`,
  `context_compaction`, `subagent_spawn`, `subagent_return`, `budget_event`,
  `approval`,
  `egress_blocked`, `redaction`, `session_reset`, `statusline`, `run_end`.

Per-event attribution (see `specs/60_observability.md`):

- Every event carries `agent_id`, `agent_type`
  (`parent` | `grilling` | `explorer` | `coder` | `reviewer`), and
  `event_idx`.
- Sub-agent events also carry `parent_step_idx`.
- `assistant_step` events carry `model_id`, `tokens_in`, `tokens_out`,
  `usd`.
- `tool_call` and `tool_result` carry `tool_call_index` (monotonic per
  `agent_id`).
- `subagent_spawn`, `subagent_return`, and `tool_call` carry `started_at`
  / `ended_at` (ISO-8601 UTC). Parallel overlap is computed from these.

Budget events:

- `budget_reason` enum: `step_cap`, `token_cap`, `usd_cap`, `daily_cap`,
  `repetition_abort`, `timeout`, `user_abort`, `user_config`, `parallel_aborted`,
  `warn_usd`, `warn_tokens`, `warn_steps`, `warn_expensive_provider`.
- `warn_expensive_provider` is emitted **once per expensive OpenRouter slug per
  run** when `assistant_step` records `openrouter_provider` matching the denylist
  (`OPENROUTER_EXPENSIVE_PROVIDERS` or generated defaults). Does not abort.
  Details include `openrouter_provider`, `model_id`, `step_idx`, `agent_id`,
  `cost_usd`.
- `warn_*` reasons are emitted **once** when their respective fraction is
  first crossed; they do not abort the run. `warn_steps` uses parent-step
  progress (`parent_step_count / MAX_PARENT_STEPS`).
- **Proactive step extend** (`step_extend`): when interactive approval is
  configured and `STEP_EXTEND_PROMPT_ON_LAST_STEP` is enabled, the parent loop
  may offer **once per run** to raise `max_steps` immediately before the next
  parent model call when `step_count == max_steps - 1` (e.g. 14/15). Deny
  continues until the hard `step_cap`; abort ends the run. This is separate
  from `warn_steps` (80% log-only).
- `parallel_aborted` is emitted when any per-slice budget is exceeded inside
  a parallel `spawn_subagents` call; remaining in-flight sub-agents are
  cancelled at the next sub-agent loop checkpoint.
- `coder_constrained_retry` is emitted when the runtime auto-retries a failed
  Coder spawn (single or parallel batch) with a stricter constrained instruction
  after actionable sub-agent tool errors.
- **Spawn repetition guard:** `record_tool_signature` applies to
  `spawn_subagent` and `spawn_subagents` (normalized request payload). Three
  identical spawn signatures in a row emit `repetition_abort` (same as
  `run_bash`).
- Live model calls must check budget before each LiteLLM/OpenRouter request
  using a conservative token estimate and record actual returned usage
  afterward. If OpenRouter/LiteLLM returns explicit USD cost, use it;
  otherwise compute cost from the local pricing table for known configured
  models. Unknown live model pricing fails closed unless explicit cost is
  returned.
- **Configured-model pricing check** (after `.env` / `config.toml` / CLI
  model overrides): every role model id (`PARENT_MODEL_ID`, sub-agents,
  `COMPACTOR_MODEL_ID`) should appear in `PRICING_USD_PER_MTOK` from
  `MODEL_CONFIG.md`. If any are missing, emit a **stderr warning** on live
  startup (`--chat` / `--task`) listing the ids and pointing to `docs/PRICE.md`.
  When `VG_STRICT_MODEL_PRICING=1`, exit code `2` instead of continuing.
- Preflight `usd_cap` still uses the conservative unknown-model estimate for
  unpriced configured models (budget protection). The chat statusline must
  **not** show `(next ~$…)` or red cap styling from that estimate when the
  parent model is unpriced; see `specs/16_chat_ui.md`.

Tool-result compaction events (`kind: compaction`):

- `original_event_idx` points to the full parent `tool_result`.
- `original_sha256` is SHA-256 of `tool_result.result_full`.
- `summary` is produced by `COMPACTOR_MODEL_ID` (or stub when `compactor_fallback=true`).
- `compactor_model` records the model id used (or omitted on stub fallback).

Conversation compaction events (`kind: context_compaction`):

- `before_tokens`, `after_tokens`, `percent_reduced` on the in-memory parent message list.
- `reason` ∈ {`auto`, `manual`}.
- `model`, `window`, `threshold` for the parent model that triggered auto compaction.
- `summary` from the conversation compaction prompt.
- `trace_pointer` is the run id; full history remains in JSONL.

Approval events:

- `approval` events are emitted *before* a gated tool runs, when a
  proactive step extend is offered (`budget_reason=step_extend`), and when a
  hard budget cap would abort an interactive run (`tool="budget_cap"`,
  optional `budget_reason`). Fields: `tool_use_id`, `tool`, `args_summary`,
  `decision` ∈ {`approved`, `approved_scoped`, `approved_always`, `denied`,
  `aborted`, `auto`}, `scope_key` (resolved cache key), `reason` (free text).
- Approval decisions never bypass the deny-list or the sensitive-path
  denylist. A scoped grant for `edit_file` does not allow editing `.env`.

Redaction:

- The trace recorder pattern-matches secret-looking substrings on every event
  write and replaces them with `***REDACTED***`. Patterns:
  `sk-or-v1-[A-Za-z0-9_\-]+`, `AKIA[0-9A-Z]{16}`, `(?i)bearer\s+[a-z0-9._\-]+`,
  and any line that contains a sensitive-path pattern from
  `specs/20_tools.md`.
- A `redaction` event records `original_event_idx`, `pattern`, `count`. This
  is visible in `--show-context` so the audit story is reproducible.
- `--no-redact` disables redaction and prints a warning to stderr. Intended
  for local debugging only.

Egress:

- The agent has exactly two egress channels: `run_bash` (covered by the
  command deny-list) and the LiteLLM OpenRouter client.
- The OpenRouter client parses `self.endpoint` with `urllib.parse.urlparse`
  before every request and refuses to call LiteLLM if
  `host != OPENROUTER_ENDPOINT_HOST`. The refusal raises
  `EndpointPinViolation` and emits an `egress_blocked` event when invoked
  from inside the agent loop.

Daily spend persistence:

- `DailySpendLedger` reads/writes `.vg_daily_spend.json` under the workspace
  root, keyed by UTC date. `BudgetGuard.__init__` consults the ledger so
  `daily_remaining_usd` is correct across runs. `record_model_call` writes
  the new total.
- The ledger file is on the sensitive-path read denylist; the agent cannot
  inspect or rewrite it through `read_file`/`write_file`. On parse error the
  ledger refuses to load and the guard treats today's spend as already at
  the daily cap (fail closed).

SQLite observability persistence:

- `TraceRecorder` mirrors every redacted JSONL event into
  `SQLITE_TRACE_DB`. JSONL remains the canonical audit source; SQLite is the
  dashboard query store.
- SQLite stores the lossless event payload and derived rollup tables for
  sessions, runs, turns, model calls, tool calls, sub-agents, approvals,
  redactions, and compactions.
- SQLite failures are fail-open for execution: a warning is written to stderr
  and JSONL tracing continues.
- The SQLite connection must be usable from any thread that calls
  `TraceRecorder.emit` (parallel `spawn_subagents`). Use
  `check_same_thread=False` and a store-level write lock around `record_event`.

Approval cache persistence (opt-in):

- `--save-approvals` writes accepted "always-for-folder" choices to
  `.vg_approvals.json` under the workspace root. The file is on the
  sensitive-path read denylist. `--reset-approvals` clears it.

Execution safety:

- Docker is the **primary execution boundary** for demos
  (`specs/50_packaging.md`). `docker-compose.yml` defines a single
  `vg-agent` service with bridged network for OpenRouter live runs.
- Mandatory container flags applied by `docker-compose.yml`:
  `cap_drop: [ALL]`, `security_opt: [no-new-privileges]`, `pids_limit: 128`,
  non-root user `vg`.
- Tool-level safety is mandatory and independent of Docker. `run_bash` must
  deny destructive commands before execution; the sensitive-path denylist
  must hold for every file tool. Unit tests run without Docker and assert
  every in-process safety property.
- The bridged egress is constrained by the in-process egress pin
  (`OPENROUTER_ENDPOINT_HOST`), which refuses any non-OpenRouter host before a
  socket opens.
- The `./workspace` bind mount is read-write so the agent can edit fixture
  files; the host repo itself is never mounted into the container.
- Unit tests must use fake clients and must not call external APIs.
- The live demo is the grading proof. Unit tests reproduce the same hard caps,
  safety, and parallel trace shape against an injected fake client so the
  behaviors are verifiable in CI without the network.

Prompt injection:

- Tool output is data, not instructions. The parent system prompt includes
  a fixed sentence asserting this. The approval gate is a second layer for
  the long tail of "legitimate-looking but unexpected" mutation requests.
