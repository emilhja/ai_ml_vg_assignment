# Remediation Plan — Live Chat Coding Agent (VG)

## Context

Goal: a **live chat** coding agent that competes with Claude Code / Codex, graded
against `background/vg_assignment_grading_requirements.md` (the pitch in
`background/emil_pitch.md` is the product promise).

Verification of the current build found that the specs (`specs/*.md`, `PROMPTS.md`)
describe a much stronger system than the code delivers, and the two have **diverged**
(all 34 tests pass and `test_generated_source_reproducible` confirms the generated
tree matches `scripts/generate_project.py` — so this is *spec-vs-implementation*
divergence, not provenance drift). The most demo- and rubric-critical gaps:

- **"Parallel" sub-agents run sequentially** and emit no wall-clock timestamps —
  the trace cannot show overlap (rubric "known-deficient anchor" → VG.1 risk).
- **The default `--task` path (`run_task`) is scripted theater** — keyword `if/else`
  emitting fabricated `assistant_step`s and a baked-in summary. It never spawns in
  parallel and never fires Grilling, so demo Scenes 2 and 3 claim JSONL signals the
  code never produces. The rubric explicitly fails "a single loop relabelled sub-agent."
- **Only Explorer of the four typed sub-agents exists**; the parent holds write tools
  directly, contradicting `specs/10`, `specs/12`, `specs/40` and the pitch.
- **Chat mode forgets every prior turn** (each turn rebuilds `messages=[task]`).
- `agent_type` is never recorded; the pitch's FinOps dashboard is deferred with a
  975-line SQLite mirror that has no consumer.

User decisions for this plan: **(1) pivot to live as the primary graded path**, with
deterministic `--replay` of *real recorded* runs as the safety net; **(2) implement
the full Grilling/Explorer/Coder/Reviewer pipeline and remove the parent's write tools.**

> **Workflow constraint (CLAUDE.md):** never hand-edit `src/vg_agent/*` or
> `fixtures/demo_repo/*`. Every change below is made in `specs/*.md`, `PROMPTS.md`,
> `MODEL_CONFIG.md`, or the template strings inside `scripts/generate_project.py`,
> then applied with `python scripts/generate_project.py --clean` and `uv run pytest`.

---

## P0 — Blocks VG or breaks the core goal

### P0.1 Make `spawn_subagents` genuinely concurrent and observable
**Change.** In the generator template for `_execute_live_tool` (the `spawn_subagents`
branch, `scripts/generate_project.py` ~line 1507) replace the sequential
`for child_id, question in accepted:` loop with a `concurrent.futures.ThreadPoolExecutor`
(`MAX_PARALLEL_SUBAGENTS = 4`) that runs each `_run_live_explorer` on its own thread.
**Add** `started_at`/`ended_at` (ISO-8601 UTC via the existing `now_iso()` in `trace.py`)
to every `subagent_spawn` and `subagent_return` event — record `started_at` immediately
before submitting the future and `ended_at` on completion.
**Why:** VG.1 MET requires "2+ sub-agents working at once" with overlap provable from
the trace. **Verify:** new test asserting two `subagent_spawn{agent_type:"explorer"}`
intervals overlap (the assertion `specs/40_demo_and_eval.md` already mandates but the
suite is missing). Reuse the existing per-slice budget split idea from `specs/12`.

### P0.2 Implement the typed pipeline; remove parent write tools
**Change.** Add a `type` field to the sub-agent request schema and a dispatcher so
`spawn_subagent(s)` can route to `grilling | explorer | coder | reviewer`
(prompts already exist verbatim in `PROMPTS.md`; only Explorer is wired today):
- **Coder** = Explorer's read tools **plus** `write_file`/`edit_file`; gated by the
  approval policy in `writes`/`all`. Reuse `tools.write_file`/`tools.edit_file` and the
  existing `ApprovalPolicy.check` flow in `_execute_live_tool`.
- **Grilling** = no tools; returns `{questions:[...]}` or `{refined_task:"..."}` JSON.
- **Reviewer** = read tools + the JSONL slice of the Coder run under review.
**Remove** `write_file` and `edit_file` from `PARENT_TOOL_SCHEMAS` (generator ~line 1284)
and the parent write branches in `_execute_live_tool` — the parent mutates **only**
through Coder, per `specs/10`/`specs/12`. Add the Coder write-path conflict serialisation
(`subagent_return{status:"conflict"}`) from `specs/12`.
**Why:** restores the pitch's headline architecture and removes the spec contradiction
that endangers VG-HG-3 (oral) and substance gate S2/S4.
**Verify:** the existing `specs/40` assertions — parent tool list excludes write tools;
a mutation task emits `subagent_spawn{agent_type:"coder"}` with the `edit_file` call in
Coder's private events; two Coders on overlapping paths → one `conflict`.

