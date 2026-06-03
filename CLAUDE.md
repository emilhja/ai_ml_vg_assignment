# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Spec-first workflow (read this first)

The source of truth for runtime behavior is **markdown**, not Python:

- `specs/*.md` — architecture, source-of-truth rules, CLI contract,
  packaging, observability, and demo assertions
- `PROMPTS.md` — parent, sub-agent, and compaction system prompts
- `MODEL_CONFIG.md` — LiteLLM/OpenRouter model IDs and pricing constants

`src/vg_agent/`, `fixtures/demo_repo/`, and the demo scripts are **generated
artifacts**. `scripts/generate_project.py` reads the markdown above, computes a
`SPEC_DIGEST` (SHA-256 over the source inputs), and writes the runtime tree
with that digest embedded in `vg_agent/__init__.py` and `vg_agent/config.py`.

**Never hand-edit files under `src/vg_agent/` or `fixtures/demo_repo/`** —
they will be overwritten on the next regenerate, and provenance tests compare
the checked-in tree byte-for-byte with a fresh regeneration. To change
runtime behavior:

1. Edit the relevant spec / `PROMPTS.md` / `MODEL_CONFIG.md`, **or** the
   matching template file under `scripts/templates/<name>.tmpl` (these hold the
   pre-render source for each `src/vg_agent/<name>`; `generate_project.py` loads
   and renders them).
2. Run `python scripts/generate_project.py --clean`.
3. Run `uv run pytest`.

**Exception — three hand-written files live inside the generated dir.**
`src/vg_agent/sqlite_store.py`, `src/vg_agent/chat_ui.py`, and
`src/vg_agent/workspace_paths.py` are **not** built from template strings.
They are listed in `EXTRA_SOURCE_GENERATED_FILES`
(`scripts/generate_project.py`), read from disk *before* `--clean` wipes the
directory, run through placeholder substitution, and written back. They **are**
their own source of truth — edit them directly, then regenerate. (Placeholder
substitution still runs, so avoid literal `__NAME__` tokens in them.) See
[`DEVELOPER_README.md`](DEVELOPER_README.md) for the full generated-vs-hand-written
map a reviewer should read first.

## Common commands

```powershell
# Regenerate all generated code + fixtures (always run after spec edits)
python scripts/generate_project.py --clean

# Run the full test suite
uv run pytest

# Run a single test
uv run pytest tests/test_vg_agent.py::test_parallel_explorers_run_concurrently_with_overlap

# Full presentation script (regenerate, test, live demo scenes if a key is set)
.\scripts\run_demo.ps1
.\scripts\run_demo.ps1 -SkipTests   # skip pytest

# Canonical live Docker demo (requires OPENROUTER_API_KEY in .env)
Copy-Item .env.example .env            # then edit .env and set OPENROUTER_API_KEY
New-Item -ItemType Directory -Force workspace,traces
docker compose build
docker compose run --rm vg-agent --seed-fixture
docker compose run --rm vg-agent --task "read data/sample.log, then summarise auth/ and utils.py in parallel" --trace --show-context 8
```

## Architecture

Spec index: `specs/README.md`. Product map: `specs/01_architecture.md`.
Technology inventory: `specs/02_tech_stack.md`. Testing: `specs/03_testing.md`.
Oral-exam cheat sheet: `docs/ARCHITECTURE.md`.

One parent agent + typed sub-agents (`Grilling`, `Explorer`, `Coder`,
`Reviewer`). The agent shell (not model quality) is the VG claim: tool
execution, context engineering, sub-agent boundaries, tracing,
safety, cost control.

**Runtime modules (`src/vg_agent/`, all generated):**

- `agent.py` — `run_live_task` is the single runtime path (OpenRouter-backed
  loop via LiteLLM). Owns parent system prompt, tool dispatch,
  compaction, Explorer spawning, trace writing. There is no offline/deterministic
  route; `--task` always runs live and exits `2` without `OPENROUTER_API_KEY`.
