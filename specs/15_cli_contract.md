# 15 CLI Contract

The executable entrypoint is:

```bash
python -m vg_agent
```

Docker services use the same entrypoint through Compose. Local `uv run` is a
developer convenience only; grading commands use `docker compose`.

The agent always runs against the live OpenRouter model and requires
`OPENROUTER_API_KEY`; it exits with code `2` if the key is missing.

## Commands and modes

Exactly one of these modes is required:

- `--task TEXT` — run one task against the current workspace.
- `--chat` — start a multi-turn REPL using one trace/session.
- `--seed-fixture` — write the fixture repository into the current workspace,
  then exit.

## Live chat slash commands

Slash commands are available only inside `--chat`. They are handled locally by
the CLI before any prompt is dispatched to the agent, so they do not consume a
model step.

| Command | Behavior |
|---|---|
| `/exit` | End the chat process cleanly. |
| `/quit` | Alias for `/exit`. |
| `/budget` | Print the current session budget counters (steps, tokens, USD spend, daily remaining USD) and a one-line hint for setting each cap. |
| `/budget …` | Set session caps without resetting counters: `/budget steps N`, `tokens N`, `usd N`, and/or `daily N` (aliases `max_steps`, `max_tokens`, `max_usd`, `daily_remaining`). Multiple pairs may appear on one line. New caps must be at least the current usage where applicable. Emits `budget_event{reason:"user_config"}`. |
| `/status` | Clear and reprint the full session dashboard when Rich TTY UI is active (welcome panel + status bar). Always print on stdout: compact statusline, budget counters, trace path, last `run_end` status, and the latest `model_error` message when present. Set `VG_PROVIDER_ERROR_DETAIL=1` to also record a redacted upstream provider body in the trace (`provider_detail` field). See `specs/16_chat_ui.md`. |
| `/finops` | Print a per-agent-type FinOps table for the session, including input/output/total tokens, model-call count, tool-call count, and USD spend. After the table, print a short **parallel batches** summary when `spawn_subagents` produced overlapping sub-agents (see `specs/60_observability.md`). |
| `/review` | Print a human-readable recap of a completed user turn: prompt, parent tool plan, parallel sub-agent summary, compaction rows, final answer, and trace pointers. `/review` = last turn; `/review N` = turn `N` (1-based `user_prompt` index). |
| `/approvals` | Print the session approval history and any cached reusable approval scopes. |
| `/reset` | Clear cached approval scopes, reset the session budget guard, clear conversation history, and emit a `session_reset` trace event. In TTY Rich chat, also clear the terminal before reprinting the dashboard. |
| `/new` | Start a fresh chat session and trace inside the current REPL process; clear cached approval scopes, reset the budget guard, clear conversation history, and emit a `session_new` trace event in the new trace. In TTY Rich chat, clear the terminal before the welcome dashboard. |
| `/show-context` | Print a **step overview**: per parent step, context message count, tools invoked that step, visible tool-result count, compaction count, and parallel sub-agent notes when `spawn_subagents` ran. |
| `/show-context N` | Print the parent-visible context at parent step `N` as formatted JSON (same as `--show-context N`). |
| `/show-context overview` | Alias for `/show-context` (overview only). |
| `/compact` | Manually fold older in-memory conversation turns via `COMPACTOR_MODEL_ID`; emits `context_compaction{reason:"manual"}`. Recent turns stay verbatim. If folding is unnecessary (too few user turns, or parent context already below the auto-fold threshold), prints a `[context] /compact skipped: …` warning and does **not** call the compactor. |
| `/help` | Print the available slash commands in their compact help form. |

Interactive TTY chat provides arrow-key autocomplete only while the current
input starts with a slash command token, and completions include short command
and parameter help.
Non-TTY chat keeps the newline-driven input path used by scripted demos.

## Interactive chat (TTY)

When stdin and stderr are TTYs and `NO_COLOR` is unset, `--chat` renders a
Claude Code-inspired layout defined in `specs/16_chat_ui.md`:

- Welcome panel with `cwd` on session start; compact chrome after the first turn.
- TTY screen clear before the welcome dashboard on start, `/new`, `/reset`, and
  `/status` (disable with `VG_CHAT_NO_CLEAR=1`; see `specs/16_chat_ui.md`).
