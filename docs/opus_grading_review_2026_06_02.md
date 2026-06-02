# VG Grading Review — `vg_assignment`

**Reviewer:** Claude (Opus 4.8) · **Date:** 2026-06-02
**Rubric:** `docs/background/vg_assignment_grading_requirements.md` (template v2.0)
**Scope of evidence:** runtime code (`agent.py`, `tools.py`, `budget.py`) + JSONL
session logs under `traces/`, focused on **2026-06-01 / 06-02**.

---

## Verdict: ALMOST PASS

All nine features (VG.1–VG.9) are **MET** with live trace evidence, and the
substance gate is effectively all-YES at the agent-shell bar. Two concrete
blockers keep this from a clean PASS **right now**:

1. The provenance test `test_generated_source_reproducible` is **currently red**
   (stale `SPEC_DIGEST`).
2. The HG-1 spec-approval gate is **not recorded in-repo** (examiner-dependent).

Both are quick-fix / examiner items, not architectural gaps.

---

## Hard gates

| Gate | Verdict | Evidence |
|---|---|---|
| HG-0 artefacts loaded | ✅ | Specs, source, and traces read and quoted concretely. |
| HG-1 approved spec | ⚠️ examiner | Spec authored and real (`specs/00_overview.md`, `docs/background/emil_pitch.md`). `docs/demo/hg1_requirement_spec_status.md` leaves "Teacher approval received?" **blank** — cannot confirm from repo. |
| HG-2 student-prompted / generated | ⚠️ see Blocker #1 | Spec-first generation genuine (`scripts/generate_project.py`, `docs/plans/cursor/*`, `docs/plans/legacy/*`). Its own proof command currently fails. |
| HG-3 architecture understanding | ⚠️ oral | Out of scope for log review. |
| HG-4 demonstrated live | ✅ | Traces are recording-equivalent; features fire in real runs. |

---

## Feature set (VG.1–VG.9) — all MET

### VG.1 Parallel sub-agents — MET
`traces/95755fb1991a.jsonl` (Jun 1 07:11), prompt
*"…summarise auth/ and utils.py in parallel; combine both sub-agent findings
into one final recommendation"*:
- two `subagent_spawn` at identical `started_at` (`…52.113926` / `…52.114186`)
- **both** `subagent_return` `status:"ok"`, consumed in the parent's next step.

`traces/a73dede4108c.jsonl` shows a second parallel batch of three explorers
with overlapping wall-clock windows. Code: `_spawn_many` uses
`ThreadPoolExecutor` + `threading.Barrier` (`agent.py:1437-1447`) — genuine
concurrency. Coders are serialised with a `conflict` result to avoid write
races (`agent.py:1418`).

### VG.2 Advanced context engineering — MET
Two mechanisms, both observed live:
- parent-scoped **tool-result compaction** over `K_COMPACT=4000`
  (`_compact_if_needed`, `agent.py:464`)
- **conversation compaction** over a model-window fraction
  (`compact_conversation`, `agent.py:521`)

`context_compaction`/`compaction` events appear in `95755fb1991a`,
`a73dede4108c`, `38d704d33f7b`, `e09a7d2aa893`. Explorer offloading returns
only a ≤2 KB summary to the parent (small `subagent_return.summary` payloads).

### VG.3 Cost monitoring + warning + hard cap — MET (strong)
`traces/e93c5de5dbda.jsonl` (Jun 2 06:14) is textbook:
`warn_steps` → `step_extend` prompt → `warn_tokens` → repeated
**`token_cap` / `step_cap` hard stops** that actually halt and are
interactively extended. `budget.py:before_model_call` enforces step/token/USD/
daily caps *before* each call; `pending_warnings()` fires soft warnings at
fractions. `run_end` carries `total_cost_usd` / `total_tokens`. Real hard stop,
not a printed number.

### VG.4 Protection against harmful tool calls — MET
Live block in `e93c5de5dbda`:
`"run_bash blocked: command 'python3' is not in the read-only allowlist"` (4×).
`tools.validate_shell_command` is deny-by-default (allowlist + destructive-token
blocklist + shell-control/glob rejection + sensitive-path patterns for
`.env`/keys). Write/spawn calls pass an approval gate — `322e77cad165` shows
`approval decision:"approved_scoped"` before `write_file`. Guard is in-process,
independent of Docker.

### VG.5 Bash execution — MET
`run_bash` runs real commands (`find auth/ -maxdepth 1 -type d` in
`a73dede4108c`), paired with the VG.4 guard.

### VG.6 Partial file editing — MET
`edit_file` = find-and-replace (`tools.edit_file`, str_replace semantics,
reports occurrence count). Demonstrated in recent runs: `655bbac4b21c`
(Jun 1, **12** `edit_file` calls — "review and fix calculator"),
`fd5540398e10` (Jun 1, 6). Distinct from whole-file `write_file`.

