# 40 Demo And Eval

Fixture layout:

- `app.py`
- `auth/__init__.py`
- `auth/session.py`
- `auth/middleware.py`
- `utils.py`
- `README.md`
- `data/sample.log`

The sample log is deterministic and larger than 200 KB so the parent
`read_file data/sample.log` result exceeds `K_COMPACT`.

VG slide assertions (context engineering — VG.2):

- A deterministic demo step reads `data/sample.log` through the parent so at
  least one parent `tool_result` exceeds `K_COMPACT`.
- A parent-scoped `compaction` event exists for that `tool_use_id`.
- `compaction.original_event_idx` points to the original event.
- `compaction.original_sha256` equals SHA-256 of the original
  `tool_result.result_full`.
- `--show-context <last_step>` contains the compacted marker.
- `--show-context <last_step>` does not contain original `sample.log` content.
- A separate parallel-Explorer step proves sub-agent offloading: parent
  context contains only sub-agent return summaries, not sub-agent
  intermediate tool calls or tool results.

Parallel-sub-agent assertions (VG.1):

- A demo run with Scene 2's task emits two `subagent_spawn{agent_type:"explorer"}`
  events whose `[started_at, ended_at]` intervals overlap.
- Both `subagent_return{status:"ok"}` payloads are referenced (sentinel
  substring match) in the next parent `assistant_step.content`.
- `MAX_PARALLEL_SUBAGENTS = 4` is enforced: a fifth request in one
  `spawn_subagents` call returns `subagent_return{status:"tool_error",
  reason:"parallel cap exceeded"}` for the overflow without spawning.

Grilling assertions (VG.1 reinforcement, VG.9):

- The task `"make it better"` triggers a `subagent_spawn{agent_type:"grilling"}`
  as the first spawn of the turn.
- Grilling's `subagent_return.payload` parses as JSON with either
  `{questions: [...]}` or `{refined_task: "..."}`.
- When `questions` is returned, the next parent `assistant_step` surfaces
  the questions and the run ends with `run_end{final_status:"ok"}` without
  further spawns.

Coder / parent-no-write assertions (VG.6):

- The parent's tool schema does not include `write_file` or `edit_file`. A
  unit test imports the parent tool list and asserts the absence.
- A task requiring a mutation emits `subagent_spawn{agent_type:"coder"}`;
  the Coder's private trace contains the `tool_call` of the write/edit;
  the file mutation is observable on disk after `run_end`.
- Two Coders spawned for overlapping write paths produce one
  `subagent_return{status:"conflict"}` for the second.

Partial-edit assertions (VG.6, `str_replace`):

- `edit_file(path, old_string="foo", new_string="bar")` on a file
  containing `foo` exactly once produces a partial edit: the resulting
  file size delta equals `len(new_string) - len(old_string)` bytes (the
  rest of the file is byte-identical to the original outside the
  replaced range).
- `edit_file` with an `old_string` that does not appear in the file
  returns `tool_result.status="error"` with reason `"not_found"`.
- `edit_file` with an `old_string` that appears more than once returns
  `tool_result.status="error"` with reason `"ambiguous"`.
- Scene 1 of the demo runbook exercises `edit_file` as the canonical
  `str_replace` operation.

Parallel-default assertions (VG.1 reinforcement):

- A task naming ≥2 distinct paths (e.g., `"summarise auth/ and utils.py"`)
  produces exactly one `spawn_subagents` call with ≥2 requests, **not** a
  sequence of single `spawn_subagent` calls. The trace shows overlapping
  `[started_at, ended_at]` for the resulting `subagent_spawn` events.

Cost monitoring assertions (VG.3):

- A run that crosses 80% of `MAX_USD_PER_RUN` emits
  `budget_event{reason:"warn_usd"}` exactly once and continues until the
  hard cap.
- A run past `MAX_USD_PER_RUN` emits `budget_event{reason:"usd_cap"}`
  immediately followed by `run_end{final_status:"aborted"}`.
- The statusline string for the warned step contains the `!` highlight
  prefix on the USD section.

Statusline assertions (VG.3, observability):

