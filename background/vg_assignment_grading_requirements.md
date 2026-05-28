# VG Grading Template — Claude-Code / Codex competitor

<!-- Copyright © Spiking Neurons AB -->

**Course:** Applicerad AI (TH25) · **Assignment:** VG assignment — build a
competitor to Claude Code / Codex with sub-agent handling and context
engineering.
**Canonical rubric (SSoT):** the **#assignment-vg Discord channel** — every
criterion below is traceable to that channel.
**Grading model:** the VG is graded against (a) the student's own approved
requirement specification and (b) the minimum feature set. Each item is MET /
NOT MET / PARTIAL. **VG is granted** when all hard gates pass, the feature set
is MET at the goldcoin-adjusted bar, and the substance gate passes.
**Template version:** 2.0 (deployment-grade) — 2026-05-20. Supersedes v1.0.

Built to be applied **consistently by different graders** (GraderBot LLM pass
and the examining teacher) and yield the **same verdict** on the same
submission. Every item states an explicit MET rule, NOT-MET rule, what to
ACCEPT / REJECT, and a calibration example.

---

## §A. The grading process

1. **Intake** (§C) — identify the submission and its artefacts.
2. **Hard gates** (§1) — any fail blocks VG until resolved.
3. **Feature pass** (§2) — every required feature gets a verdict + evidence,
   anchored to the **live demo** wherever possible.
4. **Scope & quality** (§3) and **substance gate** (§4b) — judgement checks.
5. **Oral knowledge-check** (§4) — architecture-level, at the demo.
6. **Verdict** (§5) — apply the rule; the examining teacher's verdict is final.

The LLM pass never grants VG alone — it produces an evidenced proposal. VG is
an examiner-level grade; the human examiner decides.

## §B. Universal grading rules

- **Demo-anchored evidence (MANDATORY).** Discord, verbatim: *"What you cannot
  demonstrate and prove live doesn't count, in this assignment."* Every MET on
  a feature MUST be anchored to a concrete moment in the live demo (or the
  submitted recording), or to a code+output artefact the student showed. A
  feature only described, never demonstrated, is **NOT MET**.
- **Graded against the student's own spec.** The student authored a
  requirement specification (VG-HG-1). Grade their build against *that* spec
  AND the minimum feature set §2. The spec may exceed the minimum — extra scope
  is the student's choice, not a requirement.
- **PARTIAL** counts as NOT MET unless the shortfall is purely cosmetic;
  document any exception.
- **Goldcoin bar adjustment.** Discord: the expected scope/quality bar is
  lowered in proportion to the goldcoins the student spent on this assignment.
  Record the goldcoin count in §0 and state the adjusted bar in §3 BEFORE
  judging PARTIALs. The adjustment moves the *quality/scope* bar; it never
  waives a hard gate and never waives the existence of a feature.
- **Tech-stack neutrality.** Discord: any language is allowed. Never penalise
  the language, framework, or that the student never read the code — judge the
  system and the demo.
- **No double-counting.** Each weakness lowers exactly one item.
- **Verdict rule.** VG granted iff: all hard gates pass AND VG.1–VG.9 all MET
  (at the adjusted bar) AND the substance gate §4b is all-YES AND the live demo
  was satisfactory. Anything else → *not yet*, with a concrete gap list.

## §C. Submission intake

| Field | Capture in §0 |
|---|---|
| The student's requirement-specification document | link / file |
| The pitch posted in #assignment-vg | link |
| The build (repo / package) | link |
| Demo: date, format (live / recording / AI-avatar — all allowed) | |
| Chat/prompt sessions that produced the build (shown on request) | |
| Goldcoins spent on this assignment | number |

Edge cases: a recording or AI-avatar demo is explicitly allowed in place of a
live in-class demo — grade it the same way. If no requirement spec exists or it
was never approved, VG-HG-1 fails — do not grade further until resolved.

---

## §0. Submission identification

| Field | Value |
|---|---|
| Student name / Discord ID | |
| Requirement spec — link & approval status | |
| Pitch posted in #assignment-vg? | |
| Build (repo / package) link | |
| Demo date / format | |
| Goldcoins spent on this assignment | |

