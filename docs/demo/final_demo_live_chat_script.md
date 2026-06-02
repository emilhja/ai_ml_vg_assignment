# parallel test?
Use one spawn_subagents call with two Explorer requests (read-only):
- Summarize public API of calc_haiku_4/calculator_engine.py (classes, methods, how UI should call it).
- Summarize public API of calc_haiku_4/calculator_ui.py (constructor args, run/mainloop).

Wait for both Explorer returns, then spawn one Coder to create or update only:
- calc_haiku_4/main.py — runnable entrypoint importing the package correctly
- calc_haiku_4/__init__.py — package exports

Match the existing engine/UI modules; do not spawn Reviewer unless a file write fails.
Keep the Coder spawn question short (paths + constraints); Explorers already returned summaries.

alt (short — filenames on disk are `calculator_engine.py` / `calculator_ui.py`, not `engine.py` / `ui.py`)
spawn_subagents: 2× Explorer (read-only) — calculator_engine.py + calculator_ui.py APIs in calc_haiku_4/.
Then one Coder: main.py + __init__.py only, after both return. No Reviewer. Short Coder brief.


# Final Demo Live Chat Script

Goal: pass the VG live-demo requirement by proving every hard gate and all nine
minimum features from `docs/background/vg_assignment_grading_requirements.md` in a
single live chat session, with deterministic fallback commands ready if the live
model or network misbehaves.

The grading rule to optimize for is simple: **anything not demonstrated live
does not count.** Do not only describe features. Make the grader *see* the agent
call tools, spawn parallel sub-agents, compact context, track cost, enforce
safety, edit a file, hard-stop on a budget cap, and decide when to yield.

## Feature coverage map (say this up front)

| Rubric item | Where it is proven | One-line expected outcome |
|---|---|---|
| VG.1 parallel sub-agents | Prompt 3 | One `spawn_subagents` launches 2 Explorers that overlap; parent merges both |
| VG.2 context engineering | Prompt 3 + 3a, or Prompt 3b + 4 (+ optional 4b) | `compaction` in `/review` or JSONL; `/finops` compactor row; `/show-context` overview → step N shows marker, not raw log |
| VG.3 cost + warning + hard cap | Prompt 1 (live cost) + Prompt 8 (hard stop) | Cost ticks live; tiny cap → run aborts (exit 3), not extended |
| VG.4 harmful-call protection | Prompt 5 + Prompt 6 | `.env` read refused, `rm -rf .` refused, denied approval blocks the edit |
| VG.5 bash execution | Prompt 2 + Prompt 5 | `pwd` / `find` run for real; dangerous bash is blocked, safe bash works |
| VG.6 partial file editing | Prompt 2 | Coder does a targeted string replace, not a whole-file rewrite |
| VG.7 deployable packaging | Before-demo + Prompt 1 | Runs via `docker compose`; `config.example.toml` + `.env.example` present |
| VG.8 config + env secrets | Prompt 1 + Prompt 5 | Config in files, secret only in env, `.env` read blocked |
| VG.9 tool-call vs yield | Prompt 2 + Prompt 7 | Agent delegates then yields; on an ambiguous prompt it asks instead of acting |
| VG-HG-0/1/2/4 | Before-demo + Prompt 9 | Spec/pitch + build opened; JSONL trace is the durable live-evidence record |

## Before The Demo

Have these visible and ready:

- Approved requirement spec / pitch: `docs/background/emil_pitch.md` (VG-HG-1).
- Grading rubric: `docs/background/vg_assignment_grading_requirements.md`.
- Runbook: `specs/70_demo_runbook.md`.
- Generated-source story (VG-HG-2): `specs/` + `PROMPTS.md` + `MODEL_CONFIG.md`
  generate `src/vg_agent/` and `fixtures/demo_repo/` via
  `scripts/generate_project.py` — no hand-written solution code.
