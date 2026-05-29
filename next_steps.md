# Next Steps

## 0. Typed-pipeline upgrade — follow-ups (2026-05-28)

The live agent loop now implements the full typed pipeline (Grilling, Explorer,
Coder, Reviewer), genuinely concurrent `spawn_subagents` (ThreadPoolExecutor +
barrier, overlapping `started_at`/`ended_at`), a parent with **no** write tools
(Coder is the sole mutation path), per-event `agent_type`, cross-turn chat
history, and a `--finops` / `/finops` per-agent-type view. All covered by
`uv run pytest` (38 tests). Remaining:

- **Record canonical live traces** (needs `OPENROUTER_API_KEY` + network): run
  each runbook scene with `--live-model --trace` and save the JSONL under
  `fixtures/demo_repo/traces/<scene>.jsonl` so graders can `--replay` them
  offline (the runbook now points at these).
- **Reviewer** is wired as a spawnable type but has no dedicated demo scene/test
  yet; add one (verify Coder's change is present on disk → `PASS`/`FAIL`).
- **Retire the `run_task` CI shim** once the offline cap/safety tests are
  migrated to `FakeClient` + `--replay`; it is currently labelled a CI-only
  shim in `specs/70` and still routes the parent edit directly in its
  `rename foo→bar` branch (the only place the parent "writes").
- Optional: surface the per-agent-type breakdown on the live chat statusline.


## 1. Run Deterministic Smoke Demo

Verify the existing no-network demo path still behaves as expected:

```powershell
cd fixtures/demo_repo
uv run --project ../.. python -m vg_agent --task "find all auth handling and summarise" --trace --show-context 3
```

Check that:

- the trace includes a parent compaction event;
- Explorer intermediate reads are absent from parent context;
- the deterministic demo remains stable without `OPENROUTER_API_KEY`.

## 2. Optional Live API Smoke Test

Use this only as an extension after the deterministic VG demo passes. Use a
disposable fixture copy or regenerated fixture before testing live edits.

```powershell
$env:OPENROUTER_API_KEY="..."
uv run python -m vg_agent --task "inspect app.py and suggest one small improvement" --live-model --require-approval writes --trace --show-context 3
```

Review the resulting JSONL trace for:

- model-selected tool calls;
- refused unsafe commands or path escapes;
- large-result compaction;
- `approval` events for each gated tool call;
- Explorer summaries appearing in parent context without child intermediate
  results.

## 3. Harden Live Writes — done

The following items from the earlier list are now implemented and covered by
tests: approval gating (`--require-approval`, `--yes`), persisted daily-spend
tracking (`.vg_daily_spend.json`), CLI flags for clearer output. Persistence
of "yes-folder" grants across sessions (`--save-approvals`,
`--reset-approvals`) is still future work.

## 4. Extend Presentation Script — done

`scripts/run_demo.ps1` now includes approval, denylist, and chat-mode
segments alongside the deterministic VG slide. All segments run without
`OPENROUTER_API_KEY`.

## 5. Broaden Regression Coverage

Remaining useful follow-up tests:

- live timeout behavior with a fake slow client;
- malformed model tool-call payloads;
- Explorer attempts to call write/edit/spawn tools;
- CLI behavior when live mode ends with `tool_error`;
- trace replay from a live run containing compaction and Explorer events;
- HTTPS proxy bridging `--network none` Docker + `--live-model`.

## 6. Future Safety Hardening

- `.vg_approvals.json` persistence with `--save-approvals` / `--reset-approvals`.
- Outbound HTTPS proxy implementation that lets `--network none` Docker
  coexist with `--live-model`.
- On-disk encryption of traces (current redaction handles the realistic
  threat; full encryption is overkill for the current scope).
