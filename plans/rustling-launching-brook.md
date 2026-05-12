# Plan: Initial CLAUDE.md for vg_assignment

## Context

This repo currently has no `CLAUDE.md`. The user ran `/init` to bootstrap one
so future Claude Code instances can be productive quickly. The repo is a
spec-first VG assignment: markdown specs (`specs/*.md`, `PROMPTS.md`,
`MODEL_CONFIG.md`) are the source of truth, and `scripts/generate_project.py`
regenerates `src/vg_agent/` + `fixtures/demo_repo/` from them. The key thing a
new agent must understand on first contact is **do not hand-edit generated
runtime code** — change the spec/template and regenerate.

The plan below specifies the exact contents to write to
`C:\Users\emil_\vscode\vg_assignment\CLAUDE.md` once plan mode exits.

## Proposed file: `CLAUDE.md`

```markdown
# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Spec-first workflow (read this first)

The source of truth for runtime behavior is **markdown**, not Python:

- `specs/00_overview.md`–`specs/40_demo_and_eval.md` — architecture, contracts, demo assertions
- `PROMPTS.md` — parent / Explorer / compaction system prompts
- `MODEL_CONFIG.md` — Anthropic model IDs and pricing constants

`src/vg_agent/`, `fixtures/demo_repo/`, and the demo scripts are **generated
artifacts**. `scripts/generate_project.py` reads the markdown above, computes a
`SPEC_DIGEST` (SHA-256 over the source inputs), and writes the runtime tree
with that digest embedded in `vg_agent/__init__.py` and `vg_agent/config.py`.

**Never hand-edit files under `src/vg_agent/` or `fixtures/demo_repo/`** —
they will be overwritten on the next regenerate, and provenance tests compare
the checked-in tree byte-for-byte with a fresh regeneration. To change
runtime behavior:

1. Edit the relevant spec / `PROMPTS.md` / `MODEL_CONFIG.md`, **or** the
   template string inside `scripts/generate_project.py`.
2. Run `python scripts/generate_project.py --clean`.
3. Run `uv run pytest`.

## Common commands

```powershell
# Regenerate all generated code + fixtures (always run after spec edits)
python scripts/generate_project.py --clean

# Run the full test suite
uv run pytest

# Run a single test
uv run pytest tests/test_vg_agent.py::test_sanity_run_edits_app

# Full presentation script (regenerate, test, three demo flows)
.\scripts\run_demo.ps1
.\scripts\run_demo.ps1 -SkipTests   # skip pytest

# Deterministic demos (no API key needed)
cd fixtures/demo_repo
uv run --project ../.. python -m vg_agent --task "rename foo to bar in app.py" --trace
uv run --project ../.. python -m vg_agent --task "find all auth handling and summarise" --trace --show-context 3
uv run --project ../.. python -m vg_agent --task "search this repo for the string __VG_SENTINEL_NEVER_PRESENT__ and don't stop until you find it" --trace

# Replay a previous run from its JSONL trace
uv run python -m vg_agent --replay fixtures/demo_repo/traces/<run_id>.jsonl --trace --show-context 3

