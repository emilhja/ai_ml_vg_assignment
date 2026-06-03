# 70 Dashboard (trace analysis UI)

Local-dev FastAPI + React dashboard for reviewing VG Agent sessions: live
tail during `--chat`, history browse, and FinOps statistics. JSONL remains
the audit source; SQLite is the primary query store (`specs/60_observability.md`).

## Scope

- **In scope:** `dashboard/api/` (Python), `dashboard/web/` (Vite/React/Tailwind),
  optional `[dashboard]` deps in `pyproject.toml`, `start-web.sh` (Git Bash / WSL),
  `scripts/run_dashboard.ps1` (PowerShell), Docker production path
  (`Dockerfile.dashboard`, `vg-dashboard` Compose service, `start-dashboard.sh`).
- **Out of scope:** Vite HMR inside Docker, hosted multi-user auth, run compare,
  export PDF.

## Security

- Bind API to `127.0.0.1` on the host (local dev). Docker service binds
  `0.0.0.0` inside the container only; publish `8787:8787` to localhost.
- No authentication in v1 (local machine).
- UI shows a warning that traces may contain redacted-but-sensitive content.
- API must not log full `payload_json` bodies.

## Configuration

| Variable | Default | Purpose |
|----------|---------|---------|
| `VG_WORKSPACE_ROOT` | repo `./workspace` | Agent workspace root (daily spend, default trace path) |
| `VG_SQLITE_PATH` | auto | Override SQLite file; default picks first DB with `sessions` table |
| `VG_TRACES_DIR` | auto | Override JSONL directory; default follows resolved SQLite parent |
| `VG_ACTIVE_SESSION_ID` | unset | Force active session for live tab |
| `VG_DASHBOARD_HOST` | `127.0.0.1` | Uvicorn bind |
| `VG_DASHBOARD_PORT` | `8787` | API port |
| `VG_DASHBOARD_SERVE_UI` | unset | When `1`/`true`/`yes` and `dashboard/web/dist/index.html` exists, serve the built React app from this process (Docker / single-port production) |
| `VG_DASHBOARD_NO_BACKFILL` | unset | When `1`/`true`/`yes`, never write JSONL into the agent SQLite file (required for Docker sidecar while the agent is running) |

SQLite path: resolved automatically — `workspace/traces/vg_agent.sqlite3` if it
has the mirror schema, otherwise `traces/vg_agent.sqlite3` at the repo root
(common when the agent wrote under `./traces` while `VG_WORKSPACE_ROOT` stayed
`workspace`). An empty placeholder DB in `workspace/traces/` is ignored.

JSONL for session `S`: `<resolved_traces_dir>/S.jsonl`.

`all_traces_dirs()` also scans nested `traces/` directories under
`VG_WORKSPACE_ROOT` (depth-limited glob, deduped), so JSONL written to paths
such as `workspace/workspace/traces/` is discoverable without manual copy.

## Active session detection

1. `VG_ACTIVE_SESSION_ID` if set.
2. Row in `sessions` with `status = 'running'`, highest `last_seen_at`.
3. Most recently modified `traces/*.jsonl` basename (without extension).

## API (`/api/v1`)

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | DB reachable, workspace path |
| GET | `/sessions` | Paginated session list; each item includes sub-agent, compaction, and `agent_types_present` for History filters (see **History sub-agent badges**, **History compaction filters**, **History agent filters** below) |
| GET | `/sessions/active` | Active session snapshot |
| GET | `/sessions/{session_id}` | Session + runs + turns summary |
| PATCH | `/sessions/{session_id}` | Set/clear user `display_name` (body: `{ "display_name": string \| null }`; max 120 chars); `session_id` unchanged |
| GET | `/sessions/{session_id}/events` | Paginated events (`?from_event_idx`, `?limit`) |
| GET | `/sessions/{session_id}/stream` | SSE live tail |
| GET | `/runs/{run_id}/timeline` | Turns, model_calls, tool_calls, subagents |
| GET | `/runs/{run_id}/context` | `?step_idx=N` — parent `show_context` |
| GET | `/runs/{run_id}/context/max-step` | `max_step_idx` and `compaction_steps` (parent steps where context includes a compacted tool result) |
| GET | `/runs/{run_id}/parallel` | Per-turn parallel sub-agent summaries |
| GET | `/runs/{run_id}/safety` | Approvals, redactions, budget_events |
| GET | `/stats` | `?range=today\|7d\|30d` — rollups (see below). Ranges use **UTC calendar days**: `today` = since UTC midnight today; `7d` = today plus the prior 6 days; `30d` = today plus the prior 29 days. `by_day` includes every day in the window (zeros when no runs). |
| GET | `/stats/tool-errors` | `?range=&tool=&limit=&offset=` — paginated failed tool calls for one tool |
| GET | `/finops/daily` | `.vg_daily_spend.json` + caps |

