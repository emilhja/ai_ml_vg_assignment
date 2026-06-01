# Spec deltas to close VG rubric gaps

## Context

Critical review of `specs/` against `background/vg_assignment_grading_requirements.md`
and `background/emil_pitch.md` found gaps that put **VG.1 (parallel sub-agents)**,
**VG.3 (real-time cost monitoring)**, **VG.7 (deployable packaging)**, and
**VG.9 (agent autonomy)** at risk. Current spec also drops Emil's pitched
**Grilling** sub-agent and has no spec for Docker, config-file shape, or a live
statusline.

User decisions (this thread):

1. Sequential typed pipeline (Grilling → Explorer → optional Coder/Reviewer)
   **plus at least one demo scene** that fans out 2+ parallel Explorers — needed
   to satisfy VG.1.
2. `--live-model` becomes the **default demo path**. Existing scripted
   "deterministic routes" are deleted. Reproducibility comes from
   `--replay <recorded-trace.jsonl>` driven by `FakeClient`.
3. Statusline first; JSONL trace must capture per-step tool calls, model ID
   per request, and tokens per request so a future analysis board can be built
   without re-running anything.
4. Haiku 4.5 for parent and all sub-agents initially. Sonnet-parent +
   Haiku-sub-agents documented as a future beta path.
5. **Coder is the only sub-agent that may write files.** Parent loses
   `write_file` / `edit_file` from its tool surface.
6. Docker is the **primary** execution boundary for demos, not an optional outer
   layer.

This plan only edits markdown source-of-truth files under `specs/`,
`PROMPTS.md`, `MODEL_CONFIG.md`, and adds `ARCHITECTURE.md`. Generated Python
under `src/vg_agent/` is **not** touched here — the next step after approval is
to update `scripts/generate_project.py` and regenerate per `CLAUDE.md`.

## Files to add

### `specs/12_subagent_pipeline.md` (NEW)
- Typed sub-agents: `Grilling`, `Explorer`, `Coder`, `Reviewer`.
- Tool surfaces per type:
  - Grilling: no tools, returns clarifying questions or "ready" verdict + refined task.
  - Explorer: `read_file`, `read_file_range`, `run_bash` (read-only allowlist).
  - Coder: Explorer's tools **plus** `write_file`, `edit_file`. Always gated by approval policy in `writes` and `all` modes.
  - Reviewer: Explorer's tools, plus access to the JSONL trace of the Coder run it is reviewing.
- Sequential pipeline: parent calls Grilling first if task is ambiguous (heuristic: <30 tokens OR no file paths OR contains "find/all/everything"), else skips. Then Explorer. Then optional Coder. Then optional Reviewer.
- `--no-grill` flag bypasses the Grilling step.
- **Parallel fan-out contract**:
  - `spawn_subagents(list[SubagentRequest])` runs ≥2 sub-agents under `asyncio.gather` (or `concurrent.futures.ThreadPoolExecutor`).
  - `subagent_spawn` and `subagent_return` events carry `started_at` / `ended_at` wall-clock so overlap is observable in the trace.
  - `MAX_PARALLEL_SUBAGENTS = 4`.
  - Each parallel sub-agent gets its own `BudgetGuard` slice; if any exceeds, the others are cancelled and a single `budget_event{reason:"parallel_aborted"}` is emitted.
- Failure modes:
  - Sub-agent timeout (`TOOL_TIMEOUT` reused) → `subagent_return{status:"timeout"}`.
  - Oversize return (>2 KB after retry instruction) → `subagent_return{status:"oversize", truncated: true}`.
  - Tool-error inside sub-agent → bubbles to `subagent_return{status:"tool_error", reason}`.
  - Parent decides next step based on `subagent_return.status`; never silently ignores a failure.
- Sub-agent result *consumption* assertion: at least one parent `assistant_step` after a sub-agent return must reference content only obtainable from the sub-agent.

### `specs/50_packaging.md` (NEW)
- `Dockerfile`: python:3.12-slim, uv install, non-root user `vg`, workdir `/workspace`.
- `docker-compose.yml` two services:
  - `vg-agent` (default demo): `network_mode: none`, mounts `./workspace:/workspace`, reads `.env`.
  - `vg-agent-live`: bridged network, same workspace, same `.env`. Used only with `--live-model`.
- `config.toml` for non-secret settings (model IDs override, budget caps override, approval-mode default). Loader precedence: CLI flag > env var > `config.toml` > defaults from `30_runtime_governance.md`.
- `.env.example` enumerates: `ANTHROPIC_API_KEY`, `VG_PARENT_MODEL`, `VG_SUBAGENT_MODEL`, `VG_MAX_USD_PER_RUN`, `VG_MAX_USD_PER_DAY`, `VG_APPROVAL_MODE`.
- Real `.env` is gitignored; presence test fails CI if `.env` is staged.
- README contract: install (`docker compose build`), default demo (`docker compose run vg-agent --task "…"`), live demo (`docker compose run vg-agent-live --task "…" --live-model`), replay (`docker compose run vg-agent --replay traces/<run_id>.jsonl`).