- Each parent step writes exactly one `statusline` event to JSONL.
- The matching stderr line matches the format in `specs/60_observability.md`.
- The trace contains `model_id`, `tokens_in`, `tokens_out`, `usd` on every
  `assistant_step`, and `tool_call_index` monotonically increasing per
  `agent_id`.

Safety-slide assertions (VG.4, VG.5):

- `read_file .env` (and any sensitive-path pattern) returns a
  `tool_result.status="error"` with reason `"sensitive path"` and never
  invokes the underlying read.
- `read_file .env.example` returns `ok`.
- `run_bash "find . -exec rm {} \;"` and `run_bash "find . -delete"` are
  refused before `bash -c` is invoked.
- `run_bash "sed -i 's/a/b/' app.py"` is refused (sed is not on the
  allowlist).
- With `--require-approval writes`, a denied `spawn_subagent` for a Coder
  records an `approval` event with `decision="denied"` and does not spawn
  the sub-agent.
- With `--yes`, the same Coder spawn records `approval` with
  `decision="auto"`.
- `run_bash "pwd"` or `run_bash "rg foo app.py"` succeeds and records a real
  shell-backed `tool_result{status:"ok"}`.

Cost-ledger assertions (VG.3 persistence):

- After two runs that each consume some USD, `.vg_daily_spend.json`
  reflects the cumulative spend for the UTC date and a fresh `BudgetGuard`
  reports reduced `daily_remaining_usd`.

Egress-slide assertions:

- Constructing an `AnthropicClient` with
  `endpoint="https://evil.example/v1/messages"` and calling `complete()`
  raises `EndpointPinViolation` before any socket is opened.

Trace-redaction assertions:

- A tool result containing `sk-ant-abc…` is redacted to `***REDACTED***` in
  the trace and in `--show-context`.
- A `redaction` event records the pattern and count.

Chat-mode assertions:

- Two prompts piped into `--chat` produce one JSONL with one `session_id`.
- `BudgetGuard` counters are monotone across turns.
- A turn-2 call that matches a turn-1 scoped approval records
  `decision="approved_scoped"` without invoking the prompt callback.

Replay assertions (the deterministic / CI path):

- `--replay <recorded>.jsonl` reproduces every `event_idx` and `kind` from
  the original run with no network call.
- Replay preserves `agent_id`, `agent_type`, `started_at`, and `ended_at`
  from the original.
- A replayed run with `--network none` (Docker `vg-agent` service) completes
  successfully, proving no network was needed.

Live-mode test assertions (optional live path):

- `--live-model` without `ANTHROPIC_API_KEY` exits non-zero with a clear
  error.
- A fake parent client can request a read and trigger a Coder spawn against
  a temp fixture.
- A fake parent client can spawn two Explorers in one
  `spawn_subagents` call; parent context contains only their summaries.
- A fake client can force a live budget abort before any network call.
- Live parent tool results above `K_COMPACT` are compacted before the next
  model turn.

Packaging assertions (VG.7, VG.8):

- `docker compose config` exits 0.
- `docker compose run --rm vg-agent --seed-fixture` exits 0 and creates the
  deterministic fixture under the mounted `./workspace`.
- `.env.example` enumerates every variable the agent reads from the
  environment.
- `config.example.toml` enumerates every non-secret config key accepted by
  the loader; secrets are rejected from TOML and read only from env.
- `git check-ignore .env` exits 0 in a fresh checkout.
- Optional CI step: `docker compose run --rm vg-agent --task "list files"`
  exits 0 when `DOCKER_AVAILABLE=1`. Otherwise the test is skipped with an
  explicit reason.

Provenance assertions:

- Generated runtime code, tests, fixtures, and demo scripts can be reproduced
  from markdown specs, prompt/config markdown, or generated-code templates.
- The parent and all sub-agent system prompts compiled into runtime code
  match the corresponding sections of `PROMPTS.md` (a sentinel assertion
  detects drift).
- The demo runbook (`specs/70_demo_runbook.md`) names the JSONL signals a
  grader can verify post-hoc for each scene.
- The demo explains which files are generated and how their source markdown
  is checked.