### `GET /stats` response fields

Beyond KPIs (`total_runs`, `total_turns`, `total_tokens`, `total_cost_usd`,
`error_rate`) and time series (`by_day`, `by_model`, `by_agent_type`):

| Field | Meaning |
|-------|---------|
| `configured_models` | Effective per-role models after `runtime_settings` (repo `.env` + `workspace/config.toml` on top of generated defaults): `role`, `model_id`, `price_input_per_mtok`, `price_output_per_mtok`, `has_known_pricing` |
| `models` | Per-model rollup: calls, tokens, cost, `avg_latency_ms`, `last_used_at` (in range), `last_used_at_all_time`, `configured_roles`, nested `by_role` (parent/explorer/compactor/…), `sample_session_id`, `error_count` |
| `by_agent_role` | Cost/tokens/calls grouped by agent **role** (not instance id); Stats page **Cost by agent role** chart uses this (sorted by `cost_usd`) |
| `by_agent_type` | Cost/tokens/calls grouped by `agent_id` instance (`parent`, `explorer-1`, …) — API/debug only; not shown in Stats UI |
| `by_tool` | Top tools by call count: `tool`, `count`, `error_count`, `avg_latency_ms` |
| `top_user_prompts` | Normalized duplicate user prompts: `label`, `count`, `sample_session_id` |
| `top_subagent_questions` | Normalized explorer questions (same shape) |
| `top_expensive_turns` | Top turns by `total_cost_usd` with `session_id`, `run_id`, `prompt_snippet` |
| `tool_error_groups` | Per-tool error count plus up to 5 `occurrences` (drill via `/stats/tool-errors`) |
| `tool_errors` | Legacy flat breakdown by tool name (count only) |

### Session detail deep links

`/history/:sessionId?tab=tools&runId=<run_id>&highlight=<tool_call_id>` opens the
Tools tab, selects the run when multiple exist, and scrolls/highlights the matching
tool row.

### SSE (`/sessions/{id}/stream`)

- Content-Type: `text/event-stream`
- Query: `from_event_idx` (optional), `Last-Event-ID` header (event idx)
- Poll interval: 500 ms
- Message types (JSON `data:` field):
  - `heartbeat` — `{}`
  - `events` — `{ "items": [ event dicts ] }`
  - `statusline` — latest `statusline` event payload
  - `run_end` — terminal run status when detected

Client tracks `last_event_idx` for idempotent resume.

## Frontend routes

| Route | Tab |
|-------|-----|
| `/` | Current session (SSE) |
| `/history` | Session list |
| `/history/:sessionId` | Detail: Timeline, **Parent context**, Tools, Safety, Events (`?tab`, `?runId`, `?highlight`, `?eventIdx`) |
| `/stats` | Statistics: model inventory (configured + usage by role), tool usage, prompts, expensive turns, drillable tool errors |

### Event stream (`EventFeed`)

View modes (toolbar; persisted in `localStorage`):

| Mode | Behaviour |
|------|-----------|
| **Flat** | Newest-first list with per-event time tags |
| **By turn** | Collapsible sections per `user_prompt` turn (chronological within turn) |
| **Turn + agents** | Turn sections with parent lane + sub-agent lanes |

**Compaction unit (Turn + agents):** Each `compaction` or `context_compaction`
event is rendered as one amber **compaction unit** card at its chronological
position in the parent timeline. The card header shows `before_tokens →
after_tokens` and percent reduced; nested **compactor** `llm_start` /
`assistant_step` rows appear inside the card (not in a separate bottom lane).
Preceding compactor events are linked by walking backward from the compaction
row. A footer link jumps to the original `tool_result` when
`original_event_idx` is set. Explorers and other sub-agents keep separate lanes.

