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

VG slide assertions:

- At least one parent `tool_result` exceeds `K_COMPACT`.
- A parent-scoped `compaction` event exists for that `tool_use_id`.
- `compaction.original_event_idx` points to the original event.
- `compaction.original_sha256` equals SHA-256 of the original
  `tool_result.result_full`.
- `--show-context <last_step>` contains the compacted marker.
- `--show-context <last_step>` does not contain original `sample.log` content.
- Parent context contains only Explorer return summary, not Explorer
  intermediate tool calls or tool results.

Safety-slide assertions:

- `read_file .env` (and any sensitive-path pattern) returns a
  `tool_result.status="error"` with reason `"sensitive path"` and never
  invokes the underlying read.
- `read_file .env.example` returns `ok`.
- `run_bash "find . -exec rm {} \;"` and `run_bash "find . -delete"` are
  refused before `bash -c` is invoked.
- `run_bash "sed -i 's/a/b/' app.py"` is refused (sed is not on the
  allowlist).
- With `--require-approval writes`, a denied `edit_file` records an
  `approval` event with `decision="denied"` and does not modify the file.
- With `--yes`, the same `edit_file` records `approval` with
  `decision="auto"`.

Cost-slide assertions:

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

Extension live-mode test assertions:

- `--live-model` without `ANTHROPIC_API_KEY` exits non-zero with a clear error.
- A fake parent client can request a read and edit against a temp fixture.
- A fake parent client can spawn Explorer and parent context contains only the
  Explorer summary.
- A fake client can force a live budget abort before any network call.
- Live parent tool results above `K_COMPACT` are compacted before the next
  model turn.

Provenance assertions:

- Generated runtime code, tests, fixtures, and demo scripts can be reproduced
  from markdown specs, prompt/config markdown, or generated-code templates.
- The parent and Explorer system prompts compiled into runtime code match
  the corresponding sections of `PROMPTS.md` (a sentinel assertion detects
  drift).
- The demo explains which files are generated and how their source markdown
  is checked.
