import { useEffect, useState } from "react";
import type { ParallelResponse } from "../api";
import {
  formatTurnTimeRange,
  turnHasParallelOverlap,
  type TimeAnchors,
  type TurnGroup,
} from "../lib/groupEvents";
import { formatTurnStatsLine, summarizeTurnStats, type TurnRollup } from "../lib/laneStats";
import EventRow from "./EventRow";
import ParallelTurnLayout from "./ParallelTurnLayout";

type Props = {
  group: TurnGroup;
  viewAgents: boolean;
  parallelColumns: boolean;
  parallel: ParallelResponse | null | undefined;
  sessionStart: string | null;
  turnRollup?: TurnRollup | null;
  highlightEventIdx?: number | null;
  onHighlightEventIdx?: (eventIdx: number) => void;
  defaultExpanded?: boolean;
};

export default function TurnSection({
  group,
  viewAgents,
  parallelColumns,
  parallel,
  sessionStart,
  turnRollup = null,
  highlightEventIdx = null,
  onHighlightEventIdx,
  defaultExpanded = true,
}: Props) {
  const [expanded, setExpanded] = useState(defaultExpanded);
  useEffect(() => {
    if (
      highlightEventIdx != null &&
      group.events.some((e) => e.event_idx === highlightEventIdx)
    ) {
      setExpanded(true);
    }
  }, [highlightEventIdx, group.events]);
  const overlap = turnHasParallelOverlap(group.turnIndex, group.events, parallel);
  const timeRange = formatTurnTimeRange(group.startedAt, group.endedAt);
  const statsLine = formatTurnStatsLine(summarizeTurnStats(group.events, turnRollup));
  const turnAnchors: TimeAnchors = {
    sessionStart,
    turnStart: group.startedAt,
  };

  return (
    <section className="border-l-4 border-accent/50 rounded-r bg-panel/30 border border-slate-700/40 overflow-hidden">
      <button
        type="button"
        onClick={() => setExpanded((v) => !v)}
        className="w-full text-left px-4 py-3 hover:bg-panel/50 transition-colors"
      >
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-sm font-semibold text-white">{group.label}</span>
          {overlap && (
            <span className="text-[10px] uppercase tracking-wide px-1.5 py-0.5 rounded bg-violet-500/25 text-violet-300">
              parallel
            </span>
          )}
          <span className="text-xs text-muted">{group.events.length} events</span>
          {statsLine && (
            <span className="text-[10px] font-mono text-amber-200/80 tabular-nums">{statsLine}</span>
          )}
          {timeRange && <span className="text-[10px] font-mono text-slate-500">{timeRange}</span>}
          <span className="ml-auto text-muted text-xs">{expanded ? "▼" : "▶"}</span>
        </div>
        {group.prompt && (
          <p className="mt-1 text-xs text-slate-300 line-clamp-2">{group.prompt}</p>
        )}
      </button>
      {expanded && (
        <div className="px-4 pb-4 pt-0">
          {viewAgents ? (
            <ParallelTurnLayout
              turnEvents={group.events}
              anchors={turnAnchors}
              parallelColumns={parallelColumns && overlap}
              highlightEventIdx={highlightEventIdx}
              onHighlightEventIdx={onHighlightEventIdx}
            />
          ) : (
            <ul className="space-y-2 font-mono text-xs">
              {group.events.map((e) => (
                <EventRow
                  key={`${e.run_id}-${e.event_idx}`}
                  event={e}
                  anchors={turnAnchors}
                  showSessionRelative
                  highlightEventIdx={highlightEventIdx}
                />
              ))}
            </ul>
          )}
        </div>
      )}
    </section>
  );
}