Optional **Parallel columns** toggle (when parallel sub-agents are detected):
sub-agent lanes side-by-side instead of stacked. Shown when any turn has overlap
from `GET /runs/{run_id}/parallel`, overlapping sub-agent timestamp ranges, or a
`spawn_subagents` tool call with 2+ sub-agent lanes / `subagent_spawn` events
(even before `subagent_return`).

### Agent navigation (Current + Events tab)

Toolbar chips (**Agents:** `parent`, `explorer`, `compactor`, …) appear for each
agent type present in the loaded event list (one chip per type; parallel explorer
lanes share a single **explorer** chip).

- Clicking a chip scrolls to the **next** matching event by `event_idx` (wraps to
  the first match after the last).
- Collapsed turn sections auto-expand when the target event is inside them.
- Session detail: jumps set `?tab=events&eventIdx=N` for shareable deep links
  (same scroll/highlight behaviour as manual `eventIdx` links).

Matching rules (aligned with `dashboard/api/services/session_agent_types.py`):

| Type | Matches |
|------|---------|
| `parent` | Parent-scoped events (`agent_id == "parent"`, etc.) |
| `explorer`, `grilling`, `coder`, `reviewer` | `agent_type` on event or payload |
| `compactor` | `agent_type == compactor`, or `kind` in `compaction`, `context_compaction` (scrolls to compaction unit card) |

### History sub-agent badges

`has_parallel_subagents` / `has_sequential_subagents` on the session list use **JSONL**
when `<traces_dir>/<session_id>.jsonl` exists (same audit rules as the Events tab).
SQLite is used only when no JSONL file is present.

Per user-prompt turn:

| Badge | When |
|-------|------|
| **parallel** (turn) | `iter_spawn_subagents_batch_summaries` reports overlap for a `spawn_subagents` batch (child ids from that tool_result only), **or** in-flight `spawn_subagents` with 2+ overlapping explorer lanes before the tool_result lands. |
| **sequential** (turn) | Sub-agent activity without a parallel `spawn_subagents` batch, or batch with no overlap; single `spawn_subagent` spawns. Later Coder/Reviewer returns in the same user turn do **not** count toward parallel batch size. |

Session flags OR across turns. A session may show **both** badges (e.g. one turn with
`spawn_subagent`, another with parallel `spawn_subagents`).

### History compaction filters

`has_tool_compaction`, `has_context_compaction_auto`, and
`has_context_compaction_manual` on the session list use **JSONL** when
`<traces_dir>/<session_id>.jsonl` exists (same audit rules as sub-agent badges).
SQLite `compactions` / `events` tables are used only when no JSONL file is present.

| Session field | Filter chip | When |
|---------------|-------------|------|
| `has_tool_compaction` | **Tool compaction** | Any parent `kind: compaction` (automatic tool-result compaction over `K_COMPACT`) |
| `has_context_compaction_auto` | **Auto context compaction** | Any `kind: context_compaction` with `reason: auto` (parent loop before `llm_start` when context exceeds window × fraction) |
| `has_context_compaction_manual` | **Manual context compaction** | Any `kind: context_compaction` with `reason: manual` (chat `/compact`) |

Matching any selected filter shows the session (same OR semantics as sub-agent filters).
Select none to show all sessions.

### History agent filters

`agent_types_present` on each `SessionSummary` lists distinct agent types seen in the
session (canonical order: `parent`, `explorer`, `grilling`, `coder`, `reviewer`,
`compactor`). Derived from **JSONL** when `<traces_dir>/<session_id>.jsonl` exists;
otherwise SQLite `events` / `subagents` rows.

| UI | Behaviour |
|----|-----------|
| **Agents** filter chips | OR-match sessions whose `agent_types_present` includes the type |
| **Agents** table column | Compact badge per type on each session row |

Filter persistence: `localStorage` key `vg-dashboard-history-filters` (shared with
sub-agent and compaction filters).

### Verifying compaction on a session

Use any of these on `/history/:sessionId`:

