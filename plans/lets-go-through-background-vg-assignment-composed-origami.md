# VG Grading Audit — Codesaver CLI (vg_agent)

## Context

The user asked for a self-assessment of the build against
`background/vg_assignment_grading_requirements.md` (template v2.0). For each
hard gate and each VG.1–VG.9 feature this document gives a verdict
(**PASS / ALMOST / FAIL**), grounds it in concrete code/log evidence, then
**re-reads the same item from the opposing, sceptical view** (dual-pass), and
— where the verdict is not a clean PASS — proposes a concrete fix.

The grading rubric is **demo-anchored**: "what you cannot demonstrate and prove
live doesn't count." So the audit weighs not only "does the code do it" but
"is there live/recorded evidence." Evidence base: `src/vg_agent/`,
`tests/test_vg_agent.py`, `specs/*.md`, and 41 real run traces under `traces/`
(notably `907ec426c934.jsonl`, `2af7403dd0db.jsonl`, `54436453af36.jsonl`).

**Headline:** all nine features are MET in code with test + live-trace
evidence. The residual risk is **not** code — it is three demo-anchoring /
process items (HG-1 approval, a true hard-stop demo for VG.3, and the fact that
`traces/` is git-ignored so the live run must actually happen on demo day).

---

## Hard gates (§1)

### VG-HG-0 — artefacts loaded → **PASS**
- **Evidence:** spec, build and demo logs were all opened and quoted in this
  audit. Real traces exist (`traces/907ec426c934.jsonl` etc., 41 files).
- **Critical pass:** `traces/` is git-ignored (`.gitignore:6`), so a grader
  cloning the repo sees *no* logs. The gate is about what *this* grader opened
  (met), but a remote grader has no artefacts → see remediation under VG-HG-4.

### VG-HG-1 — own approved spec → **ALMOST (examiner-dependent)**
- **Evidence:** `background/emil_pitch.md` is the student's own
  feature pitch ("Codesaver CLI by Spargeek") and maps 1:1 to the feature set
  (multi-agent sub-delegation, context compaction, destructive-call blocking,
  FinOps live monitoring). `specs/*.md` is a detailed, self-authored spec tree.
- **Critical pass:** the rubric requires a spec **approved by the examining
  teacher**. Approval is an external fact not provable from the repo, and the
  pitch is a 13-line pitch rather than a formal requirement spec. If "approved"
  cannot be shown, HG-1 fails and blocks VG regardless of the code.
- **Fix:** confirm the pitch/spec was formally approved in #assignment-vg;
  if only the pitch was approved, treat `emil_pitch.md` as the SSoT and ensure
  the examiner's approval is on record. No code change.

### VG-HG-2 — student-prompted, no hand-written code → **PASS (with nuance)**
- **Evidence:** the entire runtime tree is *generated* — `CLAUDE.md` and
  `scripts/generate_project.py` build `src/vg_agent/` from `specs/`, `PROMPTS.md`,
  `MODEL_CONFIG.md` with a `SPEC_DIGEST`. "Never hand-edit generated files."
  This is the opposite of hand-written code.
- **Critical pass:** a sceptic could argue the *generator template* itself is
  hand-authored Python. But the gate forbids hand-written *solution* code and
  requires the student show prompt sessions — the spec-first generator pattern
  satisfies "prompted, not hand-typed." Be ready to show the chat sessions.

### VG-HG-3 — architecture understanding → **examiner-dependent (oral)**
- Cannot be graded from artefacts; depends on the live oral check (§4).
  Architecture is clean and explainable (parent loop + typed sub-agents +
  trace/compaction/budget modules), which supports a strong oral.

### VG-HG-4 — demonstrated live → **PASS (conditional on demo day)**
- **Evidence:** `final_demo_live_chat_script.md` (9 scenes), `scripts/run_demo.ps1`,
  and real live traces show end-to-end runs against OpenRouter
  (`907ec426c934.jsonl` is a genuine `gemini-2.0-flash-001` run with costs,
  approvals, parallel sub-agents).
- **Critical pass:** the traces prove past runs, not a *live* one; and they are
  git-ignored. The gate is met **iff** the live/recorded demo is actually run.
- **Fix:** dry-run `scripts/run_demo.ps1` before grading; keep a screen
  recording as fallback (rubric explicitly allows a recording).

---

## Feature set (§2)

### VG.1 — Parallel sub-agents → **PASS**
- **Code:** `agent.py:804-854` `_spawn_many` runs each request in a
  `ThreadPoolExecutor(max_workers=len(runnable))`; results merged back by slot
  (`agent.py:849`) and returned into parent context (`agent.py:600-601`,
  `988`). `MAX_PARALLEL_SUBAGENTS = 4` (`config.py`).
