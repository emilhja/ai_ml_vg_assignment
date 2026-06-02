# 50 Packaging

Docker is the **primary** execution boundary for demos. Local `uv run` paths
remain available for development but the grading-anchored demo runs through
Compose. Tool-level safety (`run_bash` deny-list, sensitive-path denylist,
approval policy) holds regardless of Docker.

## Dockerfile

- Base: `python:3.12-slim`.
- Install `uv` from the official wheel; do not call `pip` directly.
- Non-root user `vg` (uid 1000); workdir `/workspace`.
- Copy `pyproject.toml`, `uv.lock`, then `uv sync --frozen`.
- Main `[project] dependencies` include **pytest** (required for the `run_tests`
  tool). Optional `[dev]` extras (e.g. `httpx`) are not installed in the image
  (`uv sync --frozen --no-dev`).
- Copy every repo-root file listed in `SOURCE_INPUTS` inside
  `scripts/generate_project.py` (`MODEL_CONFIG.md`, `PROMPTS.md`,
  `CONTEXT_WINDOWS.md`) plus `specs/` before running
  `python scripts/generate_project.py --clean` at image build time.
- Copy `src/` last so source edits invalidate fewer cache layers.
- Default entrypoint: `python -m vg_agent`. `CMD` left empty so the user
  passes the task on the command line.

## docker-compose.yml

A single live service runs every demo:

```yaml
services:
  vg-agent:
    build: .
    working_dir: /workspace
    environment:
      VG_WORKSPACE_ROOT: "."
    # bridged network for OpenRouter only; the agent's egress pin rejects
    # any non-openrouter.ai endpoint even if the network allows it.
    volumes:
      - ./workspace:/workspace
      - ./traces:/workspace/traces
    env_file:
      - path: .env
        required: false
    cap_drop: ["ALL"]
    security_opt: ["no-new-privileges"]
    pids_limit: 128
```

- `vg-agent` runs the live agent against OpenRouter; every scene in
  `specs/70_demo_runbook.md` uses it.
- `working_dir` is `/workspace` with `VG_WORKSPACE_ROOT=.` so traces and SQLite
  land in `/workspace/traces` (host `./traces`), not a nested
  `/workspace/workspace/traces` path.
- The service mounts `./workspace` read-write so the agent can edit fixture
  files. The host repo itself is never mounted — copy the demo fixture into
  `./workspace` first (`--seed-fixture`).
- Network egress is constrained in-process by the `openrouter.ai` egress pin;
  dropped capabilities and `no-new-privileges` remain the container-level
  safety layer.

## Config file

`config.example.toml` is tracked at the repo root and documents every
non-secret config key. A user may copy it to `workspace/config.toml` for demo
overrides. Runtime defaults still exist for the unit tests, but the
packaged configuration surface is the TOML schema below:

```toml
[models]
parent = "openrouter/google/gemini-2.5-flash"
grilling = "openrouter/google/gemini-2.5-flash"
explorer = "openrouter/google/gemini-2.5-flash"
coder = "openrouter/anthropic/claude-haiku-4.5"
reviewer = "openrouter/google/gemini-2.5-flash"
compactor = "openrouter/google/gemini-2.5-flash"

[budget]
max_usd_per_run = 0.50
max_usd_per_day = 5.00
max_tokens_per_run = 80000

[approval]
mode = "writes"     # off | writes | all
```

Loader precedence (highest wins):

1. CLI flag (`--max-usd`, `--require-approval`, `--parent-model`, …).
2. Environment variable (see `.env.example`).
3. `workspace/config.toml`.
4. Defaults from `specs/30_runtime_governance.md`.

Secrets never appear in `config.toml`. The config loader rejects keys
matching `*_KEY`, `*_TOKEN`, `*_SECRET`, `*_PASSWORD` with a parse error.

### Loader behaviour (`runtime_settings.py`)

On every `vg-agent` startup (after `argparse`, before the agent loop):

1. Resolve `workspace_root` via `VG_WORKSPACE_ROOT` (default `workspace`).
2. Resolve `repo_root`: parent of `workspace_root` when `pyproject.toml` exists
   there, else `Path.cwd()`.
3. Load `repo_root/.env` with `python-dotenv` (`override=False` so Docker /
   shell exports win).
4. Apply `workspace_root/config.toml` when present.
5. Apply `VG_*` environment variables (see `.env.example`).
6. Apply CLI flags last (`--parent-model`, `--subagent-model`, `--max-usd`, …).

Model IDs: values without an `openrouter/` prefix are normalized by prepending
`openrouter/` (e.g. `google/gemini-2.5-flash-lite` →
`openrouter/google/gemini-2.5-flash-lite`).

Optional compaction override: `VG_K_COMPACT` (integer token-estimate threshold
for parent tool-result compaction; default from `specs/30_runtime_governance.md`).

