---
name: Docker traces path + JSONL migration
overview: "Ensure Docker chat writes traces to host ./traces (dashboard-visible), migrate legacy JSONL from workspace/workspace/traces/, and verify dashboard/web History picks them up."
todos:
  - id: compose-env
    content: "docker-compose.yml — VG_WORKSPACE_ROOT=. when working_dir=/workspace (done)"
    status: completed
  - id: spec-packaging
    content: "specs/50_packaging.md — document Compose cwd + env contract (done)"
    status: completed
  - id: migrate-jsonl
    content: "Move unique *.jsonl from workspace/workspace/traces/ → repo traces/; drop nested duplicates"
    status: completed
  - id: verify-dashboard
    content: "start-web.sh from repo root; GET /api/v1/health traces_dirs; History shows migrated session IDs"
    status: pending
  - id: optional-nested-scan
    content: "(P2) dashboard all_traces_dirs() — include workspace/**/traces for stragglers"
    status: pending
  - id: sqlite-threading
    content: "(parallel) step_budget_sqlite_trace_plan — check_same_thread + write lock for full DB mirror"
    status: pending
isProject: false
---

# Docker traces path fix and JSONL migration

## Problem

| Layer | Expected | Broken behavior |
|-------|----------|-----------------|
| Docker Compose | `working_dir: /workspace`, mount `./traces` → `/workspace/traces` | Default `VG_WORKSPACE_ROOT=workspace` → root `/workspace/workspace` |
| Trace writes | `<workspace_root>/traces/<run_id>.jsonl` | JSONL under `workspace/workspace/traces/` on host |
| Dashboard (`dashboard/web`, React) | Scans `workspace/traces/` + repo `traces/` via `all_traces_dirs()` | Nested folder **not** scanned → sessions invisible in History |

`./start.sh` uses the same Compose service; it did **not** fix paths until `VG_WORKSPACE_ROOT=.` is set on the service.

## Goals

1. **Future runs** — Docker chat/task/seed use `/workspace` as workspace root; traces land on host `./traces`.
2. **Existing runs** — All `*.jsonl` live under a scanned directory (`traces/` or `workspace/traces/`).
3. **Dashboard** — History lists migrated sessions (`jsonl_only` or full SQLite mirror after backfill).

## Non-goals

- Merging two `vg_agent.sqlite3` files by hand (JSONL is canonical; API backfills on read).
- Changing local `uv run` default (`VG_WORKSPACE_ROOT=workspace` from repo root remains correct).

---

## Implementation

### 1. Compose contract (completed)

```yaml
working_dir: /workspace
environment:
  VG_WORKSPACE_ROOT: "."
volumes:
  - ./workspace:/workspace
  - ./traces:/workspace/traces
```

Spec: `specs/50_packaging.md`, `specs/15_cli_contract.md` (cwd-is-workspace → `VG_WORKSPACE_ROOT=.`).

Test: `test_resolve_workspace_root_docker_compose_cwd` in `tests/test_vg_agent.py`.

### 2. One-time JSONL migration

**Canonical host directory:** repo root `./traces/` (matches Docker mount and largest existing corpus).

| Source | Action |
|--------|--------|
| `workspace/workspace/traces/*.jsonl` not in `traces/` | `Move-Item` → `traces/` |
| Same basename, same size in both | Keep `traces/` copy; delete nested duplicate |
| Nested `vg_agent.sqlite3` | Leave in place or delete after confirming JSONL backfill; do not overwrite main `traces/vg_agent.sqlite3` |

**Session IDs to recover from nested folder (this repo):**

- `250785b1586c`
- `8d95ece28b4f`
- `eaeb4dd5638f`
- `a73dede4108c` — duplicate only (already in `traces/`)

Optional cleanup: remove empty `workspace/workspace/` tree after migration.

### 3. Verification

```powershell
# From repo root
./start-web.sh   # or run_dashboard.ps1
curl http://127.0.0.1:8787/api/v1/health
# traces_dirs should include .../traces and .../workspace/traces

# History UI: http://127.0.0.1:5173
# Search session IDs above; Events/Context load from JSONL
```

New Docker chat after fix:

```bash
./start.sh
# trace footer should say traces/<run_id>.jsonl (under /workspace/traces in container)
# host file: ./traces/<run_id>.jsonl
```

### 4. Follow-ups (optional)

| ID | Item |
|----|------|
| P2 | `all_traces_dirs()` glob `workspace/**/traces` so stragglers appear without migration |
| P3 | SQLite thread-safety (`step_budget_sqlite_trace_plan.md`) for complete sub-agent rows in DB |

---

## Rollback

- Compose: remove `environment.VG_WORKSPACE_ROOT` (reverts to nested writes).
- Migration: move JSONL back to `workspace/workspace/traces/` (not recommended).