- **Test:** `test_parallel_explorers_run_concurrently_with_overlap`
  asserts wall-clock overlap (`a_start <= b_end and b_start <= a_end`) and that
  both payloads appear in the parent's final answer.
- **Live log:** `traces/907ec426c934.jsonl` turn 3 — parent emits **one**
  `spawn_subagents` with 2 explorer requests; `explorer-2.0` and `explorer-2.1`
  spawn 0.5 ms apart and their `llm_start` events **interleave** (2.1 at
  `:04.505`, 2.0 at `:04.516`) → genuine concurrency, then both summaries are
  consumed by the parent.
- **Critical pass:** (a) `_spawn_many` inserts a `threading.Barrier`
  (`agent.py:835`) that *forces* the timestamp overlap the test checks — so the
  test alone could overstate concurrency. **Rebuttal:** the live trace shows
  interleaved real network `llm_start` events, which the barrier does not
  fabricate. (b) The single `spawn_subagent` path is sequential — but the rubric
  only needs 2+ at once, which `spawn_subagents` delivers. (c) GIL: the parallel
  work is network-bound LiteLLM I/O, so threads genuinely overlap. **Verdict
  holds: PASS.**

### VG.2 — Advanced context engineering → **PASS**
- **Code:** `agent.py:335-354` `_compact_if_needed` compacts any parent
  `tool_result` over `K_COMPACT=4000` tokens into a ≤300-token marker
  (`trace.py:168-174 compacted_marker`), keeping the full payload in JSONL with
  `original_event_idx` + `original_sha256`. `show_context` (`trace.py:177-237`)
  substitutes the marker and filters out sub-agent-internal events
  (`agent_id != "parent"`). Explorer offloading keeps intermediate sub-agent
  steps out of parent context (≤2 KB return only).
- **Test:** `test_parent_compaction_and_subagent_context` asserts the compacted
  marker is present and the raw `sample.log` content (`req-00001`) is **absent**
  from the reconstructed parent context.
- **Live log:** compaction events present in `traces/b7021b4a7a35.jsonl`,
  `95755fb1991a.jsonl`, `7cb2cdc7c58f.jsonl` (the big ~550 KB runs that read
  `sample.log`).
- **Critical pass:** a sceptic notes the model still *receives* a marker (some
  tokens), and only parent-scope results compact — but that is exactly
  "summarising/snipping old tool output + bounding size," which the rubric
  accepts. Two mechanisms (compaction + Explorer offloading) exceed the bar.
  **PASS.**

### VG.3 — Cost monitoring + warning + hard cap → **PASS (one demo caveat)**
- **Code:** real-time readout in `__main__.py:124-130` (`usd running/max`,
  steps, tokens) and per-step `statusline`/`assistant_step` cost in traces.
  Soft warnings at 80% (`budget.py:145-161`, non-blocking). **Hard caps**:
  `budget.py:108-119 before_model_call` returns `allowed=False` for
  `step_cap/token_cap/usd_cap/daily_cap`; `agent.py:886-890` blocks the
  `client.complete()` call when not allowed.
- **Test:** `test_live_loop_budget_abort_before_client_call` — with
  `max_steps=0` the run ends `final_status="aborted"` with **zero** client
  calls. `test_budget_guard_reasons_and_costs` checks `step_cap`/`usd_cap`.
- **Live log:** `traces/2af7403dd0db.jsonl` shows `warn_steps` at 14/15, then a
  `step_cap` budget_event; `54436453af36.jsonl` shows live `running_usd` /
  `max_usd $0.0001/$0.50` statuslines.
- **Critical pass:** the live `2af7403dd0db.jsonl` cap was **extended via an
  approval** (`extended: true`) rather than stopping — so a grader watching only
  that run sees "cap that warns then continues," which the rubric explicitly
  marks NOT MET ("a cap that only warns"). The true hard stop exists but lives
  in a unit test, not the recorded live run.
- **Fix (demo-anchoring):** add/keep a demo scene that hits a tiny cap
  (`--max-usd 0.0001` or `--max-steps 1`) and **denies** the extension, so the
  live run prints `final_status=aborted`. `scripts/run_demo.ps1` Scene 4 already
  targets this — verify it shows the abort, not an approved extension.

