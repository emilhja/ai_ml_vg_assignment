import { useQuery } from "@tanstack/react-query";
import { useEffect, useMemo, useState } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";
import { api } from "../api";
import EventFeed from "../components/EventFeed";
import { SessionCard } from "../components/SessionCards";

const TAB_IDS = ["timeline", "context", "tools", "safety", "events"] as const;
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

  const { data: detail, isLoading } = useQuery({
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
    enabled: !!runId && (tab === "timeline" || tab === "tools"),
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

  useEffect(() => {
    if (tab !== "events" || highlightEventIdx == null) return;
    const el = document.getElementById(`event-${highlightEventIdx}`);
    if (el) {
      el.scrollIntoView({ behavior: "smooth", block: "center" });
    }
  }, [tab, highlightEventIdx, eventsData]);

  if (isLoading || !detail) {
    return <p className="text-muted">Loading session…</p>;
  }

  const tabs: { id: Tab; label: string }[] = [
    { id: "timeline", label: "Timeline" },
    { id: "context", label: "Context" },
    { id: "tools", label: "Tools & errors" },
    { id: "safety", label: "Safety / FinOps" },
    { id: "events", label: "Events" },
  ];

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

      {tab === "context" && runId && (
        <div className="space-y-4">
          <div className="flex items-center gap-4">
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
                <pre className="mt-1 whitespace-pre-wrap text-xs max-h-48 overflow-y-auto">
                  {m.content ?? ""}
                </pre>
              </li>
            ))}
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
                <li key={c.compaction_id} className="bg-amber-950/20 rounded px-2 py-1">
                  #{c.original_event_idx}: {c.before_tokens}→{c.after_tokens} tokens
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
          />
        </div>
      )}
    </div>
  );
}