### P0.3 Retire scripted `run_task`; anchor the demo on the live loop + real replays
**Remove.** The keyword branches in `run_task` (generator ~line 1840 onward:
rename-foo-bar, sentinel/"don't stop", and the `_explore_auth` default theater).
**Change.** Keep one deterministic entry only for CI sanity, but make the **graded** path
`run_live_task`. Record canonical live runs for each demo scene to
`fixtures/demo_repo/traces/<scene>.jsonl` and make `--replay` of those the offline proof
(no network) — this is what `specs/00`/`specs/30` already call the "deterministic path."
Rewrite `specs/70_demo_runbook.md` so every claimed JSONL signal (parallel explorers,
`grilling` spawn in Scene 3, Coder edit in Scene 1) is one the live loop actually emits.
**Why:** the rubric requires live demonstration and fails relabelled/scripted agents;
this directly serves the "live chat agent" goal.

### P0.4 Wire Grilling into the autonomous loop
**Change.** Ensure the parent model can choose Grilling on ambiguous tasks
("make it better") and yield questions without acting — the prompt guidance is already
in `PROMPTS.md`; it just needs the `grilling` dispatch from P0.2 plus an end-to-end test
matching the `specs/40` Grilling assertions. **Why:** Scene 3 / VG.9 / pitch ("Grilling
ska vara en envis agent som ställer frågor").

---

## P1 — Strong product/credibility wins

### P1.1 Persist conversation context across chat turns
**Change.** Thread a persistent `messages` list (and the compacted parent context)
through `run_live_task` so `_chat_loop` (`__main__.py` ~line 322) accumulates turns under
one `session_id` instead of rebuilding `messages=[task]` each turn. Apply the existing
`_compact_if_needed` to the carried history. **Why:** a chat coding agent must remember
the conversation; today it is amnesiac. **Verify:** extend
`test_chat_persists_budget_and_approvals_across_turns` to assert turn-2 context contains
turn-1 content.

### P1.2 Emit `agent_type` on every event
**Change.** Add `agent_type` as a first-class field in `TraceRecorder.emit`
(`trace.py`) and set it at every emit site (parent/grilling/explorer/coder/reviewer).
Make the statusline `per_agent_breakdown` and `BudgetGuard.per_agent_type_tokens` key on
it. **Why:** `specs/30`/`specs/60` mandate it; without it the FinOps story and the
statusline breakdown are unprovable.

### P1.3 Land a minimal FinOps view (pitch headline)
**Change.** Add a read-only `--finops` (or `/finops` chat command) that renders a
per-agent-type token/USD table from the existing `sqlite_store.py` rollups — turning the
975-line mirror that currently has no consumer into the pitch's "FinOPS Dashboard."
Keep it terminal-only; the React frontend stays deferred. **Why:** substance gate S4
(credible product, not a checkbox shell) and the pitch's explicit promise.

---

## P2 — Correctness/consistency cleanup

- **P2.1 Spec/runbook truth pass.** After P0, re-derive `specs/70` signals from a fresh
  recorded run and let the provenance assertions in `specs/40` check them, so no scene
  claims a signal the trace lacks.
- **P2.2 Reviewer.** If time-bound, Reviewer may ship last; ensure it is either wired or
  clearly marked future work in one place (not promised in three).
- **P2.3 Right-size SQLite.** If P1.3 is cut, justify or trim `sqlite_store.py` against
  the ~3h examiner benchmark; an unused 37 KB mirror reads as over-engineering.

---

## Files that change (all via spec → generator → regenerate)

- `scripts/generate_project.py` — `_execute_live_tool` (concurrency, typed dispatch,
  Coder writes, started_at/ended_at), `PARENT_TOOL_SCHEMAS` (drop write tools),
  `run_task` (retire branches), `run_live_task` (persistent messages).
- `specs/10_main_agent.md`, `specs/12_subagent_pipeline.md`, `specs/40_demo_and_eval.md`,
  `specs/60_observability.md`, `specs/70_demo_runbook.md` — align to the above.
- `PROMPTS.md` — Coder/Grilling/Reviewer prompts already present; confirm dispatch.
- `src/vg_agent/trace.py` template — `agent_type` field. `tests/test_vg_agent.py`
  template — new overlap, Coder, Grilling, chat-memory assertions.

## Verification (end-to-end)

1. `python scripts/generate_project.py --clean` then `uv run pytest` — all green,
   including the new VG.1-overlap, Coder-mutation, Grilling, and chat-memory tests, and
   the existing `test_generated_source_reproducible` (no drift).
2. Record canonical live traces: with `OPENROUTER_API_KEY` set, run each Scene 1–5 task
   via `--live-model --trace` and save the JSONL under `fixtures/demo_repo/traces/`.
3. Offline proof: `docker compose run --rm vg-agent --replay traces/<scene>.jsonl
   --trace --show-context N` reproduces overlapping explorer intervals, the compacted
   marker, and the Coder edit — with `network_mode: none`.
4. Live chat: `--chat --live-model`, run two dependent turns and confirm turn 2 uses
   turn-1 context; `/finops` shows per-agent-type spend; the hard USD cap aborts a
   runaway task (`--max-usd 0.05`).
