import { useMemo } from "react";
import type { EventItem } from "../api";
import { prepareTurnAgentLanes } from "../lib/compactionUnits";
import { parallelBatchLaneIds, type TimeAnchors } from "../lib/groupEvents";
import AgentLane from "./AgentLane";
import CompactionUnitCard from "./CompactionUnitCard";
import EventRow from "./EventRow";

type Props = {
  turnEvents: EventItem[];
  anchors: TimeAnchors;
  parallelColumns: boolean;
  highlightEventIdx?: number | null;
  onHighlightEventIdx?: (eventIdx: number) => void;
};

export default function ParallelTurnLayout({
  turnEvents,
  anchors,
  parallelColumns,
  highlightEventIdx = null,
  onHighlightEventIdx,
}: Props) {
  const { lanes, unitByCompactionIdx } = useMemo(
    () => prepareTurnAgentLanes(turnEvents),
    [turnEvents],
  );

  const parentSorted = useMemo(
    () => [...lanes.parent].sort((a, b) => a.event_idx - b.event_idx),
    [lanes.parent],
  );

  const batchLaneIds = useMemo(() => parallelBatchLaneIds(turnEvents), [turnEvents]);

  const { batchEntries, otherEntries } = useMemo(() => {
    const entries = [...lanes.subagents.entries()].sort((a, b) => {
      const ai = a[1][0]?.event_idx ?? 0;
      const bi = b[1][0]?.event_idx ?? 0;
      return ai - bi;
    });
    if (!batchLaneIds) {
      return { batchEntries: [] as [string, EventItem[]][], otherEntries: entries };
    }
    const batch = entries.filter(([laneId]) => batchLaneIds.has(laneId));
    const rest = entries.filter(([laneId]) => !batchLaneIds.has(laneId));
    return { batchEntries: batch, otherEntries: rest };
  }, [lanes.subagents, batchLaneIds]);

  const showParallelRow = parallelColumns && batchEntries.length >= 2;

  return (
    <div className="space-y-3">
      {parentSorted.length > 0 && (
        <ul className="space-y-2 font-mono text-xs">
          {parentSorted.map((e) => {
            const unit = unitByCompactionIdx.get(e.event_idx);
            if (unit) {
              return (
                <CompactionUnitCard
                  key={`${e.run_id}-unit-${e.event_idx}`}
                  unit={unit}
                  anchors={anchors}
                  highlightEventIdx={highlightEventIdx}
                  onHighlightEventIdx={onHighlightEventIdx}
                />
              );
            }
            return (
              <EventRow
                key={`${e.run_id}-${e.event_idx}`}
                event={e}
                anchors={anchors}
                highlightEventIdx={highlightEventIdx}
              />
            );
          })}
        </ul>
      )}
      {showParallelRow && (
        <div className="rounded-md border border-violet-500/35 bg-violet-950/20 p-3">
          <p className="text-[10px] uppercase tracking-wide text-violet-300 mb-2">
            Parallel explorers ({batchEntries.length}) · overlapping wall-clock
          </p>
          <div className="flex flex-wrap gap-3 overflow-x-auto pb-1 items-start">
            {batchEntries.map(([laneId, evs]) => (
              <AgentLane
                key={laneId}
                laneId={laneId}
                events={evs}
                anchors={anchors}
                column
                highlightEventIdx={highlightEventIdx}
              />
            ))}
          </div>
        </div>
      )}
      {!showParallelRow && batchEntries.length > 0 && (
        <div className="space-y-3">
          {batchEntries.map(([laneId, evs]) => (
            <AgentLane
              key={laneId}
              laneId={laneId}
              events={evs}
              anchors={anchors}
              column={false}
              highlightEventIdx={highlightEventIdx}
            />
          ))}
        </div>
      )}
      {otherEntries.length > 0 && (
        <div className={showParallelRow ? "space-y-3 pt-1 border-t border-slate-700/40" : "space-y-3"}>
          {showParallelRow && otherEntries.length > 0 && (
            <p className="text-[10px] uppercase tracking-wide text-muted">Later sub-agents</p>
          )}
          {otherEntries.map(([laneId, evs]) => (
            <AgentLane
              key={laneId}
              laneId={laneId}
              events={evs}
              anchors={anchors}
              column={false}
              highlightEventIdx={highlightEventIdx}
            />
          ))}
        </div>
      )}
    </div>
  );
}
