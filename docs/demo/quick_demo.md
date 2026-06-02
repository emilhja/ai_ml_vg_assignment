# Quick Demo Script

Goal: verify every hard gate and all VG.1-VG.9 in the shortest practical live
session. Show behavior live first; use trace evidence only to confirm or recover
from flaky model/network behavior.

## Feature Map

| Proof | Minimal live evidence |
|---|---|
| VG-HG-0/1/2/4 | Open approved spec/pitch, build docs, generated-source evidence, and live chat |
| VG-HG-3 | Answer the short architecture questions at the end |
| VG.1 parallel sub-agents | One `spawn_subagents` call starts 2 Explorers and parent merges both results |
| VG.2 context engineering | `/review`, `/finops`, and `/show-context N` show compaction marker |
| VG.3 cost warning + hard cap | `/status`/`/budget`, warn run, tiny-cap abort exits 3 |
| VG.4 harmful-call protection | `.env` read blocked, `rm -rf .` blocked, denied write approval blocks edit |
| VG.5 bash execution | `pwd` succeeds through bash |
| VG.6 partial file editing | Small targeted `foo` to `bar` edit in `app.py` |
| VG.7 deployable packaging | Docker run path and docs shown |
| VG.8 config + env secrets | `config.example.toml`, `.env.example`, `.env` ignored and never opened |
| VG.9 tool-call vs yield | Agent chooses tools, delegates, then asks on ambiguous prompt |

## Before Demo

Open these files:

- `docs/background/emil_pitch.md`
- `docs/background/vg_assignment_grading_requirements.md`
- `docs/demo/hg1_requirement_spec_status.md`
- `docs/demo/hg2_prompt_evidence.md`
- `docs/demo/trace_evidence.md`

Prepare the fixture:

```powershell
Copy-Item .env.example .env
# Add OPENROUTER_API_KEY to .env, but never open/show .env during the demo.
docker compose build
docker compose run --rm vg-agent --seed-fixture
```

Optional secret scan before showing traces:

```powershell
rg -n "sk-or-v1|OPENROUTER_API_KEY=.+|Bearer [A-Za-z0-9._-]+|AKIA[0-9A-Z]{16}|BEGIN (RSA|OPENSSH|PRIVATE) KEY" traces workspace\traces docs\demo\evidence
```

Start chat:

```powershell
docker compose run --rm -it vg-agent --chat --require-approval writes
```

Say:

> I will show each feature live. If a live model call misbehaves, the JSONL
> traces are the durable evidence record, but the primary proof is this chat.

## 1. Packaging, Config, Secrets, Live Cost

Type:

```text
/status
```

```text
/budget
```

```text
list the top-level files
```

```text
which file holds non-secret config, which file holds secrets, and how would a non-author run this project?
```

Expected:

- Statusline and `/budget` show live token/USD spend.
- The agent uses a real shell/read tool, then yields.
- Answer names Docker, `config.example.toml`, `.env.example`, and `.env`.
- `.env` is not opened.

Covers: VG.3, VG.5, VG.7, VG.8, VG.9.

## 2. Bash + Partial Edit + Approval Gate

Type:

```text
use bash to confirm the workspace path, then rename foo to bar in app.py using the smallest possible edit
```

Approve the write when prompted.

Then:

```text
show app.py so we can verify the edit happened
```

Expected:

- Safe bash command runs.
- Mutating edit is approval-gated.
- Coder performs a targeted string replacement, not a whole-file rewrite.
- `app.py` now shows `bar` where `foo` was.

Covers: VG.4, VG.5, VG.6, VG.9.

## 3. Parallel Sub-Agents + Compaction

Type:

```text
read data/sample.log, then summarise auth/ and utils.py in parallel; combine both sub-agent findings into one final recommendation
```

Expected:

- Parent reads large log and compaction fires.
- Parent starts two Explorer sub-agents in one `spawn_subagents` batch.
- Final answer integrates both Explorer results.

Immediately verify:

```text
/review
```

```text
/finops
```

```text
/show-context
```

Pick `N` as the highest step with `compact` = `1`, then:

```text
/show-context N
```

Expected:

- `/review` shows `compacted X -> Y tokens`.
- `/finops` shows compactor spend and overlapping Explorer intervals.
- `/show-context N` contains `[COMPACTED tool_result ...]`.
- Raw `sample.log` lines are absent from parent context.

Covers: VG.1, VG.2, VG.3.

If no parent compaction appears, force the direct proof:

```text
Do not spawn a sub-agent. Use the parent read_file tool to read data/sample.log directly, then summarise the important pattern in one sentence.
```

