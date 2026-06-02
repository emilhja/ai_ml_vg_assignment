# Curated Trace Evidence

These traces were selected from the recent demo/dry-run evidence instead of
sharing the whole trace history. They were scanned for real provider/API-key
patterns before being copied into `docs/demo/evidence/traces/`.

## Secret scan

Command used before copying:

```powershell
rg -n "sk-or-v1|OPENROUTER_API_KEY=.+|Bearer [A-Za-z0-9._-]+|AKIA[0-9A-Z]{16}|BEGIN (RSA|OPENSSH|PRIVATE) KEY" workspace\traces\a13d4de3f4c8.jsonl workspace\traces\ac27d651d787.jsonl workspace\traces\ead26d58eb1e.jsonl workspace\traces\9ef731cdadf9.jsonl traces\af9b76f58b41.jsonl traces\2af7403dd0db.jsonl traces\fd5540398e10.jsonl traces\b758d5f38d9c.jsonl
```

Result: no matches for real API keys, bearer tokens, AWS access keys, or private
key headers.

Some traces read the fixture repository's `auth/session.py`, which contains the
demo string `fixture-secret`. That is fixture code, not a real provider secret.
Do not show or export `.env`.

## Trace map

| Rubric proof | Curated trace | Key events |
|---|---|---|
| VG.1 parallel sub-agents + integrated result | `evidence/traces/af9b76f58b41.jsonl` | Parent calls `spawn_subagents` with 2 Explorer requests; two `subagent_spawn` rows overlap; two `subagent_return` rows are merged into the final parent answer. `/finops` and chat status count only the `agent_id` entries in that `spawn_subagents` `tool_result` (not later Coder/Reviewer returns in the same turn). Unit test: `test_parallel_finops_batch_lines_ignore_later_spawns_in_turn`. |
| VG.2 parent tool-result compaction | `evidence/traces/af9b76f58b41.jsonl` and `evidence/traces/a13d4de3f4c8.jsonl` | `compaction` rows compact `data/sample.log` from `133300` tokens to short summaries with `compactor_fallback:false`. |
| VG.3 live cost / normal run | `evidence/traces/af9b76f58b41.jsonl` | `run_end` records non-zero `total_cost_usd` and `total_tokens`; model calls include per-agent cost fields. |
| VG.3 soft USD warning | `evidence/traces/ac27d651d787.jsonl` | `budget_event` has `budget_reason:"warn_usd"` and run ends `final_status:"ok"`. |
| VG.3 hard USD cap | `evidence/traces/ead26d58eb1e.jsonl` | `budget_cap` approval is denied, `budget_event` has `budget_reason:"usd_cap"`, `run_end.final_status` is `aborted`, and cost/tokens stay zero. |
| VG.3 post-compaction hard cap | `evidence/traces/9ef731cdadf9.jsonl` | Compaction succeeds, then `usd_cap` is denied and the run aborts. |
| VG.4 sensitive path block | `evidence/traces/2af7403dd0db.jsonl` | `read_file` on `.env` returns `status:"error"` with `sensitive path`. |
| VG.4 approval denial | `evidence/traces/b758d5f38d9c.jsonl` | `approval.decision:"denied"` is followed by `tool_result.status:"error"` and no tool execution result. |
| VG.5 bash execution / bash safety | `evidence/traces/af9b76f58b41.jsonl` and `evidence/traces/fd5540398e10.jsonl` | Explorer uses safe `run_bash`; unsafe `run_bash pytest` is blocked before execution. |
| VG.6 partial file edit | `evidence/traces/fd5540398e10.jsonl` | Coder calls `edit_file` on `tkinter_calc/calculator.py`; approval is recorded before the edit result. |
| VG.7/VG.8 packaging/config | Repo docs, not trace-only | Use `README.md`, `docker-compose.yml`, `config.example.toml`, `.env.example`, and `.gitignore`; `.env` is not evidence. |
| VG.9 autonomy | `evidence/traces/af9b76f58b41.jsonl` and `evidence/traces/b758d5f38d9c.jsonl` | Parent chooses tool calls, sub-agent fan-out, and yields/ends based on model stop reasons rather than a fixed script. |

## Original locations

The curated copies preserve the original JSONL contents from:

- `workspace/traces/a13d4de3f4c8.jsonl`
- `workspace/traces/ac27d651d787.jsonl`
- `workspace/traces/ead26d58eb1e.jsonl`
- `workspace/traces/9ef731cdadf9.jsonl`
- `traces/af9b76f58b41.jsonl`
- `traces/2af7403dd0db.jsonl`
- `traces/fd5540398e10.jsonl`
- `traces/b758d5f38d9c.jsonl`
