# Final Grading (according to Opus)

**Date:** 2026-06-02
**Reviewer:** Claude (Opus 4.8)
**Inputs reviewed:** `docs/background/vg_assignment_grading_requirements.md`,
`docs/demo/quick_demo.md`, supporting evidence docs
(`trace_evidence.md`, `hg1_requirement_spec_status.md`,
`hg2_prompt_evidence.md`, `emil_pitch.md`), `.vg_chat_history` session logs,
and the curated JSONL traces themselves (spot-checked, not trusted blindly).

---

## Verdict: **PASS** on everything gradeable from artifacts — with two items that only the live examiner can close

The feature set and the data-backed hard gates are solid. The only open items
are the ones the rubric *explicitly reserves* for the examiner (oral check +
confirming the approval source). Nothing in the artifacts is faked or missing —
the traces contain exactly what the demo docs claim.

---

## Hard gates

| Gate | Status | Evidence |
|---|---|---|
| HG-0 artefacts loaded | ✅ MET | Spec, build, traces all present and quotable |
| HG-1 own approved spec | ⚠️ MET *as recorded* | `specs/` is the contract; `hg1_…md` records teacher approval 2026-06-02. **Rests on a self-asserted record** — examiner must eyeball the actual #assignment-vg approval message |
| HG-2 student-prompted, no hand-code | ⚠️ MET *on request* | `.vg_chat_history` shows live prompting; runtime is generated from markdown via `generate_project.py`. **Construction sessions live in Cursor/Claude history, not the repo** — showable but not in-repo |
| HG-3 architecture understanding | ⏳ Pending oral | Prepared answers exist (`quick_demo.md` §Architecture Answers); examiner-only |
| HG-4 demonstrated live | ✅ MET | Multiple live traces with real cost/tokens |

---

## Feature set — all verified in traces

| Feature | Status | Verified |
|---|---|---|
| VG.1 parallel sub-agents | ✅ MET | `af9b76f58b41`: 2 Explorers spawned same turn (`started_at` within 0.5ms), both `subagent_return`, parent integrated |
| VG.2 context engineering | ✅ MET | Compaction `133300 → 135` tokens, `compactor_fallback:false` |
| VG.3 cost + warn + hard cap | ✅ MET | `warn_usd` (run ok) **and** `usd_cap` → `final_status:"aborted"` |
| VG.4 harmful-call protection | ✅ MET | `.env` → `sensitive path` error; `touch`/non-allowlisted → blocked; approval `denied` halts edit |
| VG.5 bash | ✅ MET | `run_bash pwd` works; allowlist enforced |
| VG.6 partial editing | ✅ MET | `fd5540398e10`: 6 targeted `edit_file` calls |
| VG.7 packaging | ✅ MET | `Dockerfile` + `docker-compose.yml` + README |
| VG.8 config + secrets | ✅ MET | `config.example.toml` (no secrets), `.env.example`, `.env` git-ignored |
| VG.9 autonomy | ✅ MET | "make it better" yields clarification |

---

## Substance gate (§4b)

- **S1 each feature actually works (not just code):** YES — verified in traces.
- **S2 genuinely integrated:** YES — sub-agent results merged, cap actually
  aborts, safety gate actually errors.
- **S3 architecture understanding:** pending oral.
- **S4 credible product at adjusted bar:** YES — not a checkbox shell.

---

## What stands between this and a granted VG

These are **not artifact gaps** — they're the inherently-live parts:

1. **HG-3 + substance S3 (oral):** Must answer the architecture questions live.
   Prepared answers are good; the weakest-part answer (even budget-splitting
   across children) is honest and credible.
2. **HG-1 approval proof:** Have the actual Discord approval message open
   alongside `hg1_requirement_spec_status.md` — the doc *asserts* approval but a
   grader following §C must see the source.
3. **HG-2 construction sessions:** `.vg_chat_history` is demo-driving, not
   build-construction. Keep 2–3 exportable Cursor/Claude sessions ready, since
   the rubric requires showing them *on request*.

---

## Bottom line

This is a genuine product, not a checkbox shell (S1–S4 pass on integration). If
the live demo runs as the traces show and the oral questions are fielded, this
is a clean VG. The risk is entirely execution-on-the-day + the approval paper
trail — not the build.

**Demo caution:** VG.1/VG.2/VG.3 lean on *curated past traces* as fallback. The
rubric is blunt — *"what you cannot demonstrate live doesn't count."* Lead with
a live reproduction of each; use the JSONL only to recover from a flaky model
call, exactly as `quick_demo.md` already advises.
