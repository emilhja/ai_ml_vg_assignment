import { useEffect, useState } from "react";
import type { CompactionUnit } from "../lib/compactionUnits";
import { compactionUnitEventIndices } from "../lib/compactionUnits";
import type { TimeAnchors } from "../lib/groupEvents";
import { formatCompactionLine } from "../lib/compactionStats";
import { formatTokenCount, summarizeLaneTokens } from "../lib/laneStats";
import CompactionStatsBadge from "./CompactionStatsBadge";
import EventRow from "./EventRow";

type Props = {
  unit: CompactionUnit;
  anchors: TimeAnchors;
  highlightEventIdx?: number | null;
  onHighlightEventIdx?: (eventIdx: number) => void;
};

function payloadNum(event: CompactionUnit["compaction"], key: string): number | null {
  const v = event.payload[key];
  if (typeof v === "number" && !Number.isNaN(v)) return v;
  if (typeof v === "string" && v.trim() !== "") {
    const n = Number(v);
    return Number.isNaN(n) ? null : n;
  }
  return null;
}

export default function CompactionUnitCard({
  unit,
  anchors,
  highlightEventIdx = null,
  onHighlightEventIdx,
}: Props) {
  const { compaction, compactorEvents, originalToolResult } = unit;
  const indices = compactionUnitEventIndices(unit);
  const shouldAutoOpen =
    highlightEventIdx != null && indices.includes(highlightEventIdx);
  const [stepsOpen, setStepsOpen] = useState(shouldAutoOpen || compactorEvents.length <= 2);

  useEffect(() => {
    if (shouldAutoOpen) setStepsOpen(true);
  }, [shouldAutoOpen]);

  const before = payloadNum(compaction, "before_tokens");
  const after = payloadNum(compaction, "after_tokens");
  const isContext = compaction.kind === "context_compaction";
  const reason = compaction.payload.reason;
  const llmStart = compactorEvents.find((e) => e.kind === "llm_start");
  const compactorModel =
    (compaction.payload.compactor_model as string | undefined) ??
    (typeof llmStart?.payload.model === "string" ? llmStart.payload.model : undefined) ??
    (typeof llmStart?.payload.model_id === "string" ? llmStart.payload.model_id : undefined);
  const fallback = compaction.payload.compactor_fallback === true;
  const compactorStats = summarizeLaneTokens(compactorEvents);
  const compactorCost = compactorEvents.reduce((sum, e) => {
    if (e.kind !== "assistant_step") return sum;
    return sum + (e.cost_usd ?? (typeof e.payload.cost_usd === "number" ? e.payload.cost_usd : 0));
  }, 0);

  const title = isContext
    ? `Context compaction${reason != null ? ` (${String(reason)})` : ""}`
    : "Tool-result compaction";

  const summarySnippet =
    typeof compaction.payload.summary === "string"
      ? compaction.payload.summary.trim().slice(0, 280)
      : null;

  const highlightClass =
    shouldAutoOpen && stepsOpen ? "ring-1 ring-violet-500/40" : "";

  return (
    <li
      id={`event-${compaction.event_idx}`}
      className={`rounded border border-amber-500/40 bg-amber-950/25 overflow-hidden ${highlightClass}`}
    >
      <div className="px-3 py-2 space-y-1.5">
        <div className="flex flex-wrap gap-2 items-center">
          <span className="text-[10px] uppercase tracking-wide text-amber-300/90 font-semibold">
            {title}
          </span>
          <span className="text-muted">#{compaction.event_idx}</span>
          {compactorEvents.length > 0 && (
            <span className="text-muted text-[10px]">
              compactor #{compactorEvents[0]?.event_idx}
              {compactorEvents.length > 1
                ? `–${compactorEvents[compactorEvents.length - 1]?.event_idx}`
                : ""}
            </span>
          )}
        </div>
        <CompactionStatsBadge before={before} after={after} variant="block" />
        {formatCompactionLine(before, after) == null && (
          <p className="text-xs text-muted">Compaction stats unavailable</p>
        )}
        <div className="flex flex-wrap gap-x-3 gap-y-1 text-[10px] font-mono text-slate-400">
          {compactorModel != null && (
            <span>
              <span className="text-muted">model · </span>
              <span className="text-slate-300">{String(compactorModel)}</span>
            </span>
          )}
          {fallback && (
            <span className="text-amber-400/90">stub fallback</span>
          )}
          {(compactorStats.tokensIn > 0 || compactorStats.tokensOut > 0) && (
            <span className="text-amber-200/80 tabular-nums">
              compactor LLM · in {formatTokenCount(compactorStats.tokensIn)} · out{" "}
              {formatTokenCount(compactorStats.tokensOut)}
              {compactorCost > 0 ? ` · $${compactorCost.toFixed(4)}` : ""}
            </span>
          )}
        </div>
        {summarySnippet && (
          <p className="text-xs text-slate-300 line-clamp-3">{summarySnippet}</p>
        )}
        {originalToolResult && onHighlightEventIdx && (
          <button
            type="button"
            className="text-[10px] text-accent hover:underline"
            onClick={() => onHighlightEventIdx(originalToolResult.event_idx)}
          >
            View original tool_result #{originalToolResult.event_idx}
            {originalToolResult.tool ? ` (${originalToolResult.tool})` : ""}
          </button>
        )}
        {compactorEvents.length > 0 && (
          <button
            type="button"
            onClick={() => setStepsOpen((v) => !v)}
            className="text-[10px] text-violet-400 hover:text-violet-300"
          >
            {stepsOpen ? "▼ hide compactor steps" : `▶ compactor steps (${compactorEvents.length})`}
          </button>
        )}
      </div>
      {stepsOpen && compactorEvents.length > 0 && (
        <ul className="px-3 pb-3 space-y-2 border-t border-amber-500/20 pt-2 font-mono text-xs">
          {compactorEvents.map((e) => (
            <EventRow
              key={`${e.run_id}-${e.event_idx}`}
              event={e}
              anchors={anchors}
              highlightEventIdx={highlightEventIdx}
            />
          ))}
        </ul>
      )}
    </li>
  );
}
