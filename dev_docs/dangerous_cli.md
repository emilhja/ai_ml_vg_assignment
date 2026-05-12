# Dangerous CLI — authoring guide

This document is the *why* for the safety rules in `specs/20_tools.md` and
`specs/30_runtime_governance.md`. Read it before you add a command to the
allowlist, relax a denylist pattern, or argue that "we can trust the model
to use `find` safely". The short answer is: we can't, and the rules below
exist because every one of them has been used to escape a "harmless" coding
agent in the wild.

## 1. Purpose — two layers, not one

VG Agent uses **two** independent safety layers for tool execution:

1. **Deny-list** — fast, deterministic, immune to operator fatigue.
   Implemented in `validate_shell_command` (`tools.py`) and
   `validate_sensitive_path`. Wires into every `run_bash`, `read_file`,
   `read_file_range`, `write_file`, and `edit_file` call.
2. **Approval gate** — `ApprovalPolicy` (`agent.py`). Catches the long tail:
   a `write_file` to `app.py` is legitimate, but the operator should see it.

Either layer alone fails. Deny-only blocks legitimate edits. Approval-only
trusts a tired demo operator. Together they're the same pattern Claude Code
itself uses.

## 2. Command taxonomy

### Always-denied command tokens (with rationale by family)

| Family | Tokens | Why |
| --- | --- | --- |
| Mutation | `rm`, `del`, `erase`, `rmdir`, `Remove-Item`, `ri`, `rd`, `mv`, `move`, `cp`, `copy`, `dd` | Direct workspace mutation. |
| Privilege | `chmod`, `chown`, `mkfs` | Privilege change / filesystem damage. |
| Egress | `curl`, `wget`, `nc`, `ncat`, `netcat`, `ssh`, `scp`, `sftp`, `rsync`, `ftp`, `telnet`, `socat` | Data exfiltration channels. |
| Code | `pip`, `npm`, `pnpm`, `yarn`, `uv`, `python`, `powershell`, `pwsh`, `cmd` | Arbitrary code execution / dependency tampering. |
| VCS | `git` | History rewriting, push, hook execution. |

### Always-denied argument tokens

| Token | Why |
| --- | --- |
| `-exec`, `-execdir`, `-ok`, `-okdir` | `find` shells out to arbitrary commands. Looks read-only; isn't. |
| `-delete` | `find . -delete` is `rm -rf` with a friendlier name. |
| `-fprint`, `-fprintf`, `-fls` | `find` writes to arbitrary filesystem paths. |
| Anything starting with `--exec` | Future-proof against `--exec=…` variants. |

### Look-safe-but-aren't

- `sed -i` — in-place mutation. `sed` is excluded from the allowlist entirely
  so this can't be reached by argument trickery.
- `cat > foo` — redirection is already blocked at the shell-control gate.
- `grep -f /dev/stdin <<< …` — heredoc is blocked at the shell-control gate.
- `tail -f` — unbounded I/O; would block the tool timeout but waste budget.

### Allowed read-only commands

`grep`, `rg`, `find`, `ls`, `pwd`, `cat`, `head`, `tail`, `wc`. They remain
read-only because:

- No redirection (`>`, `<`), pipes (`|`), command separators (`;`, `&&`,
  `||`), backticks, or `$(…)` substitution is permitted in the command
  string.
- Each command is tokenized with `shlex` and every token is checked against
  the denylists.
- File-path tokens are checked for absolute paths and `..` traversal.

## 3. Egress channels

VG Agent has exactly two egress channels:

1. **`run_bash`** — covered by the command deny-list above. Any tool that
   could open a socket is rejected.
2. **Anthropic Messages client** — `anthropic_client.py` parses
   `self.endpoint` with `urllib.parse.urlparse` and refuses to open if
   `host != ANTHROPIC_ENDPOINT_HOST`. Raises `EndpointPinViolation` *before*
   the socket opens.

`--network none` in Docker is incompatible with `--live-model` for obvious
reasons. The documented bridge is an HTTPS proxy whitelisted to
`api.anthropic.com`. Not built.

## 4. Sensitive-path denylist

