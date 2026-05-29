# Next Steps

## 0. Live-only refactor — done (2026-05-29)

The agent now has a **single live runtime path** (`run_live_task`). The
deterministic `run_task` shim, the `--replay` mode, and the `network_mode: none`
Docker service were removed; `--task` runs live by default and exits `2` without
`OPENROUTER_API_KEY`. Docker is a single `vg-agent` service. The unit suite
exercises the live loop with an injected `FakeClient`/`PipelineClient` (no
network) and all tests pass under `uv run pytest`.

The live agent loop implements the full typed pipeline (Grilling, Explorer,
Coder, Reviewer), genuinely concurrent `spawn_subagents` (ThreadPoolExecutor +
barrier, overlapping `started_at`/`ended_at`), a parent with **no** write tools
(Coder is the sole mutation path), per-event `agent_type`, cross-turn chat
history, and a `--finops` / `/finops` per-agent-type view.

Remaining:

- **Reviewer** is wired as a spawnable type but has no dedicated demo scene/test
  yet; add one (verify Coder's change is present on disk → `PASS`/`FAIL`).
- Optional: surface the per-agent-type breakdown on the live chat statusline.

## 1. Live smoke test

Confirm the live path end-to-end against OpenRouter (small cost):

```powershell
docker compose run --rm vg-agent --seed-fixture
docker compose run --rm vg-agent --task "read data/sample.log, then summarise auth/ and utils.py in parallel" --trace --show-context 8
```

Review the resulting JSONL trace for:

- model-selected tool calls and the model deciding when to yield;
- one `spawn_subagents` call with two overlapping `subagent_return` events;
- large-result compaction for `data/sample.log`;
- refused unsafe commands or path escapes;
- `approval` events for each gated tool call (when `--require-approval` is set);
- Explorer summaries appearing in parent context without child intermediate
  results.

## 2. Harden Live Writes — done

Approval gating (`--require-approval`, `--yes`), persisted daily-spend tracking
(`.vg_daily_spend.json`), and CLI flags for clearer output are implemented and
covered by tests. Persistence of "yes-folder" grants across sessions
(`--save-approvals`, `--reset-approvals`) is still future work.

## 3. Broaden Regression Coverage

Remaining useful follow-up tests:

- live timeout behavior with a fake slow client;
- malformed model tool-call payloads;
- Explorer attempts to call write/edit/spawn tools;
- CLI behavior when live mode ends with `tool_error`.

## 4. Future Safety Hardening

- `.vg_approvals.json` persistence with `--save-approvals` / `--reset-approvals`.
- On-disk encryption of traces (current redaction handles the realistic
  threat; full encryption is overkill for the current scope).
