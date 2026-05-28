# Next Steps

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
