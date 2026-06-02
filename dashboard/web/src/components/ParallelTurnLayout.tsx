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

  const subEntries = useMemo(() => {
    const entries = [...lanes.subagents.entries()].sort((a, b) => {
      const ai = a[1][0]?.event_idx ?? 0;
      const bi = b[1][0]?.event_idx ?? 0;
      return ai - bi;
    });
    if (!parallelColumns || !batchLaneIds) return entries;
    const batch = entries.filter(([laneId]) => batchLaneIds.has(laneId));
    const rest = entries.filter(([laneId]) => !batchLaneIds.has(laneId));
    return [...batch, ...rest];
  }, [lanes.subagents, parallelColumns, batchLaneIds]);

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
      {subEntries.length > 0 && (
        <div
          className={
            parallelColumns
              ? "flex flex-wrap gap-3 overflow-x-auto pb-1"
              : "space-y-3"
          }
        >
          {subEntries.map(([laneId, evs]) => (
            <AgentLane
              key={laneId}
              laneId={laneId}
              events={evs}
              anchors={anchors}
              column={parallelColumns && (batchLaneIds?.has(laneId) ?? false)}
              highlightEventIdx={highlightEventIdx}
            />
          ))}
        </div>
      )}
    </div>
  );
}