- `tools.py` — `read_file`, `read_file_range`, `write_file`, `edit_file`,
  `run_bash`. `run_bash` is **deny-by-default**: an allowlist of read-only
  commands (`grep`, `rg`, `find`, `ls`, `pwd`, `cat`, `head`, `tail`,
  `wc`; `sed` is excluded), rejection of shell control / redirection /
  substitution, and an explicit destructive-token blocklist. All file tools
  resolve paths under the workspace root and refuse absolute paths or `..`
  traversal.
- `budget.py` — `BudgetGuard` enforces step/token/USD/daily caps plus a
  3-strike repetition guard. Emits `budget_event` with a `budget_reason`
  enum (`step_cap`, `token_cap`, `usd_cap`, `daily_cap`,
  `repetition_abort`, `timeout`).
- `trace.py` — `TraceRecorder` writes one JSONL event per action to
  `traces/<run_id>.jsonl`. `show_context(events, step_idx)` reconstructs
  the parent-visible context at a given step (this is what `--show-context`
  prints).
- `live_model_client.py` — LiteLLM OpenRouter adapter. Drives every run;
  tests must inject a fake client and never hit the network.
- `config.py` — model IDs, pricing, and governance constants generated
  from `MODEL_CONFIG.md` + `specs/30_runtime_governance.md`.
- `demo_fixture.py` — emits `fixtures/demo_repo/` including a
  reproducible `data/sample.log` (~6200 lines, >200 KB) sized to exceed
  `K_COMPACT` on read.

**Two context-engineering tricks to preserve:**

1. **Parent-scoped compaction** — any parent `tool_result` whose token
   estimate exceeds `K_COMPACT` (4000) emits a `compaction` event carrying
   `original_event_idx` and `original_sha256` of the full payload. The next
   parent model turn sees only the compacted marker; the full payload stays
   in the JSONL trace and is retrievable via `read_file_range`.
2. **Explorer offloading** — `spawn_subagent` invokes one Explorer and
   `spawn_subagents` invokes parallel Explorers with
   read-only tools (`MAX_SUBAGENT_DEPTH = 1`, no nested spawns). Parent
   context receives **only** the Explorer return summary (≤2 KB), never
   Explorer's intermediate `tool_call` / `tool_result` events.

**Trace invariants:**

- Every event has a `kind` discriminator and an `event_idx`.
- `parent_id` distinguishes Explorer-scoped events from parent-scoped events.
- `show_context` filters to `agent_id == "parent"` and substitutes the
  compacted marker at the original `tool_result` position when a matching
  `compaction` event exists. Tests assert that, for the auth-summarise demo,
  the compacted-marker is present and `sample.log` content is absent from
  the parent context at the final step.

## Important constraints when editing

- **Don't touch generated files.** If `src/vg_agent/*` or
  `fixtures/demo_repo/*` need to change, edit the corresponding source under
  `specs/`, `PROMPTS.md`, `MODEL_CONFIG.md`, or the per-module template in
  `scripts/templates/<name>.tmpl`, then regenerate. (Exception: the three
  hand-written files noted above.)
- **`run_bash` allowlist changes require a spec update first.** Add the
  command to `specs/20_tools.md` with justification, regenerate, and add a
  test proving it stays read-only.
- **No network in unit tests.** Live-mode tests use the `FakeClient`
  pattern from `tests/test_vg_agent.py` — they construct a list of
  `ModelTurn` objects and inject them.
- **Model IDs are pinned in `MODEL_CONFIG.md`.** Marketing names may appear
  in prose but executable selection must use LiteLLM OpenRouter IDs such as
  `openrouter/anthropic/claude-haiku-4.5`. The doc notes the current
  verification date; update it when re-verifying.
- **Changing `VG_*_MODEL` requires pricing in `MODEL_CONFIG.md`.** Add
  per-Mtok constants and regenerate, or startup warns (see `docs/PRICE.md` checklist);
  optional `VG_STRICT_MODEL_PRICING=1` exits instead of warning.
- **Windows / Git Bash environment.** This repo is developed on Windows;
  demo scripts are `.ps1`. The `run_bash` tool still shells out via
  `bash -c` and normalizes paths at tool boundaries.
- **Docker is an outer safety layer, not the only one.** The in-process
  `validate_shell_command` gate is mandatory and unit-tested regardless of
  whether the demo runs in a container.