## §1. Hard gates — any FAIL blocks VG until resolved

| Gate | MET (pass) when | FAIL when | Verdict + evidence |
|---|---|---|---|
| VG-HG-0 — artefacts loaded | The spec, the build, and demo evidence were actually opened; the grader can quote concrete content of each. | Any of them is missing/unreadable — do not grade hallucinated artefacts. | |
| VG-HG-1 — own approved spec | The student authored a requirement specification AND it was approved by the examining teacher. | No spec, or never approved. | |
| VG-HG-2 — student-prompted, no hand-written code | The student prompted the solution themselves and can show the chat sessions on request. (Manually hand-written code is **not allowed** for this assignment.) | The student cannot show the sessions, or wrote the code by hand. | |
| VG-HG-3 — architecture understanding | The student can explain the system at the **architecture** level — how it works, strengths, weaknesses. (Line-by-line code understanding is **not** required.) | The student cannot explain their own system's architecture. | |
| VG-HG-4 — demonstrated live | The solution was shown working live (or by recording / avatar). | It was only described; key parts were never shown working. | |

---

## §2. Minimum feature set (#assignment-vg)

Each feature: MET only if **demonstrated** (see §B). "Shown in code but never
run in the demo" = NOT MET.

**VG.1 — Multi-agents: parallel sub-agents**
- MET: the main agent **starts sub-agents that run in parallel**, and **uses
  their results** back in the main session — shown in the demo.
- NOT MET: only one agent; or "sub-agents" that run strictly sequentially with
  no parallelism; or sub-agent results that are produced but never consumed.
- ✅ the demo shows 2+ sub-agents working at once and the main agent
  integrating their output. ❌ a single loop relabelled "sub-agent".

**VG.2 — Advanced context engineering**
- MET: a concrete mechanism keeps the context window under control — e.g.
  automatic conversation compaction, summarising/snipping old tool output,
  bounding tool-result size, or an MCP-style external-context integration —
  and the student can point to it working or explain when it triggers.
- NOT MET: the full transcript just grows unbounded with no mechanism.
- ✅ compaction that summarises old turns once a threshold is hit. ❌ "we send
  the whole history every time" with nothing else.

**VG.3 — Real-time cost monitoring + budget warnings + hard cap**
- MET: token/USD cost is shown in real time, AND there is a budget warning,
  AND a hard cap that actually stops the agent. The hard stop must be shown or
  clearly evidenced in code (not merely a printed number).
- NOT MET: a cost counter with no enforced cap; or a cap that only warns.
- ✅ live cost readout + a warning threshold + a hard stop when the cap is hit.
  ❌ prints cost but would run forever.

**VG.4 — Protection against harmful tool calls**
- MET: destructive/dangerous tool calls are actively blocked or gated *before*
  execution (allow/deny-list, confirmation, sandbox) — demonstrably in code.
- NOT MET: tool calls run unchecked; or "safety" is only a prompt sentence.
- ✅ a destructive command is refused/blocked in the demo or by a shown rule.
  ❌ the only protection is telling the model to behave.

**VG.5 — Bash execution** — MET: the agent runs real shell commands. NOT MET:
no shell capability. (Pairs with VG.4 — the guard must cover bash.)

**VG.6 — Partial file editing** — MET: the agent edits a *section* of a file
(find-and-replace a region / line range), not whole-file overwrite only. NOT
MET: the only file capability rewrites whole files.

**VG.7 — Deployable / idiot-proof packaging**
- MET: a clean, documented install/run path that a non-author can follow — a
  Docker container, or an equivalent well-packaged method.
- NOT MET: "clone it and figure it out"; undocumented manual steps.
- ✅ `docker compose up` (or equivalent) + a short README. ❌ no instructions.

**VG.8 — Config file + env-var secrets**
- MET: all configuration is in a config file; all secrets come from environment
  variables; no secret is committed in code or config.
- NOT MET: hard-coded settings, or a key pasted into a tracked file.
- ✅ `config.*` + `.env` (with `.env.example`, real `.env` git-ignored).

