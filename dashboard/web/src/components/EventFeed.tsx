import { useEffect, useMemo, useRef, useState } from "react";
import type { EventItem, ParallelResponse, SessionDetail } from "../api";
import type { TurnRollup } from "../lib/laneStats";
import {
  groupByTurn,
  loadEventViewMode,
  loadParallelColumns,
  saveEventViewMode,
  saveParallelColumns,
  sessionShowsParallelToggle,
  sessionStartIso,
  type EventViewMode,
  type TimeAnchors,
} from "../lib/groupEvents";
import AgentNavBar from "./AgentNavBar";
import EventRow from "./EventRow";
import EventStreamToolbar from "./EventStreamToolbar";
import TurnSection from "./TurnSection";

type Props = {
  events: EventItem[];
  parallel?: ParallelResponse | null;
  turns?: SessionDetail["turns"];
  highlightEventIdx?: number | null;
  onHighlightEventIdx?: (eventIdx: number) => void;
  showAgentNav?: boolean;
};

function buildTurnRollupMap(turns: SessionDetail["turns"] | undefined): Map<string, TurnRollup> {
  const map = new Map<string, TurnRollup>();
  if (!turns) return map;
  for (const t of turns) {
    map.set(t.turn_id, {
      total_tokens: t.total_tokens,
      total_cost_usd: t.total_cost_usd ?? 0,
    });
  }
  return map;
}

export default function EventFeed({
  events,
  parallel,
  turns,
  highlightEventIdx = null,
  onHighlightEventIdx,
  showAgentNav = true,
}: Props) {
  const [viewMode, setViewMode] = useState<EventViewMode>(loadEventViewMode);
  const [parallelColumns, setParallelColumns] = useState(loadParallelColumns);

  const sessionStart = useMemo(() => sessionStartIso(events), [events]);
  const turnGroups = useMemo(() => groupByTurn(events), [events]);
  const turnRollups = useMemo(() => buildTurnRollupMap(turns), [turns]);

  const anyOverlap = useMemo(
    () => sessionShowsParallelToggle(events, parallel),
    [events, parallel],
  );

  const sessionKey = events[0]?.session_id ?? events[0]?.run_id ?? "";
  const autoParallelApplied = useRef<string | null>(null);

  useEffect(() => {
    if (!anyOverlap || !sessionKey || autoParallelApplied.current === sessionKey) {
      return;
    }
    autoParallelApplied.current = sessionKey;
    setParallelColumns(true);
    saveParallelColumns(true);
    setViewMode((mode) => {
      if (mode === "by-turn") {
        saveEventViewMode("turn-agents");
        return "turn-agents";
      }
      return mode;
    });
  }, [anyOverlap, sessionKey]);

  const handleViewMode = (mode: EventViewMode) => {
    setViewMode(mode);
    saveEventViewMode(mode);
  };

  const handleParallelColumns = (enabled: boolean) => {
    setParallelColumns(enabled);
    saveParallelColumns(enabled);
  };

  const handleAgentJump = (eventIdx: number) => {
    onHighlightEventIdx?.(eventIdx);
    requestAnimationFrame(() => {
      document.getElementById(`event-${eventIdx}`)?.scrollIntoView({
        behavior: "smooth",
        block: "center",
      });
    });
  };

  const agentNav =
    showAgentNav && events.length > 0 ? (
      <AgentNavBar events={events} onJump={(idx) => handleAgentJump(idx)} />
    ) : null;

  if (!events.length) {
    return <p className="text-muted text-sm">No events yet.</p>;
  }

  const flatAnchors: TimeAnchors = { sessionStart, turnStart: null };

  if (viewMode === "flat") {
    const sorted = [...events].sort((a, b) => b.event_idx - a.event_idx);
    return (
      <div className="flex flex-col flex-1 min-h-0">
        <EventStreamToolbar
          viewMode={viewMode}
          onViewModeChange={handleViewMode}
          parallelColumns={parallelColumns}
          onParallelColumnsChange={handleParallelColumns}
          showParallelToggle={anyOverlap}
          agentNav={agentNav}
        />
        <ul className="flex-1 min-h-0 overflow-y-auto space-y-2 font-mono text-xs">
          {sorted.map((e) => (
            <EventRow
              key={`${e.run_id}-${e.event_idx}`}
              event={e}
              anchors={flatAnchors}
              showSessionRelative
              highlightEventIdx={highlightEventIdx}
            />
          ))}
        </ul>
      </div>
    );
  }

  const viewAgents = viewMode === "turn-agents";
  const groupsChronological = [...turnGroups].reverse();

  return (
    <div className="flex flex-col flex-1 min-h-0">
      <EventStreamToolbar
        viewMode={viewMode}
        onViewModeChange={handleViewMode}
        parallelColumns={parallelColumns}
        onParallelColumnsChange={handleParallelColumns}
        showParallelToggle={anyOverlap}
        agentNav={agentNav}
      />
      <div className="flex-1 min-h-0 overflow-y-auto space-y-4">
        {groupsChronological.map((group) => (
          <TurnSection
            key={group.turnId}
            group={group}
            viewAgents={viewAgents}
            parallelColumns={parallelColumns}
            parallel={parallel}
            sessionStart={sessionStart}
            turnRollup={turnRollups.get(group.turnId) ?? null}
            highlightEventIdx={highlightEventIdx}
            onHighlightEventIdx={onHighlightEventIdx}
            defaultExpanded={group.turnId === groupsChronological[0]?.turnId}
          />
        ))}
      </div>
    </div>
  );
}
