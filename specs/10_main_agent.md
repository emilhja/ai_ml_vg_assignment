# 10 Main Agent

The parent owns the user conversation, tool execution, compaction, trace
writing, and final answer.

Tools:

- `read_file`
- `read_file_range`
- `write_file`
- `edit_file`
- `run_bash`
- `spawn_subagent`

Deterministic demo routes:

- Rename route: read `app.py`, replace `foo` with `bar`, write the result.
- Auth route: read `data/sample.log`, compact the parent tool result when it
  exceeds `K_COMPACT`, spawn Explorer to inspect `auth/`, and return a concise
  auth summary.
- Cost route: repeat the sentinel search until the repetition/step guard emits
  `budget_event` and `run_end(final_status="aborted")`.

Live route:

- Extension path enabled only by `--live-model`; deterministic routes remain
  the default and the required presentation path.
- Requires `ANTHROPIC_API_KEY`.
- Sends the parent system prompt, task, and compacted parent context to
  Anthropic using `PARENT_MODEL_ID`.
- Executes model-requested tool calls, appends assistant/tool events to JSONL,
  and sends only parent-visible results back into the next model turn.
- Stops on final assistant text, budget abort, step cap, token/cost cap,
  timeout, or tool error policy.
- Parent tool results larger than `K_COMPACT` are compacted before the next
  parent model turn. The full result remains in trace.