### VG.7 Deployable / idiot-proof packaging — MET (at bar)
`Dockerfile`, `docker-compose.yml`, 10 KB `README.md`, `start-web.sh`, and a
documented runbook in `CLAUDE.md`
(`docker compose run --rm vg-agent --task …`).

### VG.8 Config file + env-var secrets — MET
`config.example.toml` + `runtime_settings.py` loader; secrets via env.
`git ls-files` confirms **only** `.env.example` (and `workspace/.env.example`)
are tracked — the real `.env` is git-ignored (`.gitignore:10-12`). No committed
secret.

### VG.9 Agent autonomy — MET
Model-driven loop; the parent yields exactly when a turn has no tool calls
(`run_end final_status:"ok"`, `agent.py:1575`). It re-spawns Coder on
`writes_ok==0` and Reviewer on `FAIL:` autonomously.

---

## Substance gate (§4b)

| # | Question | Verdict |
|---|---|---|
| S1 | Each feature actually works live (not just code)? | **YES** — observed firing in Jun 1-2 traces. |
| S2 | Features genuinely integrated? | **YES** — parallel returns consumed; caps abort; gate blocks; Reviewer re-spawns Coder. |
| S3 | Oral confirms architecture understanding? | examiner/oral. |
| S4 | Credible product at adjusted bar? | **YES, with caveat** (below). |

**S2 highlight** — `322e77cad165.jsonl` (Jun 2): the weak Coder model
(`gemini-2.5-flash-lite`) emitted file *text* with no tool call
(`stop_reason:"length"`) → harness caught `writes_ok=0` → **re-spawned coder-2,
which wrote the file successfully** (`wrote calc4/calculator.py`). Shell
resilience is real.

**S4 caveat (honest)** — artifact quality is model-bound. In `fd5540398e10`
(Jun 1) the built calculator "is not really calculating correctly" and the
verify run ended `tool_error`; the **system itself surfaced this** rather than
hiding it. Consistent with the stated VG claim ("the agent shell, not model
quality") in `specs/00_overview.md` and the self-eval in
`specs/41_runtime_quality_eval.md` / `specs/model_experience.md`. Per rubric §B
(tech-stack/quality neutrality) this does not sink the feature verdicts.

---

## Blockers (why "almost," not "pass")

### Blocker #1 — reproducibility test is RED
`uv run pytest` → **1 failed, 163 passed**. Failure is
`test_generated_source_reproducible`:

```
- DIGEST = "0d2b348d0cac3032a3dba578074af25e25107967964b4ba13cf4570b3f7ed163"  (checked in)
+ DIGEST = "85a41a6845f4551a4784fda3a6b3fe9bf8333931dea65dbf31b5071f73112039"  (regenerated)
```

The `.py` bodies are **byte-identical** — only the `SPEC_DIGEST` constant is
stale because today's spec edits (`specs/40_demo_and_eval.md`,
`41_runtime_quality_eval.md`, `model_experience.md`; Jun 2 10:14-10:15) were not
followed by `python scripts/generate_project.py --clean`. Trivial to fix, but as
committed the exact command `docs/demo/hg2_prompt_evidence.md` cites as proof of
provenance **fails** — a tough grader hits it immediately on `uv run pytest`.

### Blocker #2 — HG-1 approval unrecorded
The spec exists and is solid, but teacher approval is a hard gate and is not
captured anywhere in the repo.

---

## What closes the gap to a clean PASS

1. Run `python scripts/generate_project.py --clean` and re-commit so
   `test_generated_source_reproducible` is green (164/164).
2. Record spec approval (date/approver) in
   `docs/demo/hg1_requirement_spec_status.md`.
3. At the oral (HG-3), be ready to explain: parallel fan-out via
   barrier + threadpool; the two compaction triggers; where the hard cap is
   enforced (`budget.py:before_model_call`); and the weakest part — which the
   logs already show is sub-agent **model** quality, mitigated by Reviewer +
   `writes_ok` / empty-turn retries.

---

## Evidence index (trace IDs)

| Trace | Date | Demonstrates |
|---|---|---|
| `95755fb1991a` | Jun 1 07:11 | VG.1 clean parallel (both `ok`, combined) + VG.2 compaction |
| `a73dede4108c` | Jun 1 10:37 | VG.1 parallel overlap (2× then 3×) + VG.2 compaction |
| `e93c5de5dbda` | Jun 2 06:14 | VG.3 warn → step_extend → token/step hard caps; VG.4 `run_bash blocked`; run_tests |
| `322e77cad165` | Jun 2 07:40 | S2 Coder re-spawn after `writes_ok=0`; VG.4 write approval gate |
| `fd5540398e10` | Jun 1 18:57 | VG.6 edit_file; S4 honest failure surfaced |
| `655bbac4b21c` | Jun 1 19:05 | VG.6 review-and-fix (12 `edit_file`) |
| `38d704d33f7b` / `e09a7d2aa893` | Jun 1 | VG.2 compaction |
