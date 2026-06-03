# 17 Rich TUI stack

Reference for libraries, modules, and activation rules behind the interactive
`--chat` terminal UI. **Behavior and layout** live in `specs/16_chat_ui.md`; this
spec is the technology map for contributors extending presentation.

## Scope

- Applies to **TTY `--chat`** presentation only.
- Does **not** cover the web dashboard (`specs/70_dashboard.md`, optional
  `dashboard` extra in `pyproject.toml`).
- Does **not** cover `--task`, piped chat, or JSONL trace schema.

## Primary dependencies

Declared in `pyproject.toml` `[project] dependencies`:

| Package | Constraint | Role |
|---------|------------|------|
| [Rich](https://github.com/Textualize/rich) | `rich>=13` | Panels, tables, Markdown, syntax highlighting, rules, trees, styled console output |
| [prompt-toolkit](https://github.com/prompt-toolkit/python-prompt-toolkit) | `prompt-toolkit>=3.0` | Chat REPL: `> ` prompt, file history, slash-command autocomplete, placeholder |

No Textual, urwid, curses, or blessed layer — Rich renders into a normal terminal
via **stdout** and **stderr**.

### Optional / unrelated to chat TUI

| Package | Where | Notes |
|---------|-------|-------|
| `litellm` | Core agent | Model API only; not terminal UI |
| `fastapi`, `uvicorn`, … | `[project.optional-dependencies] dashboard` | HTTP dashboard, separate from Rich chat |

## Implementation map

| Area | Module | Notes |
|------|--------|-------|
| Rich presentation | `src/vg_agent/chat_ui.py` | Hand-written; preserved across `generate_project.py --clean` (`EXTRA_SOURCE_GENERATED_FILES`) |
| Chat loop, progress sink, slash wiring | `src/vg_agent/__main__.py` | Generated from `scripts/templates/__main__.py.tmpl` |
| `/review` section data | `src/vg_agent/trace.py` | `build_turn_review_sections`, `format_turn_review`; rendering in `chat_ui.print_turn_review` |

## Rich components in use

Imports are lazy (inside functions) unless noted.

| Rich API | Used for |
|----------|----------|
| `Console` | stdout: turn output, `/finops`, `/show-context overview`; stderr: dashboard, approvals |
| `Panel` | Welcome, Response, approvals, file preview, diff hunks |
| `Markdown` | Turn **Response** and `/review` **Answer** (`render_rich_answer`) |
| `Table` | `/finops` agent-type spend; `/show-context` overview |
| `Rule` | Input section separators (`input` titled rule + bottom rule) |
| `Syntax` | Multi-line file bodies and unified diffs (`background_color="black"`) |
| `Tree` | Directory listings (`find` / `ls`-style tool output) |
| `Text`, `Group` | Approval panel body (budget-cap copy, diff + shortcut lines) |

### prompt-toolkit

Used from `__main__.py` when `use_rich_ui()` is true:

- `PromptSession` with `FileHistory`
- `Completer` / `Completion` for slash commands
- `Style` for dim prompt
- Placeholder: `CHAT_PLACEHOLDER` from `chat_ui.py`

Approvals read the user choice with `input()` / readline **after** the Rich panel
(no nested `PromptSession` per approval).

## Stdlib and non-Rich terminal output

| Mechanism | Where | Role |
|-----------|-------|------|
| `difflib.unified_diff` | `chat_ui.py` | Build diff hunks; Rich `Syntax` displays them |
| ANSI escape codes | `__main__.py` (`_ANSI_*`) | Compact **progress** stream: `[llm]`, `[tool]`, `[parallel]`, turn headers — colored lines, not Rich widgets |
| `threading.RLock` | `chat_ui.progress_stderr_lock` | Serialize stderr progress + approval panels |
| `readline` / `input()` | Non-TTY fallback; approval choice | Plain chat and post-panel approval input |

Low-priority follow-ups to move more progress chrome into Rich are listed in
`docs/TODO.md` (Rich TTY chat — low-priority polish).

## Activation

Rich chat UI is enabled when `chat_ui.use_rich_ui()` returns true:

1. Mode is `--chat` (wired from `__main__.py`).
2. **stdin and stderr** are TTYs, **or** Rich was **latched** at session start
   (`latch_rich_chat_session()` — approvals can stay Rich if stderr stops
   reporting TTY mid-run).
3. Environment variable **`NO_COLOR`** is unset.

Otherwise: plain `input()`, ASCII tables, no panels (`specs/16_chat_ui.md` Non-TTY
fallback).

## Environment variables (presentation)

| Variable | Effect |
|----------|--------|
| `NO_COLOR` | Disable Rich UI and ANSI styling |
| `NO_EMOJI` | ASCII status prefixes (`dir:`, `mdl:`, …) instead of emoji |
| `VG_CHAT_NO_CLEAR` | Keep Rich UI but disable screen clear before dashboard |
| `VG_CHAT_VERBOSE_PROGRESS` | `1` = full progress log in Rich TTY chat (default: compact) |
| `VG_CHAT_FILE_PREVIEW_LINES` | Max lines for large `read_file` tail preview (default `30`) |
| `VG_CHAT_STATUS_THROTTLE_S` | Min seconds between status-bar redraws while running (default `0.75`) |

## stdout vs stderr split

| Stream | Typical content |
|--------|-----------------|
| **stdout** | User-facing turn output: Response Markdown, tool literal panels, Changes diffs, `/finops`, `/show-context overview`, `/review` (Rich path), slash-command tables |
| **stderr** | Session chrome: welcome panel, status bar, input rules, approvals, compact progress lines, inline edit diffs during progress |

Machine-readable trace `statusline` events are separate from this split
(`specs/60_observability.md`).

## Plain vs Rich by surface

| Surface | Rich TTY | Non-TTY / `NO_COLOR` |
|---------|----------|----------------------|
| Dashboard, status bar, input rules | Yes | No |
| Turn Response / `/review` Answer | Markdown (+ panel when multi-line) | `format_response_bullets` / plain text |
| End-of-turn Changes | `Syntax` panels | Plain `+`/`-` lines |
| `/finops`, `/show-context overview` | `Table` | Fixed-width ASCII |
| `/show-context N` | Always plain JSON | Same |
| Progress during run | ANSI log lines (compact default) | Same structure, optional color |
| `--task` | Not used | Plain CLI |

## Extension checklist

When adding new TTY presentation:

1. Update **`specs/16_chat_ui.md`** (behavior) and this file if new libraries or Rich APIs are introduced.
2. Implement in **`chat_ui.py`** when possible (hand-written, survives regenerate).
3. Wire slash commands or progress in **`scripts/templates/__main__.py.tmpl`**, then
   `python scripts/generate_project.py --clean`.
4. Add tests in `tests/test_vg_agent.py` with `monkeypatch.setattr(chat_ui, "use_rich_ui", lambda: True)` and `io.StringIO` on stdout/stderr as appropriate.
5. Do not add network calls in UI tests.

## Related specs

- `specs/02_tech_stack.md` — full repository technology inventory
- `specs/01_architecture.md` — product architecture and module map
- `specs/16_chat_ui.md` — layout, refresh rules, colors, slash output
- `specs/15_cli_contract.md` — slash commands and chat entry
- `specs/60_observability.md` — progress stream vs trace JSONL
- `docs/TODO.md` — low-priority Rich progress polish backlog

## Out of scope (terminal)

- Full-screen TUIs (Textual apps)
- Streaming partial assistant tokens into the prompt area
- Rich rendering for `--task` or CI log parsers
- Web dashboard component library (React in `dashboard/web/`)
