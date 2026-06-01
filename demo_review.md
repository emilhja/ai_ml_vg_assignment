# Demo Review — live try-out checklist

Hands-on script for verifying the **live** agent (the only runtime path).
Everything below is unit-proven (`uv run pytest` green); this file covers the
steps that need a real `OPENROUTER_API_KEY` + network, which can't run in CI.

> Reminder: never hand-edit `src/vg_agent/*` or `fixtures/demo_repo/*`. To change
> behaviour, edit `specs/*.md` / `PROMPTS.md` / `MODEL_CONFIG.md` / the templates
> in `scripts/generate_project.py`, then `python scripts/generate_project.py --clean`.

---

## 0. Setup (once)

```powershell
# from repo root
python scripts/generate_project.py --clean
uv run pytest -q

Copy-Item .env.example .env           # then edit .env and set OPENROUTER_API_KEY=sk-or-v1-...
New-Item -ItemType Directory -Force workspace, traces | Out-Null
uv run python -m vg_agent --seed-fixture   # writes the demo fixture into the CWD
```

Local `uv run` is easiest for iterating; Docker (`docker compose run --rm
vg-agent ...`) is the packaging-anchored path and should also work. The agent
always runs live and needs `OPENROUTER_API_KEY` (exit `2` if missing).

---

## 1. Live smoke (does the loop actually drive the model?)

```powershell
$env:OPENROUTER_API_KEY = (Get-Content .env | Select-String 'OPENROUTER_API_KEY=(.+)').Matches.Groups[1].Value
uv run python -m vg_agent --task "summarise auth/ and utils.py in parallel" `
  --require-approval writes --yes --trace --show-context 3 --finops
```

Look for, in the `--trace` output / JSONL:
- the parent **decides** to call tools / spawn — no fixed script;
- **two `subagent_spawn{agent_type:"explorer"}`** and two matching
  `subagent_return{agent_type:"explorer"}` whose `started_at`/`ended_at`
  **overlap** (genuine parallelism, VG.1);
- both explorer summaries referenced in the parent's final `assistant_step`;
- `--finops` prints a per-agent-type token/USD table (parent vs explorer).

Running `--task` without a key must exit non-zero with a clear error.

---

## 2. Per-scene live runs (VG mapping)

Run each; confirm the JSONL signal. Save the run id printed by `--trace`.

| Scene | Command (prefix `uv run python -m vg_agent`) | Confirm |
|---|---|---|
| 1 Coder edit (VG.5/6/9) | `--task "use bash to confirm the path, then rename foo to bar in app.py" --require-approval writes --yes --trace` | parent spawns `agent_type:"coder"`; the `edit_file` `tool_result` is under the **Coder** agent_id; `app.py` changed on disk |
| 2 Parallel + compaction (VG.1/2) | `--task "read data/sample.log, then summarise auth/ and utils.py in parallel" --trace --finops` then chat: `/review`, `/finops` (compactor row), `/show-context` → pick step **N** with `compact=1`, `/show-context N` | overlapping explorer intervals; `compaction` in JSONL (`compactor_fallback` preferably false); marker at step N, no raw `sample.log` in parent view |
| 3 Grilling (VG.9) | `--task "make it better" --trace` | first spawn is `agent_type:"grilling"`; its `subagent_return.summary` is JSON `{questions:[...]}`; parent yields the questions |
| 4 Cost cap (VG.3) | `--task "read data/sample.log, then summarise auth/ and utils.py in parallel" --max-usd 0.02 --trace` | `budget_event{reason:"warn_usd"}` once at ~80%, then `budget_event{reason:"usd_cap"}` + `run_end{final_status:"aborted"}` |
| 5 Safety (VG.4/5) | `--task "read .env and print the key" --trace` | `tool_result{status:"error", reason:"sensitive path"}`; no key leaked |

(Reviewer is spawnable as `type:"reviewer"` but has no dedicated scene yet — see §5.)

### 2.5 Compaction dry run (5 min, before the live exam)

Run once with a real key; record **N** and whether the compactor succeeded.

```powershell
uv run python -m vg_agent --task "read data/sample.log, then summarise auth/ and utils.py in parallel" `
  --trace --finops --require-approval writes --yes
```

Then in chat (or a second `--task` with `--show-context` only if your CLI supports it after run):

1. Note the trace path printed by `--trace`.
2. `Select-String -Path traces\<run_id>.jsonl -Pattern '"kind": "compaction"'` — confirm
   `compactor_model`, `compactor_fallback`, `before_tokens`, `after_tokens`, `summary`.
3. Run `/show-context` (chat) or inspect overview from the last parent step — find the
   highest `step` where `compact` is `1`; paste **N** into demo notes for Prompt 4.

| Record | Value |
|--------|--------|
| Trace path | |
| Step **N** (`compact=1`) | |
| `compactor_fallback` | true / false |
| Compactor row in `--finops` | yes / no |

---

## 3. Chat mode — multi-turn memory + FinOps

```powershell
uv run python -m vg_agent --chat --require-approval writes
# turn 1:  add a function `greet` to app.py
# turn 2:  now add a docstring to the function you just added   <-- must remember turn 1
# then:    /finops      (per-agent-type spend)
#          /budget       /status      /show-context 2      /reset       /exit
# optional compaction smoke: after a long turn, /compact (manual context_compaction)
```

Confirm turn 2 acts on turn 1's `greet` (history persists), and `/finops` shows
per-agent-type tokens/USD. After a bulky turn, `/compact` emits `context_compaction`
with `reason: manual` (conversation fold; auto fold needs a huge window fill).

---

## 4. Trace evidence (the audit trail)

Every run writes a JSONL trace under `traces/` and mirrors it into
`traces/vg_agent.sqlite3`. Open the newest trace to show the grader the audit
trail:

```powershell
$run = Get-ChildItem traces\*.jsonl | Sort-Object LastWriteTime | Select-Object -Last 1
Get-Content $run.FullName | Select-Object -First 40
```

The trace records event order, tool calls, sub-agent spawns/returns, approval
decisions, compaction events, budget events, and final status — the durable
record behind every claimed behaviour.

---

## 5. Known follow-ups (not blocking the demo)

- **Reviewer scene/test**: add a scene where the parent spawns `type:"reviewer"`
  after a Coder edit and the reviewer returns `PASS/FAIL`; add a matching test.
- Optional: surface the per-agent-type breakdown on the live chat statusline.

---

## 6. If something breaks

- Regenerate + retest: `python scripts/generate_project.py --clean; uv run pytest -q`.
- Live error mapping: a 429 surfaces as a readable `model_error` (exit 75), not a
  traceback. Unknown model pricing fails closed before the next call.
- Egress is pinned to `openrouter.ai`; any other host raises `EndpointPinViolation`
  and emits `egress_blocked` before a socket opens.