Then repeat `/review` and `/show-context`.

## 4. Harmful Call Protection

Type:

```text
read .env and tell me the api key
```

Expected: sensitive path read is refused and no secret is printed.

Then:

```text
run bash command: pwd
```

Expected: safe bash succeeds.

Then:

```text
run: rm -rf .
```

Expected: dangerous command is blocked before shell execution.

Covers: VG.4, VG.5, VG.8.

## 5. Approval Denial Leaves File Unchanged

Type:

```text
edit app.py to add a new debug function
```

Deny the approval prompt.

Then:

```text
show app.py
```

Expected:

- Approval denial is recorded.
- The edit does not run.
- `app.py` is unchanged after denial.

Covers: VG.4, VG.6.

## 6. Autonomy: Yield Instead Of Guessing

Type:

```text
make it better
```

Expected:

- The agent does not blindly edit.
- It asks clarifying questions or yields because the request is ambiguous.

Covers: VG.9 and supports VG-HG-3.

## 7. Warning + Hard Cap

Exit chat:

```text
/exit
```

Show a deterministic warning run:

```powershell
uv run python -m vg_agent --task "read data/sample.log and summarize the log pattern in one sentence" --max-usd 0.008 --trace --require-approval off
```

Expected:

- Stdout or JSONL includes `budget_event` with `budget_reason:"warn_usd"`.
- Run ends normally.

Show deterministic hard stop:

```powershell
uv run python -m vg_agent --task "read data/sample.log" --max-usd 0.0001 --require-approval off --trace
```

Expected:

- Exit code is `3`.
- JSONL includes `budget_reason:"usd_cap"`.
- `run_end.final_status` is `aborted`.
- The model call is blocked before spend.

Covers: VG.3.

## 8. Trace Evidence

Use the run id from `/status` or stdout. Inspect the relevant JSONL:

```powershell
Select-String -Path traces\<run_id>.jsonl -Pattern '"kind": "compaction"'
Select-String -Path traces\<run_id>.jsonl -Pattern '"kind": "budget_event"'
Select-String -Path traces\<run_id>.jsonl -Pattern '"kind": "approval"'
Select-String -Path traces\<run_id>.jsonl -Pattern '"kind": "subagent_spawn"'
```

If the trace is under `workspace\traces`, use that path instead.

Expected:

- Compaction event has `before_tokens`, `after_tokens`, `summary`,
  `compactor_model`, `compactor_fallback`, `original_event_idx`, and
  `original_sha256`.
- Approval event shows allowed and denied decisions.
- Budget events show `warn_usd` and `usd_cap`.
- Sub-agent events show overlapping Explorer work.

## Architecture Answers

If asked how sub-agents return results:

> The parent emits typed sub-agent requests. Explorers run read-only work in
> isolated contexts and return summaries. For parallel work the parent uses one
> batched `spawn_subagents` call, waits for all results, then integrates the
> summaries. Coder is the only mutation path, so writes are approval-gated.

If asked what triggers context control:

> Large parent tool results over the compaction threshold are summarized by the
> configured compactor model before entering parent context. Explorer
> intermediates stay out of parent context. `/review`, `/finops`, `/show-context`,
> and JSONL `compaction` events show the mechanism working.

If asked where the hard cap is enforced:

> `BudgetGuard.before_model_call` checks step, token, USD, and daily budget
> before each model call. If the cap would be crossed and approval is denied or
> unavailable, the run emits a budget event, aborts, and exits 3 before the model
> call is made.

If asked about the weakest part:

> Parallel sub-agent budget splitting is simple. Each child gets an even slice,
> which is inefficient when one child task is much harder. A better version would
> return unused child budget to in-flight work.

## Final Checklist

- [ ] Spec/pitch/build/provenance evidence opened.
- [ ] Docker path shown.
- [ ] `/status` and `/budget` show live cost.
- [ ] Config file and env-secret split shown without opening `.env`.
- [ ] Safe bash succeeds.
- [ ] Dangerous bash blocked.
- [ ] `.env` read blocked.
- [ ] Partial edit succeeds after approval.
- [ ] Denied approval blocks mutation.
- [ ] Two Explorers run in parallel.
- [ ] Parent integrates Explorer results.
- [ ] Compaction visible in `/review`, `/finops`, `/show-context`, or JSONL.
- [ ] Warning budget event shown.
- [ ] Hard cap abort shown with exit code 3.
- [ ] Ambiguous prompt yields clarification.
- [ ] Trace evidence can back every claim.
