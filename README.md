# VG Agent

This repository implements the VG assignment as a spec-first coding-agent demo.
The source of truth is the markdown spec set plus `PROMPTS.md` and
`MODEL_CONFIG.md`; executable project code is generated from those files or
from generated-code templates with traceable provenance.

## Recommended Run Path: Docker

Use Docker Compose for demos and grading. The default `vg-agent` service runs
with `network_mode: none`, so deterministic runs do not need an API key and
cannot make network calls.

### 1. Build And Seed

```powershell
Copy-Item .env.example .env
New-Item -ItemType Directory -Force workspace,traces
docker compose build
docker compose run --rm vg-agent --seed-fixture
```

### 2. Deterministic Demo, No API Key

```powershell
docker compose run --rm vg-agent `
  --task "read data/sample.log, then summarise auth/ and utils.py in parallel" `
  --trace --show-context 8
```

This is the primary evidence path. It proves tracing, replayability,
compaction, sub-agent isolation, budget guards, and safety behavior without
using a live model.

### 3. Optional Live OpenRouter Demo

Edit `.env` and set:

```ini
OPENROUTER_API_KEY=your-key
```

Then run the live service:

```powershell
docker compose run --rm vg-agent-live `
  --task "inspect app.py and suggest one small improvement" `
  --live-model --trace --show-context 3
```

`vg-agent-live` is the only Compose service intended for live model calls. The
client still pins egress to `openrouter.ai` before calling LiteLLM.

Live chat mode (`--chat --live-model`) prints a compact statusline before each
prompt with the active model, latest parent context size, run token budget,
step count, cost, approval events, and last run state. Use `/status` to print
the same line on demand. In an interactive terminal, slash commands autocomplete
after a leading `/`; for example `/fin` shows `/finops` with a short description
and can be selected with the arrow keys and Enter.

### 4. Replay A Trace

After any traced run, replay it without network:

```powershell
docker compose run --rm vg-agent --replay traces/<run_id>.jsonl --trace --show-context 3
```

## Developer Commands

Local `uv` commands are for development and test iteration. Prefer Docker for
demo runs.

### Regenerate Generated Code

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

Presentation script for local development:

```powershell
.\scripts\run_demo.ps1
.\scripts\run_demo.ps1 -SkipTests
```

Test locally:

```powershell
python scripts/generate_project.py --clean
uv run pytest
```

Cost-cap demo: use the deterministic Docker scene in
`specs/70_demo_runbook.md` so the hard cap proof does not depend on live
model behavior.

Without `--live-model`, commands use deterministic demo routes and do not call
external APIs.

## Model configuration

The exact LiteLLM/OpenRouter model IDs and pricing constants are declared once in
`MODEL_CONFIG.md`. Generated runtime code reads from generated constants, not
from marketing names in prose.

OpenRouter/LiteLLM docs checked on 2026-05-28:

- OpenRouter provider: https://docs.litellm.ai/docs/providers/openrouter
- OpenRouter docs: https://openrouter.ai/docs

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

- `--require-approval off|writes|all` controls whether mutating tools and
  sub-agent spawns prompt before execution. Default is `off` so the
  deterministic demo and tests remain reproducible.
- `--yes` auto-approves and still records an `approval` event with
  `decision="auto"` so the audit trail is preserved.
- Scoped approvals (choice 2) reuse the grant for the same `(tool, folder)`
  in the rest of the session.

Endpoint pin:

- The LiteLLM OpenRouter client refuses any non-`openrouter.ai` host. A
  `EndpointPinViolation` is raised before the socket opens.

Daily spend:

- `BudgetGuard` reads and writes `.vg_daily_spend.json` (UTC date-keyed) so
  the daily cap survives across runs. The file is gitignored and on the
  sensitive-path denylist.

Trace redaction:

- Tool outputs are scanned for `sk-or-v1-*`, `AKIA*`, and `Bearer *` tokens
  before being written to the JSONL trace. Each substitution produces a
  `redaction` event. `--no-redact` disables this for local debugging only.

SQLite observability:

- Every redacted JSONL event is also mirrored to
  `traces/vg_agent.sqlite3`. JSONL remains the replay/audit source; SQLite is
  the dashboard query store.
- The SQLite database keeps the lossless event payloads plus rollup tables for
  sessions, runs, turns, model calls, tool calls, sub-agents, approvals,
  redactions, and compactions. This records prompt durations, response
  latency, token and cost totals, tool latency/errors, and model usage without
  requiring a frontend yet.

See [`dev_docs/dangerous_cli.md`](dev_docs/dangerous_cli.md) for the *why*
behind every command, argument token, and path on the deny-list.

Docker Compose is the canonical demo wrapper. The `vg-agent` service runs
without networking; `vg-agent-live` is the only service intended for live
OpenRouter calls.

Docker is an outer safety layer, not the only safety layer. The Python
`run_bash` gate still rejects dangerous commands before shell execution.
# ai_ml_vg_assignment
