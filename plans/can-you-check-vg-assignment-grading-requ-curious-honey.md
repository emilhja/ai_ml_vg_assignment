# VG rubric fit — gap analysis

## Context

`vg_assignment_grading_requirements.md` defines the grading rubric: 5 hard
gates (VG-HG-0..4), 9 feature criteria (VG.1..VG.9), a substance gate, and an
oral check. This document maps each criterion to concrete evidence in the
current repo (`src/vg_agent/`, `specs/`, `tests/`, packaging) and flags the
single hard miss that would block VG today.

The summary: **8 of 9 feature criteria are MET. VG.1 (parallel sub-agents) is
NOT MET as the rubric is worded** — `MAX_CONCURRENT_SUBAGENTS = 2` exists in
`config.py:18` but is unused; `specs/00_overview.md:18-19` explicitly says
*"No sub-agent concurrency requirement unless a future spec adds a demo and
test proving it."* Spawning is synchronous in `agent.py:334-341`. The rubric
(VG.1) explicitly calls out *"sub-agents that run strictly sequentially with
no parallelism"* as NOT MET.

## Feature-by-feature verdict

| ID | Criterion | Verdict | Key evidence |
|---|---|---|---|
| VG.1 | Parallel sub-agents | **NOT MET** | `agent.py:334-341` spawns Explorer synchronously; `config.py:18` `MAX_CONCURRENT_SUBAGENTS=2` is unused; `specs/00_overview.md:18-19` explicitly disclaims concurrency |
| VG.2 | Advanced context engineering | MET | `agent.py:208-234` `_compact_if_needed` with `K_COMPACT=4000` (`config.py:24`); Explorer offloads to a 2 KB summary (`agent.py:397`); proved in `tests/test_vg_agent.py:118-125` |
| VG.3 | Cost monitoring + warn + hard cap | MET | `budget.py:93-103` enforces step / token / USD / daily caps; `agent.py:456-458` aborts before model call; `budget_reason` enum in `specs/30_runtime_governance.md:30-31`; 3-strike repetition guard in `budget.py:114-123`; tested in `tests/test_vg_agent.py:59-77, 143-150` |
| VG.4 | Harmful-tool protection | MET | `tools.py:12-41` allowlist + destructive-token blocklist + sensitive-path denylist + shell-control rejection; `validate_shell_command` at `tools.py:85-115`; enforced before every tool execution |
| VG.5 | Bash execution | MET | `tools.py:192` `subprocess.run(["bash","-c",…])`; demo run in `agent.py:645` |
| VG.6 | Partial file editing | MET | `tools.py:171-184` `edit_file` find-and-replace (not whole-file overwrite); demo at `agent.py:617`; tested at `tests/test_vg_agent.py:80-88` |
| VG.7 | Deployable / idiot-proof packaging | MET | `Dockerfile` + `README.md:140-151` docker run cmd; `pyproject.toml` + `uv.lock`; reproducible regen via `scripts/generate_project.py --clean` |
| VG.8 | Config file + env-var secrets | MET | `src/vg_agent/config.py` holds all constants; `.env.example` template; `.gitignore:10-12,26` excludes `.env`, keys, daily-spend; `ANTHROPIC_API_KEY` read from env only |
| VG.9 | Agent autonomy (tool-call vs. yield) | MET | `agent.py:485-492` — model's empty `tool_calls` ends the loop; non-empty continues. Model chooses, not a script |

## Hard gates

| Gate | Status | Note |
|---|---|---|
| VG-HG-0 artefacts loaded | OK | spec + build + tests all present and readable |
| VG-HG-1 own approved spec | **VERIFY** | `assignment_background.md` is the *teacher's* brief, not a student spec. No `requirement-specification.md` in repo. The rubric requires "the student authored a requirement specification AND it was approved by the examining teacher." Confirm this exists somewhere (Discord pin, separate doc) or write one |
| VG-HG-2 student-prompted, no hand-written code | OK | `CLAUDE.md` "Spec-first workflow" + `scripts/generate_project.py` produces all runtime code from markdown — match the assignment's "ZERO meat-bag code" rule (`assignment_background.md:7`) |
| VG-HG-3 architecture understanding | OK (oral) | `specs/`, `CLAUDE.md`, `README.md` give you the talking points; depends on live answer |
| VG-HG-4 demonstrated live | OK | `scripts/run_demo.ps1` exercises sanity edit + VG slide (`--show-context`) + cost-cap abort; replay path also demoable |