| Tab | What to look for |
|-----|------------------|
| **Safety / FinOps** | **Compactions** list: `before_tokens→after_tokens` per tool-result compaction |
| **Events** | Rows with `kind: compaction` (expand for `original_event_idx`, `original_sha256`) |
| **Parent context** | Step slider: tool-result **compacted** markers (`[COMPACTED tool_result…]`) and **context_compaction** meta rows (fold summary + before→after). Use **Jump to compaction step** when present. Full payloads remain in JSONL only. |

Canonical live demo: task reads `data/sample.log` then parallel explorers (`docs/demo/demo_review.md` scene 2).

### Session display names

- `session_id` remains the canonical trace key (URL, JSONL filename, SQLite PK).
- Optional `display_name` on `SessionSummary` for UI labels.
- Persisted in **both** places (dual-write on PATCH):
  - SQLite table `session_metadata` (created by dashboard on startup)
  - `<traces_dir>/session_metadata.json` (human-readable sidecar for jsonl-only review)
- Read merges both sources; newer `updated_at` wins.

### Events tab expandable rows

Click a row to expand inline `<pre>` sections (no separate drawer). Kinds:

| Kind | Sections |
|------|----------|
| `assistant_step` | assistant text, tool_calls, model |
| `llm_start` | model + payload |
| `tool_call` | args (+ spawn batch for sub-agent tools) |
| `tool_result` | summary/full result, stderr |
| `compaction` | original idx/sha256, marker |
| `budget_event` | reason + counters |
| `approval` | tool/path + decision |
| `user_prompt` | full prompt when long |
| `subagent_spawn` / `subagent_return` | instruction / return summary |
| `egress_blocked` / `redaction` | details |

Large bodies truncated (~10 KB) in the UI.

Turn section headers show **in / out / USD** from SQLite `turns` rollups when available, else summed from visible events.

### `EventItem` fields (grouping)

| Field | Purpose |
|-------|---------|
| `turn_id` | Turn boundary (`session:turn:N` from trace) |
| `turn_index` | 1-based user prompt index |
| `parent_id` | `"parent"` for sub-agent-scoped events |
| `child_agent_id` | Sub-agent id on `subagent_spawn` / `subagent_return` |
| `timestamp_iso` | Wall-clock + relative time tags in UI |

## JSONL backfill

On session list or detail, if `<session_id>.jsonl` exists but the session row is
missing from the resolved SQLite file, the API replays the JSONL into that DB
(same `SQLiteTraceStore.record_event` path as live runs). Files larger than 50 MiB
are skipped. `VG_SQLITE_PATH` selects the backfill target.

## Data authority

| View | Primary source |
|------|----------------|
| Lists, rollups, stats | SQLite (session sub-agent and compaction badges: JSONL when file exists) |
| Session event list (`GET …/events`), run loaders (timeline, context, parallel) | **Merge** SQLite + JSONL by `event_idx`; JSONL wins on conflict (audit source). JSONL events beyond the SQLite mirror are included when the mirror lags. |
| Live tail (low latency) | JSONL file tail + SQLite events |
| Parent context at step N | `vg_agent.trace.show_context` on merged events |
| Parallel overlap | `vg_agent.trace.parallel_subagent_summary` on merged events |

## Dependencies

Python optional group `dashboard`: fastapi, uvicorn, sqlalchemy, pydantic.  
Node: Vite, React, Tailwind, TanStack Query, React Router, Recharts.

**Local dev:** from repo root run `./start-web.sh` (Git Bash / WSL) so uvicorn’s
cwd resolves `traces/` correctly; use `scripts/run_dashboard.ps1` on PowerShell.
Do not start the API from `dashboard/web` without `VG_TRACES_DIR` / `VG_SQLITE_PATH`.

**Docker (persistent):** `./start-dashboard.sh` builds `vg-dashboard` (when needed)
and runs `docker compose up -d vg-dashboard`. Open http://127.0.0.1:8787 — API and
UI share one origin (`/api/v1` relative paths). Uses the same `./workspace` and
`./traces` mounts as `vg-agent` (`VG_WORKSPACE_ROOT=.`). Rebuilding or restarting
the agent container does not stop the dashboard. Rebuild the dashboard image only
after UI/API changes: `docker compose build vg-dashboard && docker compose up -d vg-dashboard`.
