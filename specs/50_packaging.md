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
- Copy `src/` last so source edits invalidate fewer cache layers.
- Default entrypoint: `python -m vg_agent`. `CMD` left empty so the user
  passes the task on the command line.

## docker-compose.yml

Two services share the same image and `.env`:

```yaml
services:
  vg-agent:
    build: .
    network_mode: "none"
    volumes:
      - ./workspace:/workspace
      - ./traces:/workspace/traces
    env_file:
      - path: .env
        required: false
    cap_drop: ["ALL"]
    security_opt: ["no-new-privileges"]
    pids_limit: 128

  vg-agent-live:
    build: .
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

- `vg-agent` is the default for replay, deterministic smoke tests, and any
  run that does not need OpenRouter.
- `vg-agent-live` is used for optional `--live-model` runs after the
  deterministic grading path passes.
- Both services mount `./workspace` read-write so the agent can edit fixture
  files. The host repo itself is never mounted — copy the demo fixture into
  `./workspace` first.

## Config file

`config.example.toml` is tracked at the repo root and documents every
non-secret config key. A user may copy it to `workspace/config.toml` for demo
overrides. Runtime defaults still exist for deterministic tests, but the
packaged configuration surface is the TOML schema below:

```toml
[models]
parent = "openrouter/anthropic/claude-haiku-4.5"
grilling = "openrouter/anthropic/claude-haiku-4.5"
explorer = "openrouter/anthropic/claude-haiku-4.5"
coder = "openrouter/anthropic/claude-haiku-4.5"
reviewer = "openrouter/anthropic/claude-haiku-4.5"
compactor = "openrouter/anthropic/claude-haiku-4.5"

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

## .env.example

```ini
# Required for --live-model runs only.
OPENROUTER_API_KEY=

# Optional OpenRouter app attribution.
OPENROUTER_SITE_URL=
OPENROUTER_APP_NAME=

# Optional overrides (see config.toml for the same keys).
VG_PARENT_MODEL=openrouter/anthropic/claude-haiku-4.5
VG_GRILLING_MODEL=openrouter/anthropic/claude-haiku-4.5
VG_EXPLORER_MODEL=openrouter/anthropic/claude-haiku-4.5
VG_CODER_MODEL=openrouter/anthropic/claude-haiku-4.5
VG_REVIEWER_MODEL=openrouter/anthropic/claude-haiku-4.5
VG_COMPACTOR_MODEL=openrouter/anthropic/claude-haiku-4.5
VG_MAX_USD_PER_RUN=0.50
VG_MAX_USD_PER_DAY=5.00
VG_MAX_TOKENS_PER_RUN=80000
VG_APPROVAL_MODE=writes
```

- `.env` is optional at Compose-parse time so `docker compose config` works
  in a fresh checkout. Live mode still fails clearly if
  `OPENROUTER_API_KEY` is missing.
- `.env` is gitignored. A pre-commit check fails CI if a staged file matches
  `^\.env$` or `^\.env\..+$` (the `.env.example` allowance lives in the
  sensitive-path denylist in `specs/20_tools.md`).

## README contract

The repo root README documents three commands and nothing else for the
grading-anchored install path:

```bash
# Build
docker compose build

# Default demo (network: none, replay or non-live runs)
docker compose run --rm vg-agent --task "..." [--replay traces/<run_id>.jsonl]

# Live demo (OpenRouter through LiteLLM)
docker compose run --rm vg-agent-live --task "..." --live-model --trace
```

A grader who has Docker installed must reach a working demo with no other
setup beyond copying `.env.example` to `.env` and (for live mode) filling in
`OPENROUTER_API_KEY`. This is VG.7's "idiot-proof packaging" anchor.

## Smoke test

`tests/test_packaging.py` asserts:

- `docker compose config` exits 0 (compose file parses).
- `Dockerfile` builds in CI if `DOCKER_AVAILABLE=1`; otherwise the test is
  skipped with an explicit reason (no silent skips).
- `.env.example` enumerates every variable the agent reads via
  `os.environ.get`.
- `config.example.toml` enumerates every accepted non-secret config key.
- Real `.env` is gitignored: `git check-ignore .env` exits 0 in a fresh
  checkout.
