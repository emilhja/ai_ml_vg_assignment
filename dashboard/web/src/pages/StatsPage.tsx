import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router-dom";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { api, type ToolErrorOccurrence } from "../api";

const RANGES = [
  { id: "today", label: "Today" },
  { id: "7d", label: "7 days" },
  { id: "30d", label: "30 days" },
] as const;

function toolErrorHref(occ: ToolErrorOccurrence): string {
  const params = new URLSearchParams({
    tab: "tools",
    runId: occ.run_id,
    highlight: occ.tool_call_id,
  });
  return `/history/${occ.session_id}?${params.toString()}`;
}

function sessionHref(sessionId: string | null | undefined): string | undefined {
  if (!sessionId) return undefined;
  return `/history/${sessionId}`;
}

function expensiveTurnHref(turn: { session_id: string; run_id: string }): string {
  const params = new URLSearchParams({ tab: "tools", runId: turn.run_id });
  return `/history/${turn.session_id}?${params.toString()}`;
}

export default function StatsPage() {
  const [range, setRange] = useState<string>("7d");
  const [expandedTools, setExpandedTools] = useState<Set<string>>(new Set());
  const [drillTool, setDrillTool] = useState<string | null>(null);

  const { data: stats, isLoading, isError, error } = useQuery({
    queryKey: ["stats", range],
    queryFn: () => api.stats(range),
  });
  const { data: finops } = useQuery({
    queryKey: ["finops"],
    queryFn: api.finops,
  });
  const { data: drillData } = useQuery({
    queryKey: ["stats-tool-errors", range, drillTool],
    queryFn: () => api.statsToolErrors(range, drillTool!),
    enabled: !!drillTool,
  });

  if (isLoading || !stats) return <p className="text-muted">Loading statistics…</p>;

  if (isError) {
    return (
      <div className="space-y-2">
        <p className="text-red-400">Cannot load statistics: {(error as Error).message}</p>
        <p className="text-sm text-muted">
          Is the API running on port 8787? Check http://127.0.0.1:8787/api/v1/health
        </p>
      </div>
    );
  }

  const toggleTool = (tool: string) => {
    setExpandedTools((prev) => {
      const next = new Set(prev);
      if (next.has(tool)) next.delete(tool);
      else next.add(tool);
      return next;
    });
  };

  return (
    <div className="space-y-8">
      <div className="flex gap-2">
        {RANGES.map((r) => (
          <button
            key={r.id}
            type="button"
            onClick={() => setRange(r.id)}
            className={`px-3 py-1.5 rounded text-sm ${
              range === r.id ? "bg-accent/25 text-accent" : "text-muted hover:text-white"
            }`}
          >
            {r.label}
          </button>
        ))}
      </div>

      {finops && (
        <div className="rounded-lg border border-slate-700/50 bg-panel p-4 text-sm">
          <p className="text-muted text-xs">Daily spend (UTC)</p>
          <p>
            ${finops.today_spent_usd.toFixed(4)} / ${finops.daily_cap_usd.toFixed(2)} cap · $
            {finops.remaining_usd.toFixed(4)} remaining
          </p>
        </div>
      )}

      <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
        <Kpi label="Runs" value={String(stats.total_runs)} />
        <Kpi label="Turns" value={String(stats.total_turns)} />
        <Kpi label="Tokens" value={stats.total_tokens.toLocaleString()} />
        <Kpi label="Cost" value={`$${stats.total_cost_usd.toFixed(4)}`} />
        <Kpi label="Error rate" value={`${(stats.error_rate * 100).toFixed(1)}%`} />
      </div>

      <section>
        <h3 className="text-sm text-muted mb-3">Activity by day</h3>
        <div className="h-64 bg-panel/50 rounded-lg p-2">
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={stats.by_day}>
              <CartesianGrid stroke="#334155" strokeDasharray="3 3" />
              <XAxis dataKey="date" tick={{ fill: "#8b9cb3", fontSize: 11 }} />
              <YAxis tick={{ fill: "#8b9cb3", fontSize: 11 }} />
              <Tooltip contentStyle={{ background: "#1a2332", border: "1px solid #334155" }} />
              <Line type="monotone" dataKey="tokens" stroke="#e07a5f" dot={false} name="Tokens" />
              <Line type="monotone" dataKey="cost_usd" stroke="#34d399" dot={false} name="Cost USD" />
              <Line type="monotone" dataKey="runs" stroke="#818cf8" dot={false} name="Runs" />
            </LineChart>
          </ResponsiveContainer>
        </div>
      </section>

      <div className="grid lg:grid-cols-2 gap-8">
        <section>
          <h3 className="text-sm text-muted mb-3">Cost by model</h3>
          <div className="h-56 bg-panel/50 rounded-lg p-2">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={stats.by_model.slice(0, 10)} layout="vertical">
                <CartesianGrid stroke="#334155" strokeDasharray="3 3" />
                <XAxis type="number" tick={{ fill: "#8b9cb3", fontSize: 11 }} />
                <YAxis
                  type="category"
                  dataKey="label"
                  width={180}
                  tick={{ fill: "#8b9cb3", fontSize: 10 }}
                />
                <Tooltip contentStyle={{ background: "#1a2332", border: "1px solid #334155" }} />
                <Bar dataKey="cost_usd" fill="#e07a5f" />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </section>

        {stats.by_agent_type.length > 0 && (
          <section>
            <h3 className="text-sm text-muted mb-3">Cost by agent id</h3>
            <div className="h-56 bg-panel/50 rounded-lg p-2">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={stats.by_agent_type.slice(0, 10)} layout="vertical">
                  <CartesianGrid stroke="#334155" strokeDasharray="3 3" />
                  <XAxis type="number" tick={{ fill: "#8b9cb3", fontSize: 11 }} />
                  <YAxis
                    type="category"
                    dataKey="label"
                    width={120}
                    tick={{ fill: "#8b9cb3", fontSize: 10 }}
                  />
                  <Tooltip contentStyle={{ background: "#1a2332", border: "1px solid #334155" }} />
                  <Bar dataKey="cost_usd" fill="#818cf8" />
                </BarChart>
              </ResponsiveContainer>
            </div>
          </section>
        )}
      </div>

      {stats.by_tool.length > 0 && (
        <section>
          <h3 className="text-sm text-muted mb-3">Tool usage</h3>
          <div className="overflow-x-auto rounded-lg border border-slate-700/50">
            <table className="w-full text-sm">
              <thead className="bg-panel text-muted text-left">
                <tr>
                  <th className="px-3 py-2">Tool</th>
                  <th className="px-3 py-2">Calls</th>
                  <th className="px-3 py-2">Errors</th>
                  <th className="px-3 py-2">Avg latency</th>
                </tr>
              </thead>
              <tbody>
                {stats.by_tool.map((row) => (
                  <tr key={row.tool} className="border-t border-slate-700/40">
                    <td className="px-3 py-2 font-mono">{row.tool}</td>
                    <td className="px-3 py-2">{row.count}</td>
                    <td className={`px-3 py-2 ${row.error_count > 0 ? "text-red-400" : ""}`}>
                      {row.error_count}
                    </td>
                    <td className="px-3 py-2 text-muted">
                      {row.avg_latency_ms != null ? `${row.avg_latency_ms}ms` : "—"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}

      <div className="grid lg:grid-cols-2 gap-8">
        <Leaderboard
          title="Most common user prompts"
          items={stats.top_user_prompts}
          emptyLabel="No user prompts in this range."
        />
        <Leaderboard
          title="Most common explorer questions"
          items={stats.top_subagent_questions}
          emptyLabel="No sub-agent questions in this range."
        />
      </div>

      <section>
        <h3 className="text-sm text-muted mb-3">Most expensive turns</h3>
        {stats.top_expensive_turns.length === 0 ? (
          <p className="text-sm text-muted">No turns with cost data in this range.</p>
        ) : (
          <div className="overflow-x-auto rounded-lg border border-slate-700/50">
            <table className="w-full text-sm">
              <thead className="bg-panel text-muted text-left">
                <tr>
                  <th className="px-3 py-2">#</th>
                  <th className="px-3 py-2">Prompt</th>
                  <th className="px-3 py-2">Cost</th>
                  <th className="px-3 py-2">Tokens</th>
                  <th className="px-3 py-2">When</th>
                </tr>
              </thead>
              <tbody>
                {stats.top_expensive_turns.map((turn, i) => (
                  <tr key={turn.turn_id} className="border-t border-slate-700/40 hover:bg-panel/40">
                    <td className="px-3 py-2 text-muted">{i + 1}</td>
                    <td className="px-3 py-2 max-w-md">
                      <Link
                        to={expensiveTurnHref(turn)}
                        className="text-accent hover:underline line-clamp-2"
                      >
                        {turn.prompt_snippet || "(no prompt)"}
                      </Link>
                    </td>
                    <td className="px-3 py-2 font-mono">${turn.total_cost_usd.toFixed(4)}</td>
                    <td className="px-3 py-2">{turn.total_tokens.toLocaleString()}</td>
                    <td className="px-3 py-2 text-muted text-xs">
                      {turn.started_at?.slice(0, 16) ?? "—"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      <section>
        <h3 className="text-sm text-muted mb-3">Tool errors</h3>
        {stats.tool_error_groups.length === 0 ? (
          <p className="text-sm text-muted">No tool errors in this range.</p>
        ) : (
          <ul className="space-y-2 text-sm">
            {stats.tool_error_groups.map((group) => {
              const expanded = expandedTools.has(group.tool);
              const showDrill = drillTool === group.tool;
              return (
                <li key={group.tool} className="rounded-lg border border-slate-700/50 bg-panel overflow-hidden">
                  <button
                    type="button"
                    onClick={() => toggleTool(group.tool)}
                    className="w-full flex justify-between items-center px-3 py-2 hover:bg-slate-800/40 text-left"
                  >
                    <span className="font-mono">{group.tool}</span>
                    <span className="text-red-400">{group.count} errors</span>
                  </button>
                  {expanded && (
                    <ul className="border-t border-slate-700/40 divide-y divide-slate-700/30">
                      {group.occurrences.map((occ) => (
                        <li key={occ.tool_call_id} className="px-3 py-2">
                          <Link
                            to={toolErrorHref(occ)}
                            className="text-accent hover:underline block"
                          >
                            <span className="text-red-300">{occ.error_type ?? "error"}</span>
                            {occ.error_message && (
                              <span className="text-muted"> — {occ.error_message}</span>
                            )}
                          </Link>
                          <p className="text-xs text-muted mt-0.5 font-mono">
                            {occ.started_at?.slice(0, 19) ?? ""} · {occ.session_id.slice(0, 8)}…
                          </p>
                        </li>
                      ))}
                      {group.count > group.occurrences.length && (
                        <li className="px-3 py-2">
                          <button
                            type="button"
                            className="text-xs text-accent hover:underline"
                            onClick={() => setDrillTool(showDrill ? null : group.tool)}
                          >
                            {showDrill ? "Hide" : "Show all"} {group.count} occurrences
                          </button>
                          {showDrill && drillData && (
                            <ul className="mt-2 space-y-2">
                              {drillData.items.map((occ) => (
                                <li key={occ.tool_call_id}>
                                  <Link to={toolErrorHref(occ)} className="text-accent hover:underline text-xs">
                                    {occ.error_type}: {occ.error_message}
                                  </Link>
                                </li>
                              ))}
                            </ul>
                          )}
                        </li>
                      )}
                    </ul>
                  )}
                </li>
              );
            })}
          </ul>
        )}
      </section>
    </div>
  );
}

function Kpi({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg border border-slate-700/50 bg-panel p-4">
      <p className="text-xs text-muted">{label}</p>
      <p className="text-lg font-semibold mt-1">{value}</p>
    </div>
  );
}

function Leaderboard({
  title,
  items,
  emptyLabel,
}: {
  title: string;
  items: { label: string; count: number; sample_session_id: string | null }[];
  emptyLabel: string;
}) {
  return (
    <section>
      <h3 className="text-sm text-muted mb-3">{title}</h3>
      {items.length === 0 ? (
        <p className="text-sm text-muted">{emptyLabel}</p>
      ) : (
        <ul className="space-y-1 text-sm">
          {items.map((item) => {
            const href = sessionHref(item.sample_session_id);
            return (
              <li
                key={item.label}
                className="flex justify-between gap-3 bg-panel rounded px-3 py-2 border border-slate-700/40"
              >
                {href ? (
                  <Link to={href} className="text-accent hover:underline line-clamp-2 flex-1">
                    {item.label}
                  </Link>
                ) : (
                  <span className="line-clamp-2 flex-1">{item.label}</span>
                )}
                <span className="text-muted shrink-0">×{item.count}</span>
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}
