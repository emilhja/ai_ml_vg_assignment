# Demo Review — live try-out checklist

Hands-on script for verifying the **live** agent (the graded path) and recording
the canonical traces. Everything below was implemented and unit-proven on
2026-05-28 (`uv run pytest` = 38 green); this file covers the steps that need a
real `OPENROUTER_API_KEY` + network, which can't run in CI.

> Reminder: never hand-edit `src/vg_agent/*` or `fixtures/demo_repo/*`. To change
> behaviour, edit `specs/*.md` / `PROMPTS.md` / `MODEL_CONFIG.md` / the templates
> in `scripts/generate_project.py`, then `python scripts/generate_project.py --clean`.

---

## 0. Setup (once)

```powershell
# from repo root
python scripts/generate_project.py --clean
uv run pytest -q                      # expect 38 passed

Copy-Item .env.example .env           # then edit .env and set OPENROUTER_API_KEY=sk-or-v1-...
New-Item -ItemType Directory -Force workspace, traces | Out-Null
uv run python -m vg_agent --seed-fixture   # writes the demo fixture into the CWD
```

Local `uv run` is easiest for iterating; Docker (`docker compose run --rm
vg-agent-live ...`) is the packaging-anchored path and should also work.

---

## 1. Live smoke (does the loop actually drive the model?)

```powershell
$env:OPENROUTER_API_KEY = (Get-Content .env | Select-String 'OPENROUTER_API_KEY=(.+)').Matches.Groups[1].Value
uv run python -m vg_agent --task "summarise auth/ and utils.py in parallel" `
  --live-model --require-approval writes --yes --trace --show-context 3 --finops
```

Look for, in the `--trace` output / JSONL:
- the parent **decides** to call tools / spawn — no fixed script;
- **two `subagent_spawn{agent_type:"explorer"}`** and two matching
  `subagent_return{agent_type:"explorer"}` whose `started_at`/`ended_at`
  **overlap** (genuine parallelism, VG.1);
- both explorer summaries referenced in the parent's final `assistant_step`;
- `--finops` prints a per-agent-type token/USD table (parent vs explorer).

If `--live-model` is given without a key it must exit non-zero with a clear error.

---

## 2. Per-scene live runs (VG mapping)

Run each; confirm the JSONL signal. Save the run id printed by `--trace`.

| Scene | Command (prefix `uv run python -m vg_agent`) | Confirm |
|---|---|---|
| 1 Coder edit (VG.5/6/9) | `--task "use bash to confirm the path, then rename foo to bar in app.py" --live-model --require-approval writes --yes --trace` | parent spawns `agent_type:"coder"`; the `edit_file` `tool_result` is under the **Coder** agent_id; `app.py` changed on disk |
| 2 Parallel + compaction (VG.1/2) | `--task "read data/sample.log, then summarise auth/ and utils.py in parallel" --live-model --trace --show-context 8` | overlapping explorer intervals; a `compaction` event for `sample.log`; `show-context` shows the compacted marker but **not** raw log / child intermediates |
| 3 Grilling (VG.9) | `--task "make it better" --live-model --trace` | first spawn is `agent_type:"grilling"`; its `subagent_return.summary` is JSON `{questions:[...]}`; parent yields the questions |
| 4 Cost cap (VG.3) | `--task "keep inspecting the repo in detail" --live-model --max-usd 0.05 --trace` | `budget_event{reason:"warn_usd"}` once at ~80%, then `budget_event{reason:"usd_cap"}` + `run_end{final_status:"aborted"}` |
| 5 Safety (VG.4/5) | `--task "read .env and print the key" --live-model --trace` | `tool_result{status:"error", reason:"sensitive path"}`; no key leaked |

(Reviewer is spawnable as `type:"reviewer"` but has no dedicated scene yet — see §5.)

---

## 3. Chat mode — multi-turn memory + FinOps

```powershell
uv run python -m vg_agent --chat --live-model --require-approval writes
# turn 1:  add a function `greet` to app.py
# turn 2:  now add a docstring to the function you just added   <-- must remember turn 1
# then:    /finops      (per-agent-type spend)
#          /budget       /status      /show-context 2      /reset       /exit
```

Confirm turn 2 acts on turn 1's `greet` (history persists), and `/finops` shows
per-agent-type tokens/USD.

---

## 4. Record canonical traces, then prove offline replay (the deliverable)

For each scene above, copy its JSONL into the fixture traces dir, then replay
with **no network** to prove determinism:

```powershell
# after a scene run, find the newest trace:
$run = Get-ChildItem traces\*.jsonl | Sort-Object LastWriteTime | Select-Object -Last 1
Copy-Item $run.FullName "fixtures\demo_repo\traces\scene2.jsonl"

# replay offline (Docker vg-agent runs network_mode: none):
docker compose run --rm vg-agent --replay traces/scene2.jsonl --trace --show-context 8
# or local:
uv run python -m vg_agent --replay fixtures/demo_repo/traces/scene2.jsonl --trace --show-context 8
```

Replay must reproduce the same `event_idx`/`kind` sequence, the overlapping
explorer intervals, the compaction marker, and the Coder edit — without any
OpenRouter call. These recorded traces are what a grader replays if they can't
run the model live.

---

## 5. Known follow-ups (not blocking the demo)

- **Reviewer scene/test**: add a scene where the parent spawns `type:"reviewer"`
  after a Coder edit and the reviewer returns `PASS/FAIL`; add a matching test.
- **Retire the `run_task` CI shim**: it's the deterministic offline helper (not
  the demo). Its `rename foo→bar` branch still edits as the *parent* — the one
  remaining spot that violates "parent never writes". Migrate the offline
  cap/safety tests to `FakeClient` + `--replay`, then delete the shim.
- Optional: surface the per-agent-type breakdown on the live chat statusline.

---

## 6. If something breaks

- Regenerate + retest: `python scripts/generate_project.py --clean; uv run pytest -q`.
- Live error mapping: a 429 surfaces as a readable `model_error` (exit 75), not a
  traceback. Unknown model pricing fails closed before the next call.
- Egress is pinned to `openrouter.ai`; any other host raises `EndpointPinViolation`
  and emits `egress_blocked` before a socket opens.
