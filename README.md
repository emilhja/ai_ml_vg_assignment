# VG Agent

This repository implements the VG assignment as a spec-first coding-agent demo.
The source of truth is the markdown spec set plus `PROMPTS.md` and
`MODEL_CONFIG.md`; executable project code is generated from those files or
from generated-code templates with traceable provenance.

## One-command generation

```powershell
python scripts/generate_project.py --clean
```

That command regenerates:

- `src/vg_agent/`
- `fixtures/demo_repo/`

The generated code contains a `SPEC_DIGEST` derived from the markdown specs and
prompt/config files. Provenance verification regenerates generated artifacts
into a temporary directory and compares them byte-for-byte with the checked-in
tree.

## Demo commands

Presentation script:

```powershell
.\scripts\run_demo.ps1
```

Use `.\scripts\run_demo.ps1 -SkipTests` when you already ran the test suite
and only want the live demo flow.

```powershell
python scripts/generate_project.py --clean
uv run pytest
```

Sanity edit:

```powershell
cd fixtures/demo_repo
uv run --project ../.. python -m vg_agent --task "rename foo to bar in app.py" --trace
```

VG slide:

```powershell
cd fixtures/demo_repo
uv run --project ../.. python -m vg_agent --task "find all auth handling and summarise" --trace --show-context 3
```

Cost-cap demo:

```powershell
cd fixtures/demo_repo
uv run --project ../.. python -m vg_agent --task "search this repo for the string __VG_SENTINEL_NEVER_PRESENT__ and don't stop until you find it" --trace
```

Replay:

```powershell
uv run python -m vg_agent --replay fixtures/demo_repo/traces/<run_id>.jsonl --trace --show-context 3
```

Optional live Anthropic-backed extension run:

```powershell
$env:ANTHROPIC_API_KEY="..."
uv run python -m vg_agent --task "add input validation to app.py" --live-model --trace --show-context 3
```

Without `--live-model`, commands use deterministic demo routes and do not call
external APIs.

## Model configuration

The exact Anthropic API model IDs and pricing constants are declared once in
`MODEL_CONFIG.md`. Generated runtime code reads from generated constants, not
from marketing names in prose.

Official Anthropic docs checked on 2026-05-10:

- Model IDs: https://platform.claude.com/docs/en/about-claude/models/overview
- Pricing: https://platform.claude.com/docs/en/about-claude/pricing

## Command safety

`run_bash` is intentionally not a general shell escape. The generated tool
accepts only simple read-only inspection commands and rejects shell control
operators, redirection, command substitution, and destructive command tokens
such as `rm`, `del`, `rmdir`, `Remove-Item`, `mv`, `cp`, `chmod`, `mkfs`,
`dd`, `git`, `ssh`, `scp`, and any package installer or foreign-language
runtime. `sed` is excluded from the allowlist because `sed -i` mutates files
in place. Argument tokens that shell out (`-exec`, `-execdir`, `-delete`,
`-ok`, `-okdir`, `-fprint`, anything starting with `--exec`) are also
rejected. Rejected commands are returned as tool errors and are not executed.

File tools (`read_file`, `read_file_range`, `write_file`, `edit_file`) refuse
any path matching the sensitive-path denylist (`.env`, `id_rsa`, `*.pem`,
`*.key`, `.aws/`, `.ssh/`, `credentials`, etc.). `.env.example` stays
readable so the agent can learn the schema.

Approval gate:

- `--require-approval off|writes|all` controls whether mutating tools (and
  `spawn_subagent`) prompt before execution. Default is `off` so the
  deterministic demo and tests remain reproducible.
- `--yes` auto-approves and still records an `approval` event with
  `decision="auto"` so the audit trail is preserved.
- Scoped approvals (choice 2) reuse the grant for the same `(tool, folder)`
  in the rest of the session.

Endpoint pin:

- The Anthropic client refuses any non-`api.anthropic.com` host. A
  `EndpointPinViolation` is raised before the socket opens.

Daily spend:

- `BudgetGuard` reads and writes `.vg_daily_spend.json` (UTC date-keyed) so
  the daily cap survives across runs. The file is gitignored and on the
  sensitive-path denylist.

Trace redaction:

- Tool outputs are scanned for `sk-ant-*`, `AKIA*`, and `Bearer *` tokens
  before being written to the JSONL trace. Each substitution produces a
  `redaction` event. `--no-redact` disables this for local debugging only.

See [`dev_docs/dangerous_cli.md`](dev_docs/dangerous_cli.md) for the *why*
behind every command, argument token, and path on the deny-list.

For a safer live demo, run inside Docker and let the container absorb any file
changes:

```powershell
docker build -t vg-agent-demo .
docker run --rm --network none --cap-drop ALL --security-opt no-new-privileges --pids-limit 128 vg-agent-demo
```

Interactive VG-slide demo in the container:

```powershell
docker run --rm -it --network none --cap-drop ALL --security-opt no-new-privileges --pids-limit 128 vg-agent-demo `
  python -m vg_agent --task "find all auth handling and summarise" --trace --show-context 3
```

Docker is an outer safety layer, not the only safety layer. The Python
`run_bash` gate still rejects dangerous commands before shell execution.
# ai_ml_vg_assignment
