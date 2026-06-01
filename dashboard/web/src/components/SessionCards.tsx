import type { SessionSummary } from "../api";
import SessionTitleEditor from "./SessionTitleEditor";

export function SessionCard({ session }: { session: SessionSummary }) {
  return (
    <div className="rounded-lg border border-slate-700/50 bg-panel p-4 space-y-4">
      <SessionTitleEditor session={session} />
      <div className="grid grid-cols-2 md:grid-cols-3 gap-3 text-sm">
        <div>
          <p className="text-muted text-xs">Status</p>
          <p>{session.status ?? "—"}</p>
        </div>
        <div>
          <p className="text-muted text-xs">Tokens</p>
          <p>{session.total_tokens.toLocaleString()}</p>
        </div>
        <div>
          <p className="text-muted text-xs">Cost</p>
          <p>${session.total_cost_usd.toFixed(4)}</p>
        </div>
      </div>
    </div>
  );
}
