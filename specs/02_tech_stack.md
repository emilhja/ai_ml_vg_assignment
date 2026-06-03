# 02 Tech stack

Technology inventory for the VG Agent repository: languages, dependencies,
infrastructure, configuration surfaces, and codegen tooling. For how these
pieces fit together behaviorally, see [`specs/01_architecture.md`](01_architecture.md).
For Rich/prompt-toolkit terminal UI detail, see
[`specs/17_rich_tui_stack.md`](17_rich_tui_stack.md).

## Runtime platform

| Item | Value |
|------|--------|
| Language | Python `>=3.10` ([`pyproject.toml`](../pyproject.toml)) |
| Package manager | [uv](https://github.com/astral-sh/uv) (`uv sync`, `uv run`) |
| CLI entrypoint | `vg-agent` → `vg_agent.__main__:main` |
| Module layout | `src/vg_agent/` (setuptools `where = ["src", "."]`) |
| Demo OS target | Windows dev + Git Bash; `run_bash` shells via `bash -c` |

Docker images use **Python 3.12 slim** ([`specs/50_packaging.md`](50_packaging.md)).

## Core Python dependencies

From `[project] dependencies` in [`pyproject.toml`](../pyproject.toml):

| Package | Constraint | Role |
|---------|------------|------|
| `litellm` | `>=1.0` | OpenRouter API adapter for all live model calls |
| `rich` | `>=13` | TTY panels, Markdown, tables, syntax highlighting (`--chat`) |
| `prompt-toolkit` | `>=3.0` | Chat REPL: history, slash autocomplete |
| `python-dotenv` | `>=1.0` | Load `.env` at startup |
| `pytest` | `>=8` | Test runner; also exposed as parent/Coder `run_tests` tool |
| `tomli` | `>=2.0` (Python < 3.11) | Parse `config.toml` on older Python |

### Optional extras

| Extra | Packages | When to install |
|-------|----------|-----------------|
| `dev` | `httpx>=0.27` | Dashboard/API dev tests |
| `dashboard` | `fastapi`, `uvicorn[standard]`, `sqlalchemy`, `pydantic`, `httpx` | Trace analysis UI |

```powershell
uv sync                    # agent + tests
uv sync --extra dashboard  # + FastAPI stack
uv sync --extra dev        # + httpx for dev tests
```

## LLM and prompt layer

| Input file | Contents |
|------------|----------|
| [`MODEL_CONFIG.md`](../MODEL_CONFIG.md) | LiteLLM model IDs, `OPENROUTER_ENDPOINT_HOST`, per-model $/Mtok pricing |
| [`CONTEXT_WINDOWS.md`](../CONTEXT_WINDOWS.md) | Context window sizes and auto-compact fractions |
| [`PROMPTS.md`](../PROMPTS.md) | Parent, sub-agent, and compaction system prompts |

Runtime flow:

```
vg_agent.live_model_client → LiteLLM → https://openrouter.ai (pinned host)
```

- **Egress pin** — any other host raises `EndpointPinViolation` before a socket opens.
- **Overrides** — `VG_*_MODEL` env vars and `[models]` in `config.toml` map through
  `runtime_settings.py` (see below).
- **Pricing warnings** — missing $/Mtok for a selected model warns at startup;
  `VG_STRICT_MODEL_PRICING=1` fails instead ([`docs/PRICE.md`](../docs/PRICE.md)).

Codegen embeds defaults from `MODEL_CONFIG.md` / `CONTEXT_WINDOWS.md` into
`config.py` at regenerate time. Env/TOML overrides apply at runtime without
regenerate.

## Terminal UI stack

| Layer | Technology | Spec |
|-------|------------|------|
| Presentation | Rich (`Console`, `Panel`, `Markdown`, `Syntax`, …) | [`17_rich_tui_stack.md`](17_rich_tui_stack.md) |
| Input | prompt-toolkit `PromptSession` | [`16_chat_ui.md`](16_chat_ui.md) |
| Implementation | `src/vg_agent/chat_ui.py` (Tier B) | [`17_rich_tui_stack.md`](17_rich_tui_stack.md) |
| Wiring | `src/vg_agent/__main__.py` (generated template) | [`16_chat_ui.md`](16_chat_ui.md) |

**Not used:** Textual, urwid, blessed, full-screen TUIs.

Progress during runs uses ANSI-colored stderr lines by default; Rich TTY chat
collapses noise unless `VG_CHAT_VERBOSE_PROGRESS=1` (see `17` env table).

## Persistence

| Store | Location | Writer | Reader |
|-------|----------|--------|--------|
| JSONL trace | `traces/<session_id>.jsonl` (or under workspace) | `trace.py` / agent run | CLI `--show-context`, dashboard, replay |
| SQLite mirror | `workspace/traces/vg_agent.sqlite3` or `traces/vg_agent.sqlite3` | `sqlite_store.py` | Dashboard API |
| Daily spend ledger | Under workspace root | `budget.py` | FinOps slash commands, dashboard stats |

Path resolution: `workspace_paths.py` (Tier B). Schema and mirror writes:
`sqlite_store.py` (Tier B).

JSONL remains the **audit source of truth**; SQLite is a query index
([`specs/60_observability.md`](60_observability.md)).

## Dashboard stack (optional)

Install: `uv sync --extra dashboard`. Spec: [`specs/70_dashboard.md`](70_dashboard.md).

### Backend (Python)

| Package | Constraint (pyproject) | Role |
|---------|----------------------|------|
| FastAPI | `>=0.115` | HTTP API |
| Uvicorn | `>=0.32` | ASGI server |
| SQLAlchemy | `>=2.0` | SQLite access |
| Pydantic | `>=2.0` | Request/response models |
| httpx | `>=0.27` | HTTP client (tests/dev) |

Code: `dashboard/api/` (Tier C).

### Frontend (Node)

From [`dashboard/web/package.json`](../dashboard/web/package.json):

| Package | Version (approx) | Role |
|---------|------------------|------|
| React | ^18.3 | UI |
| react-router-dom | ^6.28 | Routing |
| Vite | ^5.4 | Build/dev server |
| TypeScript | ~5.6 | Types |
| Tailwind CSS | ^3.4 | Styling |
| @tanstack/react-query | ^5.62 | Server state |
| Recharts | ^2.14 | Charts on stats page |

Build: `npm ci && npm run build` in `dashboard/web/` (also in `Dockerfile.dashboard`).

**Not in scope:** hosted multi-tenant auth, Vite HMR inside production Docker image.

## Infrastructure

### Docker Compose ([`docker-compose.yml`](../docker-compose.yml))

| Service | Image | Purpose |
|---------|-------|---------|
| `vg-agent` | [`Dockerfile`](../Dockerfile) | Live agent; needs `OPENROUTER_API_KEY` |
| `vg-dashboard` | [`Dockerfile.dashboard`](../Dockerfile.dashboard) | Trace UI on port 8787 |

Shared volumes: `./workspace` → `/workspace`, `./traces` → `/workspace/traces`.
Agent service: `cap_drop: ALL`, `pids_limit: 128`, `VG_WORKSPACE_ROOT=.`.

### Shell launchers

| Script | Platform |
|--------|----------|
| `scripts/run_demo.ps1` | Windows demo |
| `scripts/run_dashboard.ps1` | Dashboard (PowerShell) |
| `start.sh` / `start-dashboard.sh` | Git Bash |

## Configuration surfaces

Configuration is layered: generated defaults → `config.toml` → environment
→ CLI flags (CLI wins where applicable).

| Surface | Path | Notes |
|---------|------|-------|
| Environment | `.env` (from [`.env.example`](../.env.example)) | Secrets; `OPENROUTER_API_KEY` required for live runs |
| TOML | `config.toml` (from [`config.example.toml`](../config.example.toml)) | Models, budget, approval |
| Runtime loader | `src/vg_agent/runtime_settings.py` | Merges env/TOML over `config.py` |
| CLI | `vg-agent --help` | [`specs/15_cli_contract.md`](15_cli_contract.md) |

### Key environment variables (index)

| Variable | Purpose | Detail in |
|----------|---------|-----------|
| `OPENROUTER_API_KEY` | Live API auth | README, `.env.example` |
| `VG_WORKSPACE_ROOT` | Workspace + trace roots | [`70_dashboard.md`](70_dashboard.md), packaging |
| `VG_PARENT_MODEL` … `VG_COMPACTOR_MODEL` | Per-role model overrides | `MODEL_CONFIG.md`, `runtime_settings.py` |
| `VG_MAX_USD_PER_RUN` / `VG_MAX_USD_PER_DAY` / `VG_MAX_TOKENS_PER_RUN` | Budget caps | [`30_runtime_governance.md`](30_runtime_governance.md) |
| `VG_APPROVAL_MODE` | `off` \| `writes` \| `all` | [`10_main_agent.md`](10_main_agent.md) |
| `VG_K_COMPACT` | Compaction threshold | [`01_architecture.md`](01_architecture.md) |
| `VG_STRICT_MODEL_PRICING` | Fail on missing pricing | `docs/PRICE.md` |
| `VG_SQLITE_PATH` / `VG_TRACES_DIR` | Dashboard path overrides | [`70_dashboard.md`](70_dashboard.md) |
| `VG_DASHBOARD_*` | Dashboard bind, UI serve, backfill | [`70_dashboard.md`](70_dashboard.md) |
| `NO_COLOR` / `NO_EMOJI` | Disable Rich/ANSI | [`17_rich_tui_stack.md`](17_rich_tui_stack.md) |
| `VG_CHAT_VERBOSE_PROGRESS` | Full progress log in Rich chat | [`16_chat_ui.md`](16_chat_ui.md) |

Full chat/dashboard presentation env vars: [`17_rich_tui_stack.md`](17_rich_tui_stack.md).

## Codegen toolchain

| Piece | Path |
|-------|------|
| Generator | [`scripts/generate_project.py`](../scripts/generate_project.py) |
| Templates | [`scripts/templates/*.tmpl`](../scripts/templates/) |
| Digest | `SPEC_DIGEST` in `vg_agent/__init__.py` / `config.py` |

**`SOURCE_INPUTS` (hashed for digest):** `specs/00`, `10`, `11`, `20`, `30`, `40*.md`,
`PROMPTS.md`, `MODEL_CONFIG.md`, `CONTEXT_WINDOWS.md`.

**Not in digest:** this file (`02_tech_stack.md`), `01_architecture.md`, and other
behavioral specs (`12`, `15`, `16`, `17`, `50`, `60`, `70`, …). Changing them does
not require regenerate unless you also change a digest input.

```powershell
python scripts/generate_project.py --clean
uv run pytest
```

## Testing

| Tool | Usage |
|------|--------|
| pytest | `uv run pytest`; config in `pyproject.toml` `[tool.pytest.ini_options]` |
| `FakeClient` / `PipelineClient` | Injected model responses in `tests/test_vg_agent.py` |
| Network | **Forbidden** in unit tests — no live OpenRouter in CI |

Other suites: dashboard API (`tests/test_dashboard*.py`), packaging, runtime
settings, provider routing.

## Explicit non-stack

Technologies **not** used (avoid confusion when extending the repo):

| Category | Not used |
|----------|----------|
| Terminal | Textual, urwid, blessed, curses apps |
| Agent framework | LangChain, AutoGPT-style orchestrators |
| Model hosting | Local LLM servers (Ollama, etc.) in the default path |
| Auth | Dashboard v1 has no login/OAuth |
| DB | PostgreSQL/Redis (SQLite only for traces) |
| CI model calls | Live API in unit tests |

## Related specs

- [`README.md`](README.md) — full spec index
- [`specs/01_architecture.md`](01_architecture.md) — system design and module map
- [`specs/03_testing.md`](03_testing.md) — test and provenance contract
- [`specs/04_demo_fixture.md`](04_demo_fixture.md) — demo workspace layout
- [`specs/25_security.md`](25_security.md) — safety layers rollup
- [`specs/05_source_of_truth_and_generation.md`](05_source_of_truth_and_generation.md) — edit tiers and regenerate
- [`specs/17_rich_tui_stack.md`](17_rich_tui_stack.md) — Rich/prompt-toolkit deep dive
- [`specs/50_packaging.md`](50_packaging.md) — Docker images and Compose
- [`specs/70_dashboard.md`](70_dashboard.md) — dashboard API and deployment
