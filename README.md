# VG Agent

This repository implements the VG assignment as a spec-first coding-agent demo.
The source of truth is the markdown spec set plus `PROMPTS.md` and
`MODEL_CONFIG.md`; executable project code is generated from those files or
from generated-code templates with traceable provenance.

The agent has a single runtime path: a live OpenRouter-backed loop (via LiteLLM)
where the parent model decides each turn whether to call a tool, spawn a typed
sub-agent, or yield. It requires `OPENROUTER_API_KEY`.

## Recommended Run Path: Docker

Use Docker Compose for demos and grading. The single `vg-agent` service has
bridged network access for OpenRouter only; the in-process egress pin refuses
any non-`openrouter.ai` host before a socket opens.

### 1. Build And Configure

```powershell
Copy-Item .env.example .env
# Edit .env and set OPENROUTER_API_KEY=<your-key>
New-Item -ItemType Directory -Force workspace,traces
docker compose build
```

### 2. Seed The Fixture Workspace

```powershell
docker compose run --rm vg-agent --seed-fixture
```

### 3. Run The Live Demo

```powershell
docker compose run --rm vg-agent `
  --task "read data/sample.log, then summarise auth/ and utils.py in parallel" `
  --trace --show-context 8
```

This exercises the full agent: parallel Explorer sub-agents, parent-scoped
tool-result compaction, sub-agent context isolation, budget guards, and tracing.
See `specs/70_demo_runbook.md` for the five graded scenes (autonomy + edit,
parallel summarise, Grilling clarification, cost-cap abort, safety blocks).

### Interactive Chat

```powershell
docker compose run --rm -it vg-agent --chat --require-approval writes
```

Chat prints a compact statusline before each prompt with the active model, latest
parent context size, run token budget, step count, cost, approval events, and
last run state. Use `/status` to print it on demand; `/budget`, `/finops`,
`/approvals`, `/reset`, and `/new` are also available. In an interactive
terminal, slash commands autocomplete after a leading `/`.

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

Test locally (no network; live loop is exercised with an injected fake client):

```powershell
python scripts/generate_project.py --clean
uv run pytest
```

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
  tests remain reproducible.
- `--yes` auto-approves and still records an `approval` event with
  `decision="auto"` so the audit trail is preserved.
- Scoped approvals (choice 2) reuse the grant for the same `(tool, folder)`
  in the rest of the session.

Budget caps:

- `--max-usd` / `--max-tokens` override the per-run caps from `MODEL_CONFIG.md`.
  A soft warning fires at 80% of a cap; the hard cap aborts the run with
  `run_end{final_status:"aborted"}` and a `budget_event` carrying the reason.

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
  `traces/vg_agent.sqlite3`. JSONL remains the audit source; SQLite is
  the dashboard query store.
- The SQLite database keeps the lossless event payloads plus rollup tables for
  sessions, runs, turns, model calls, tool calls, sub-agents, approvals,
  redactions, and compactions. This records prompt durations, response
  latency, token and cost totals, tool latency/errors, and model usage.

### Trace analysis dashboard

Local FastAPI + React UI for live session tail (SSE), history browse, and
statistics. See [`specs/70_dashboard.md`](specs/70_dashboard.md).

**Important:** start the **API from the repository root**, not from
`dashboard/web`. The API resolves trace paths from the process working
directory. If you run uvicorn inside `dashboard/web`, startup will log
`trace_dirs=[]` and History will show zero sessions even though
`traces/*.jsonl` exists one level up.

```powershell
# Install dashboard deps (once)
uv sync --extra dashboard --extra dev
```

**Recommended (Git Bash / WSL)** — one command from repo root starts API + Vite:

```bash
./start-web.sh
# Optional: ./start-web.sh --no-install --api-port 8787
```

**Manual two-terminal setup** (fallback):

```powershell
# From repo root: C:\Users\emil_\vscode\vg_assignment
cd C:\Users\emil_\vscode\vg_assignment

# Terminal 1 — API (must be repo root)
$env:VG_WORKSPACE_ROOT = "workspace"
uv run uvicorn dashboard.api.main:app --host 127.0.0.1 --port 8787 --reload

# Agent traces use the same root (default workspace/ when run from repo root):
# uv run vg-agent --task "..."   # writes workspace/traces/*.jsonl + vg_agent.sqlite3
# If your cwd is already the workspace folder: $env:VG_WORKSPACE_ROOT = "."
```

On startup you should see something like:

```text
dashboard: sqlite=...\vg_assignment\traces\vg_agent.sqlite3 schema_ready=True
dashboard: trace_dirs=['...\workspace\traces', '...\traces']
```

If you see `trace_dirs=[]` or a sqlite path under `dashboard\web\`, stop
uvicorn, `cd` to the repo root, and start again.

```powershell
# Terminal 2 — frontend (dashboard/web is fine here)
cd dashboard\web
npm install
npm run dev
# Open http://127.0.0.1:5173  (Vite proxies /api → :8787)
```

**PowerShell launcher** (starts API from repo root in a new window):

```powershell
.\scripts\run_dashboard.ps1
```

Do **not** run `uvicorn` from `dashboard/web` unless you set `VG_TRACES_DIR` /
`VG_SQLITE_PATH` (see alternative below).

**Alternative:** keep uvicorn in `dashboard/web` but point at real traces:

```powershell
cd dashboard\web
$env:VG_TRACES_DIR = "C:\Users\emil_\vscode\vg_assignment\traces"
$env:VG_SQLITE_PATH = "C:\Users\emil_\vscode\vg_assignment\traces\vg_agent.sqlite3"
uv run uvicorn dashboard.api.main:app --host 127.0.0.1 --port 8787 --reload
```

Quick checks:

- http://127.0.0.1:8787/api/v1/health — `schema_ready: true`, non-empty `traces_dirs`
- http://127.0.0.1:8787/api/v1/sessions?limit=5 — `total` should be &gt; 0 if you have JSONL traces

See [`dev_docs/dangerous_cli.md`](dev_docs/dangerous_cli.md) for the *why*
behind every command, argument token, and path on the deny-list.

Docker Compose is the canonical demo wrapper. The `vg-agent` service is the only
service and is the live OpenRouter path.

Docker is an outer safety layer, not the only safety layer. The Python
`run_bash` gate still rejects dangerous commands before shell execution.
