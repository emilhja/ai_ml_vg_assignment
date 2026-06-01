# Demo dry-run notes (2026-06-01)

Live dry-run against `OPENROUTER_API_KEY` in `.env`. Use these values during
the exam so you do not guess `/show-context N` on the day.

## Primary parallel + compaction run (Prompt 3 / Scene 2)

**Command:**

```powershell
uv run python -m vg_agent --task "read data/sample.log, then summarise auth/ and utils.py in parallel" `
  --trace --finops --require-approval writes --yes
```

**Trace:** `workspace/traces/a13d4de3f4c8.jsonl`

| Record | Value |
|--------|--------|
| Parent read + compaction | `133300 -> 108` tokens (event 7) |
| `compactor_model` | `openrouter/google/gemini-2.5-flash-lite` |
| `compactor_fallback` | **false** (live compactor, not stub) |
| Parallel sub-agents | `spawn_subagents` × 2 Explorers |
| Overlap | **yes** (`/finops`: "overlapping wall-clock") |
| Compactor FinOps row | yes (`0.006620` USD in sample run) |
| Final status | `ok` (hit `token_cap` extend via auto approval) |

### `/show-context` step **N**

From `show_context_overview` on this trace:

| step | compact | notes |
|------|---------|--------|
| **1** | 1 | First parent step after log read + compaction — **use for Prompt 4** |
| 3 | 1 | After parallel `spawn_subagents` |
| 7 | 1 | After `run_bash ls auth/` |
| 8 | 1 | After three `read_file` on auth |
| 9 | 1 | Final parent step |

**Recommended Prompt 4 command:** `/show-context 1` (or `/show-context 9` for final context).

**Verify at step 1:**

- `[COMPACTED tool_result for tool_use_id=…]` present
- Raw `req-00001` log lines **absent**
- Explorer intermediate `tool_call` / `tool_result` **absent** at step 1 (only appear after step 3 spawn)

### Prompt 3b fallback

**Not needed** for this dry-run: parent read `data/sample.log` directly and
compactor fired before parallel spawn. If a future run routes the log through
Explorer only, run Prompt 3b from
[final_demo_live_chat_script.md](final_demo_live_chat_script.md) before Prompt 4.

---

## VG.3 — `warn_usd` (Scene 4)

**Command:**

```powershell
uv run python -m vg_agent --task "read data/sample.log and summarize the log pattern in one sentence" `
  --max-usd 0.008 --trace --require-approval off
```

**Trace:** `workspace/traces/ac27d651d787.jsonl`

| Signal | Present |
|--------|---------|
| `[budget] warn_usd` on stdout | yes |
| `budget_event{reason:"warn_usd"}` in JSONL | yes (event before `run_end ok`) |
| `budget_event{reason:"warn_tokens"}` | yes (large log read) |
| Hard abort on same cap | use Prompt 8 below |

**Note:** With `--max-usd 0.007` the run aborts with `usd_cap` (exit **3**) after
compaction when cap extension is denied — trace `9ef731cdadf9.jsonl`. Show **both**:
warn run (`0.008`) then hard abort (`0.007` or Prompt 8).

---

## VG.3 — hard cap abort (Prompt 8)

**Command:**

```powershell
uv run python -m vg_agent --task "read data/sample.log" --max-usd 0.0001 --require-approval off --trace
```

**Trace:** `workspace/traces/ead26d58eb1e.jsonl`

| Signal | Value |
|--------|--------|
| Exit code | **3** |
| `budget_event` | `usd_cap` |
| `run_end.final_status` | `aborted` |
| Model call made | no (preflight block) |

---

## Docker parity

Repeat the primary scene through Compose before the exam if grading is Docker-only:

```powershell
docker compose build
docker compose run --rm vg-agent --seed-fixture
docker compose run --rm vg-agent --task "read data/sample.log, then summarise auth/ and utils.py in parallel" --trace --finops
```

Record the new trace path if step **N** differs from local `uv run`.

---

## Known environment quirks (Windows)

- Scene 4 parallel task with `--max-usd 0.02` may hit `bash` timeout on
  `ls auth` inside Explorer on some Windows Git Bash setups. Prefer the simpler
  one-sentence summarize task above for `warn_usd` / `usd_cap` proof.
- Unicode in model answers can raise `UnicodeEncodeError` on cp1252 consoles;
  the trace and budget events are still written. Use Docker or `$OutputEncoding`
  if stdout garbles.
