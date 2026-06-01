# Plan: arrow-key history for chat mode

## Context

Running:

```
docker compose run --rm -it vg-agent-live --chat --live-model --require-approval writes
```

drops the user into a REPL where prompts are read with `sys.stdin.readline()` (`src/vg_agent/__main__.py:188`). That call bypasses GNU readline's line-editor, so arrow-up / arrow-down do nothing (you just see `^[[A` / `^[[B`). The user wants standard shell-style history navigation across turns within a session, and ideally persisted across container runs.

The Docker base image is `python:3.12-slim` (Linux), so Python's built-in `readline` module is available with no new dependency. The `./workspace` volume is already mounted into the container (`docker-compose.yml:7,24`), so a history file written there persists across `--rm` runs.

## Approach

Switch the chat loop's input call from `sys.stdin.readline()` to `input()` and import `readline`, which automatically engages line editing + arrow-key history. Persist history to `<root>/.vg_chat_history` so it survives container restarts. Leave the approval prompt (`_stdin_prompt`, `src/vg_agent/__main__.py:27`) untouched — single-digit yes/no answers shouldn't pollute prompt history.

Per `CLAUDE.md`, the runtime tree is generated; all edits go to the template inside `scripts/generate_project.py`, then we regenerate.

## Files to modify

**`scripts/generate_project.py`** — the `"__main__.py": '''...'''` template block:

1. **Top of template** (just after `import sys`): add a guarded readline import.

   ```python
   try:
       import readline  # GNU readline: enables arrow-key history in input()
   except ImportError:
       readline = None  # Windows host without pyreadline; chat mode requires a TTY anyway
   ```

2. **`_chat_loop` (template lines 1955–2009)** — replace the prompt-write + `sys.stdin.readline()` block with `input("vg> ")`, and load/save history around the loop:

   ```python
   def _chat_loop(root: Path, args: argparse.Namespace) -> int:
       recorder = TraceRecorder(root, redact=not args.no_redact, event_sink=_make_progress_sink())
       policy = _make_policy(args)
       guard = BudgetGuard.for_workspace(root)
       history_path = root / ".vg_chat_history"
       if readline is not None:
           readline.set_history_length(1000)
           try:
               readline.read_history_file(str(history_path))
           except OSError:
               pass  # first run, or file unreadable — start fresh
       sys.stderr.write("VG Agent chat mode. Type /help for commands.\n")
       try:
           while True:
               try:
                   prompt = input("vg> ").strip()
               except KeyboardInterrupt:
                   recorder.emit("budget_event", budget_reason="user_abort", details={})
                   sys.stderr.write("\n")
                   break
               except EOFError:
                   break
               if not prompt:
                   continue
               # ... rest of slash-command handling and run dispatch unchanged ...
       finally:
           if readline is not None:
               try:
                   readline.write_history_file(str(history_path))
               except OSError:
                   pass
       return 0
   ```

   Note the small behavioural changes vs. today:
   - The `vg> ` prompt now goes to **stdout** (via `input()`) instead of stderr. Acceptable: chat mode requires a TTY; users piping output already need `--task` instead.
   - `EOFError` (Ctrl-D / empty stdin) replaces the old "empty line means EOF" check, which is what `input()` raises natively.
   - History is flushed in a `finally` so `/exit`, Ctrl-C, and EOF all persist.

3. **No changes** to `_stdin_prompt` (approval callback, template lines 1796–1828). Keep `fh.readline()` there — single-character answers don't need history.

## Regenerate + verify

```powershell
python scripts/generate_project.py --clean
uv run pytest
```

Then end-to-end:

```powershell
docker compose build
docker compose run --rm -it vg-agent-live --chat --live-model --require-approval writes
# At the vg> prompt:
#   1. type "hello", Enter
#   2. type "/help", Enter
#   3. press Up-arrow twice — should recall "hello"
#   4. press Down-arrow — should move forward to "/help"
#   5. /exit
# Re-run the same `docker compose run ...` command:
#   6. press Up-arrow — should still recall "/help" from the prior session
#      (proves <workspace>/.vg_chat_history persisted via the volume mount)
```

Also confirm the approval flow still works: trigger a `write_file` and verify the `[approval]  1) yes ...` prompt accepts a digit (it should — that path is unchanged).

## Out of scope

- `prompt_toolkit` (richer features like multi-line editing, autocompletion) — would add a dependency; not needed for the requested arrow-key recall.
- Sharing history with the approval prompt — intentionally kept separate.
- Windows host (non-Docker) — `readline` is guarded so import failure is silent; arrow keys won't work there, but the requested invocation runs inside the Linux container.