`--require-approval` defaults to `None` at parse time; after the loader runs,
unset CLI uses `config.REQUIRE_APPROVAL_DEFAULT` (which env/TOML may have set).

Budget caps from env/TOML mutate `config.MAX_*`; `BudgetGuard` receives explicit
`max_usd` / `max_tokens` from `_guard_overrides` so dataclass defaults are not
stale.

## .env.example

```ini
# Required: the agent always runs live against OpenRouter.
OPENROUTER_API_KEY=

# Optional OpenRouter app attribution.
OPENROUTER_SITE_URL=
OPENROUTER_APP_NAME=

# Optional OpenRouter provider routing (provider-selection guide on openrouter.ai).
# OPENROUTER_PROVIDER_ORDER=
# OPENROUTER_PROVIDER_ONLY=
OPENROUTER_PROVIDER_ONLY_DEEPSEEK=baidu/fp8,deepinfra/fp4
# OPENROUTER_PROVIDER_SORT=price
# OPENROUTER_PROVIDER_ALLOW_FALLBACKS=true
OPENROUTER_EXPENSIVE_PROVIDERS=alibaba,morph,parasail/fp8

# Optional overrides (see config.toml for the same keys).
VG_PARENT_MODEL=openrouter/google/gemini-2.5-flash
VG_GRILLING_MODEL=openrouter/google/gemini-2.5-flash
VG_EXPLORER_MODEL=openrouter/google/gemini-2.5-flash
VG_CODER_MODEL=openrouter/anthropic/claude-haiku-4.5
VG_REVIEWER_MODEL=openrouter/google/gemini-2.5-flash
VG_COMPACTOR_MODEL=openrouter/google/gemini-2.5-flash
VG_MAX_USD_PER_RUN=0.50
VG_MAX_USD_PER_DAY=5.00
VG_MAX_TOKENS_PER_RUN=80000
VG_APPROVAL_MODE=writes
VG_K_COMPACT=4000
# Exit at startup if any VG_*_MODEL lacks PRICING_USD_PER_MTOK (default: warn only).
# VG_STRICT_MODEL_PRICING=1
```

- `.env` is optional at Compose-parse time so `docker compose config` works
  in a fresh checkout. Live mode still fails clearly if
  `OPENROUTER_API_KEY` is missing.
- `.env` is gitignored. A pre-commit check fails CI if a staged file matches
  `^\.env$` or `^\.env\..+$` (the `.env.example` allowance lives in the
  sensitive-path denylist in `specs/20_tools.md`).

## README contract

The repo root README documents this install path and nothing else:

```bash
# Build
docker compose build

# Seed the fixture into ./workspace
docker compose run --rm vg-agent --seed-fixture

# Live demo (OpenRouter through LiteLLM)
docker compose run --rm vg-agent --task "..." --trace
```

A grader who has Docker installed must reach a working demo with no other
setup beyond copying `.env.example` to `.env` and filling in
`OPENROUTER_API_KEY`. This is VG.7's "idiot-proof packaging" anchor.

## Smoke test

`tests/test_packaging.py` asserts:

- `docker compose config` exits 0 (compose file parses).
- `Dockerfile` builds in CI if `DOCKER_AVAILABLE=1`; otherwise the test is
  skipped with an explicit reason (no silent skips).
- `.env.example` enumerates every `VG_*` variable in `KNOWN_ENV_VARS` (plus
  `OPENROUTER_*` keys read directly by the live client).

### OpenRouter provider routing (optional)

The live client may read these environment variables and pass a `provider`
object to OpenRouter via LiteLLM `extra_body` (see OpenRouter provider-selection
docs). Slugs must match the model's Providers tab (e.g. `alibaba` for Qwen).

| Variable | Purpose |
| --- | --- |
| `OPENROUTER_PROVIDER_ORDER` | Comma-separated slugs to try first (`order`) |
| `OPENROUTER_PROVIDER_ONLY` | Comma-separated whitelist (`only`) for all models |
| `OPENROUTER_PROVIDER_ONLY_DEEPSEEK` | `only` whitelist applied **only** when `model_id` contains `/deepseek/` |
| `OPENROUTER_PROVIDER_SORT` | `price`, `throughput`, or `latency` |
| `OPENROUTER_PROVIDER_ALLOW_FALLBACKS` | `true` or `false`; default `true` when unset |
| `OPENROUTER_EXPENSIVE_PROVIDERS` | Comma-separated denylist; triggers `warn_expensive_provider` once per slug per run (default `alibaba,morph,parasail/fp8`) |

For a **DeepSeek parent/coder + Gemini sub-agent** stack, use
`OPENROUTER_PROVIDER_ONLY_DEEPSEEK` and leave global `OPENROUTER_PROVIDER_ORDER`
unset so Gemini keeps default OpenRouter routing.
- `config.example.toml` enumerates every accepted non-secret config key.
- Real `.env` is gitignored: `git check-ignore .env` exits 0 in a fresh
  checkout.