- Framed `> ` prompt with a grey task placeholder.
- Bottom status bar (model, parent-visible context, USD, steps, run state) below
  the input; refreshes during agent runs (`… running` while in flight).
- Rich approval panel on stderr when `--require-approval` is not `off` (see
  `specs/16_chat_ui.md`); shortcuts `y`/`n`/`a` alias numbered choices.
- Agent turn answers in a Response panel; directory listings may use a `Tree`.
- No repeating compact statusline before every idle prompt; trace still records
  `statusline` events each parent step.

Piped or scripted chat keeps the plain one-line startup message and `> `
prompt via `input()`.

For direct read-style prompts (`read`, `show`, `cat`, `list`, `pwd`, etc.),
chat prints the parent tool output after the assistant answer when the answer
does not already include it. Failed parent read/inspection tools are printed as
`Tool error (...)` with the tool's refusal/error text, so a refused read does
not collapse into only a final `tool_error` run state.

Literal read output follows `specs/16_chat_ui.md` **File preview** rules: when
the parent `tool_result` was compacted, show the compaction banner instead of
raw file bytes; when the file exceeds `VG_CHAT_FILE_PREVIEW_LINES` (default 30),
show the **last N lines** plus a trace pointer and `read_file_range` hint.

## Flags

| Flag | Default | Behavior |
|---|---:|---|
| `--trace` | off | Print a human-readable trace tree and the JSONL path after the run. |
| `--show-context N` | unset | Print parent-visible context at parent step `N`. |
| `--live-model` | off | Accepted no-op alias (the agent always runs live). Retained for backward compatibility with older docs. |
| `--budget` | off | Print a budget summary (steps/tokens/USD/daily) at run end. |
| `--finops` | off | Print a per-agent-type token/USD FinOps breakdown at run end. |
| `--require-approval off|writes|all` | config/default | Gate tools before execution. |
| `--yes` | off | Auto-approve gated tools and record `approval{decision:"auto"}`. |
| `--no-step-extend-prompt` | off | Disable the proactive “extend step budget?” offer at `max_steps - 1` (hard `step_cap` approval unchanged). |
| `--no-redact` | off | Disable trace redaction and print a warning to stderr. |
| `--max-usd FLOAT` | config/default | Override per-run USD cap. |
| `--max-tokens INT` | config/default | Override per-run token cap. |
| `--parent-model MODEL_ID` | config/default | Override parent model. |
| `--subagent-model MODEL_ID` | config/default | Override all sub-agent models unless type-specific env/config is set. |

## Workspace root

- Default workspace: `./workspace` relative to the process current working directory.
- Override with `VG_WORKSPACE_ROOT` (absolute path or relative to cwd). The dashboard
  uses the same variable; agent and API must agree so JSONL and SQLite land in
  `<workspace_root>/traces/`.
- If the shell cwd is already the workspace directory, set `VG_WORKSPACE_ROOT=.`.

## Streams and exit codes

- Final user-facing answers go to stdout.
- Statusline, approval prompts, warnings, and live progress go to stderr.
- JSONL traces are written to `<workspace_root>/traces/<run_id>.jsonl`.
- The redacted event stream is mirrored to
  `<workspace_root>/traces/vg_agent.sqlite3` for dashboard/statistics queries.
- `0`: successful run, seed, or chat exit.
- `1`: validation/config/tool-policy error.
- `2`: missing live-model secret (`OPENROUTER_API_KEY`).
- `3`: budget, timeout, or user-abort termination.

All runs are live. The single `vg-agent` Compose service has bridged network
access for OpenRouter; the in-process egress pin refuses any non-`openrouter.ai`
host before a socket opens.

## Sub-agent tools

Parent model tool schema exposes both:

- `spawn_subagent(request: SubagentRequest) -> SubagentReturn`
- `spawn_subagents(requests: list[SubagentRequest]) -> list[SubagentReturn]`

`spawn_subagents` is the only parallel primitive. A task with two or more
independent inspection targets must use one `spawn_subagents` call rather
than serial `spawn_subagent` calls.
