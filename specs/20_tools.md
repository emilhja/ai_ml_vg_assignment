# 20 Tools

Tool schemas are stable, traceable, and Windows-aware. Detailed authoring
guidance for the safety rules below — *why* each token or pattern is rejected —
lives in `docs/dev/dangerous_cli.md`.

Common result fields:

- `tool_use_id`
- `tool`
- `result_full`
- `bytes`
- `tokens`
- `latency_ms`
- `status`

Tool semantics:

- `read_file(path)` — returns the entire UTF-8 content of `path` under the
  workspace root.
- `read_file_range(path, start_line, end_line)` — returns lines
  `start_line..end_line` (1-indexed, inclusive) of `path`. Used for
  targeted follow-up after compaction.
- `write_file(path, content)` — **whole-file overwrite or create**. Creates
  parent directories as needed. Used only when no prior content exists
  worth preserving.
- `edit_file(path, old_string, new_string)` — **partial / find-and-replace
  edit** (the `str_replace` equivalent). `old_string` must appear in the
  file **exactly once**; the runtime returns `tool_result.status="error"`
  with reason `"not_found"` if it is absent and `"ambiguous"` if it
  matches more than once. Indentation, newlines, and trailing whitespace
  must match byte-for-byte. The file's other content is untouched. This
  is the canonical partial-edit operation for VG.6 and the operation
  Coder is instructed to prefer (`PROMPTS.md`).
- `run_bash(command)` — see Windows/Git Bash rules below.
- `run_tests(path)` — run pytest on a workspace-relative test file or
  directory. See `run_tests` rules below. Parent and Coder only; not
  Explorer or Reviewer.

`run_tests` rules:

- `run_tests(path)` invokes a fixed subprocess:
  `[sys.executable, "-m", "pytest", <resolved_path>, "-q", "--tb=short"]`
  with `cwd` set to the workspace root. No shell, no user-supplied flags,
  no `-c`, no plugins configuration from the model.
- `path` must resolve under the workspace root (same rules as file tools:
  no absolute paths, no `..` traversal, no sensitive paths).
- `path` must exist and match `**/test_*.py`, `**/tests/**`, or be a
  directory containing tests. Reject arbitrary non-test paths.
- Exit code 0 → `tool_result.status = "ok"`; non-zero → `status = "error"`.
  stdout/stderr are captured and truncated to `MAX_TOOL_RESULT_BYTES`.
- Timeout: `TOOL_TIMEOUT` seconds (same as other tools).
- Use `run_tests` for pytest verification. Do **not** call `run_bash` with
  `pytest`, `python -m pytest`, or `python -c`.

Windows/Git Bash rules:

- `run_bash` invokes `bash -c`.
- `run_bash` is deny-by-default for command families that can mutate or
  destroy the workspace. It accepts simple read-only inspection commands:
  `grep`, `rg`, `find`, `ls`, `pwd`, `cat`, `head`, `tail`, and `wc`. `sed` is
  intentionally excluded because `sed -i` mutates files in place.
- One narrow Python exception is allowed for syntax checks only:
  `python3 -m py_compile <relative .py path> [<relative .py path> ...]` where
  each path is workspace-relative. At most **8** targets per command. No
  additional flags, no absolute paths, no traversal, no non-`.py` paths.
- `run_bash` also accepts narrowly scoped workspace mutations:
  - `mkdir [-p] <dir> [<dir> ...]` — creates directories only under the
    workspace root. Only the `-p` flag is allowed. Targets must be relative,
    must not use globs or `..` traversal, and must not name sensitive paths.
    When every target already exists as a directory, `run_bash` returns `ok`
    with `mkdir: directory already exists: …` instead of shelling out (plain
    `mkdir` without `-p` would otherwise fail with "File exists").
  - `rm <file>` — deletes exactly one existing regular file under the workspace
    root (no flags, no directories, no globs). See runtime validation in
    `validate_shell_command` / `validate_shell_command_for_workspace`.
