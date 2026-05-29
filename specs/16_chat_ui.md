# 16 Chat UI

Interactive `--chat` presentation for TTY terminals. Implementation lives in
generated `chat_ui.py` and is wired from `__main__.py`.

## Scope

Applies only to `--chat` when **both** stdin and stderr are TTYs and
`NO_COLOR` is unset. All other modes (`--task`, `--replay`, piped chat) are
unaffected.

## Layout (top to bottom)

1. **Product label** — `vg-agent` in dim text, left-aligned.
2. **Welcome panel** — Rich `Panel` with thin accent border:
   - Line 1: `* Welcome to VG Agent!` (accent asterisk, bold title).
   - Line 2: italic dim `/help for commands · /status for your current setup`.
   - Line 3: `cwd: {short_cwd}` where `short_cwd` tilde-expands `$HOME`.
3. **Input section** — dim `Rule`, then prompt, then dim `Rule`:
   - Prompt character: `> ` (not `vg>`).
   - Placeholder (empty buffer): `Try "read data/sample.log and summarise auth/"`.
   - Slash-command autocomplete unchanged (`prompt_toolkit` completer).
4. **Status bar** — one line **below** the bottom rule, pipe-separated segments:
   - `📁 {workspace_dir_name}` — basename of workspace root.
   - `🤖 {short_model}` — from latest parent `llm_start` or config default.
   - `{mode}` — `live` or `deterministic`.
   - `ctx {compact} in` — latest parent context token estimate.
   - `🪙 ${running_usd:.4f}/${max_usd:.2f}` — session spend vs cap.
   - `📊 {steps}/{max_steps} steps`.
   - `{status_icon} {status}` — `✓ ready` | `⚠ warn` | `✗ error` from
     `_latest_run_state` and tool-error count.
5. **Hint line** — dim: `/help for commands · /status to refresh session`.
6. **Secondary status** (conditional) — only when `final_status ∉ {ok, ready}`
   or `tool_errors > 0`:
   - `!! {reason} — see progress above` in yellow/cyan accent.

## Refresh rules

| Event | What reprints |
|---|---|
| Session start | Full dashboard (welcome + rules + status bar + hint) |
| After each agent turn | Status bar + hint (+ secondary if needed) |
| `/status` | Full dashboard |
| `/reset`, `/new` | Full dashboard (new `session_id` on `/new`) |
| Before each prompt | Top rule only (avoids flicker); bottom rule + status bar after input |

Idle chat does **not** repeat the compact one-line statusline before every
prompt. That string remains the trace `statusline` event payload during agent
runs only (`specs/60_observability.md`).

## Colors (TTY, `NO_COLOR` unset)

| Element | Rich style |
|---|---|
| Welcome border | `rgb(224,122,95)` |
| Welcome title | bold white |
| Welcome hints | italic dim |
| Product label | dim |
| Rules | dim |
| Status segments | default white; status token green/yellow/red |
| Hint line | dim |
| Progress stream (`[llm]`, `[tool]`) | unchanged from `specs/60_observability.md` |

## Non-TTY fallback

- No Rich panels or rules on stdout/stderr.
- Single line: `VG Agent chat mode. Type /help for commands.`
- Prompt: `> ` via `input()`; readline history when available.
- `/status` prints the compact statusline text plus budget counters (no panel).

## Machine-readable statusline (unchanged)

The compact string from `_format_chat_statusline` remains the trace
`statusline` event payload during agent runs. The TTY status bar is a
**presentation layer** only; it must not change JSONL schema.

## Dependencies

- `rich>=13` for panels, rules, and styled stderr console.
- `prompt-toolkit>=3.0` for prompt, history, autocomplete, placeholder.

## Out of scope

- Git branch / version emoji in status bar (no git integration in v1).
- Plan-mode indicator (`!! plan mode on`).
- Streaming partial assistant text into the input area.
- Vegvisir-style full-width metadata box at startup.
