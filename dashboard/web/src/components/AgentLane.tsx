import type { EventItem } from "../api";
import { agentTypeForLane } from "../lib/groupEvents";
import type { TimeAnchors } from "../lib/groupEvents";
import { formatTokenCount, summarizeLaneTokens } from "../lib/laneStats";
import EventRow from "./EventRow";

type Props = {
  laneId: string;
  events: EventItem[];
  anchors: TimeAnchors;
  column?: boolean;
  highlightEventIdx?: number | null;
};

function LaneTokenFooter({ events }: { events: EventItem[] }) {
  const stats = summarizeLaneTokens(events);
  const hasSteps = stats.tokensIn > 0 || stats.tokensOut > 0;
  const hasReturn = stats.childTotalTokens != null;

  if (!hasSteps && !hasReturn) return null;

  const totalLabel =
    stats.childTotalTokens != null
      ? formatTokenCount(stats.childTotalTokens)
      : formatTokenCount(stats.tokensIn + stats.tokensOut);

  return (
    <div className="mt-2 pt-2 border-t border-violet-500/30 text-[10px] font-mono text-slate-400 space-y-0.5">
      {hasSteps && (
        <p>
          <span className="text-muted">LLM steps · </span>
          in {formatTokenCount(stats.tokensIn)}
          <span className="text-muted"> · </span>
          out {formatTokenCount(stats.tokensOut)}
        </p>
      )}
      {hasReturn && (
        <p>
          <span className="text-muted">subagent_return · </span>
          <span className="text-amber-200/90">{totalLabel} tok total</span>
          {stats.childCostUsd != null && (
            <>
              <span className="text-muted"> · </span>
              <span>${stats.childCostUsd.toFixed(4)}</span>
            </>
          )}
        </p>
      )}
    </div>
  );
}

export default function AgentLane({
  laneId,
  events,
  anchors,
  column = false,
  highlightEventIdx = null,
}: Props) {
  const agentType = agentTypeForLane(events);
  const isParent = laneId === "parent";
  const showFooter = !isParent && events.some((e) => e.kind === "subagent_return");

  return (
    <div
      className={
        column
          ? "min-w-[14rem] flex-1 rounded border border-violet-500/25 bg-violet-950/20 p-2"
          : isParent
            ? "space-y-2"
            : "ml-3 pl-3 border-l-2 border-violet-500/40 space-y-2"
      }
    >
      {!isParent && (
        <div className="flex items-center gap-2 text-xs font-medium text-violet-300 mb-1">
          <span>{laneId}</span>
          {agentType && <span className="text-muted font-normal">({agentType})</span>}
          <span className="text-muted font-normal">{events.length} events</span>
        </div>
      )}
      <ul className="space-y-2 font-mono text-xs">
        {events.map((e) => (
          <EventRow
            key={`${e.run_id}-${e.event_idx}`}
            event={e}
            anchors={anchors}
            highlightEventIdx={highlightEventIdx}
          />
        ))}
      </ul>
      {showFooter && <LaneTokenFooter events={events} />}
    </div>
  );
}