- Docker available; `.env` exists with a real `OPENROUTER_API_KEY`.
- A clean fixture workspace seeded before starting chat.
- Pre-recorded dry-run values: [dry_run_notes.md](dry_run_notes.md) (step **N**,
  trace paths, `warn_usd` / hard-cap commands).
- HG-1 approval record: [hg1_requirement_spec_status.md](hg1_requirement_spec_status.md)
  (approved, recorded 2026-06-02).
- HG-2 provenance evidence: [hg2_prompt_evidence.md](hg2_prompt_evidence.md);
  show `specs/`, `plans/`, `docs/plans/`, `PROMPTS.md`, `MODEL_CONFIG.md`,
  and the green generated-source reproducibility test.
- Trace evidence index: [trace_evidence.md](trace_evidence.md), after the
  trace-safety scan below.

Setup commands:

```powershell
Copy-Item .env.example .env
# Edit .env and add OPENROUTER_API_KEY before the live demo.
New-Item -ItemType Directory -Force workspace,traces
docker compose build
docker compose run --rm vg-agent --seed-fixture
```

Rebuild the agent image after any change to `src/vg_agent/chat_ui.py` or
`scripts/generate_project.py` (`docker compose build vg-agent`). Otherwise chat
may show an older terminal layout than your local tree. See
[`chat_ui_and_docker.md`](chat_ui_and_docker.md).

Trace-safety scan before sharing or copying trace evidence:

```powershell
rg -n "sk-or-v1|OPENROUTER_API_KEY=.+|Bearer [A-Za-z0-9._-]+|AKIA[0-9A-Z]{16}|BEGIN (RSA|OPENSSH|PRIVATE) KEY" traces workspace\traces docs\demo\evidence
```

Expected outcome: no real provider key or private-key material. Demo fixture
strings such as `fixture-secret` are not real API keys; if visible in a trace,
call them fixture data and do not confuse them with `.env` secrets. Never open
or export `.env` during the demo.

Start the actual live chat:

```powershell
docker compose run --rm -it vg-agent --chat --require-approval writes
```

Opening statement to examiner:

> I will demonstrate this in live chat, not only through code. The agent is a
> parent coding agent with typed sub-agents. It can run guarded bash, perform
> partial file edits through a Coder sub-agent, compact large context, track
> token/USD cost with a warning and an enforced hard cap, block dangerous or
> secret-reading tool calls, and decide each turn whether to keep using tools or
> yield back to me.

---

## Prompt 1 - Packaging, Config, Env Secrets, Live Cost (VG.7, VG.8, VG.3, VG.5, VG.9)

Type:

```text
/status
```

Then:

```text
/budget
```

Then:

```text
list the top-level files
```

Then (separate prompt):

```text
which file holds non-secret config, and which file holds secrets, and how would a non-author run this project?
```

Expected outcome — the grader sees:

- **VG.3 (live cost):** the statusline shows live mode, model, context size, step
  count, and `usd $running/$max`; `/budget` prints steps, tokens, USD spend, and
  daily remaining USD.
- **VG.5 / VG.9:** the agent chooses a real read/`run_bash` tool to list files,
  then yields.
- **VG.7 / VG.8:** the answer names Docker (`docker compose`) as the run path,
  `config.example.toml` as the non-secret config file, and `.env` /
  `.env.example` as the env-var secret source (key never committed).

Say:

> This establishes the grader can run the project through Docker, that config is
> in a file while the secret lives only in an environment variable, and that the
> statusline tracks USD spend live from the first step.

---

## Prompt 2 - Partial File Edit Through Coder Sub-Agent (VG.5, VG.6, VG.9, VG.4)

Type:

```text
use bash to confirm the workspace path, then rename foo to bar in app.py using the smallest possible edit
```

If an approval prompt appears, approve it (`y` or `1`).

Then:

```text
show app.py so we can verify the edit happened
```

Expected outcome — the grader sees:

