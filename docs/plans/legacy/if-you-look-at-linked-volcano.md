# Make the project live-demo-only (remove the offline/deterministic path)

## Context

The project is graded by a **live demo**. A prior review (same file, earlier
version) found that the offline/deterministic path was the source of every demo
gap: the no-key `run_task` shim can't show parallel sub-agents, no replay traces
are shipped, and the documented cost-cap command doesn't run. Rather than patch
those, we delete the offline path entirely and make the **live `run_live_task`
loop the only runtime path**.

Decisions (confirmed with the user):
- **Remove `--replay` entirely** (code, tests, docs).
- **Single live Docker service** (drop the `network_mode: none` service).
- **`--task` is live by default**; errors clearly if `OPENROUTER_API_KEY` is missing.
- **One real OpenRouter smoke run** is allowed to prove end-to-end after regen.

Hard rule still in force: **no network in unit tests** — pytest exercises the
live loop with an injected `FakeClient`/`PipelineClient` (already the dominant
pattern). The real smoke run is the only thing that hits OpenRouter.

Generation rule: runtime under `src/vg_agent/` and `fixtures/demo_repo/` is
**generated**. Edit specs / `PROMPTS.md` / `MODEL_CONFIG.md` / the template in
`scripts/generate_project.py`, then `python scripts/generate_project.py --clean`
and `uv run pytest`. Never hand-edit generated files.

## What "offline" means here (remove all of it)
- The deterministic `run_task` shim and its helpers (`_explore_auth`, the
  `_compact_if_needed(deterministic=True)` branch).
- The `--replay` mode + `load_trace` usage + "offline replay" framing.
- The `network_mode: none` Docker service and "no-API-key / deterministic demo"
  docs.
- Keep: `--seed-fixture` (demo setup), `--trace`, `--show-context` (work on live
  in-memory events), the large `data/sample.log` fixture (drives live compaction),
  `render_tree`/`show_context`, the budget/safety/compaction/sub-agent engines.

## Changes

### 1. Generator template — `scripts/generate_project.py`
- **Delete `run_task`** (template ~line 2297) and deterministic-only helpers it
  uniquely calls (`_explore_auth`; collapse `_compact_if_needed`'s `deterministic`
  param to the live path only).
- **CLI (`main`, template ~3369-3439):**
  - Remove `parser.add_argument("--replay")` and the replay dispatch block
    (~3397-3403). Remove `load_trace` import/usage if now unused.
  - Make live the default: in both the chat dispatch (~3338-3346) and single-task
    dispatch (~3418-3426), always build `LiveModelClient.from_env` (exit `2` on
    `MissingOpenRouterKey`), always build `BudgetGuard.for_workspace`, always call
    `run_live_task`. Delete the `else: run_task(...)` arms.
  - Treat `--live-model` as always-on: either drop the flag and replace
    `if args.live_model:` checks (progress sink ~3414, chat statusline
    `live_model=bool(args.live_model)`, etc.) with unconditional live, or keep the
    flag as an accepted no-op alias. Prefer dropping it; update the error string in
    the "one mode required" `parser.error` (~3409) to `--task, --chat, or --seed-fixture`.
- **Optional but recommended (closes spec drift + enables a cheap live cap demo):**
  wire the `--max-usd`/`--max-tokens` flags the CLI spec already advertises
  (`specs/15_cli_contract.md:84-85`) into `BudgetGuard.for_workspace(root, max_usd=..., max_tokens=...)`. This lets the live VG.3 demo hit the cap without burning real budget. If skipped, remove those rows from the spec instead.

