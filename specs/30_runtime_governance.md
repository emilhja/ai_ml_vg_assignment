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

Model and pricing constants are imported from `MODEL_CONFIG.md`.

Budget events:

- Top-level `kind` is always the event discriminator.
- Budget abort causes use `budget_reason`, one of `step_cap`, `token_cap`,
  `usd_cap`, `daily_cap`, `repetition_abort`, or `timeout`.
- Live model calls must check budget before each Anthropic request using a
  conservative token estimate and record actual returned usage afterward.

Compaction events:

- `original_event_idx` points to the full parent `tool_result`.
- `original_sha256` is SHA-256 of `tool_result.result_full`.

Execution safety:

- Tool-level safety is mandatory but not sufficient. `run_bash` must deny
  destructive commands before execution, and demos should run in an outer
  sandbox when possible.
- Recommended Docker runtime flags for live demos:
  `--network none --cap-drop ALL --security-opt no-new-privileges --pids-limit 128`.
- Prefer writing traces and temporary fixture edits inside the container rather
  than bind-mounting the host workspace writable.
- If a host bind mount is needed for inspection, mount it read-only and provide
  a separate writable temp volume for traces.
- The agent must never rely on Docker for correctness: the in-process command
  safety gate is still required and unit-tested.
- Live tests must use fake clients; unit tests must not call external APIs.