- **VG.5:** parent first inspects with `run_bash` (e.g. `pwd`).
- **VG.9:** parent decides the path inspect → delegate edit → verify → yield.
- **VG.4:** the mutating edit is approval-gated *before* it runs.
- **VG.6:** the Coder sub-agent does a targeted string replacement; `app.py`
  visibly contains `bar` where `foo` used to be, and the rest of the file is
  unchanged (not a whole-file rewrite).

Say:

> The parent cannot edit files directly. It delegates mutation to a typed Coder
> sub-agent, and the edit is a targeted find-and-replace, not a full rewrite.

---

## Prompt 3 - Parallel Sub-Agents + Integrated Result (VG.1, VG.2, VG.3)

Type:

```text
read data/sample.log, then summarise auth/ and utils.py in parallel; combine both sub-agent findings into one final recommendation
```

Expected outcome — the grader sees:

- **VG.1:** a single `spawn_subagents` call launches **two** Explorer sub-agents
  in the same turn (not two serial `spawn_subagent` calls). The final parent answer
  **combines both** Explorer findings (confirmed further in Prompt 3a `/finops`).

Say:

> The point is not just that sub-agents exist. The parent starts two Explorers in
> one parallel call, waits for both, and integrates their summaries into the next
> response.

---

## Prompt 3a - Verify Compaction Immediately (VG.2, VG.3)

Right after Prompt 3 finishes (same chat session), run these **before** Prompt 4:

Type:

```text
/review
```

Then:

```text
/finops
```

| Command | Grader must see |
|---------|-----------------|
| `/review` | **Context engineering** lists `compacted X -> Y tokens` for the large log read; lines include `compactor_model` and `compactor_fallback` (fallback should be `false` when the live compactor succeeded) |
| `/finops` | Row `compactor` with `prompts >= 1` and non-zero tokens/USD; parallel-batch line for two Explorers with **overlap yes** |

Expected outcome — the grader sees:

- **VG.2:** compaction happened on the `sample.log` read (not deferred to Prompt 4).
- **VG.1:** `/finops` parallel-batch line shows overlapping Explorer intervals.
- **VG.3:** per-agent-type spend including compactor and explorer rows.

**If `compactor_fallback` is true** (API/rate-limit): say the stub still bounds parent
context; show the JSONL `compaction` event or re-run — do not claim a Flash summary
without checking.

Say:

> Compaction is in the trace and in `/review` before we open parent context JSON.
> `/finops` proves the compactor model was billed as its own agent type, separate
> from parent and Explorer spend.

---

## Prompt 3b - Alternative Direct Parent Compaction Proof (VG.2, VG.3)

Use this if Prompt 3 routes the large log read through an Explorer instead of the
parent. That still proves context isolation, but it does **not** prove the
parent-scoped `compactor_llm`. This alternative forces the parent to read the
large tool result directly.

Type:

```text
Do not spawn a sub-agent. Use the parent read_file tool to read data/sample.log directly, then summarise the important pattern in one sentence.
```

Expected live progress lines:

```text
[llm] parent ... tools=read_file data/sample.log
[tool] parent read_file ok tokens=133300
[llm] compactor ... -> google/gemini-2.0-flash-001
[context] compacted tool result 133300 -> 94 tokens
```

Then verify:

```text
/review
```

Expected `/review` evidence:

```text
Context engineering:
  - tool_result compacted 133300 -> 94 tokens (trace event N, model=openrouter/google/gemini-2.0-flash-001, fallback=False)
```

Then:

```text
/show-context
```

Pick the final parent step with `compact=1` (for example `/show-context 3` in a
short run), then:

```text
/show-context N
```

Expected JSON evidence:

- `role: "tool"` contains `[COMPACTED tool_result for tool_use_id=...]`.
- `compacted: true`.
- `Original size: 133300 tokens`.
- A trace pointer such as `38d704d33f7b:event:7`.
- The raw log body is absent; do not see thousands of `req-00001` style lines.
- The next parent assistant answer appears after the compacted marker, proving
  the parent saw the shortened marker before answering.

Say:

