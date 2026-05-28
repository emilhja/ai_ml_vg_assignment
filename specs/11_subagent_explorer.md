# 11 Explorer Sub-Agent

Explorer is one of four typed sub-agents. Orchestration (sequential and
parallel), failure modes, and the full type table live in
`specs/12_subagent_pipeline.md`. This file specifies only the Explorer type.

Contract:

- Read-only. Tools: `read_file`, `read_file_range`, `run_bash` (the
  read-only allowlist from `specs/20_tools.md`).
- `MAX_SUBAGENT_DEPTH = 1`. Explorer cannot call `spawn_subagent` or
  `spawn_subagents`.
- Returns one string of at most 2 KB as `subagent_return.payload`.
- Uses `EXPLORER_MODEL_ID` (`MODEL_CONFIG.md`).
- Parent context receives only the return summary. Intermediate
  `assistant_step`, `tool_call`, and `tool_result` events stay in the JSONL
  trace under Explorer's `agent_id` and are filtered out of `show_context`.

Auth demo behavior (Scene 2, `specs/70_demo_runbook.md`):

- One Explorer inspects `auth/session.py` and `auth/middleware.py` and
  summarises token issuing, token validation, session loading, and route
  guard behavior.
- A second Explorer, spawned in parallel, summarises `utils.py`.
- The parent's next `assistant_step` integrates both summaries.