### VG.4 — Protection against harmful tool calls → **PASS**
- **Code:** `tools.py:142-174 validate_shell_command` — deny-by-default
  allowlist (`SAFE_COMMANDS`), rejects shell control/redirection/substitution
  (`;`, `&&`, `||`, `|`, `>`, `<`, backtick, `$(`), a `DESTRUCTIVE_TOKENS`
  blocklist (`mv`, `cp`, `chmod`, `curl`, `git`, `ssh`, …), `-exec/-delete`
  arg blocking, and path-traversal refusal (`resolve_workspace_path`,
  `_path_token_error`). Sensitive-path denylist blocks `.env`, keys, creds.
  Validation runs **before** `subprocess.run` (`tools.py` `run_bash`) and
  **before** the approval prompt.
- **Test:** `test_run_bash_rejects_dangerous_commands` (rm -rf, pipes,
  redirection, `sed -i`, `find -delete`, `git`, `ssh` all blocked; victim file
  survives), `test_file_tools_reject_path_traversal`,
  `test_unsafe_run_bash_is_rejected_before_approval_prompt`.
- **Critical pass:** `rm` IS in `SAFE_COMMANDS` (`tools.py:12`) — surprising for
  a "destructive protection" claim. **Rebuttal:** it is special-cased
  (`validate_shell_command_for_workspace` / `rm_delete_target`) to permit only a
  single existing *regular file inside the workspace*; `rm -rf .` is rejected
  (proven by test). Still, be ready to justify this design choice in the oral —
  it is the one line a sceptical grader will probe. **PASS.**

### VG.5 — Bash execution → **PASS**
- **Code:** `tools.py` `run_bash` → `subprocess.run(["bash","-c",command],
  cwd=root, timeout=30)`; available to Explorer/Coder/Reviewer
  (`SUBAGENT_TOOL_NAMES`, `agent.py:39-44`).
- **Live log:** `traces/907ec426c934.jsonl` and `54436453af36.jsonl` show real
  `find . -maxdepth 1 ...` executions with actual workspace output.
- **Critical pass:** every bash call passes the VG.4 guard first (pairs as the
  rubric requires). No weakness. **PASS.**

### VG.6 — Partial file editing → **PASS**
- **Code:** `tools.py:248-262 edit_file` does find-and-replace
  (`content.replace(old, new)`) and reports occurrence count; `read_file_range`
  supports line-range inspection. Whole-file `write_file` exists but is not the
  only path. Edits are Coder-only (`PARENT_TOOL_SCHEMAS` excludes write/edit).
- **Test:** `test_edit_file_reports_replacement_count`,
  `test_parent_has_no_write_tools_and_coder_is_sole_mutation_path`.
- **Live log:** `traces/0fed272a2098.jsonl` — Coder `edit_file old:"Small"
  new:"Big"` → "edited README.md; replaced 1 occurrence(s)".
- **Critical pass:** `replace(old,new)` replaces **all** occurrences, not a
  bounded line range, so it is coarser than `str_replace` with a unique anchor.
  **Rebuttal:** the rubric explicitly accepts "find-and-replace a region" as
  partial editing; a section is edited, not the whole file. **PASS.**

### VG.7 — Deployable / idiot-proof packaging → **PASS**
- **Code/docs:** `Dockerfile` (non-root user, pinned base, runs generator at
  build), `docker-compose.yml` (volume mounts, `cap_drop ALL`,
  `no-new-privileges`), `README.md` step-by-step (`copy .env`, build, seed,
  run). `pyproject.toml` defines the `vg-agent` entry point.
- **Critical pass:** README is PowerShell/Windows-centric and requires manual
  `.env` editing + dir creation — a Linux grader must adapt. **Rebuttal:**
  `docker compose` is cross-platform and the steps are documented and short, so
  a non-author can follow them. **PASS.**

### VG.8 — Config file + env-var secrets → **PASS**
- **Code:** `OPENROUTER_API_KEY` read only via `os.environ.get`
  (`live_model_client.py`), raising `MissingOpenRouterKey` if absent — never
  defaulted or read from a tracked file. Config lives in `config.py` /
  `MODEL_CONFIG.md` / `.env.example`. `.gitignore:9-23` ignores `.env`,
  `*.pem`, `*.key`, `credentials*`, keeps only `.env.example`. `trace.py`
  carries a redaction regex for `sk-or-v1-…` so keys can't leak into logs.
- **Critical pass:** a real `.env` exists on disk (`.env`) with a live key — but
  it is git-ignored and not tracked (`git ls-files` shows only `.env.example`),
  so no secret is committed. **PASS.**

### VG.9 — Agent autonomy: tool-call vs yield → **PASS**
- **Code:** `agent.py:857-989 run_live_task` is a model-driven `while` loop;
  the model is called every iteration with the full tool schema; if it returns
  no tool calls the loop emits `run_end` and yields (`agent.py:944-952`). The
  parent system prompt states "you decide each transition; this is not a fixed
  script" and "decide each turn whether to call another tool or yield."