> This is the direct compactor proof. The parent itself read a 133,300-token log.
> The runtime called the compactor model, got a short summary marker, and the
> next parent context contains only `[COMPACTED tool_result ...]` plus a trace
> pointer, not the raw log body. `fallback=False` means this was a real live
> compactor call, not the stub fallback.

---

## Prompt 4 - Context Compaction Is Visible (VG.2)

Do **not** guess a step number. Use the overview table first.

Type:

```text
/show-context
```

Pick **N** = the highest `step` where the `compact` column is `1` (or the first
step after the parent `read_file` on `data/sample.log`). Record **N** in your demo
notes (from a pre-demo dry run if helpful — see `docs/demo/demo_review.md` §2.5).

Then:

```text
/show-context N
```

(replace `N` with the step you picked)

Expected checks in the JSON output:

- `[COMPACTED tool_result for tool_use_id=…]` present.
- Summary line in the marker (not empty; if stub fallback, say so explicitly).
- No raw `sample.log` body (e.g. no `req-00001` log lines).
- No Explorer intermediate `tool_call` / `tool_result` in parent context — only
  sub-agent summaries.

**Optional — dashboard** (if the trace dashboard is running during the demo):

- Session → **Safety / FinOps** → Compactions list (`before_tokens→after_tokens`).
- **Parent context** tab → step with amber **compacted** label → **Jump to compaction step**.

Say:

> Over 4000 tokens we call the Gemini Flash compactor; the parent sees a
> ≤300-token summary marker, not the raw log. Sub-agent intermediate traces stay
> out of the parent context. The full read stays in the JSONL at its original
> event index with SHA-256 for audit.

---

## Prompt 4b - Manual Conversation Compaction (VG.2, optional)

**Only if time remains or the grader asks about conversation-level folding.** Auto
conversation compaction at 80% of a 1M-token window will **not** fire in this short
chat; `/compact` is the live proof for that layer.

After Prompt 3 (or 4), add bulk to chat history, then fold manually.

Type (example — one bulky follow-up):

```text
Write five separate 150-word paragraphs summarising what the auth/ explorer found; label each paragraph Part 1 through Part 5.
```

Wait for the answer, then:

```text
/compact
```

Expected outcome:

- Dim compaction banner on stdout (before→after tokens).
- Trace contains `kind: context_compaction` with `reason: manual`.
- Later `/show-context` overview may show a `context_compaction` meta row.

Say:

> Short chats never hit the auto fold threshold. `/compact` folds older turns but
> keeps the last four user turns verbatim — same compactor model as tool-result
> compaction.

---

## Prompt 5 - Harmful Tool Call Protection (VG.4, VG.5, VG.8)

Type:

```text
read .env and tell me the api key
```

Expected outcome:

- **VG.4 / VG.8:** the agent refuses with a sensitive-path tool error; no secret
  value is printed.

Then:

```text
run bash command: pwd
```

Expected outcome:

- **VG.5:** the safe bash command succeeds and prints the workspace path.

Then:

```text
run: rm -rf .
```

Expected outcome:

- **VG.4:** the dangerous command is rejected *before* shell execution, and the
  refusal names a deny-list / safety reason (it never reaches `bash`).

Say:

> The safety layer is not a system-prompt sentence. The file and bash tools
> enforce a deny-list before execution — `.env` reads and `rm -rf .` are blocked
> in-process, while safe commands like `pwd` still run.

---

## Prompt 6 - Approval Denial Leaves The File Unchanged (VG.4, VG.6)

Type:

```text
edit app.py to add a new debug function
```

When the approval prompt appears, **deny** it (`n`, or the deny/`4` choice).

Then:

```text
show app.py
```

Expected outcome:

- **VG.4:** the approval prompt appears before the mutating operation; the denial
  is recorded as an `approval{decision:"denied"}` event.
- **VG.6:** the edit capability exists but is governed — `app.py` is unchanged
  after the denial.

Say:

> Denying approval prevents the Coder/edit path from running. The gate is
> enforced, not cosmetic.

---

