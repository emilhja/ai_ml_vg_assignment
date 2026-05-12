# 11 Explorer Sub-Agent

Explorer is read-only, depth-limited, and cheaper than the parent.

Contract:

- `MAX_SUBAGENT_DEPTH = 1`.
- Explorer cannot call `spawn_subagent`.
- Explorer returns one string of at most 2 KB.
- Parent context receives only the Explorer return summary, never Explorer
  intermediate `assistant_step`, `tool_call`, or `tool_result` events.
- In live mode the parent may invoke Explorer through `spawn_subagent` with a
  bounded question. Explorer receives read-only tools only and uses
  `EXPLORER_MODEL_ID`.
- Explorer never receives parent-private write tools and cannot invoke
  `spawn_subagent`.

Auth demo behavior:

- Inspect `auth/session.py` and `auth/middleware.py`.
- Summarise token issuing, token validation, session loading, and route guard
  behavior.
