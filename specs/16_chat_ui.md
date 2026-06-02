# 16 Chat UI

Interactive `--chat` presentation for TTY terminals. Implementation lives in
generated `chat_ui.py` and is wired from `__main__.py`.

## Scope

Applies only to `--chat` when **both** stdin and stderr are TTYs and
`NO_COLOR` is unset. All other modes (`--task`, piped chat) are
unaffected.

## Layout (top to bottom)

1. **Product label** — `vg-agent` in dim text, left-aligned.
2. **Welcome panel** — Rich `Panel` with thin accent border (full dashboard only):
   - Line 1: `* Welcome to VG Agent!` (accent asterisk, bold title).
   - Line 2: `cwd: {short_cwd}` where `short_cwd` tilde-expands `$HOME`.
   - After the first completed agent turn, the welcome panel is **not** shown
     again until `/status`, `/reset`, or `/new` (compact idle chrome).
3. **Input section** — separated from turn output and session chrome by **two
   blank lines**, then a dim `Rule` titled **`input`**, then prompt, then dim
   `Rule` (no title):
   - Prompt character: `> ` (not `vg>`).
   - Placeholder (empty buffer): `Try "read data/sample.log and summarise auth/"`.
   - Slash-command autocomplete unchanged (`prompt_toolkit` completer).
4. **Status bar** — one line **below** the bottom rule, pipe-separated segments
   built from `SessionStatus` (shared with trace `statusline` events):
   - `📁 {workspace_dir_name}` or `dir:` when `NO_EMOJI` is set.
   - `🤖 {short_model}` or `mdl:` — from latest parent `llm_start` or config default.
   - `{mode}` — always `live` (the agent has a single live runtime path).
   - `ctx {tokens}` or `ctx {tokens}/{window} ({pct}%)` — **parent-visible** context
     for the next parent prompt (`show_context` at the latest step), not session spend.
   - `session … {running}/{max} tok` — **session budget** counter (`BudgetGuard.running_tokens`:
     cumulative tokens across parent, compactor, and sub-agents). Distinct from `ctx`.
   - `⚠️ 🪙 ${running}/${cap}` (or `! usd:` without emoji) — session spend vs cap; **bold red**
     when the next model step is projected to exceed `--max-usd`, **yellow** with the same
     warning icon at the 80% warn threshold (`WARN_USD_FRACTION`). May append
     `(next ~$projected)` when over cap **only if** the parent model id is in
     `PRICING_USD_PER_MTOK`. For unpriced models, append `(unpriced model)` instead
     (no `(next ~$…)` from the unknown-model fallback).
   - `📊 {steps}/{max_steps} steps` — prefix `!` when `steps == max_steps - 1`
     (one step remaining before hard `step_cap`).
   - `{status_icon} {status}` — `✓ ready` | `✓ ok` | `… running` | `⚠ warn` |
     `✗ error` | `✗ partial` (sub-agent failed but parent `run_end` is `ok`).
5. **Hint line** — dim: `/help for commands · /status to refresh session` (once
   per screen; not duplicated in the welcome panel).
   - On first welcome panel only: if any configured role model lacks local pricing,
     add a dim line listing short model ids and `see docs/PRICE.md`.
6. **Secondary status** (conditional):
   - When `final_status ∉ {ok, ready}` or `tool_errors > 0`: `!! {reason} — see
     progress above` in yellow accent.
   - When the latest completed turn had **overlapping** parallel explorers (from
     `subagent_return` intervals): dim `last turn: N parallel explorers (overlap
     confirmed)` (at most one line; no full `/review` dump).

## Refresh rules

| Event | What reprints |
|---|---|
| Session start | Full dashboard (welcome + status bar + hint) |
| After first turn | Compact chrome (label + status bar + hint) on idle prompts |
| During agent run | Status bar refresh (throttled) on progress events; `… running` state |
| After each agent turn | Status bar + hint (+ secondary if needed); `mark_turn_completed()` |
| `/status` | Full dashboard (after screen clear) + `reset_dashboard_mode()`; stdout session summary (statusline, budget, trace, last run) |
| `/reset`, `/new` | Full dashboard (after screen clear); `/new` also `reset_dashboard_mode()` |
| Before each prompt | Two blank lines + top `Rule("input")`; bottom rule + status bar after input (slash commands handled before footer) |

### Screen clear

When Rich TTY UI is active, `clear_chat_screen()` runs **before** the full
dashboard on:

- `--chat` session start
- `/status`, `/reset`, `/new`

It does **not** run during agent turns, after each turn, or for other slash
commands (`/budget`, `/help`, etc.) so in-flight progress and approvals stay
visible.