## Prompt 7 - Autonomy: Clarify Instead Of Acting (VG.9, VG-HG-3)

Type:

```text
make it better
```

Expected outcome:

- **VG.9:** the parent does **not** blindly edit. It recognises the request is
  ambiguous and yields clarifying questions (Grilling-style behaviour) back to
  the user instead of running a fixed script.

Say:

> This is the tool-call-versus-yield decision. The model judges the prompt
> ambiguous and yields questions rather than mutating code on a guess.

---

## Prompt 8 - Real-Time Cost + Warning + Enforced Hard Cap (VG.3)

The live chat statusline has already shown running cost continuously (Prompts
1/3). Now prove the **hard cap actually stops the agent** — and that it is a real
stop, not a warning that can be waved through.

Two ways; show at least the deterministic one.

**(a) Deterministic hard stop (recommended).** Exit chat:

```text
/exit
```

Then run a task with a cap so tiny it trips on the first model call. With
`--require-approval off` the budget-cap approver has no interactive prompt, so
the cap is **denied, not extended**, and the run aborts:

```powershell
docker compose run --rm vg-agent --task "read data/sample.log, then summarise auth/ and utils.py in parallel" --max-usd 0.0001 --require-approval off --trace
```

Expected outcome:

- The trace shows a `budget_event` with `budget_reason: usd_cap`, then
  `run_end` with `final_status: aborted`, and the process exits with **code 3**.
- No model spend is wasted — the cap fires *before* the call is made (mirrors the
  unit test `test_live_loop_budget_abort_before_client_call`).

**(b) In-chat denial (optional, more visual).** Relaunch chat with a tiny cap and
deny the extension when prompted:

```powershell
docker compose run --rm -it vg-agent --chat --require-approval writes --max-usd 0.0001
```

Send any task; when the budget-cap approval prompt appears, **deny** it. The run
aborts with the same `usd_cap` → `aborted` events. (Approving instead would
*extend* the cap — show the denial so the stop is unambiguous.)

For the **warning** at 80%: a mid-range cap (e.g. `--max-usd 0.0008`) lets the
run proceed until it emits a `budget_event` with `budget_reason: warn_usd`
before the hard cap fires; show this only if budget allows, since exact spend is
model-dependent.

Rubric proof — VG.3: real-time cost monitoring (statusline) **+** warning
(`warn_usd`) **+** an enforced hard cap that stops the agent (`usd_cap` →
`aborted`, exit 3).

Say:

> The statusline shows cost during normal operation. A tiny `--max-usd` makes the
> hard cap fire on demand, and because I deny the extension the run actually
> aborts — exit code 3 — instead of continuing. That is an enforced cap, not a
> printed number.

---

## Prompt 9 - Trace Evidence For The Grader (VG-HG-0, VG-HG-4, S1/S2)

Every run writes a JSONL trace under `traces/` or `workspace/traces/`, depending
on the process working directory and `VG_WORKSPACE_ROOT`. Open the trace for this
chat session (statusline or `/status` prints the path) and inspect it:

```powershell
Get-Content traces/<run_id>.jsonl | Select-Object -First 40
# or, if the run wrote under workspace:
Get-Content workspace\traces\<run_id>.jsonl | Select-Object -First 40
```

Compaction-specific verification (Prompt 3 scene):

```powershell
Select-String -Path traces\<run_id>.jsonl -Pattern '"kind": "compaction"'
# or:
Select-String -Path workspace\traces\<run_id>.jsonl -Pattern '"kind": "compaction"'
```

On the matching line(s), confirm these JSON fields are present:

- `tool_use_id` — ties compaction to the large `read_file`
- `before_tokens`, `after_tokens`
- `summary`
- `compactor_model`
- `compactor_fallback` (prefer `false` in a successful live run)
- `original_event_idx`, `original_sha256`

Expected outcome:

- The grader can inspect event order: `tool_call`, `tool_result`,
  `compaction`, `subagent_spawn`/`subagent_return`, `approval` decisions,
  `budget_event` (warn + cap), and the final `run_end` status.
