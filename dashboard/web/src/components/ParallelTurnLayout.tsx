import type { AgentLanes, TimeAnchors } from "../lib/groupEvents";
import AgentLane from "./AgentLane";

type Props = {
  lanes: AgentLanes;
  anchors: TimeAnchors;
  parallelColumns: boolean;
  highlightEventIdx?: number | null;
};

export default function ParallelTurnLayout({
  lanes,
  anchors,
  parallelColumns,
  highlightEventIdx = null,
}: Props) {
  const subEntries = [...lanes.subagents.entries()].sort((a, b) => {
    const ai = a[1][0]?.event_idx ?? 0;
    const bi = b[1][0]?.event_idx ?? 0;
    return ai - bi;
  });

  return (
    <div className="space-y-3">
      {lanes.parent.length > 0 && (
        <AgentLane
          laneId="parent"
          events={lanes.parent}
          anchors={anchors}
          highlightEventIdx={highlightEventIdx}
        />
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
              column={parallelColumns}
              highlightEventIdx={highlightEventIdx}
            />
          ))}
        </div>
      )}
    </div>
  );
}