**VG.9 — Agent autonomy: tool-call vs. yield**
- MET: the agent itself decides each turn whether to call another tool or yield
  back to the user (the baseline ASSN-2 behaviour).
- NOT MET: a fixed script decides; the model never chooses to stop.

## §3. Scope & quality (at the goldcoin-adjusted bar)

State the adjusted bar first, then assess:

| Check | Note |
|---|---|
| Goldcoins spent → adjusted scope/quality bar | |
| Treated as a real *product* — has a feature "pitch" | |
| Build vs. the ~3 h examiner benchmark (≈40 h student-equivalent), adjusted down per goldcoins | |
| Cost-cap / monitoring present "for your own protection" against runaway API loops | |

## §4. Oral knowledge-check (examiner, at the demo)

2–3 architecture-level questions. The student must answer at the level of
system design, not code lines. Examples: "How do your sub-agents return
results to the main agent, and what happens if one fails?" · "What triggers
your context mechanism, and what does it drop?" · "Where is the hard cost cap
enforced and what happens when it fires?" · "What is the weakest part of your
design?" Record: ANSWERED WELL / SHAKY / CANNOT EXPLAIN. SHAKY or worse feeds
VG-HG-3 and §4b S3.

## §4b. Substantive quality gate (judgement — NOT a checkbox)

Meeting every feature in §2 is **necessary but not sufficient**. A submission
can present all nine and still be a shell.

| # | Substance question | Y/N + note |
|---|---------------------|-----------|
| S1 | In the live demo, did each claimed feature actually *work* — not just exist in code? | |
| S2 | Are the features genuinely integrated — sub-agent results actually used, the cap actually enforced, the safety gate actually blocking? | |
| S3 | Does the oral check confirm architecture-level understanding (strengths, weaknesses, failure modes)? | |
| S4 | At the goldcoin-adjusted bar, is this a credible *product* — not a checkbox shell? | |

Any **NO** ⇒ VG *not yet*, regardless of the feature checklist.

## §5. Verdict

| Item | Result |
|---|---|
| Hard gates VG-HG-0..4 — all pass? | |
| Feature set VG.1–VG.9 — all MET at the adjusted bar? | |
| Substance gate S1–S4 — all YES? | |
| Live demo satisfactory? | |
| **VG verdict** | **VG granted / not yet** |
| If *not yet*: concrete gap list + what would close each gap | |

## §6. Calibration (for inter-grader consistency)

Before trusting a borderline verdict, dry-run against two anchors:

- **Known-good anchor.** The GraderBot VG reference solution
  (`course-materials/vg-reference-solution/hellcode/`) is a deliberately
  compliant build (parallel sub-agents, context compaction + tool-output caps,
  budget warn + hard cap, command-safety classifier, bash, `str_replace`,
  Docker packaging, config + `.env`, autonomous tool/yield). Applying §2 to it
  must yield **every feature MET**. If it does not, the criterion wording — not
  the reference — is wrong; fix the wording.
- **Known-deficient anchor.** A build that prints a token count but never
  enforces a cap, and whose "sub-agents" run sequentially, must yield VG.1 NOT
  MET and VG.3 NOT MET → *not yet*. If the template passes it, §2 is too loose.

If two graders disagree on an item for the same submission, that item's MET/
NOT-MET rule is under-specified — record it and tighten it.

## §7. Deployment notes & honest limitations

- **Versioned.** v2.0; bump the version + date on any change; graded
  submissions record the version used.
- **Scope.** This template covers **this exact VG assignment** (the
  #assignment-vg Discord spec). It is not a generic rubric.
- **HITL by design.** VG is an examiner grade. The substance gate (§4b), the
  oral check (§4) and the demo (VG-HG-4) require the human examiner. The
  template makes that pass *structured and repeatable* — it does not remove it.
- **Not empirically calibrated against a VG-submission corpus.** Consistency
  rests on the operationalised rules and the §6 anchors; measured inter-rater
  statistics require a real body of graded VG submissions and are a separate
  validation step