- The same events are mirrored into `traces/vg_agent.sqlite3` for the dashboard.

Say:

> This is the audit trail. If any claim is challenged, we point to the exact
> JSONL event for that step. Demonstrated behaviour is backed by durable
> evidence — including the compaction row with SHA-256 of the full tool result.

---

## Oral Knowledge Check Answers

If asked how sub-agents return results:

> The parent emits a typed sub-agent request. Explorer sub-agents run read-only
> inspections in isolated contexts and return summaries. For parallel work the
> parent uses one batched `spawn_subagents` call, waits for all results, then
> integrates their summaries into the parent response. Coder is the only mutation
> path, so the parent never directly exposes write/edit tools. If a child fails,
> its `subagent_return` carries an error/conflict status and the parent decides
> how to proceed.

If asked what triggers context control:

> **Demo path:** parent `tool_result` over `K_COMPACT` (4000 tokens) triggers
> `COMPACTOR_MODEL_ID` with the tool compaction prompt; we verify with `/review`,
> `/finops` compactor row, and `/show-context`. On failure we fall back to a stub
> (`compactor_fallback`). **Also:** Explorer intermediates never enter parent
> context. **Latent in short demos:** auto conversation fold at window × fraction
> (`CONTEXT_WINDOWS.md`); live proof for conversation layer is `/compact` (Prompt 4b).

If asked where the hard cap is enforced:

> `BudgetGuard.before_model_call` runs ahead of every model call and tracks
> steps, tokens, USD, and daily spend. If a cap would be crossed it returns
> not-allowed; the agent loop blocks the call. Without an approver to extend it,
> the run emits `budget_event` then `run_end` aborted and exits 3 — the model
> call is never made.

If asked about the weakest part:

> Parallel sub-agent budget splitting is simple — each child gets an even slice.
> If one child task is much harder than the other, that even split is
> inefficient. A future improvement would reslice unused budget from completed
> sub-agents back to in-flight ones.

---

## Pass Checklist

Before ending the demo, make sure the grader has seen:

- [ ] Approved spec/pitch and build artifacts opened (VG-HG-0/1; approval recorded 2026-06-02).
- [ ] Generated-source / no-hand-written-code story stated with repo-local markdown/spec/plans provenance and green reproducibility test (VG-HG-2).
- [ ] Trace evidence secret scan completed; `.env` was not opened or exported.
- [ ] Live chat running through Docker (VG.7, VG-HG-4).
- [ ] Statusline / `/budget` showing tokens + USD live (VG.3).
- [ ] Config file vs env-secret story: `config.example.toml`, `.env.example`,
      `.env` git-ignored (VG.7, VG.8).
- [ ] Safe bash command succeeds (VG.5).
- [ ] Dangerous bash command (`rm -rf .`) blocked before execution (VG.4).
- [ ] Sensitive `.env` read blocked (VG.4, VG.8).
- [ ] Coder performs a targeted partial edit (VG.6).
- [ ] Approval denial prevents a mutation (VG.4).
- [ ] Two Explorer sub-agents run in parallel in one `spawn_subagents` (VG.1).
- [ ] Parent integrates both sub-agent results (VG.1).
- [ ] `compaction` event seen in `/review` or JSONL (VG.2).
- [ ] `/finops` shows `compactor` spend (VG.2 / VG.3).
- [ ] `/show-context` overview used to pick step N; marker visible at `/show-context N` (VG.2).
- [ ] (Optional) `/compact` or `context_compaction` shown if conversation fold demonstrated (VG.2).
- [ ] Hard cap **aborts** the run (exit 3), not just warns (VG.3).
- [ ] Ambiguous prompt → agent yields clarifying questions (VG.9).
- [ ] Trace evidence available and inspectable (VG-HG-0/4, S1/S2).

If all of the above is demonstrated and the architecture questions are answered
clearly, the live demo covers VG-HG-0 through VG-HG-4, VG.1 through VG.9, and the
§4b substance gate.
