# Code Review + Refactor Plan — clarity / DRY / SOC

## Context

The user asked for a thorough code review of the `vg_agent` repo focused on
**clarity**, **DRY** (don't repeat yourself), and **SOC** (separation of
concerns), ignoring `traces/`, `workspace/`, `.venv/`, `__pycache__`, `.git`.
The repo runs **locally only** (the dashboard is local-only too), so
security/CORS/auth/secret-exposure hardening is explicitly **out of scope** —
this review is about maintainability, not threat modeling.

Decisions from the user:
- Deliverable: **review report + a concrete refactor plan** (not just prose).
- Generated code under `src/vg_agent/*` is **in scope at line level**, and so is
  the generator that produces it.

### The single most important structural fact

This is a **spec-first / code-gen** repo. Everything under `src/vg_agent/*` and
`fixtures/demo_repo/*` is **generated** by `scripts/generate_project.py`
(6,071 lines). About **4,000+ lines of runtime Python live as triple-quoted
template strings** inside that one file (`GENERATED_FILES` dict, lines ~133–6012):

| Generated module | Template lines in generator | Generated size |
|---|---|---|
| `agent.py` | ~2514–4554 | 2,041 |
| `__main__.py` | ~4555–6012 | 1,458 |
| `trace.py` | ~1649–2424 | 776 |
| `tools.py` | ~1148–1648 | 501 |
| `live_model_client.py` | ~731–1147 | 417 |
| `budget.py` | ~441–730 | 290 |
| `runtime_settings.py` | ~222–440 | 218 |
| `config.py` | ~140–221 | 82 |
| `demo_fixture.py` | ~2425–2513 | 89 |

Three modules are **copied verbatim** from disk, not templated:
`sqlite_store.py` (1,005), `chat_ui.py` (1,526), `workspace_paths.py` (15)
(generator lines ~6016–6032). `dashboard/`, `tests/`, `docs/`, `scripts/` are
hand-maintained.

**Consequence for this review:** every clarity/DRY fix to a `src/vg_agent/*`
module must be made to its template string inside `generate_project.py`, then
regenerated (`python scripts/generate_project.py --clean`). The generator's
own design is therefore the highest-leverage finding.

---

## Findings

Severity: **[1]** structural / high-leverage · **[2]** real but localized ·
**[3]** polish. Each finding names where the fix actually lives.

### A. Separation of concerns

- **[1] The generator mixes "template engine" with "4,000 lines of product
  code as strings."** `scripts/generate_project.py` is both the build tool and
  the de-facto home of the entire runtime. IDE navigation, type-checking,
  linting, and diffs don't work on the embedded code. *Fix:* extract each
  template to a real `.py.tmpl` file under `scripts/templates/` (or, better,
  promote the modules to real source files and let the generator only inject
  `__PLACEHOLDER__` constants + the `SPEC_DIGEST`). This single change makes
  every other finding below directly fixable with normal tooling.

- **[1] `render()` is a 6-line string-replace with no undefined-variable
  detection** (`generate_project.py` ~125–130). A typo in a `__KEY__`
  placeholder silently emits broken Python. *Fix:* switch to Jinja2 with
  `StrictUndefined`, or assert all placeholders were consumed after render.

- **[1] `agent.py` owns five concerns at once:** approval policy, budget
  enforcement, model I/O, tool dispatch, and sub-agent orchestration. The
  function `_run_live_subagent()` (~1145–1471, **327 lines**) alone interleaves
  model calls, tool execution, retry logic, and metrics. *Fix (in the
  template):* split into `orchestrator.py`, `subagent_runner.py`,
  `tool_executor.py`, `compaction.py`; pass a small `RunContext`
  (guard + approval + recorder) instead of threading them individually.

- **[1] `__main__.py` `_chat_loop()` is ~257 lines** (~1110–1367) doing CLI
  dispatch, approval prompts, progress rendering, and session state. *Fix:*
  a slash-command **dispatch table** (`{name: handler}`) replacing the
  if/elif ladder (~1158–1280), plus a `ProgressRenderer` and a `ChatState`
  object.

- **[2] `tools.py` `run_bash()` validates, creates directories, and executes
  in one function** (~416–449). Validation should be separable from execution.

- **[2] `TraceRecorder` mixes recording + redaction + dual-sink storage**
  (`trace.py` ~80–144 writes JSONL **and** SQLite inline, redacting on the
  way). *Fix:* `Recorder → Redactor → [JsonlSink, SqliteSink]`.

