# 70 Dashboard (trace analysis UI)

Local-dev FastAPI + React dashboard for reviewing VG Agent sessions: live
tail during `--chat`, history browse, and FinOps statistics. JSONL remains
the audit source; SQLite is the primary query store (`specs/60_observability.md`).

## Scope

- **In scope:** `dashboard/api/` (Python), `dashboard/web/` (Vite/React/Tailwind),
  optional `[dashboard]` deps in `pyproject.toml`, `start-web.sh` (Git Bash / WSL),
  `scripts/run_dashboard.ps1` (PowerShell).
- **Out of scope:** Docker sidecar, hosted multi-user auth, run compare, export PDF.

## Security

- Bind API to `127.0.0.1` only.
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
| GET | `/sessions` | Paginated session list; each item includes sub-agent and compaction flags for History filters (see **History sub-agent badges** and **History compaction filters** below) |
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
| GET | `/stats` | `?range=today\|7d\|30d` — rollups (see below) |
| GET | `/stats/tool-errors` | `?range=&tool=&limit=&offset=` — paginated failed tool calls for one tool |
| GET | `/finops/daily` | `.vg_daily_spend.json` + caps |

### `GET /stats` response fields

Beyond KPIs (`total_runs`, `total_turns`, `total_tokens`, `total_cost_usd`,
`error_rate`) and time series (`by_day`, `by_model`, `by_agent_type`):

| Field | Meaning |
|-------|---------|
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
| `/stats` | Statistics: tool usage, prompts, expensive turns, drillable tool errors |

### Event stream (`EventFeed`)

View modes (toolbar; persisted in `localStorage`):

| Mode | Behaviour |
|------|-----------|
| **Flat** | Newest-first list with per-event time tags |
| **By turn** | Collapsible sections per `user_prompt` turn (chronological within turn) |
| **Turn + agents** | Turn sections with parent lane + sub-agent lanes |

Optional **Parallel columns** toggle (when parallel sub-agents are detected):
sub-agent lanes side-by-side instead of stacked. Shown when any turn has overlap
from `GET /runs/{run_id}/parallel`, overlapping sub-agent timestamp ranges, or a
`spawn_subagents` tool call with 2+ sub-agent lanes / `subagent_spawn` events
(even before `subagent_return`).

### History sub-agent badges

`has_parallel_subagents` / `has_sequential_subagents` on the session list use **JSONL**
when `<traces_dir>/<session_id>.jsonl` exists (same audit rules as the Events tab).
SQLite is used only when no JSONL file is present.

Per user-prompt turn:

| Badge | When |
|-------|------|
| **parallel** (turn) | `parallel_subagent_summary` reports overlapping `subagent_return` intervals, **or** `spawn_subagents` with 2+ overlapping sub-agent lanes (timestamp overlap on lane events, including before returns land). |
| **sequential** (turn) | `parallel_subagent_summary` with 2+ returns but no overlap, single `spawn_subagent`, or other sub-agent activity without parallel overlap. |

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

### Verifying compaction on a session

Use any of these on `/history/:sessionId`:

| Tab | What to look for |
|-----|------------------|
| **Safety / FinOps** | **Compactions** list: `before_tokens→after_tokens` per tool-result compaction |
| **Events** | Rows with `kind: compaction` (expand for `original_event_idx`, `original_sha256`) |
| **Parent context** | Step slider: tool-result **compacted** markers (`[COMPACTED tool_result…]`) and **context_compaction** meta rows (fold summary + before→after). Use **Jump to compaction step** when present. Full payloads remain in JSONL only. |

Canonical live demo: task reads `data/sample.log` then parallel explorers (`demo_review.md` scene 2).

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
