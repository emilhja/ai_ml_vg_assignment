import { useState } from "react";
import type { EventItem } from "../api";
import {
  collectAgentNavTargets,
  nextEventIndex,
  type AgentNavType,
} from "../lib/agentNav";

type Props = {
  events: EventItem[];
  onJump: (eventIdx: number, agentType: AgentNavType) => void;
  activeType?: AgentNavType | null;
};

export default function AgentNavBar({ events, onJump, activeType: activeTypeProp = null }: Props) {
  const targets = collectAgentNavTargets(events);
  const [activeType, setActiveType] = useState<AgentNavType | null>(activeTypeProp);
  const [cursorByType, setCursorByType] = useState<Partial<Record<AgentNavType, number>>>({});

  if (!targets.length) return null;

  const handleClick = (type: AgentNavType, indices: number[]) => {
    const cursor = activeType === type ? cursorByType[type] ?? null : null;
    const next = nextEventIndex(indices, cursor);
    if (next == null) return;
    setActiveType(type);
    setCursorByType((prev) => ({ ...prev, [type]: next }));
    onJump(next, type);
  };

  return (
    <div className="flex flex-wrap items-center gap-1">
      <span className="text-[10px] uppercase tracking-wide text-muted mr-1">Agents</span>
      {targets.map((t) => {
        const on = activeType === t.type;
        return (
          <button
            key={t.type}
            type="button"
            title={`${t.label}: ${t.eventIndices.length} events — click for next`}
            onClick={() => handleClick(t.type, t.eventIndices)}
            className={`px-2.5 py-1 rounded text-xs font-medium border transition-colors ${
              on
                ? "bg-accent/25 border-accent/50 text-accent"
                : "bg-panel/60 border-slate-700/50 text-muted hover:border-slate-500 hover:text-white"
            }`}
          >
            {t.label}
            <span className="ml-1 text-[10px] opacity-70 tabular-nums">{t.eventIndices.length}</span>
          </button>
        );
      })}
    </div>
  );
}