- **[2] Dashboard backend has overlapping "event analysis" services.**
  `services/session_tags.py`, `session_agent_types.py`,
  `session_compaction_tags.py` each re-scan events with similar loops; and
  JSONL loading is duplicated between `services/trace_backfill.py` and
  `services/sessions.py`. *Fix (hand-maintained, safe):* one
  `load_events()` util + one `SessionEventAnalyzer` with typed methods.
  `services/context.py` and `routes/runs.py` also both build message context —
  pick one home.

### B. DRY violations (verified)

- **[1] Security pattern lists are defined twice in `tools.py`** — confirmed by
  reading the file. `SENSITIVE_PATH_PATTERNS` (compiled regexes, lines 33–47)
  is re-encoded inline as `re.search(...)` literals in `_sensitive_path_hint()`
  (lines 65–86). The same kind of duplication exists for the bash safety lists
  (`DESTRUCTIVE_TOKENS`, `FORBIDDEN_ARG_TOKENS`, `GLOB_MARKERS`), which are
  declared at **generator scope** *and* inside the `tools.py` template — two
  sources of truth for the safety rules. *Fix:* single table of
  `(compiled_pattern, hint)` tuples; derive both the block check and the hint
  from it. Collapse the generator-scope copy into the template (or vice-versa).

- **[1] `config.py` repeats every model ID across five dicts** — confirmed.
  Lines 5–10 declare `*_MODEL_ID`, then the same IDs are keys in
  `SUBAGENT_MODEL_IDS`, `PRICING_USD_PER_MTOK`, `CONTEXT_WINDOW_TOKENS`, and
  `AUTO_COMPACT_FRACTION` (lines 12–48). Adding/renaming a model touches 4–5
  places. *Fix (in `MODEL_CONFIG.md` + the `config.py` template):* one
  `MODELS = {id: {pricing, context_window, compact_fraction}}` table; derive the
  per-field dicts from it if back-compat is needed.

- **[2] Tool-call summary formatting is implemented three different ways** in
  `__main__.py` (~551–567), `trace.py` (~595–596), and `agent.py` (~589–591).
  *Fix:* one `format_tool_summary()` helper in `trace.py`, imported by the rest.

- **[2] Budget/per-agent iteration duplicated** in `__main__.py`
  `_print_budget` (~112–120) and `_print_finops` (~372–382), both walking
  `guard.per_agent_type_*`. *Fix:* one `iter_agent_costs(guard)` helper.

- **[2] Event-kind filtering duplicated** between
  `_should_print_compact_progress_event` (~671–694) and `progress_sink_event`
  (~778–799) in `__main__.py`. *Fix:* shared predicate.

- **[2] ANSI color codes (`\x1b[31m`, `\x1b[33m`, …) are scattered** through
  `__main__.py` (520, 530, 702–715, 823–825). *Fix:* a small `COLORS` constants
  block (these belong in a `constants.py` template alongside event-kind names).

- **[3] Event-kind string literals** ("llm_start", "assistant_step",
  "tool_result", …) are hardcoded across `trace.py` and `__main__.py`. *Fix:*
  an `EventKind` constants module.

- **[2] Tests repeat `PipelineClient` setup and approval/budget stubs** across
  50+ tests in `tests/test_vg_agent.py` (4,719 lines, 88 tests). *Fix:* pytest
  fixtures + small factory helpers (e.g. `parent_spawns_coder()`); consider
  splitting the monolith by domain (approval / budget / compaction / parallel).

### C. Clarity

- **[2] Over-long functions** beyond those above: `_execute_live_tool()`
  (`agent.py` ~906–1031, validate+approve+dispatch+record),
  `render_tree()` (`trace.py` ~160–203, 20+ kind branches),
  `extend_cap()` (`budget.py` ~271–289, one function for 6 budget reasons).
  *Fix:* extract per-concern helpers; table-drive the kind→formatter and
  reason→bump mappings.

- **[3] Magic numbers without rationale** in `config.py` (`WARN_*_FRACTION =
  0.8`, `FINAL_STEP_RESERVE = 1`, `K_COMPACT = 4000`). Add a one-line comment
  per constant in the template (these are governed by
  `specs/30_runtime_governance.md` — cross-reference it).

- **[3] `_LiteLLMNoiseFilter` stderr scraping** (`live_model_client.py` ~18–63)
  is a hack around library logging; prefer `logging` configuration.

### D. Smells flagged by exploration — **verify before acting** (do not assume bugs)

