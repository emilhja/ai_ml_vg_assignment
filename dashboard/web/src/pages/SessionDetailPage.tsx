import { useQuery } from "@tanstack/react-query";
import { useEffect, useMemo, useState } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { api } from "../api";
import CompactionStatsBadge from "../components/CompactionStatsBadge";
import EventFeed from "../components/EventFeed";
import { SessionCard } from "../components/SessionCards";

const TAB_IDS = ["timeline", "cost", "context", "tools", "safety", "events"] as const;
type Tab = (typeof TAB_IDS)[number];

function parseTab(value: string | null): Tab {
  if (value && (TAB_IDS as readonly string[]).includes(value)) {
    return value as Tab;
  }
  return "timeline";
}

export default function SessionDetailPage() {
  const { sessionId = "" } = useParams();
  const [searchParams, setSearchParams] = useSearchParams();
  const tab = parseTab(searchParams.get("tab"));
  const urlRunId = searchParams.get("runId");
  const highlight = searchParams.get("highlight");
  const eventIdxParam = searchParams.get("eventIdx");
  const highlightEventIdx =
    eventIdxParam && /^\d+$/.test(eventIdxParam) ? Number(eventIdxParam) : null;
  const [stepIdx, setStepIdx] = useState(0);
  const [expandContext, setExpandContext] = useState(false);
  const [flashHighlight, setFlashHighlight] = useState<string | null>(null);

  const setTab = (next: Tab) => {
    setSearchParams(
      (prev) => {
        const p = new URLSearchParams(prev);
        p.set("tab", next);
        return p;
      },
      { replace: true },
    );
  };

  const setRunId = (runId: string) => {
    setSearchParams(
      (prev) => {
        const p = new URLSearchParams(prev);
        p.set("runId", runId);
        return p;
      },
      { replace: true },
    );
  };

  const {
    data: detail,
    isLoading,
    isError,
    error,
  } = useQuery({
    queryKey: ["session", sessionId],
    queryFn: () => api.session(sessionId),
    enabled: !!sessionId,
  });

  const runId = useMemo(() => {
    if (!detail?.runs.length) return "";
    if (urlRunId && detail.runs.some((r) => r.run_id === urlRunId)) {
      return urlRunId;
    }
    return detail.runs[detail.runs.length - 1]?.run_id ?? detail.runs[0]?.run_id ?? "";
  }, [detail, urlRunId]);

  const { data: timeline } = useQuery({
    queryKey: ["timeline", runId],
    queryFn: () => api.timeline(runId),
    enabled: !!runId && (tab === "timeline" || tab === "cost" || tab === "tools"),
  });

  const { data: maxStep } = useQuery({
    queryKey: ["maxStep", runId],
    queryFn: () => api.maxStep(runId),
    enabled: !!runId && tab === "context",
  });

  const { data: context } = useQuery({
    queryKey: ["context", runId, stepIdx],
    queryFn: () => api.context(runId, stepIdx),
    enabled: !!runId && tab === "context",
  });

  const { data: parallel } = useQuery({
    queryKey: ["parallel", runId],
    queryFn: () => api.parallel(runId),
    enabled: !!runId && (tab === "timeline" || tab === "events"),
  });

  const { data: safety } = useQuery({
    queryKey: ["safety", runId],
    queryFn: () => api.safety(runId),
    enabled: !!runId && tab === "safety",
  });

  const { data: eventsData } = useQuery({
    queryKey: ["events", sessionId],
    queryFn: () => api.events(sessionId, -1, 300),
    enabled: !!sessionId && tab === "events",
  });

  const toolErrors = useMemo(
    () => (timeline?.tool_calls ?? []).filter((t) => t.status !== "ok"),
    [timeline],
  );

  useEffect(() => {
    if (tab !== "tools" || !highlight) return;
    const el = document.getElementById(`tool-row-${highlight}`);
    if (el) {
      el.scrollIntoView({ behavior: "smooth", block: "center" });
    }
    setFlashHighlight(highlight);
    const timer = window.setTimeout(() => setFlashHighlight(null), 3000);
    return () => window.clearTimeout(timer);
  }, [tab, highlight, timeline]);

  const handleHighlightEventIdx = (eventIdx: number) => {
    setSearchParams(
      (prev) => {
        const p = new URLSearchParams(prev);
        p.set("tab", "events");
        p.set("eventIdx", String(eventIdx));
        return p;
      },
      { replace: true },
    );
  };

  useEffect(() => {
    if (tab !== "events" || highlightEventIdx == null) return;
    const el = document.getElementById(`event-${highlightEventIdx}`);
    if (el) {
      el.scrollIntoView({ behavior: "smooth", block: "center" });
    }
  }, [tab, highlightEventIdx, eventsData]);

  if (!sessionId) {
    return (
      <div className="space-y-3">
        <p className="text-red-400">Invalid session id in URL.</p>
        <Link to="/history" className="text-sm text-accent hover:underline">
          ← Back to history
        </Link>
      </div>
    );
  }

  if (isLoading) {
    return <p className="text-muted">Loading session…</p>;
  }

  if (isError) {
    const message = (error as Error)?.message ?? "Unknown error";
    return (
      <div className="space-y-3">
        <p className="text-red-400">
          Cannot load session <span className="font-mono">{sessionId}</span>: {message}
        </p>
        <Link to="/history" className="text-sm text-accent hover:underline">
          ← Back to history
        </Link>
      </div>
    );
  }

  if (!detail) {
    return (
      <div className="space-y-3">
        <p className="text-red-400">
          Session <span className="font-mono">{sessionId}</span> was not found.
        </p>
        <Link to="/history" className="text-sm text-accent hover:underline">
          ← Back to history
        </Link>
      </div>
    );
  }

  const tabs: { id: Tab; label: string }[] = [
    { id: "timeline", label: "Timeline" },
    { id: "cost", label: "Cost" },
    { id: "context", label: "Parent context" },
    { id: "tools", label: "Tools & errors" },
    { id: "safety", label: "Safety / FinOps" },
    { id: "events", label: "Events" },
  ];

  const runTotals = detail.runs.find((r) => r.run_id === runId);

  const turnSeries = useMemo(
    () =>
      (timeline?.turns ?? [])
        .slice()
        .sort((a, b) => (a.turn_index ?? 0) - (b.turn_index ?? 0))
        .map((turn, idx) => {
          const turnIndex = turn.turn_index ?? idx;
          const totalTokens = Number(turn.total_tokens ?? 0);
          return {
            turnIndex,
            label: `T${turnIndex}`,
            totalTokens,
            totalCostUsd: Number(turn.total_cost_usd ?? 0),
            toolCalls: Number(turn.total_tool_calls ?? 0),
          };
        }),
    [timeline],
  );

  const modelCostByModel = useMemo(() => {
    const grouped = new Map<string, { model: string; costUsd: number; calls: number }>();
    for (const call of timeline?.model_calls ?? []) {
      const model = call.model_id ?? "unknown";
      const current = grouped.get(model) ?? { model, costUsd: 0, calls: 0 };
      current.costUsd += Number(call.cost_usd ?? 0);
      current.calls += 1;
      grouped.set(model, current);
    }
    return Array.from(grouped.values())
      .sort((a, b) => b.costUsd - a.costUsd)
      .slice(0, 10);
  }, [timeline]);

  const toolUsageByTool = useMemo(() => {
    const grouped = new Map<
      string,
      { tool: string; calls: number; errors: number; totalLatencyMs: number; latencySamples: number }
    >();
    for (const call of timeline?.tool_calls ?? []) {
      const tool = call.tool ?? "unknown";
      const current = grouped.get(tool) ?? {
        tool,
        calls: 0,
        errors: 0,
        totalLatencyMs: 0,
        latencySamples: 0,
      };
      current.calls += 1;
      if (call.status !== "ok") current.errors += 1;
      if (call.latency_ms != null) {
        current.totalLatencyMs += Number(call.latency_ms);
        current.latencySamples += 1;
      }
      grouped.set(tool, current);
    }
    return Array.from(grouped.values())
      .map((row) => ({
        tool: row.tool,
        calls: row.calls,
        errors: row.errors,
        avgLatencyMs: row.latencySamples > 0 ? Math.round(row.totalLatencyMs / row.latencySamples) : 0,
      }))
      .sort((a, b) => b.calls - a.calls)
      .slice(0, 12);
  }, [timeline]);

  const toolCallsByTime = useMemo(() => {
    return (timeline?.tool_calls ?? [])
      .slice()
      .sort((a, b) => (a.started_at ?? "").localeCompare(b.started_at ?? ""))
      .map((call, idx) => ({
        idx: idx + 1,
        ok: call.status === "ok" ? 1 : 0,
        error: call.status === "ok" ? 0 : 1,
      }));
  }, [timeline]);

  const modelCalls = timeline?.model_calls.length ?? 0;
  const toolCalls = timeline?.tool_calls.length ?? 0;
  const toolErrorCount = toolErrors.length;
  const toolErrorRate = toolCalls > 0 ? (toolErrorCount / toolCalls) * 100 : 0;

  return (
    <div className={`space-y-6 ${tab === "events" ? "flex flex-col flex-1 min-h-0" : "overflow-y-auto"}`}>
      <Link to="/history" className="text-sm text-accent hover:underline">
        ← History
      </Link>
      <SessionCard session={detail.session} />
      <p className="text-xs text-muted font-mono">{detail.jsonl_path}</p>

      {detail.runs.length > 1 && (
        <label className="text-sm text-muted flex items-center gap-2">
          Run
          <select
            value={runId}
            onChange={(e) => setRunId(e.target.value)}
            className="bg-panel border border-slate-700/50 rounded px-2 py-1 text-white text-xs font-mono"
          >
            {detail.runs.map((r) => (
              <option key={r.run_id} value={r.run_id}>
                {r.run_id.slice(0, 12)}… · ${r.total_cost_usd.toFixed(4)}
              </option>
            ))}
          </select>
        </label>
      )}

      <div className="flex flex-wrap gap-2 border-b border-slate-700/50 pb-2">
        {tabs.map((t) => (
          <button
            key={t.id}
            type="button"
            onClick={() => setTab(t.id)}
            className={`px-3 py-1.5 rounded text-sm ${
              tab === t.id ? "bg-accent/25 text-accent" : "text-muted hover:text-white"
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>

      {tab === "timeline" && timeline && (
        <div className="space-y-6">
          <section>
            <h3 className="text-sm font-medium text-muted mb-2">Turns</h3>
            <ul className="space-y-2">
              {timeline.turns.map((t) => (
                <li key={t.turn_id} className="bg-panel rounded p-3 text-sm border border-slate-700/40">
                  <span className="text-muted">Turn {t.turn_index}</span> · {t.status} · {t.total_tool_calls}{" "}
                  tools
                  <p className="mt-1 line-clamp-2">{t.prompt}</p>
                </li>
              ))}
            </ul>
          </section>
          {parallel && parallel.turns.length > 0 && (
            <section>
              <h3 className="text-sm font-medium text-muted mb-2">Parallel sub-agents</h3>
              {parallel.turns.map((pt) => (
                <div key={pt.turn_index} className="mb-3 bg-panel rounded p-3 border border-violet-500/30">
                  <p className="text-sm">
                    Turn {pt.turn_index} · overlap: {pt.overlap ? "yes" : "no"}
                  </p>
                  <ul className="mt-2 text-xs space-y-1">
                    {pt.returns.map((r) => (
                      <li key={r.child_agent_id}>
                        {r.agent_type} ({r.duration_sec?.toFixed(1) ?? "?"}s) — {r.payload_snippet || r.status}
                      </li>
                    ))}
                  </ul>
                </div>
              ))}
            </section>
          )}
          <section>
            <h3 className="text-sm font-medium text-muted mb-2">Sub-agent timeline</h3>
            <div className="space-y-1">
              {timeline.subagents.map((s) => (
                <div
                  key={s.subagent_id}
                  className="flex gap-2 text-xs font-mono bg-violet-950/30 rounded px-2 py-1"
                >
                  <span>{s.agent_type}</span>
                  <span className="text-muted">{s.started_at?.slice(11, 19)}</span>
                  <span>→</span>
                  <span className="text-muted">{s.ended_at?.slice(11, 19)}</span>
                  <span>{s.duration_ms != null ? `${s.duration_ms}ms` : ""}</span>
                </div>
              ))}
            </div>
          </section>
          <section>
            <h3 className="text-sm font-medium text-muted mb-2">Model calls</h3>
            <div className="overflow-x-auto text-xs">
              <table className="w-full">
                <thead className="text-muted">
                  <tr>
                    <th className="text-left py-1">Step</th>
                    <th className="text-left">Model</th>
                    <th className="text-left">Latency</th>
                    <th className="text-left">USD</th>
                  </tr>
                </thead>
                <tbody>
                  {timeline.model_calls.map((m) => (
                    <tr key={m.model_call_id} className="border-t border-slate-700/30">
                      <td className="py-1">{m.step_idx}</td>
                      <td className="truncate max-w-xs">{m.model_id}</td>
                      <td>{m.latency_ms ?? "—"}ms</td>
                      <td>{m.cost_usd?.toFixed(4) ?? "—"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>
        </div>
      )}

      {tab === "cost" && (
        <div className="space-y-6">
          {!timeline ? (
            <p className="text-sm text-muted">Loading cost telemetry…</p>
          ) : (
            <>
              <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
                <Kpi label="Run tokens" value={(runTotals?.total_tokens ?? 0).toLocaleString()} />
                <Kpi label="Run cost" value={`$${(runTotals?.total_cost_usd ?? 0).toFixed(4)}`} />
                <Kpi label="Model calls" value={modelCalls.toLocaleString()} />
                <Kpi label="Tool calls" value={toolCalls.toLocaleString()} />
                <Kpi label="Tool error rate" value={`${toolErrorRate.toFixed(1)}%`} />
              </div>

              {turnSeries.length > 0 ? (
                <section>
                  <h3 className="text-sm font-medium text-muted mb-2">Per-turn tokens, cost, and tool calls</h3>
                  <div className="h-64 bg-panel/50 rounded-lg p-2">
                    <ResponsiveContainer width="100%" height="100%">
                      <LineChart data={turnSeries}>
                        <CartesianGrid stroke="#334155" strokeDasharray="3 3" />
                        <XAxis dataKey="label" tick={{ fill: "#8b9cb3", fontSize: 11 }} />
                        <YAxis yAxisId="left" tick={{ fill: "#8b9cb3", fontSize: 11 }} />
                        <YAxis yAxisId="right" orientation="right" tick={{ fill: "#8b9cb3", fontSize: 11 }} />
                        <Tooltip contentStyle={{ background: "#1a2332", border: "1px solid #334155" }} />
                        <Legend />
                        <Line
                          yAxisId="left"
                          type="monotone"
                          dataKey="totalTokens"
                          stroke="#e07a5f"
                          dot={false}
                          name="Tokens"
                        />
                        <Line
                          yAxisId="right"
                          type="monotone"
                          dataKey="totalCostUsd"
                          stroke="#34d399"
                          dot={false}
                          name="Cost USD"
                        />
                        <Line
                          yAxisId="left"
                          type="monotone"
                          dataKey="toolCalls"
                          stroke="#818cf8"
                          dot={false}
                          name="Tool calls"
                        />
                      </LineChart>
                    </ResponsiveContainer>
                  </div>
                </section>
              ) : (
                <p className="text-sm text-muted">No turn-level token/cost data available for this run.</p>
              )}

              <div className="grid lg:grid-cols-2 gap-6">
                <section>
                  <h3 className="text-sm font-medium text-muted mb-2">Top models by cost</h3>
                  {modelCostByModel.length > 0 ? (
                    <div className="h-72 bg-panel/50 rounded-lg p-2">
                      <ResponsiveContainer width="100%" height="100%">
                        <BarChart data={modelCostByModel} layout="vertical" margin={{ left: 8, right: 8 }}>
                          <CartesianGrid stroke="#334155" strokeDasharray="3 3" />
                          <XAxis type="number" tick={{ fill: "#8b9cb3", fontSize: 11 }} />
                          <YAxis
                            type="category"
                            dataKey="model"
                            width={190}
                            tick={{ fill: "#8b9cb3", fontSize: 10 }}
                          />
                          <Tooltip contentStyle={{ background: "#1a2332", border: "1px solid #334155" }} />
                          <Bar dataKey="costUsd" fill="#e07a5f" name="Cost USD" radius={[0, 4, 4, 0]} />
                        </BarChart>
                      </ResponsiveContainer>
                    </div>
                  ) : (
                    <p className="text-sm text-muted">No model call cost data available for this run.</p>
                  )}
                </section>

                <section>
                  <h3 className="text-sm font-medium text-muted mb-2">Tool calls and errors by tool</h3>
                  {toolUsageByTool.length > 0 ? (
                    <div className="h-72 bg-panel/50 rounded-lg p-2">
                      <ResponsiveContainer width="100%" height="100%">
                        <BarChart data={toolUsageByTool} margin={{ left: 8, right: 8 }}>
                          <CartesianGrid stroke="#334155" strokeDasharray="3 3" />
                          <XAxis dataKey="tool" tick={{ fill: "#8b9cb3", fontSize: 10 }} interval={0} />
                          <YAxis tick={{ fill: "#8b9cb3", fontSize: 11 }} />
                          <Tooltip contentStyle={{ background: "#1a2332", border: "1px solid #334155" }} />
                          <Legend />
                          <Bar dataKey="calls" fill="#818cf8" name="Calls" radius={[4, 4, 0, 0]} />
                          <Bar dataKey="errors" fill="#f87171" name="Errors" radius={[4, 4, 0, 0]} />
                        </BarChart>
                      </ResponsiveContainer>
                    </div>
                  ) : (
                    <p className="text-sm text-muted">No tool telemetry available for this run.</p>
                  )}
                </section>
              </div>

              {toolUsageByTool.length > 0 && (
                <section className="overflow-x-auto">
                  <h3 className="text-sm font-medium text-muted mb-2">Tool latency summary</h3>
                  <table className="w-full text-xs">
                    <thead className="text-muted text-left">
                      <tr>
                        <th className="py-1">Tool</th>
                        <th>Calls</th>
                        <th>Errors</th>
                        <th>Avg latency</th>
                      </tr>
                    </thead>
                    <tbody>
                      {toolUsageByTool.map((row) => (
                        <tr key={row.tool} className="border-t border-slate-700/30">
                          <td className="py-1 font-mono">{row.tool}</td>
                          <td>{row.calls}</td>
                          <td className={row.errors > 0 ? "text-red-400" : "text-emerald-400"}>
                            {row.errors}
                          </td>
                          <td>{row.avgLatencyMs > 0 ? `${row.avgLatencyMs}ms` : "—"}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </section>
              )}

              {toolCallsByTime.length > 0 && (
                <section>
                  <h3 className="text-sm font-medium text-muted mb-2">Tool call outcomes over sequence</h3>
                  <div className="h-56 bg-panel/50 rounded-lg p-2">
                    <ResponsiveContainer width="100%" height="100%">
                      <BarChart data={toolCallsByTime}>
                        <CartesianGrid stroke="#334155" strokeDasharray="3 3" />
                        <XAxis dataKey="idx" tick={{ fill: "#8b9cb3", fontSize: 11 }} />
                        <YAxis tick={{ fill: "#8b9cb3", fontSize: 11 }} />
                        <Tooltip contentStyle={{ background: "#1a2332", border: "1px solid #334155" }} />
                        <Legend />
                        <Bar dataKey="ok" stackId="outcome" fill="#34d399" name="OK" />
                        <Bar dataKey="error" stackId="outcome" fill="#f87171" name="Error" />
                      </BarChart>
                    </ResponsiveContainer>
                  </div>
                </section>
              )}
            </>
          )}
        </div>
      )}

      {tab === "context" && runId && (
        <div className="space-y-4">
          <p className="text-xs text-muted max-w-3xl">
            Parent model input at the selected step (same as CLI <code className="text-[11px]">--show-context</code>
            ). Excludes sub-agent intermediates. Compacted tool results show markers only — open the{" "}
            <button type="button" onClick={() => setTab("events")} className="text-accent hover:underline">
              Events
            </button>{" "}
            tab or JSONL for full payloads.
          </p>
          <div className="flex flex-wrap items-center gap-4">
            <label className="text-sm text-muted">
              Parent step
              <input
                type="range"
                min={0}
                max={maxStep?.max_step_idx ?? 0}
                value={stepIdx}
                onChange={(e) => setStepIdx(Number(e.target.value))}
                className="ml-2 w-48"
              />
              <span className="ml-2 font-mono">{stepIdx}</span>
            </label>
            {(maxStep?.compaction_steps?.length ?? 0) > 0 && (
              <div className="flex flex-wrap items-center gap-2 text-xs">
                <span className="text-muted">Compaction at step:</span>
                {maxStep!.compaction_steps.map((s) => (
                  <button
                    key={s}
                    type="button"
                    onClick={() => setStepIdx(s)}
                    className={`px-2 py-0.5 rounded font-mono ${
                      stepIdx === s
                        ? "bg-amber-500/30 text-amber-200"
                        : "bg-panel border border-amber-500/30 text-amber-300/90 hover:text-amber-100"
                    }`}
                  >
                    {s}
                  </button>
                ))}
              </div>
            )}
            <label className="text-sm text-muted flex items-center gap-2 cursor-pointer">
              <input
                type="checkbox"
                checked={expandContext}
                onChange={(e) => setExpandContext(e.target.checked)}
                className="rounded"
              />
              Expand all messages
            </label>
          </div>
          <ul className="space-y-2 text-sm">
            {(context?.messages ?? []).map((m, i) => (
              <li
                key={i}
                className={`rounded p-3 border ${
                  m.compacted ? "border-amber-500/40 bg-amber-950/20" : "border-slate-700/40 bg-panel"
                }`}
              >
                <span className="text-muted text-xs">{m.role}</span>
                {m.tool && <span className="ml-2 text-cyan-300 text-xs">{m.tool}</span>}
                {m.compacted && <span className="ml-2 text-amber-300 text-xs">compacted</span>}
                {m.compacted && (
                  <CompactionStatsBadge
                    variant="block"
                    before={m.compaction_before_tokens}
                    after={m.compaction_after_tokens}
                  />
                )}
                <pre
                  className={`mt-1 whitespace-pre-wrap text-xs overflow-y-auto ${
                    expandContext ? "max-h-[32rem]" : "max-h-48"
                  }`}
                >
                  {m.content ?? ""}
                </pre>
              </li>
            ))}
            {!context?.messages?.length && (
              <li className="text-muted text-sm">No parent messages at this step yet.</li>
            )}
          </ul>
        </div>
      )}

      {tab === "tools" && timeline && (
        <div className="space-y-4">
          {toolErrors.length > 0 && (
            <section>
              <h3 className="text-sm text-red-400 mb-2">Errors ({toolErrors.length})</h3>
              <ul className="space-y-2 text-sm">
                {toolErrors.map((t) => (
                  <li
                    key={t.tool_call_id}
                    id={`tool-row-${t.tool_call_id}`}
                    className={`bg-red-950/30 border rounded p-2 ${
                      flashHighlight === t.tool_call_id
                        ? "border-red-400 ring-2 ring-red-400"
                        : "border-red-500/30"
                    }`}
                  >
                    <span className="font-mono">{t.tool}</span>: {t.error_type} — {t.error_message}
                    <p className="text-xs text-muted mt-1">
                      {t.started_at?.slice(0, 19) ?? "—"}
                    </p>
                  </li>
                ))}
              </ul>
            </section>
          )}
          <section>
            <h3 className="text-sm font-medium text-muted mb-2">All tool calls</h3>
            <table className="w-full text-xs">
              <thead className="text-muted text-left">
                <tr>
                  <th className="py-1">Tool</th>
                  <th>Status</th>
                  <th>Latency</th>
                  <th>Started</th>
                  <th>Summary</th>
                </tr>
              </thead>
              <tbody>
                {timeline.tool_calls.map((t) => (
                  <tr
                    key={t.tool_call_id}
                    id={`tool-row-${t.tool_call_id}`}
                    className={`border-t border-slate-700/30 ${
                      flashHighlight === t.tool_call_id ? "ring-2 ring-red-400 ring-inset" : ""
                    }`}
                  >
                    <td className="py-1">{t.tool}</td>
                    <td className={t.status === "ok" ? "text-emerald-400" : "text-red-400"}>{t.status}</td>
                    <td>{t.latency_ms ?? "—"}ms</td>
                    <td className="text-muted">{t.started_at?.slice(11, 19) ?? "—"}</td>
                    <td className="truncate max-w-md">{t.args_summary}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </section>
        </div>
      )}

      {tab === "safety" && safety && (
        <div className="grid md:grid-cols-2 gap-4 text-sm">
          <section>
            <h3 className="text-muted text-xs mb-2">Approvals</h3>
            <ul className="space-y-1">
              {safety.approvals.map((a) => (
                <li key={a.approval_id} className="bg-panel rounded px-2 py-1">
                  {a.tool}: {a.decision}
                </li>
              ))}
              {!safety.approvals.length && <li className="text-muted">None</li>}
            </ul>
          </section>
          <section>
            <h3 className="text-muted text-xs mb-2">Compactions</h3>
            <ul className="space-y-1">
              {safety.compactions.map((c) => (
                <li key={c.compaction_id} className="bg-amber-950/20 rounded px-2 py-1 space-y-0.5">
                  <span className="text-muted">#{c.original_event_idx}</span>
                  {c.before_tokens != null && c.after_tokens != null ? (
                    <CompactionStatsBadge variant="block" before={c.before_tokens} after={c.after_tokens} />
                  ) : (
                    <span className="text-xs text-muted">(token counts unavailable)</span>
                  )}
                </li>
              ))}
              {!safety.compactions.length && <li className="text-muted">None</li>}
            </ul>
          </section>
          <section>
            <h3 className="text-muted text-xs mb-2">Redactions</h3>
            <ul className="space-y-1">
              {safety.redactions.map((r) => (
                <li key={r.redaction_id} className="bg-panel rounded px-2 py-1">
                  {r.pattern} ×{r.count}
                </li>
              ))}
            </ul>
          </section>
          <section>
            <h3 className="text-muted text-xs mb-2">Budget events</h3>
            <ul className="space-y-1">
              {safety.budget_events.map((b) => (
                <li key={b.event_idx} className="bg-panel rounded px-2 py-1">
                  #{b.event_idx} {b.budget_reason}
                </li>
              ))}
            </ul>
          </section>
        </div>
      )}

      {tab === "events" && (
        <div className="flex flex-col flex-1 min-h-0">
          <EventFeed
            events={eventsData?.items ?? []}
            parallel={parallel ?? null}
            turns={detail.turns}
            highlightEventIdx={highlightEventIdx}
            onHighlightEventIdx={handleHighlightEventIdx}
          />
        </div>
      )}
    </div>
  );
}

function Kpi({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg border border-slate-700/50 bg-panel p-3">
      <p className="text-xs text-muted">{label}</p>
      <p className="text-base font-semibold mt-1">{value}</p>
    </div>
  );
}
