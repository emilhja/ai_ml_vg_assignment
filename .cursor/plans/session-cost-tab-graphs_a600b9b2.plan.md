---
name: session-cost-tab-graphs
overview: Add a new Cost tab on the session detail page that visualizes run-level token/cost/tool-call metrics with reusable chart patterns already used in the dashboard.
todos:
  - id: wire-cost-tab
    content: Add cost tab route state and query enablement in SessionDetailPage
    status: completed
  - id: derive-metrics
    content: Compute model/tool cost-token datasets from timeline payload
    status: completed
  - id: render-charts
    content: Implement KPI cards and recharts visualizations for cost tab
    status: completed
  - id: ux-empty-states
    content: Add empty/fallback states and consistent formatting
    status: completed
  - id: validate-ui
    content: Run frontend checks and manually validate /history/:sessionId?tab=cost
    status: completed
isProject: false
---

# Add Cost Tab To Session Detail

## Goal

Add a dedicated `Cost` tab on the session detail page (`/history/:sessionId`) that shows a compact run overview (tokens/cost/tool activity) plus charts for model cost/tokens and tool-call behavior.

## Scope and approach

- Reuse existing timeline data from `[dashboard/web/src/pages/SessionDetailPage.tsx](dashboard/web/src/pages/SessionDetailPage.tsx)` (`api.timeline(runId)`), which already includes `model_calls` and `tool_calls`.
- Reuse the existing chart library/patterns from `[dashboard/web/src/pages/StatsPage.tsx](dashboard/web/src/pages/StatsPage.tsx)` (`recharts`) to keep visual consistency and avoid dependency churn.
- Keep this as a frontend-only change first; no API contract changes unless we detect missing fields during implementation.

## Planned changes

### 1) Add `cost` tab wiring in session detail page

- Update tab union and parser in `[dashboard/web/src/pages/SessionDetailPage.tsx](dashboard/web/src/pages/SessionDetailPage.tsx)`:
  - Extend `TAB_IDS` with `"cost"`.
  - Add tab button label `Cost`.
  - Ensure query param `?tab=cost` works alongside `runId` selection.
- Expand timeline query enablement so `timeline` is fetched for the new tab.

### 2) Build derived cost/token/tool datasets

- In `[dashboard/web/src/pages/SessionDetailPage.tsx](dashboard/web/src/pages/SessionDetailPage.tsx)`, add memoized derived arrays:
  - **Model-by-step series**: `step_idx`, `tokens_in`, `tokens_out`, `total_tokens`, `cost_usd`, `latency_ms`.
  - **Model aggregate bars**: grouped by `model_id` (`sum cost`, `sum tokens`, `call_count`).
  - **Tool aggregate bars**: grouped by `tool` (`call_count`, `error_count`, `avg latency`).
  - **Tool timeline series**: call count / error count over time buckets (or sequence index fallback if timestamps sparse).
- Normalize null/undefined numeric fields to `0` for chart safety.

### 3) Render cost overview cards + charts

- In the new `tab === "cost"` section of `[dashboard/web/src/pages/SessionDetailPage.tsx](dashboard/web/src/pages/SessionDetailPage.tsx)`, render:
  - KPI row: run total tokens, run total cost, model call count, tool call count, tool error rate.
  - Line chart: step-level tokens vs cost.
  - Bar chart: top models by cost (and/or tokens).
  - Bar chart: tool calls + error count by tool.
- Use styling and tooltip conventions already used on `[dashboard/web/src/pages/StatsPage.tsx](dashboard/web/src/pages/StatsPage.tsx)` for consistent dark-theme readability.

### 4) Empty/error states and UX polish

- Add robust placeholders for runs lacking model/tool telemetry (e.g., old traces).
- Keep table/chart sections scroll-safe in the same layout constraints used by existing tabs.
- Add concise labels/units (USD, tokens, ms) and deterministic sort order (highest cost first for bars).

### 5) Validation

- Frontend type-check/build pass for dashboard web app.
- Manual UI validation on `/history/:sessionId?tab=cost`:
  - tab routing state persists in URL,
  - charts render with real run data,
  - empty-state behavior is clean,
  - numbers match existing timeline totals.

## Key files

- `[dashboard/web/src/pages/SessionDetailPage.tsx](dashboard/web/src/pages/SessionDetailPage.tsx)`
- `[dashboard/web/src/pages/StatsPage.tsx](dashboard/web/src/pages/StatsPage.tsx)`
- `[dashboard/web/src/api.ts](dashboard/web/src/api.ts)`

## Data flow (cost tab)

```mermaid
flowchart TD
  routeHistory[HistoryRoute /history/:sessionId] --> sessionDetail[SessionDetailPage]
  sessionDetail --> runSelection[runIdFromQueryOrLatest]
  runSelection --> timelineApi[api.timeline(runId)]
  timelineApi --> modelCalls[timeline.model_calls]
  timelineApi --> toolCalls[timeline.tool_calls]
  timelineApi --> turnTotals[timeline.turns]
  modelCalls --> modelSeries[stepAndModelAggregates]
  toolCalls --> toolSeries[toolAggregatesAndErrors]
  turnTotals --> kpis[costAndTokenKpis]
  modelSeries --> costTabCharts[CostTabCharts]
  toolSeries --> costTabCharts
  kpis --> costTabCharts
```



## Notes

- Initial implementation keeps all logic in `SessionDetailPage` for speed.
- If component size grows too much, follow-up refactor can extract a `SessionCostTab` component under `dashboard/web/src/components/` without changing behavior.

