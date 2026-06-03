# Specs index

Executable behavioral contract for the VG Agent. Markdown here (plus
`PROMPTS.md`, `MODEL_CONFIG.md`, `CONTEXT_WINDOWS.md` at the repo root) is the
source of truth; most Python under `src/vg_agent/` is generated from templates.

**Start here:** [`00_overview.md`](00_overview.md) → [`01_architecture.md`](01_architecture.md) → [`02_tech_stack.md`](02_tech_stack.md) → [`05_source_of_truth_and_generation.md`](05_source_of_truth_and_generation.md).

## Numbered specs

| File | Purpose |
|------|---------|
| [`00_overview.md`](00_overview.md) | Goals, success criteria, non-goals, execution model |
| [`01_architecture.md`](01_architecture.md) | Product architecture, context engineering, module map |
| [`02_tech_stack.md`](02_tech_stack.md) | Dependencies, Docker, config surfaces, codegen |
| [`03_testing.md`](03_testing.md) | Test rules, provenance, FakeClient, when to run pytest |
| [`04_demo_fixture.md`](04_demo_fixture.md) | Demo workspace layout, `sample.log`, seed command |
| [`05_source_of_truth_and_generation.md`](05_source_of_truth_and_generation.md) | Edit tiers, regenerate, `SPEC_DIGEST` |
| [`10_main_agent.md`](10_main_agent.md) | Parent tools, approval, conversation compaction |
| [`11_subagent_explorer.md`](11_subagent_explorer.md) | Explorer-only deep dive (other types in `12`) |
| [`12_subagent_pipeline.md`](12_subagent_pipeline.md) | Typed pipeline, parallel fan-out, failure modes |
| [`15_cli_contract.md`](15_cli_contract.md) | CLI flags, slash commands |
| [`16_chat_ui.md`](16_chat_ui.md) | Rich TTY chat layout and behavior |
| [`17_rich_tui_stack.md`](17_rich_tui_stack.md) | Rich / prompt-toolkit technology map |
| [`20_tools.md`](20_tools.md) | Tool contracts, `run_bash` safety |
| [`25_security.md`](25_security.md) | Threat model and safety layers (rollup) |
| [`30_runtime_governance.md`](30_runtime_governance.md) | Caps, constants, event kinds, budget reasons |
| [`40_demo_and_eval.md`](40_demo_and_eval.md) | Demo assertions, eval criteria |
| [`41_runtime_quality_eval.md`](41_runtime_quality_eval.md) | Side-by-side model comparison protocol |
| [`50_packaging.md`](50_packaging.md) | Docker images, Compose, distribution |
| [`60_observability.md`](60_observability.md) | Traces, statusline, SQLite, **event catalog** |
| [`70_dashboard.md`](70_dashboard.md) | Trace analysis UI (FastAPI + React) |
| [`70_demo_runbook.md`](70_demo_runbook.md) | Graded live demo scenes |

### Numbering notes

- Gaps between `05` and `10` are intentional (room for cross-cutting specs like `03`/`04`/`25`).
- **Two files share the `70_` prefix** — different topics, not a duplicate spec:
  - `70_dashboard` = optional web UI
  - `70_demo_runbook` = examiner-facing live script

## Auxiliary docs (in `specs/`, not codegen inputs)

| File | Purpose |
|------|---------|
| [`model_experience.md`](model_experience.md) | Per-model behavior notes and profile recipes |
| [`gabriel_tips.md`](gabriel_tips.md) | Workflow / review notes (not runtime contract) |

## Repo-root generator inputs

| File | Purpose |
|------|---------|
| [`../PROMPTS.md`](../PROMPTS.md) | System prompts embedded in generated agent code |
| [`../MODEL_CONFIG.md`](../MODEL_CONFIG.md) | Model IDs, pricing, OpenRouter host |
| [`../CONTEXT_WINDOWS.md`](../CONTEXT_WINDOWS.md) | Context windows and auto-compact fractions |

Hashed into `SPEC_DIGEST` via `scripts/generate_project.py` `SOURCE_INPUTS` (see `05`).

## Recommended reading order

1. `00_overview` — what “done” means
2. `01_architecture` — how the system fits together
3. `02_tech_stack` — what it is built with
4. `03_testing` — how changes are verified
5. `04_demo_fixture` — demo workspace contents
6. `05_source_of_truth` — how to edit safely
7. `12_subagent_pipeline` → `10_main_agent` → `20_tools` → `30_runtime_governance`
8. `16_chat_ui` + `17_rich_tui_stack` (if working on terminal UI)
9. `60_observability` (especially trace event catalog)
10. `25_security` (reviewer / safety pass)
11. `50_packaging` → `70_dashboard` → `15_cli_contract` → `40_demo_and_eval` → `70_demo_runbook`

Oral-exam cheat sheet (not a spec): [`../docs/ARCHITECTURE.md`](../docs/ARCHITECTURE.md).

Contributor guide: [`../DEVELOPER_README.md`](../DEVELOPER_README.md).