### `specs/60_observability.md` (NEW)
- **Statusline contract** (stderr, one line per parent step, rewritten in place):
  ```
  [step 5/15] tokens 12340/80000 (15%) · usd 0.041/0.500 (8%) · agents parent=8.2k explorer=4.1k · tools 7 · model haiku-4.5
  ```
- Warning thresholds: `WARN_USD_FRACTION = 0.8`, `WARN_TOKEN_FRACTION = 0.8`, `WARN_STEP_FRACTION = 0.8`. Emit `budget_event{reason:"warn_usd"|"warn_tokens"|"warn_steps"}` once when crossed; statusline highlights the warned dimension. Warnings never abort.
- Per-event attribution required for analysis-board future work:
  - `agent_id` (parent or sub-agent UUID).
  - `agent_type` (parent | grilling | explorer | coder | reviewer).
  - `model_id` on every `assistant_step` and every Anthropic request.
  - `tokens_in`, `tokens_out`, `usd` on every `assistant_step`.
  - `tool_call_index` monotonically increasing per agent.
  - `parent_step_idx` so sub-agent events can be grouped by the parent step that spawned them.
- `BudgetGuard` aggregates per-agent totals and exposes them via `--budget` / `/budget`.
- Analysis-board is **deferred**: spec mandates only that the JSONL trace carries enough fields to build it later. `python -m vg_agent.board <run_id>` is a future deliverable.

### `specs/70_demo_runbook.md` (NEW)
Five scenes, each mapped to rubric items. For each scene: command, expected statusline, expected JSONL signals, what to point at during oral defense.

| Scene | Command | Rubric items |
|---|---|---|
| 1 — autonomous rename | `docker compose run vg-agent-live --task "rename foo to bar in app.py"` | VG.5, VG.6, VG.9 |
| 2 — parallel auth+utils summary | `docker compose run vg-agent-live --task "summarise auth/ and utils.py in parallel"` | VG.1, VG.2 |
| 3 — Grilling clarifies | `docker compose run vg-agent-live --task "make it better"` (ambiguous → Grilling fires) | VG.1, VG.9, oral defense |
| 4 — cost cap fires | `docker compose run vg-agent-live --task "search for sentinel forever" --max-usd 0.05` | VG.3 |
| 5 — safety blocks + replay | `--task "read .env"`, `--task "rm -rf ."`, then `--replay <previous>.jsonl` | VG.4, VG.5, VG.2 |

Each scene names which JSONL fields/events the grader can read post-hoc.

### `ARCHITECTURE.md` (NEW, top-level deliverable)
- Mermaid diagram: User → Parent (Haiku) → {Grilling, Explorer × N, Coder, Reviewer} → Tools → Workspace; sidecar: JSONL trace, BudgetGuard, ApprovalPolicy, Statusline.
- Three short paragraphs: pipeline / context-engineering tricks / weakest part of the design (e.g., per-agent budget split heuristic, single approval policy across types).
- Used in §4 oral knowledge-check.

## Files to edit

### `specs/00_overview.md`
- Delete line 18-19 ("No sub-agent concurrency requirement…").
- Replace "Deterministic routes remain the core VG proof" with: "Live model runs (`--live-model`) are the default demo path. `--replay <trace.jsonl>` produces deterministic CI runs from previously recorded live sessions via `FakeClient`."
- Add success criterion: "At least one demo scene shows ≥2 sub-agents executing with overlapping wall-clock and both returns consumed in the next parent step."

### `specs/10_main_agent.md`
- Remove `write_file` and `edit_file` from the parent's tool list (lines 8-13). Parent tools become: `read_file`, `read_file_range`, `run_bash`, `spawn_subagent`.
- Add: "Writes are performed exclusively by a Coder sub-agent spawned via `spawn_subagent`. The parent never writes files directly."
- Delete the "Deterministic demo routes" block (lines 38-46) entirely.
- Replace "Live route" section heading with "Parent loop"; make it unconditional (no `--live-model` gating for the default demo).
- Keep `--replay` documented in the chat-mode and CLI sections as the deterministic path.

### `specs/11_subagent_explorer.md`
- Shorten to "Explorer sub-agent type" definition only.
- Add cross-reference: "Orchestration of Explorer (sequential and parallel) lives in `specs/12_subagent_pipeline.md`."

### `specs/30_runtime_governance.md`
- Add constants block:
  - `MAX_PARALLEL_SUBAGENTS = 4`
  - `WARN_USD_FRACTION = 0.8`
  - `WARN_TOKEN_FRACTION = 0.8`
  - `WARN_STEP_FRACTION = 0.8`
