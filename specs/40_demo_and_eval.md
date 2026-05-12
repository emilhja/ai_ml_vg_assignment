# 40 Demo And Eval

Fixture layout:

- `app.py`
- `auth/__init__.py`
- `auth/session.py`
- `auth/middleware.py`
- `utils.py`
- `README.md`
- `data/sample.log`

The sample log is deterministic and larger than 200 KB so the parent
`read_file data/sample.log` result exceeds `K_COMPACT`.

VG slide assertions:

- At least one parent `tool_result` exceeds `K_COMPACT`.
- A parent-scoped `compaction` event exists for that `tool_use_id`.
- `compaction.original_event_idx` points to the original event.
- `compaction.original_sha256` equals SHA-256 of the original
  `tool_result.result_full`.
- `--show-context <last_step>` contains the compacted marker.
- `--show-context <last_step>` does not contain original `sample.log` content.
- Parent context contains only Explorer return summary, not Explorer
  intermediate tool calls or tool results.

Extension live-mode test assertions:

- `--live-model` without `ANTHROPIC_API_KEY` exits non-zero with a clear error.
- A fake parent client can request a read and edit against a temp fixture.
- A fake parent client can spawn Explorer and parent context contains only the
  Explorer summary.
- A fake client can force a live budget abort before any network call.
- Live parent tool results above `K_COMPACT` are compacted before the next
  model turn.

Provenance assertions:

- Generated runtime code, tests, fixtures, and demo scripts can be reproduced
  from markdown specs, prompt/config markdown, or generated-code templates.
- The demo explains which files are generated and how their source markdown is
  checked.
