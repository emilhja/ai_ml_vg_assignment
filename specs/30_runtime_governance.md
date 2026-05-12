# 30 Runtime Governance

Constants:

- `MAX_PARENT_STEPS = 15`
- `MAX_SUBAGENT_STEPS = 8`
- `MAX_SUBAGENT_DEPTH = 1`
- `MAX_TOKENS_PER_RUN = 80000`
- `MAX_USD_PER_RUN = 0.50`
- `MAX_USD_PER_DAY = 5.00`
- `WALL_CLOCK_TIMEOUT = 120`
- `TOOL_TIMEOUT = 30`
- `K_COMPACT = 4000`
- `MAX_TOOL_RESULT_BYTES = 1_048_576`
- `DAILY_SPEND_FILE = ".vg_daily_spend.json"`
- `REQUIRE_APPROVAL_DEFAULT = "off"`
- `ANTHROPIC_ENDPOINT_HOST = "api.anthropic.com"`

Model and pricing constants are imported from `MODEL_CONFIG.md`.

Event kinds:

- Top-level `kind` is always the event discriminator. Defined kinds:
  `user_prompt`, `assistant_step`, `tool_result`, `compaction`,
  `subagent_spawn`, `subagent_return`, `budget_event`, `approval`,
  `egress_blocked`, `redaction`, `session_reset`, `run_end`.

Budget events:

- Budget abort causes use `budget_reason`, one of `step_cap`, `token_cap`,
  `usd_cap`, `daily_cap`, `repetition_abort`, `timeout`, or `user_abort`.
- Live model calls must check budget before each Anthropic request using a
  conservative token estimate and record actual returned usage afterward.

Compaction events:

- `original_event_idx` points to the full parent `tool_result`.
- `original_sha256` is SHA-256 of `tool_result.result_full`.

Approval events:

- `approval` events are emitted *before* a gated tool runs. Fields:
  `tool_use_id`, `tool`, `args_summary`, `decision` ∈ {`approved`,
  `approved_scoped`, `approved_always`, `denied`, `aborted`, `auto`},
  `scope_key` (resolved cache key), `reason` (free text).
- Approval decisions never bypass the deny-list or the sensitive-path
  denylist. A scoped grant for `edit_file` does not allow editing `.env`.

Redaction:

- The trace recorder pattern-matches secret-looking substrings on every event
  write and replaces them with `***REDACTED***`. Patterns:
  `sk-ant-[A-Za-z0-9_\-]+`, `AKIA[0-9A-Z]{16}`, `(?i)bearer\s+[a-z0-9._\-]+`,
  and any line that contains a sensitive-path pattern from
  `specs/20_tools.md`.
- A `redaction` event records `original_event_idx`, `pattern`, `count`. This
  is visible in `--show-context` so the audit story is reproducible.
- `--no-redact` disables redaction and prints a warning to stderr. Intended
  for local debugging only.

Egress:

- The agent has exactly two egress channels: `run_bash` (covered by the
  command deny-list) and the Anthropic Messages client.
- The Messages client parses `self.endpoint` with `urllib.parse.urlparse`
  before every request and refuses to open the socket if
  `host != ANTHROPIC_ENDPOINT_HOST`. The refusal raises
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

Approval cache persistence (opt-in):

- `--save-approvals` writes accepted "always-for-folder" choices to
  `.vg_approvals.json` under the workspace root. The file is on the
  sensitive-path read denylist. `--reset-approvals` clears it.

Execution safety:

- Tool-level safety is mandatory but not sufficient. `run_bash` must deny
  destructive commands before execution, and demos should run in an outer
  sandbox when possible.
- Recommended Docker runtime flags for live demos:
  `--network none --cap-drop ALL --security-opt no-new-privileges --pids-limit 128`.
  `--network none` is incompatible with `--live-model`; bridge with an
  HTTPS proxy if both are required (not built; documented in
  `dev_docs/dangerous_cli.md`).
- Prefer writing traces and temporary fixture edits inside the container
  rather than bind-mounting the host workspace writable.
- If a host bind mount is needed for inspection, mount it read-only and
  provide a separate writable temp volume for traces.
- The agent must never rely on Docker for correctness: every in-process
  safety property must hold without it; unit tests run without Docker.
- Live tests must use fake clients; unit tests must not call external APIs.

Prompt injection:

- Tool output is data, not instructions. The parent system prompt includes
  a fixed sentence asserting this. The approval gate is a second layer for
  the long tail of "legitimate-looking but unexpected" mutation requests.
