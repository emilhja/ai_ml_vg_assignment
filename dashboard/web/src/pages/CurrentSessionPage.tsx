import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { api } from "../api";
import EventFeed from "../components/EventFeed";
import { SessionCard } from "../components/SessionCards";
import { useSessionStream } from "../hooks/useSessionStream";

export default function CurrentSessionPage() {
  const { data, isLoading, error, isError } = useQuery({
    queryKey: ["activeSession"],
    queryFn: api.activeSession,
    refetchInterval: 5_000,
    retry: 2,
  });

  const sessionId = data?.session_id ?? null;
  const { events, connected, statusline } = useSessionStream(sessionId);

  const displayEvents =
    events.length > 0 ? events : (data?.recent_events ?? []);

  const runs = data?.session?.runs ?? [];
  const runId = runs[runs.length - 1]?.run_id ?? runs[0]?.run_id ?? "";

  const { data: parallel } = useQuery({
    queryKey: ["parallel", runId],
    queryFn: () => api.parallel(runId),
    enabled: !!runId,
  });

  if (isLoading) return <p className="text-muted">Loading active session…</p>;
  if (isError) {
    return (
      <div className="space-y-2">
        <p className="text-red-400">Cannot reach dashboard API: {(error as Error).message}</p>
        <p className="text-sm text-muted">
          Start the API on port 8787 and ensure Vite proxies <code className="text-xs">/api</code>{" "}
          (npm run dev in dashboard/web).
        </p>
      </div>
    );
  }

  if (!sessionId) {
    return (
      <div className="space-y-4">
        <p className="text-muted">
          No active session detected. Run <code className="text-xs">vg-agent --chat</code> in your
          workspace (traces land in <code className="text-xs">workspace/traces/</code> or{" "}
          <code className="text-xs">traces/</code> at the repo root).
        </p>
        <Link to="/history" className="text-accent hover:underline text-sm">
          Browse history →
        </Link>
      </div>
    );
  }

  const sessionMeta = data?.session?.session;

  return (
    <div className="flex flex-col flex-1 min-h-0 gap-4">
      <div className="shrink-0 flex items-center gap-3 flex-wrap">
        <span
          className={`inline-flex h-2.5 w-2.5 rounded-full ${connected ? "bg-emerald-400" : "bg-red-500"}`}
          title={connected ? "SSE connected" : "SSE disconnected"}
        />
        <span className="text-sm text-muted font-mono">{sessionId}</span>
        <span className="text-sm text-muted">
          {connected ? "Live" : "Reconnecting…"}
        </span>
        <Link
          to={`/history/${sessionId}`}
          className="ml-auto text-sm text-accent hover:underline"
        >
          Open full detail →
        </Link>
      </div>
      {sessionMeta ? (
        <SessionCard session={sessionMeta} />
      ) : (
        <p className="text-sm text-amber-200/90">
          Session trace found (JSONL). SQLite rollups may be missing — showing live events below.
        </p>
      )}
      {statusline && (
        <pre className="shrink-0 text-xs bg-panel border border-slate-700/50 rounded p-3 overflow-x-auto text-emerald-200/90">
          {statusline}
        </pre>
      )}
      <section className="flex flex-col flex-1 min-h-0">
        <h2 className="shrink-0 text-sm font-medium text-muted mb-2">Event stream</h2>
        <EventFeed events={displayEvents} parallel={parallel ?? null} />
      </section>
    </div>
  );
}
