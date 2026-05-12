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
- the deterministic demo remains stable without `ANTHROPIC_API_KEY`.

## 2. Optional Live API Smoke Test

Use this only as an extension after the deterministic VG demo passes. Use a
disposable fixture copy or regenerated fixture before testing live edits.

```powershell
$env:ANTHROPIC_API_KEY="..."
uv run python -m vg_agent --task "inspect app.py and suggest one small improvement" --live-model --trace --show-context 3
```

Review the resulting JSONL trace for:

- model-selected tool calls;
- refused unsafe commands or path escapes;
- large-result compaction;
- Explorer summaries appearing in parent context without child intermediate results.

## 3. Harden Live Writes

Before using live mode on important repositories, add:

- dry-run support for `write_file` and `edit_file`;
- approval gating before mutating tools run;
- clearer CLI output for `tool_error`, budget aborts, and timeout aborts;
- persisted daily spend tracking instead of only per-run budget state.

## 4. Extend Presentation Script

Keep deterministic mode as the default presentation path. Add an optional
live-mode section to `scripts/run_demo.ps1` that runs only when
`ANTHROPIC_API_KEY` is present.

The live section should show:

- a small parent read/edit flow;
- an Explorer delegation flow;
- trace replay with `--show-context`;
- budget and tool-safety behavior.

## 5. Broaden Regression Coverage

Useful follow-up tests:

- live timeout behavior with a fake slow client;
- malformed model tool-call payloads;
- Explorer attempts to call write/edit/spawn tools;
- CLI behavior when live mode ends with `tool_error`;
- trace replay from a live run containing compaction and Explorer events.