These were reported by automated exploration and are **plausible but
unconfirmed**; treat as a verification checklist, not facts:
- `had_tool_error` / `impl_read_ok` in `agent.py` (~1170, 1420) possibly dead.
- Read-only isolation flag (`__main__.py` ~1304) possibly never reset per-turn.
- `read_file_range()` silently returns empty on out-of-bounds start
  (`tools.py` ~379).
- `DailySpendLedger.fail_closed` silently breaks spend tracking (`budget.py`
  ~70).
- `barrier.wait()` parallel coordination has no timeout recovery
  (`agent.py` ~1597).

Each should be confirmed by reading the surrounding code + a focused test
before any change. **Bugs are out of the stated scope (clarity/DRY/SOC); list
them for the user but don't silently "fix" behavior.**

---

## Refactor plan (ordered, lowest-risk first)

> Rule for all `src/vg_agent/*` edits: change the **template** in
> `scripts/generate_project.py` (or the spec it reads), then
> `python scripts/generate_project.py --clean` and `uv run pytest`. Never hand-edit
> generated files — provenance tests compare the checked-in tree byte-for-byte.

**Phase 0 — make the generated code reviewable (enables everything else)**
1. Extract the embedded module templates out of `generate_project.py` into
   `scripts/templates/<module>.py.tmpl` files; the generator reads + renders
   them. Keep `SPEC_DIGEST` inputs unchanged so the digest is stable.
2. Replace `render()` with Jinja2 `StrictUndefined` (or add a post-render
   assertion that no `__…__` placeholders remain).
3. Regenerate; confirm the byte-for-byte provenance test still passes. *This
   phase changes no runtime behavior — it only relocates source.*

**Phase 1 — DRY wins (mechanical, well-covered by tests)**
4. `tools.py` template: collapse `SENSITIVE_PATH_PATTERNS` + `_sensitive_path_hint`
   into one `(pattern, hint)` table; remove the generator-scope duplicate of the
   bash-safety lists.
5. `config.py` template + `MODEL_CONFIG.md`: introduce a single `MODELS` table;
   derive the per-field dicts.
6. Add a `constants.py` template (event kinds + ANSI colors); replace literals
   in `trace.py` / `__main__.py`.
7. One `format_tool_summary()` and one `iter_agent_costs()` helper; delete the
   duplicates.

**Phase 2 — SOC splits (bigger, do after Phase 0/1)**
8. Split `agent.py` template into `orchestrator` / `subagent_runner` /
   `tool_executor` / `compaction`; introduce a `RunContext`.
9. `__main__.py`: slash-command dispatch table + `ProgressRenderer` + `ChatState`.
10. `TraceRecorder`: separate redaction and the two sinks.

**Phase 3 — hand-maintained code (no regeneration needed)**
11. Dashboard: one `load_events()` util; merge the three session-tag services
    into `SessionEventAnalyzer`; pick a single home for context building.
12. Tests: add `PipelineClient`/approval/budget fixtures; optionally split
    `test_vg_agent.py` by domain.
13. `scripts/run_demo.ps1`: extract a `RunLiveScene` function for the repeated
    `uv run … -m vg_agent --task …` scenes.

**Phase 4 — verify smells in section D**, report findings to the user, fix only
those the user confirms are in scope.

---

## Verification

- After **every** template edit: `python scripts/generate_project.py --clean`
  then `uv run pytest` (full suite; provenance + contract tests guard the
  generated tree).
- After Phase 0: confirm `SPEC_DIGEST` in `src/vg_agent/__init__.py` is
  unchanged and the byte-for-byte regeneration test passes (proves the template
  extraction was behavior-preserving).
- After DRY/SOC edits: targeted tests, e.g.
  `uv run pytest tests/test_vg_agent.py::test_parent_has_no_write_tools_and_coder_is_sole_mutation_path`
  and the sensitive-path / bash-safety tests in `tests/`.
- Dashboard changes: `uv run pytest tests/test_dashboard_api.py`
  `tests/test_dashboard_paths.py`; smoke-run `scripts/run_dashboard.ps1` locally.
- Optional end-to-end: `.\scripts\run_demo.ps1 -SkipTests` to confirm the live
  loop still drives.

## Notes / non-goals
- **Local-only**: no auth/CORS/secret-hardening work — explicitly excluded.
- This plan preserves the two context-engineering tricks (parent-scoped
  compaction, Explorer offloading) and all trace invariants; the SOC splits must
  keep `show_context` filtering and the compaction-marker behavior intact.
- Phases are independent enough to land as separate PRs; Phase 0 should go first
  because it makes the rest reviewable with normal tooling.