### 2. Specs (source of truth) — broad sweep, same pattern everywhere
Remove every offline/deterministic/replay reference and reframe the live loop as
the only path. Representative files (verify each, don't enumerate lines):
- `specs/15_cli_contract.md` — drop the `--replay` mode and the
  "`network_mode: none` is the canonical replay/smoke path" line (102-103); state
  `--task` runs live and needs `OPENROUTER_API_KEY`; reconcile the flag table
  (84-88) with what's actually generated.
- `specs/70_demo_runbook.md` — **rewrite** to live-only scenes on the single
  service: Scene 1 autonomy+edit+bash, Scene 2 parallel `spawn_subagents`+compaction,
  Scene 3 Grilling, **Scene 4 cost cap that actually fires** (live + `--max-usd`
  or a tight repetition), Scene 5 safety blocks. Remove the replay scene and the
  "record canonical traces / ship under fixtures/.../traces" section.
- `specs/50_packaging.md` — single live service; remove net-off/deterministic and
  replay framing.
- `specs/40_demo_and_eval.md`, `00_overview.md`, `10_main_agent.md`,
  `20_tools.md`, `30_runtime_governance.md`, `60_observability.md`,
  `16_chat_ui.md` — strip `run_task`/replay/deterministic/offline mentions.

### 3. `docker-compose.yml`
- Collapse to one service named `vg-agent` (the current `vg-agent-live` body):
  bridged network, `cap_drop: [ALL]`, `no-new-privileges`, `pids_limit`, `.env`.
- Delete the `network_mode: none` service. (Trade-off the user accepted: the
  net-off sandbox is gone; VG.4 safety now rests on the in-process command guard +
  egress pin + dropped caps — still substantive.)

### 4. README.md
- Remove "§2 Deterministic Demo, No API Key" and "§4 Replay a Trace".
- New flow: build → `--seed-fixture` → set `OPENROUTER_API_KEY` in `.env` →
  `docker compose run --rm vg-agent --task "..." --trace --show-context 8` (live)
  → chat. Remove the "Without `--live-model` ... deterministic demo routes"
  paragraph and replay mentions in the safety section.

### 5. Tests — `tests/test_vg_agent.py`
- Remove `run_task` from imports; delete `test_replay_round_trip_tree_and_context`.
- Migrate the remaining `run_task` tests to `run_live_task` + `FakeClient`/
  `PipelineClient` (live equivalents already exist for most):
  `test_sanity_run_edits_app` (→ live Coder edit, cf. `test_parent_has_no_write_tools_and_coder_is_sole_mutation_path`),
  `test_parent_compaction_and_subagent_context` (→ cf. `test_live_parent_large_tool_result_compacted_before_next_turn`),
  `test_cost_cap_run_uses_budget_reason` (→ live cap/repetition, cf. `test_live_loop_budget_abort_before_client_call`),
  the two approval tests (~707/719 → live approval, cf. `test_approval_required_for_write_tools`).
- Drop genuinely redundant ones; keep one live test per behavior (parallel
  overlap, compaction, cap abort, safety reject, partial edit, autonomy/yield).
- Keep `test_generated_source_reproducible` (provenance) — it will pass after regen.

### 6. `scripts/run_demo.ps1` and `CLAUDE.md`
- `run_demo.ps1`: regenerate → `uv run pytest` → if `OPENROUTER_API_KEY` set, one
  live `--task` smoke scene; remove deterministic/replay scenes.
- `CLAUDE.md`: update "Common commands" (remove the deterministic Docker demo and
  the `--replay` command) and the architecture/constraints notes that describe the
  `run_task` shim and replay invariants. (CLAUDE.md is not generated.)

## Verification
1. `python scripts/generate_project.py --clean` — regenerates cleanly; no
   `run_task`/`--replay`/`load_trace` left in `src/vg_agent/`.
2. `uv run pytest` — green, including the provenance test; no test imports
   `run_task`; no test opens the network.
3. **Live smoke run** (real, one-time): with the key in `.env`,
   `docker compose run --rm vg-agent --task "read data/sample.log, then summarise auth/ and utils.py in parallel" --trace --show-context 8`
   — confirm in the JSONL/`--show-context`: one `spawn_subagents` → two
   overlapping `subagent_return{explorer}`, a `compaction` event for
   `data/sample.log`, and the final answer integrating both summaries. Report the
   actual token/USD cost.
4. Grep the repo (excluding `.venv`) for `replay|run_task|network_mode: none|deterministic demo|No API Key`
   → no remaining references outside this plan file.
5. Rotate the OpenRouter key after the smoke run (it's been exposed locally).