- `run_bash` rejects shell control operators and redirection (`;`, `&&`, `||`,
  pipes, `>`, `<`, backticks, and command substitution) so a safe-looking first
  command cannot hide a destructive second command.
- `run_bash` rejects destructive tokens anywhere in the parsed command,
  including `del`, `erase`, `rmdir`, `Remove-Item`, `mv`, `move`, `cp`,
  `copy`, `chmod`, `chown`, `mkfs`, `dd`, package installers (`pip`, `npm`,
  `pnpm`, `yarn`, `uv`), foreign code runners (`python`, `powershell`, `pwsh`,
  `cmd`) except for the narrow `python3 -m py_compile <relative .py> [...]` form,
  and any egress utility (`curl`, `wget`, `nc`, `ncat`, `netcat`, `ssh`, `scp`,
  `sftp`, `rsync`, `ftp`, `telnet`, `socat`, `git`).
- `run_bash` rejects forbidden argument tokens anywhere in the parsed
  arguments: `-exec`, `-execdir`, `-delete`, `-ok`, `-okdir`, `-fprint`,
  `-fprintf`, `-fls`, and any token starting with `--exec`. This blocks
  `find . -exec rm {} \;`, `find . -delete`, and any future tool that grows a
  shell-out flag.
- Rejected commands are returned as `tool_result.status = "error"` with a
  refusal message. They are not passed to `bash -c`.
- The safety gate is intentionally conservative. If a demo needs a command not
  on the allowlist, add it to the spec first, regenerate code, and add a test
  proving it cannot mutate the workspace under any flag combination.
- Use safe single-command forms instead of pipelines. For example, top-level
  folders should be listed with `find . -maxdepth 1 -type d`, not
  `ls -l | grep '^d'`.
- Normalize Windows and Git Bash paths at tool boundaries.

Sensitive-path denylist (applies to `read_file`, `read_file_range`,
`write_file`, `edit_file` *before* path resolution):

- `(^|/)\.env($|\.)` matches `.env` and `.env.local` but **not**
  `.env.example`, which is allowed so the agent can learn the schema without
  the secret values.
- `(^|/)id_rsa(\..*)?$` and `(^|/)id_ed25519(\..*)?$` — SSH private keys.
- `\.pem$`, `\.key$`, `\.pfx$`, `\.p12$` — TLS / signing keys.
- `(^|/)\.aws/`, `(^|/)\.ssh/` — credential directories.
- `(^|/)\.netrc$`, `(^|/)credentials(\.json)?$` — common credential files.

Rejected reads/writes return `tool_result.status = "error"` with a message
starting with `"sensitive path:"`, a short explanation, and a path-specific
hint (for example `.env` → use `.env.example`). The filesystem is never touched.

Tool-result size cap:

- `MAX_TOOL_RESULT_BYTES = 1_048_576` (1 MiB).
- Tool results above the cap are truncated in the value returned to the
  parent model and appended with a marker that points to the full content in
  the JSONL trace (`run_id`, `event_idx`). Truncation is recorded as a
  `tool_result` field (`truncated: true`) so the trace shows what the model saw.

Path-resolution rules:

- All file tools resolve requested paths under the workspace root before
  reading or writing. Absolute paths and `..` traversal outside the root are
  refused as traceable tool errors.
- Write text files with `\n`.
- Use `read_file_range` for targeted follow-up after compaction.

Approval policy (see `specs/10_main_agent.md` and `specs/30_runtime_governance.md`):

- Tools are grouped into approval categories: `reads` (`read_file`,
  `read_file_range`, `run_bash`) and `writes` (`write_file`, `edit_file`,
  `run_tests`, `run_bash` when it would mutate — not currently reachable, but
  `spawn_subagent` and `spawn_subagents` are also gated because they consume
  budget).
- The runtime exposes `--require-approval [off|writes|all]` and `--yes`.
  Default is `off` so the unit tests stay reproducible;
  `writes` is the recommended live setting.