Implementation: Rich `Console.clear()` on stderr, then optional `\033[3J` for
best-effort scrollback wipe on xterm-compatible terminals (Windows Terminal,
iTerm). Scrollback clearing is not guaranteed on all emulators.

Set `VG_CHAT_NO_CLEAR=1` to disable clearing while keeping Rich UI.

After `/new`, an optional dim line may show the active trace path:
`trace: {short_path}`.

Idle chat does **not** repeat the compact one-line statusline before every
prompt. That string is emitted as trace `statusline` events during agent runs
(`specs/60_observability.md`). Rich TTY chat does **not** also print a `\r`
compact statusline during runs (bottom bar is the live HUD).

## Turn output

After each agent turn (not slash commands), when `use_rich_ui()` is true and
the turn produces a parent answer and/or literal tool outputs:

1. Top dim `Rule` on **stdout**.
2. **Response** — Rich `Panel` when the parent answer is non-empty. When the
   body has **more than one non-empty line**, each line is prefixed with `• `
   unless it already looks like a list item (`- `, `* `, `• `, or `N. `).
   Single-line answers are unchanged. Tool output, Trees, Syntax, diffs, and
   compaction banners are not bulletized.
3. **Tool output** — optional `Panel` with `Tree` for directory listings or
   `Syntax` for multi-line file content; skip a literal block when every line
   already appears in the answer. Large reads use **File preview** (below).
4. **Changes** (conditional) — when the turn includes a successful `edit_file` or
   `write_file` (any agent), a `Changes` panel on **stdout** lists each touched
   path once with a unified diff (see **File-edit diffs** below). Omitted when
   there are no writes in the turn.
5. Bottom dim `Rule` on **stdout**.

The status bar refresh on stderr follows immediately after the framed block.

Non-TTY chat keeps the current plain single-block stdout write with no rules.
Slash-command output is never framed.

## File preview (literal tool output)

When chat echoes parent `read_file` / `read_file_range` results after a turn
(`specs/15_cli_contract.md`):

| Condition | TTY shows |
|-----------|-----------|
| Matching `compaction` for that `tool_use_id` | Compaction banner (`format_compaction_banner`), not raw body |
| Body line count &gt; `VG_CHAT_FILE_PREVIEW_LINES` (default **30**) | Header (path, total lines, bytes, `event_idx`, trace path) + **last N lines** + footer `… M earlier lines (full payload in trace)` and `read_file_range` hint |
| Small files / `run_bash` listings | Existing Tree or full `Syntax` behavior |

## File-edit diffs

Unified-diff presentation for `edit_file` and `write_file`. Diffs are built from
`tool_call.args` in the trace (and, for `write_file`, prior on-disk content read
before the write runs). `tool_result.result_full` stays a short status string.

### Format

- `difflib.unified_diff` hunks; default 3 lines of context per hunk.
- Rich styles when `NO_COLOR` is unset: `-` lines **red**, `+` lines **green**,
  `---` / `+++` / `@@` headers **dim**. Diff content uses a **black** background
  (`Syntax` with `background_color="black"`, same as multi-line `read_file` tool
  output) inside a dim-bordered panel.
- Truncate to **40** diff lines per panel; append a dim footer
  `… N more lines (full edit in trace)` when truncated.
- Non-TTY / `NO_COLOR`: plain `+`/`-` prefixed lines, no Rich styles.

### Surfaces

1. **Approval** (`--require-approval` `writes` or `all`, Rich TTY): below the
   tool summary, show the diff. `edit_file`: `old` → `new` from args.
   `write_file`: prior workspace file content (if any) vs `content` from args.
2. **Live progress** (Rich TTY `--chat`): on successful `tool_result` for
   `edit_file` / `write_file` (any `agent_id`), print a dim-bordered diff panel
   on **stderr** immediately after the `[tool]` line. For `write_file`, capture
   prior content when the matching `tool_call` is emitted (before execution).
3. **End-of-turn Changes** — panel on **stdout** after the Response / tool-output
   block when the turn has at least one successful write/edit; one diff per path
   (last successful change wins if the same path is touched twice).

## Approvals (TTY)

When `--require-approval` is not `off` and `use_rich_ui()` is true:

- Show a cyan-bordered Rich `Panel` on stderr with tool summary, optional diff
  (see **File-edit diffs**), and shortcuts:
  `1/y yes`, `2 yes (scoped)`, `3/a always`, `4/n no`, `5 abort`.
- For `budget_cap` prompts, option `2 yes (this cap)` is cached by the
  `budget_reason` (e.g. `step_cap`, `token_cap`) rather than by a filesystem
  folder path, so the agent won’t re-prompt for the same cap type repeatedly.