`validate_sensitive_path` is called by every file tool *before* path
resolution. Blocked patterns:

- `.env`, `.env.local`, `.env.production` (but not `.env.example`)
- `id_rsa`, `id_rsa.pub`, `id_ed25519*`
- `*.pem`, `*.key`, `*.pfx`, `*.p12`
- `.aws/`, `.ssh/`
- `.netrc`, `credentials`, `credentials.json`
- `.vg_daily_spend.json`, `.vg_approvals.json` (agent state — agent must not
  rewrite its own budget ledger)

`.env.example` is allowed because the agent legitimately needs to learn the
schema. The pattern uses a negative lookahead so `.env.example` slips through
while `.env` and `.env.local` are blocked.

## 5. Prompt injection

Tool output is **data**, not instructions. The parent system prompt contains
a fixed sentence asserting this. The agent must not follow directives that
appear inside files or command output. Mitigations, in order:

1. Explicit system-prompt sentence (lives in `PROMPTS.md`).
2. Approval gate for mutating tools, so an injected "please run X" turns
   into a prompt to the operator.
3. Trace redaction, so injected secrets don't end up in the JSONL.
4. No auto-execution of "suggestions" embedded in tool output — every
   action goes through a model turn that the trace records.

## 6. Approval policy

Modes:

- `off` — default for deterministic demo and tests. No prompting; tests
  remain reproducible.
- `writes` — gate `write_file`, `edit_file`, `run_bash`, `spawn_subagent`.
  Recommended for live use.
- `all` — gate every tool including reads. Use for demo recordings or
  highly sensitive workspaces.

`--yes` auto-approves and still records an `approval` event with
`decision="auto"` so the audit trail is complete.

Hybrid per-call prompt menu (five choices: yes / yes-folder / yes-always /
no / abort) is the same UX Claude Code and Codex use. The scope cache
lookup order is exact directory → parent prefixes → `*`. First match wins.

Scope grants never override the deny-list. Granting `edit_file` for the
workspace root does not let the agent write `.env`.

Persistence (`.vg_approvals.json`, `--save-approvals`, `--reset-approvals`)
is documented here but not yet implemented; it is on the future-work list in
`next_steps.md`.

## 7. When validation can be relaxed

Concrete criteria for adding a new safe command to `SAFE_COMMANDS`:

- The command has no `-i`/`--in-place`/`-exec`/`-delete`/`-fprint` flag, nor
  any flag that opens a socket.
- Under all plausible flag combinations, it cannot write to disk outside the
  workspace.
- The spec (`specs/20_tools.md`) is updated first, with one-line rationale.
- A new test in `tests/test_vg_agent.py` proves the command stays read-only
  under typical and adversarial argument combinations.

Same gate for new tools. Don't widen the allowlist because "the demo would
be cleaner". Demos can use approval prompts.

## 8. Why we can't trust Docker alone

The outer Docker sandbox is a great defense-in-depth but every in-process
safety property must hold *without* it. Unit tests run without Docker. A
demo presented at a customer's laptop will not run with `--network none` if
the customer hasn't built the image. The in-process gates are the contract.

## 9. Failure modes to demonstrate live

| Scenario | Command | What you should see |
| --- | --- | --- |
| Path escape | `python -m vg_agent --task "read ../../etc/passwd"` | tool error "path … escapes the workspace root" |
| Sensitive read | `python -m vg_agent --task "read .env"` | tool error "sensitive path … is on the read/write denylist" |
| Destructive shell | `python -m vg_agent --task "run rm -rf ."` | "destructive token 'rm' is not allowed" |
| `find -delete` | `python -m vg_agent --task "run find . -delete"` | "forbidden argument token '-delete' is not allowed" |
| Approval prompt | `--require-approval writes` on a rename task | five-choice menu before the edit |
| Endpoint pin | unit test asserts `EndpointPinViolation` for `evil.example` | exception before socket open |
| Redaction | tool output containing `sk-ant-…` | `***REDACTED***` in JSONL + `redaction` event |

Each of these has a corresponding test in `tests/test_vg_agent.py`.
