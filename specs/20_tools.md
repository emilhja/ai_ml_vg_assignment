# 20 Tools

Tool schemas are stable, traceable, and Windows-aware.

Common result fields:

- `tool_use_id`
- `tool`
- `result_full`
- `bytes`
- `tokens`
- `latency_ms`
- `status`

Windows/Git Bash rules:

- `run_bash` invokes `bash -c`.
- `run_bash` is deny-by-default for command families that can mutate or
  destroy the workspace. It accepts only simple read-only inspection commands
  such as `grep`, `rg`, `find`, `ls`, `pwd`, `cat`, `sed`, `head`, `tail`, and
  `wc`.
- `run_bash` rejects shell control operators and redirection (`;`, `&&`, `||`,
  pipes, `>`, `<`, backticks, and command substitution) so a safe-looking first
  command cannot hide a destructive second command.
- `run_bash` rejects destructive tokens anywhere in the parsed command,
  including `rm`, `del`, `erase`, `rmdir`, `Remove-Item`, `mv`, `move`, `cp`,
  `copy`, `chmod`, `chown`, `mkfs`, `dd`, and package install commands.
- Rejected commands are returned as `tool_result.status = "error"` with a
  refusal message. They are not passed to `bash -c`.
- The safety gate is intentionally conservative. If a demo needs a command not
  on the allowlist, add it to the spec first, regenerate code, and add a test
  proving why it is read-only.
- Normalize Windows and Git Bash paths at tool boundaries.
- All file tools must resolve requested paths under the workspace root before
  reading or writing. Absolute paths and `..` traversal outside the root are
  refused as traceable tool errors.
- Write text files with `\n`.
- Use `read_file_range` for targeted follow-up after compaction.
