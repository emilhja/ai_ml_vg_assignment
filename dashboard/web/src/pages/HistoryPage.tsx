import { useQuery } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { api, type SessionSummary } from "../api";
import {
  filterSessions,
  loadSessionFilters,
  saveSessionFilters,
  SESSION_FILTER_OPTIONS,
  type SessionSubagentFilter,
} from "../lib/sessionFilters";

function SubagentBadges({ session }: { session: SessionSummary }) {
  if (!session.has_subagents) {
    return <span className="text-[10px] text-muted">parent only</span>;
  }
  return (
    <span className="flex flex-wrap gap-1">
      {session.has_parallel_subagents && (
        <span className="text-[10px] uppercase tracking-wide px-1 py-0.5 rounded bg-violet-500/25 text-violet-300">
          parallel
        </span>
      )}
      {session.has_sequential_subagents && (
        <span className="text-[10px] uppercase tracking-wide px-1 py-0.5 rounded bg-slate-600/40 text-slate-300">
          sequential
        </span>
      )}
    </span>
  );
}

export default function HistoryPage() {
  const [activeFilters, setActiveFilters] = useState<Set<SessionSubagentFilter>>(loadSessionFilters);

  const { data, isLoading, error, isError } = useQuery({
    queryKey: ["sessions"],
    queryFn: () => api.sessions(200),
    retry: 2,
  });

  const toggleFilter = (id: SessionSubagentFilter) => {
    setActiveFilters((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      saveSessionFilters(next);
      return next;
    });
  };

  const clearFilters = () => {
    const next = new Set<SessionSubagentFilter>();
    saveSessionFilters(next);
    setActiveFilters(next);
  };

  const filteredItems = useMemo(
    () => filterSessions(data?.items ?? [], activeFilters),
    [data?.items, activeFilters],
  );

  if (isLoading) return <p className="text-muted">Loading sessions…</p>;
  if (isError) {
    return (
      <div className="space-y-2">
        <p className="text-red-400">Cannot load sessions: {(error as Error).message}</p>
        <p className="text-sm text-muted">
          Is the API running on port 8787? Check http://127.0.0.1:8787/api/v1/health
        </p>
      </div>
    );
  }

  const total = data?.total ?? 0;
  const showing = filteredItems.length;

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <h2 className="text-lg font-medium">
          Sessions ({showing}
          {activeFilters.size > 0 && total !== showing ? ` of ${total}` : ""})
        </h2>
        {activeFilters.size > 0 && (
          <button
            type="button"
            onClick={clearFilters}
            className="text-xs text-muted hover:text-white"
          >
            Clear filters
          </button>
        )}
      </div>

      <div className="space-y-2">
        <p className="text-xs text-muted">Show sessions with:</p>
        <div className="flex flex-wrap gap-2">
          {SESSION_FILTER_OPTIONS.map((opt) => {
            const on = activeFilters.has(opt.id);
            return (
              <button
                key={opt.id}
                type="button"
                title={opt.hint}
                onClick={() => toggleFilter(opt.id)}
                className={`px-3 py-1.5 rounded-full text-xs border transition-colors ${
                  on
                    ? "bg-accent/25 border-accent/50 text-accent"
                    : "bg-panel/60 border-slate-700/50 text-muted hover:border-slate-500 hover:text-white"
                }`}
              >
                {opt.label}
              </button>
            );
          })}
        </div>
        {activeFilters.size > 0 && (
          <p className="text-[11px] text-muted">
            Matching any selected category. Select none to show all sessions.
          </p>
        )}
      </div>

      {total === 0 && (
        <p className="text-sm text-muted">
          No traces found. Run the agent once, then confirm JSONL files exist under{" "}
          <code className="text-xs">workspace/traces/</code> or <code className="text-xs">traces/</code>.
        </p>
      )}

      {total > 0 && showing === 0 && (
        <p className="text-sm text-muted">No sessions match the selected filters.</p>
      )}

      <div className="overflow-x-auto rounded-lg border border-slate-700/50">
        <table className="w-full text-sm">
          <thead className="bg-panel text-muted text-left">
            <tr>
              <th className="px-4 py-2">Session</th>
              <th className="px-4 py-2">Sub-agents</th>
              <th className="px-4 py-2">Last seen</th>
              <th className="px-4 py-2">Status</th>
              <th className="px-4 py-2">Turns</th>
              <th className="px-4 py-2">Tokens</th>
              <th className="px-4 py-2">USD</th>
            </tr>
          </thead>
          <tbody>
            {filteredItems.map((s) => (
              <tr key={s.session_id} className="border-t border-slate-700/40 hover:bg-panel/40">
                <td className="px-4 py-2">
                  <Link to={`/history/${s.session_id}`} className="text-accent hover:underline font-medium">
                    {s.display_name?.trim() || `${s.session_id.slice(0, 12)}…`}
                  </Link>
                  <p className="text-xs text-muted font-mono truncate max-w-md">{s.session_id}</p>
                  {s.last_prompt_snippet && (
                    <p className="text-xs text-muted truncate max-w-md">{s.last_prompt_snippet}</p>
                  )}
                </td>
                <td className="px-4 py-2">
                  <SubagentBadges session={s} />
                </td>
                <td className="px-4 py-2 text-muted">{s.last_seen_at?.slice(0, 19) ?? "—"}</td>
                <td className="px-4 py-2">
                  {s.status ?? "—"}
                  {s.status === "jsonl_only" && (
                    <span className="ml-1 text-xs text-amber-300/80">(JSONL)</span>
                  )}
                </td>
                <td className="px-4 py-2">{s.total_turns}</td>
                <td className="px-4 py-2">{s.total_tokens.toLocaleString()}</td>
                <td className="px-4 py-2">${s.total_cost_usd.toFixed(4)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