# Optional live Anthropic-backed run (extension path)
$env:ANTHROPIC_API_KEY="..."
uv run python -m vg_agent --task "add input validation to app.py" --live-model --trace --show-context 3
```

## Architecture

One parent agent + one read-only `Explorer` sub-agent type. The agent shell
(not model quality) is the VG claim: tool execution, context engineering,
sub-agent boundaries, tracing, replay, safety, cost control.

**Runtime modules (`src/vg_agent/`, all generated):**

- `agent.py` — `run_task` (deterministic demo routes) and `run_live_task`
  (Anthropic-backed loop). Owns parent system prompt, tool dispatch,
  compaction, Explorer spawning, trace writing.
- `tools.py` — `read_file`, `read_file_range`, `write_file`, `edit_file`,
  `run_bash`. `run_bash` is **deny-by-default**: an allowlist of read-only
  commands (`grep`, `rg`, `find`, `ls`, `pwd`, `cat`, `sed`, `head`, `tail`,
  `wc`), rejection of shell control / redirection / substitution, and an
  explicit destructive-token blocklist. All file tools resolve paths under
  the workspace root and refuse absolute paths or `..` traversal.
- `budget.py` — `BudgetGuard` enforces step/token/USD/daily caps plus a
  3-strike repetition guard. Emits `budget_event` with a `budget_reason`
  enum (`step_cap`, `token_cap`, `usd_cap`, `daily_cap`,
  `repetition_abort`, `timeout`).
- `trace.py` — `TraceRecorder` writes one JSONL event per action to
  `traces/<run_id>.jsonl`. `show_context(events, step_idx)` reconstructs
  the parent-visible context at a given step (this is what `--show-context`
  prints and what `--replay` reads).
- `anthropic_client.py` — minimal `urllib`-based Messages API client.
  Used only in live mode; tests must inject a fake client and never hit
  the network.
- `config.py` — model IDs, pricing, and governance constants generated
  from `MODEL_CONFIG.md` + `specs/30_runtime_governance.md`.
- `demo_fixture.py` — emits `fixtures/demo_repo/` including a
  deterministic `data/sample.log` (~6200 lines, >200 KB) sized to exceed
  `K_COMPACT` on read.

**Two context-engineering tricks to preserve:**

1. **Parent-scoped compaction** — any parent `tool_result` whose token
   estimate exceeds `K_COMPACT` (4000) emits a `compaction` event carrying
   `original_event_idx` and `original_sha256` of the full payload. The next
   parent model turn sees only the compacted marker; the full payload stays
   in the JSONL trace and is retrievable via `read_file_range` or replay.
2. **Explorer offloading** — `spawn_subagent` invokes Explorer with
   read-only tools (`MAX_SUBAGENT_DEPTH = 1`, no nested spawns). Parent
   context receives **only** the Explorer return summary (≤2 KB), never
   Explorer's intermediate `tool_call` / `tool_result` events.

**Trace + replay invariants:**

- Every event has a `kind` discriminator and an `event_idx`.
- `parent_id` distinguishes Explorer-scoped events from parent-scoped events.
- `show_context` filters to `agent_id == "parent"` and substitutes the
  compacted marker at the original `tool_result` position when a matching
  `compaction` event exists. Tests assert that, for the auth-summarise demo,
  the compacted-marker is present and `sample.log` content is absent from
  the parent context at the final step.

## Important constraints when editing

- **Don't touch generated files.** If `src/vg_agent/*` or
  `fixtures/demo_repo/*` need to change, edit the corresponding
  spec/template under `specs/`, `PROMPTS.md`, `MODEL_CONFIG.md`, or
  `scripts/generate_project.py`, then regenerate.
- **`run_bash` allowlist changes require a spec update first.** Add the
  command to `specs/20_tools.md` with justification, regenerate, and add a
  test proving it stays read-only.
- **No network in unit tests.** Live-mode tests use the `FakeClient`
  pattern from `tests/test_vg_agent.py` — they construct a list of
  `ModelTurn` objects and inject them.
- **Model IDs are pinned in `MODEL_CONFIG.md`.** Marketing names like
  "Sonnet 4.6" may appear in prose but executable selection must use the
  exact IDs (`claude-sonnet-4-6`, `claude-haiku-4-5-20251001`). The doc
  notes "Checked against official Anthropic documentation on 2026-05-10";
  update that date when re-verifying.
- **Windows / Git Bash environment.** This repo is developed on Windows;
  demo scripts are `.ps1`. The `run_bash` tool still shells out via
  `bash -c` and normalizes paths at tool boundaries.
- **Docker is an outer safety layer, not the only one.** The in-process
  `validate_shell_command` gate is mandatory and unit-tested regardless of
  whether the demo runs in a container.
```

## Critical files referenced

- `C:\Users\emil_\vscode\vg_assignment\README.md` — source for demo commands
- `C:\Users\emil_\vscode\vg_assignment\specs\00_overview.md` — non-goals + success criteria
- `C:\Users\emil_\vscode\vg_assignment\specs\10_main_agent.md` — parent tools + routes
- `C:\Users\emil_\vscode\vg_assignment\specs\11_subagent_explorer.md` — Explorer contract
- `C:\Users\emil_\vscode\vg_assignment\specs\20_tools.md` — `run_bash` safety rules
- `C:\Users\emil_\vscode\vg_assignment\specs\30_runtime_governance.md` — budget + compaction constants
- `C:\Users\emil_\vscode\vg_assignment\specs\40_demo_and_eval.md` — VG slide assertions
- `C:\Users\emil_\vscode\vg_assignment\MODEL_CONFIG.md` — model IDs + pricing
- `C:\Users\emil_\vscode\vg_assignment\PROMPTS.md` — system prompts
- `C:\Users\emil_\vscode\vg_assignment\scripts\generate_project.py` — codegen entry point
- `C:\Users\emil_\vscode\vg_assignment\src\vg_agent\agent.py` — generated runtime loop
- `C:\Users\emil_\vscode\vg_assignment\tests\test_vg_agent.py` — `FakeClient` pattern

## Verification

After the file is written:

1. Open `CLAUDE.md` and confirm the required prefix line is the first line.
2. Re-read it and confirm every command listed actually works in this repo
   (the commands are taken verbatim from `README.md` / `scripts/run_demo.ps1`,
   so they should match the existing demo path).
3. Confirm there is no `.cursor/rules/`, `.cursorrules`, or
   `.github/copilot-instructions.md` content to merge in — none exist in the
   repo at the time of writing, so nothing was lost.