- Extend `budget_reason` enum with `warn_usd`, `warn_tokens`, `warn_steps`, `parallel_aborted`.
- Extend event-kind list with `statusline` (sampled at parent step boundaries; trace also stores the most recent statusline string for replay UI).
- Promote Docker block (currently lines 91-101) from "outer safety layer" to "primary execution boundary for demos"; keep the "must hold without Docker" guarantee for unit tests.
- Add per-event attribution required fields (forward-pointer to `60_observability.md`).

### `specs/40_demo_and_eval.md`
- Add assertions:
  - **Parallel sub-agents**: two `subagent_spawn` events with overlapping `[started_at, ended_at]`; both `subagent_return` payloads referenced in the next `assistant_step.content`.
  - **Grilling**: ambiguous task emits `subagent_spawn{agent_type:"grilling"}` whose return reshapes the parent's plan (next parent `assistant_step` includes the refined task).
  - **Statusline**: stderr contains at least one statusline match per parent step; JSONL contains a `statusline` event with the same payload.
  - **Warning threshold**: a run at 81% USD emits `budget_event{reason:"warn_usd"}` without `run_end{final_status:"aborted"}`.
  - **Parent has no write tools**: parent attempting `write_file` directly is a programmer error caught by a type/assertion test.
  - **Coder writes**: `subagent_spawn{agent_type:"coder"}` with a write request produces a `tool_call` of `write_file`/`edit_file` inside the Coder's private trace, and the file mutation is observable.
  - **Docker smoke**: `docker compose config` parses; `docker compose run vg-agent --task "list files"` exits 0 in CI (smoke only — full demo runs remain manual).
- Remove obsolete "Deterministic demo routes" references.

### `PROMPTS.md`
- Update Parent prompt: drop `write_file` / `edit_file` from the tool list; add "Spawn Coder to perform any file mutation."
- Add **Grilling** system prompt: "You are Grilling. The user task is ambiguous. Ask up to 3 sharp clarifying questions OR, if the task is already concrete enough, return a one-line refined task. Never call tools. Return JSON: `{questions: [...]} | {refined_task: '...'}`."
- Add **Coder** system prompt: "You are Coder. You make the smallest possible code change that satisfies the parent's instruction. Use `read_file_range` to confirm context before `edit_file`. Return a one-line summary of the change and the file path."
- Add **Reviewer** system prompt: "You are Reviewer. Read the supplied Coder trace and the resulting file. Return PASS or FAIL with one-line reason. Do not modify files."
- Treat-output-as-data sentence applies to all four sub-agent types.

### `MODEL_CONFIG.md`
- Change `PARENT_MODEL_ID` from `claude-sonnet-4-6` to `claude-haiku-4-5-20251001` (matches user decision #4: ship Haiku-only first).
- Add explicit IDs:
  - `GRILLING_MODEL_ID: claude-haiku-4-5-20251001`
  - `CODER_MODEL_ID: claude-haiku-4-5-20251001`
  - `REVIEWER_MODEL_ID: claude-haiku-4-5-20251001`
- Add "Beta profile" subsection documenting the future Sonnet-parent setting (config override only — no code change needed when flipped).
- Bump verification date.

## Verification

After regeneration via `python scripts/generate_project.py --clean` (a separate
step, not part of this plan):

1. `uv run pytest` passes including new assertions.
2. `docker compose build` succeeds.
3. `docker compose run vg-agent --task "list files"` exits 0 and writes a JSONL trace.
4. `docker compose run vg-agent-live --task "summarise auth/ and utils.py in parallel"` shows two overlapping `subagent_spawn` events in the trace; both summaries appear in the parent's final message.
5. Statusline renders on stderr each parent step; ≥1 `statusline` event per step in JSONL.
6. A run pushed to 81% of `MAX_USD_PER_RUN` emits `budget_event{reason:"warn_usd"}` and continues.
7. A run pushed past `MAX_USD_PER_RUN` emits `budget_event{reason:"usd_cap"}` and `run_end{final_status:"aborted"}`.
8. Parent attempting to call `write_file` raises in unit test (parent tool surface no longer includes writes).
9. `--replay <recorded>.jsonl` reproduces a full trace without any network call.
10. `ARCHITECTURE.md` renders the diagram and matches the spec's pipeline.

## Out of scope for this plan

- Regenerating `src/vg_agent/`, `fixtures/demo_repo/`, `tests/`, and demo scripts. Tracked as a follow-up: update `scripts/generate_project.py` templates, then `python scripts/generate_project.py --clean && uv run pytest`.
- Building the analysis-board frontend. Spec only mandates that JSONL captures enough data; the renderer is a future deliverable.
- Implementing the Sonnet-parent beta profile. Config-only change once base ships.
- HTTPS-proxy bridge for `--network none` + `--live-model`. Already noted as future work in `30_runtime_governance.md`.