- Use `prompt_toolkit` for input when available; otherwise numbered menu on stderr.
- Record `approval` events unchanged; progress stream still logs
  `[approval] decision=…` after the choice.

## Progress stream

- Optional dim header `── turn N ──` at the start of each user dispatch.
- `[agent]` lines indented under the header when grouping is enabled.
- `compaction` and `context_compaction` events may print an extra dim banner
  (`format_compaction_banner`).
- On successful parent `spawn_subagents` `tool_result`, print one **`[parallel]`**
  summary line (overlap yes/no, per-child duration, truncated question snippets)
  derived from `parallel_subagent_summary` in `trace.py`. No new JSONL kinds.
- Successful `edit_file` / `write_file` results may print a diff panel on stderr
  (Rich TTY only; see **File-edit diffs**). No new JSONL event kinds.

## `/review` output

Plain stdout (optional dim Rich sections when TTY). Sections:

1. **Prompt** — user text for the turn.
2. **Parent plan** — parent `assistant_step` tool-call summaries.
3. **Parallel** — overlap, durations, truncated explorer payloads when present.
4. **Context engineering** — for each `compaction` in the turn: `before_tokens ->
   after_tokens`, trace `original_event_idx`, `compactor_model`, `compactor_fallback`,
   and the first ~80 characters of `summary` (ellipsis if longer). For each
   `context_compaction`: `reason`, before/after tokens, and summary snippet.
5. **Answer** — final parent `assistant_text` (truncate above ~2 KB with trace pointer).
6. **Pointers** — JSONL path; suggest `/show-context <step>`.

Complements `/show-context` (machine JSON for graders); does not replace it.

## `/show-context` overview

Bare `/show-context` (or `/show-context overview`) prints a table of **parent
steps** with:

- `ctx` — parent-visible message count at that step (`show_context` length)
- `tools` — tool calls issued **in that step** (from `assistant_step.tool_calls`)
- `results` / `compact` — cumulative tool results and compacted markers visible
- `notes` — tool names; `N parallel sub-agents (overlap yes|no)` when
  `spawn_subagents` ran that step

Use `/show-context N` for the full JSON parent context at step `N`.

## Colors (TTY, `NO_COLOR` unset)

| Element | Rich style |
|---|---|
| Welcome border | `rgb(224,122,95)` |
| Welcome title | bold white |
| Product label | dim |
| Rules | dim |
| Status segments | default white; status token green/yellow/red |
| Hint line | dim |
| Approval panel border | cyan (tool writes); **red** for `budget_cap` |
| Budget-cap approval body | Reason-dispatch via `format_budget_cap_approval_text(reason, details)`: `step_extend` / `step_cap` show steps used/max; `usd_cap` shows cap / spent / step estimate / projected; other caps have short reason-specific copy |
| Diff panel background | black (matches `Syntax` tool output) |
| Diff removals (`-` lines) | red |
| Diff additions (`+` lines) | green |
| Diff headers (`@@`, `---`, `+++`) | dim |
| Progress stream | unchanged from `specs/60_observability.md` |

## Environment

| Variable | Effect |
|---|---|
| `NO_COLOR` | Disable Rich UI (existing). |
| `NO_EMOJI` | ASCII status prefixes (`dir:`, `mdl:`, `usd:`, `stp:`) instead of emoji. |
| `VG_CHAT_NO_CLEAR` | Disable TTY screen clear before dashboard refresh. |
| `VG_CHAT_FILE_PREVIEW_LINES` | Max lines shown for large literal `read_file` bodies (default `30`). |

## Non-TTY fallback

- No Rich panels or rules on stdout/stderr.
- Single line: `VG Agent chat mode. Type /help for commands.`
- Prompt: `> ` via `input()`; readline history when available.
- `/status` prints the compact statusline text, budget counters, trace path, and
  last run status on stdout (no Rich panel).
- During agent runs, one compact statusline per parent step (newline-terminated).

## Machine-readable statusline

`build_session_status` + `format_statusline_compact` produce the trace
`statusline` event `text` field and structured counters (`ctx_tokens`,
`steps`, `running_tokens`, etc.). The TTY status bar is a **presentation layer**
only; JSONL schema additions are limited to optional fields on `statusline` events.

## Dependencies

- `rich>=13` for panels, rules, tree, syntax, and styled stderr console.
- `prompt-toolkit>=3.0` for prompt, history, autocomplete, placeholder, approvals.

## Out of scope

- Git branch / version emoji in status bar.
- Plan-mode indicator.
- Streaming partial assistant text into the input area.
- Vegvisir-style full-width metadata box at startup.