- **Live log:** `traces/907ec426c934.jsonl` line 46 — parent `assistant_step`
  with `stop_reason:"stop"` and empty `tool_calls` → the **model** chose to
  yield; earlier turns it chose `spawn_subagents`. Different prompts produce
  different tool sequences in different traces.
- **Critical pass:** the pipeline (Grilling→Explorer→Coder→Reviewer) could look
  scripted, but it is only prompt guidance — no Python switch forces the
  sequence, and traces show variable paths. **PASS.**

---

## Substance gate (§4b)
- **S1 (each feature actually works live):** YES — live traces back VG.1/2/3/5/6/9;
  VG.4/8 are code+test (safety is intentionally not exercised destructively live).
- **S2 (genuinely integrated):** YES — sub-agent summaries are consumed by the
  parent, compaction marker reaches the model, cap blocks the client call, guard
  fires before approval.
- **S3 (oral understanding):** examiner-dependent (§4).
- **S4 (credible product, not a shell):** YES — typed pipeline, tracing, SQLite
  mirror, FinOps statuslines, Docker, dashboard dir; matches the pitch.

---

## Verdict summary

| Item | Verdict | Note |
|---|---|---|
| VG-HG-0 artefacts | PASS | traces git-ignored (local only) |
| VG-HG-1 approved spec | **ALMOST** | approval is external; confirm pitch/spec approved |
| VG-HG-2 student-prompted | PASS | spec-first generator, show chat sessions |
| VG-HG-3 architecture (oral) | examiner | strong, but graded live |
| VG-HG-4 demonstrated live | PASS* | conditional on running the demo / recording |
| VG.1 parallel sub-agents | PASS | live interleave in 907ec426c934 |
| VG.2 context engineering | PASS | compaction + Explorer offload |
| VG.3 cost+warn+hard cap | PASS | demo a *denied* extension → true abort |
| VG.4 harmful-call guard | PASS | be ready to justify `rm` allow |
| VG.5 bash | PASS | real `bash -c`, guarded |
| VG.6 partial edit | PASS | find-and-replace |
| VG.7 packaging | PASS | Docker + README |
| VG.8 config + env secrets | PASS | `.env` git-ignored, no committed key |
| VG.9 autonomy | PASS | model-driven yield in trace |

**Overall: VG-grantable on the feature set and substance gate.** The only items
that can still block are process/demo-anchoring, not code.

---

## Remediation plan (close the residual risk)

No runtime code is broken; the work is to make the not-clean items
demo-provable. (Per repo rules, any runtime change goes through
`specs/`+`scripts/generate_project.py` then `--clean` + `uv run pytest`, never a
hand-edit of `src/vg_agent/`.)

1. **VG.3 true hard-stop demo (highest priority).** In the demo, run a scene
   with `--max-steps 1` (or `--max-usd 0.0001`) and **deny** the extension so
   the live output ends `final_status=aborted`. Verify `scripts/run_demo.ps1`
   Scene 4 does this (deny, not approve). No code change — it's a runbook fix in
   `final_demo_live_chat_script.md` / `run_demo.ps1`.
2. **VG-HG-1 approval.** Confirm in #assignment-vg that `emil_pitch.md` (and/or
   the `specs/` tree) is the approved requirement spec; note the approval where
   the examiner can see it.
3. **VG-HG-4 / HG-0 evidence durability.** Because `traces/` is git-ignored,
   either (a) dry-run `scripts/run_demo.ps1` immediately before grading, and/or
   (b) capture a screen recording as the allowed fallback. Optionally commit one
   sanitized reference trace under a non-ignored path (e.g. `docs/sample_trace.jsonl`)
   so a remote grader has an artefact.
4. **VG.4 oral readiness.** Prepare the one-line justification for `rm` in
   `SAFE_COMMANDS`: single existing regular file, inside workspace,
   `rm -rf .`/dirs/escapes all rejected (cite
   `test_run_bash_rejects_dangerous_commands`).

## Verification

- `uv run pytest` — confirm all safety/budget/parallel/compaction tests green.
- `scripts/run_demo.ps1` (with `OPENROUTER_API_KEY` set) — confirm Scene 2
  parallel explorers overlap, Scene 4 cap **aborts** on deny, Scene 5 blocks the
  `.env` read live.
- Inspect a fresh trace: `--show-context 8` should show the compacted marker and
  absence of `sample.log` body at the final parent step.
