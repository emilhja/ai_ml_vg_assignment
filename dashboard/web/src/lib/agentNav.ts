import type { EventItem } from "../api";
import { isParentAgent } from "./groupEvents";

export type AgentNavType =
  | "parent"
  | "explorer"
  | "grilling"
  | "coder"
  | "reviewer"
  | "compactor";

export const KNOWN_AGENT_TYPES: AgentNavType[] = [
  "parent",
  "explorer",
  "grilling",
  "coder",
  "reviewer",
  "compactor",
];

const AGENT_LABELS: Record<AgentNavType, string> = {
  parent: "parent",
  explorer: "explorer",
  grilling: "grilling",
  coder: "coder",
  reviewer: "reviewer",
  compactor: "compactor",
};

export type AgentNavTarget = {
  type: AgentNavType;
  label: string;
  eventIndices: number[];
};

function eventAgentType(e: EventItem): string | null {
  if (e.agent_type) return e.agent_type;
  const p = e.payload.agent_type;
  return typeof p === "string" ? p : null;
}

export function matchAgentType(event: EventItem, type: AgentNavType): boolean {
  if (type === "parent") {
    return isParentAgent(event);
  }
  if (type === "compactor") {
    return (
      eventAgentType(event) === "compactor" ||
      event.kind === "context_compaction" ||
      event.kind === "compaction"
    );
  }
  return eventAgentType(event) === type;
}

export function collectAgentNavTargets(events: EventItem[]): AgentNavTarget[] {
  const byType = new Map<AgentNavType, number[]>();
  const sorted = [...events].sort((a, b) => a.event_idx - b.event_idx);

  for (const e of sorted) {
    for (const type of KNOWN_AGENT_TYPES) {
      if (!matchAgentType(e, type)) continue;
      if (!byType.has(type)) byType.set(type, []);
      byType.get(type)!.push(e.event_idx);
    }
  }

  return KNOWN_AGENT_TYPES.filter((t) => byType.has(t)).map((type) => ({
    type,
    label: AGENT_LABELS[type],
    eventIndices: byType.get(type)!,
  }));
}

/** Next index strictly after cursor, or wrap to first. */
export function nextEventIndex(indices: number[], cursor: number | null): number | null {
  if (!indices.length) return null;
  if (cursor == null) return indices[0];
  const next = indices.find((i) => i > cursor);
  return next ?? indices[0];
}