## Substance gate (§4b) — pre-demo self-check

- **S1 each feature works in the demo**: confirmed for VG.2–VG.9 via deterministic demo routes (`agent.py` `run_task`). VG.1 currently has no parallel demo.
- **S2 features genuinely integrated**: yes — compaction marker is verified absent-of-payload in tests; cost cap is *enforced*, not just warned; safety gate *blocks*, not just warns.
- **S3 oral check**: depends on examiner Q&A — `specs/00_overview.md`, `specs/30_runtime_governance.md`, `CLAUDE.md` cover the standard "how do sub-agents return / what triggers compaction / where is the hard cap" questions.
- **S4 credible product at goldcoin-adjusted bar**: yes — Docker, README, replay, JSONL trace, three demos, full test suite — above the 3 h examiner benchmark (`assignment_background.md:3`).

## The one blocking gap (and what closes it)

**VG.1 — parallel sub-agents.** The rubric is unambiguous:
> "the main agent **starts sub-agents that run in parallel**, and **uses their
> results** back in the main session — shown in the demo … only one agent;
> or 'sub-agents' that run strictly sequentially with no parallelism …
> is NOT MET."

Two options to close it, in order of effort:

1. **Spawn two Explorers concurrently** in one parent turn (e.g. via
   `concurrent.futures.ThreadPoolExecutor(max_workers=MAX_CONCURRENT_SUBAGENTS)`
   in `agent.py` `_execute_tool_call` when multiple `spawn_subagent` tool
   calls arrive in the same model response). Wire one deterministic demo task
   that issues two questions (e.g. "inspect auth/" + "inspect api/") and
   shows both summaries returned. Update `specs/00_overview.md:18-19` to make
   concurrency a real requirement, add a `subagent_spawn`/`subagent_return`
   ordering test, and regenerate.
2. **If you do not want to add concurrency**, you can argue the goldcoin
   adjustment (`§B "Goldcoin bar adjustment"`) lowers the bar — but the
   rubric also says the adjustment "moves the *quality/scope* bar; it never
   waives a hard gate and never waives the existence of a feature." VG.1
   *existence* is the issue, so option 2 is risky.

**Recommendation: option 1.** ~80–150 lines in `agent.py`, one spec edit, one
test, one demo task addition. This is the smallest change that turns a likely
"not yet" into a clean VG pass.

## Smaller polish items (non-blocking)

- **VG-HG-1**: confirm the requirement spec exists and is teacher-approved.
  If not, draft one (~1 page: scope, non-goals, success criteria — copy from
  `specs/00_overview.md` and `assignment_background.md`).
- **README**: add a one-paragraph "What this demonstrates against the VG
  rubric" section near the top — saves the grader from reading specs to map
  feature → file.
- **Demo script**: have `scripts/run_demo.ps1` print a short header before
  each demo naming which VG criteria it exercises (cheap, helps the grader
  follow along live).

## Files referenced (read-only — no edits made)

- `vg_assignment_grading_requirements.md` (rubric)
- `assignment_background.md` (teacher brief)
- `specs/00_overview.md`
- `src/vg_agent/agent.py`, `config.py`, `budget.py`, `tools.py`, `trace.py`,
  `anthropic_client.py`, `__main__.py`
- `tests/test_vg_agent.py`
- `Dockerfile`, `pyproject.toml`, `README.md`, `.env.example`, `.gitignore`,
  `scripts/run_demo.ps1`, `scripts/generate_project.py`

## Verification

This plan is a diagnosis, not an implementation. To verify the gap call on
VG.1 yourself:

```
# 1. Confirm no concurrency primitive in the runtime:
grep -nE "asyncio|gather|Thread|concurrent\.futures" src/vg_agent/*.py

# 2. Confirm MAX_CONCURRENT_SUBAGENTS is unused:
grep -n "MAX_CONCURRENT_SUBAGENTS" src/vg_agent/*.py

# 3. Read the spec disclaimer:
sed -n '18,19p' specs/00_overview.md
```

If you decide to close VG.1, a follow-up plan should cover: spec edit,
`agent.py` concurrency in `_execute_tool_call`, demo task wiring, test in
`tests/test_vg_agent.py` asserting both `subagent_spawn` events appear before
either `subagent_return`, and regeneration via `scripts/generate_project.py
--clean`.
