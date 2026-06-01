import type { EventItem } from "../api";
import type { AgentLanes } from "./groupEvents";
import { splitAgentLanes } from "./groupEvents";

export type CompactionUnit = {
  compaction: EventItem;
  compactorEvents: EventItem[];
  originalToolResult: EventItem | null;
};

export type CompactionUnitsResult = {
  units: CompactionUnit[];
  consumedCompactorIdxs: Set<number>;
  unitByCompactionIdx: Map<number, CompactionUnit>;
};

function isCompactorEvent(e: EventItem): boolean {
  return e.agent_id === "compactor" || e.agent_type === "compactor";
}

function isCompactionAnchor(e: EventItem): boolean {
  return e.kind === "compaction" || e.kind === "context_compaction";
}

function numPayload(value: unknown): number | null {
  if (typeof value === "number" && !Number.isNaN(value)) return value;
  if (typeof value === "string" && value.trim() !== "") {
    const n = Number(value);
    return Number.isNaN(n) ? null : n;
  }
  return null;
}

/** Group each compaction/context_compaction with immediately preceding compactor events. */
export function buildCompactionUnits(turnEvents: EventItem[]): CompactionUnitsResult {
  const sorted = [...turnEvents].sort((a, b) => a.event_idx - b.event_idx);
  const byIdx = new Map(sorted.map((e) => [e.event_idx, e]));
  const consumedCompactorIdxs = new Set<number>();
  const units: CompactionUnit[] = [];
  const unitByCompactionIdx = new Map<number, CompactionUnit>();

  for (let i = 0; i < sorted.length; i++) {
    const e = sorted[i];
    if (!isCompactionAnchor(e)) continue;

    const compactorEvents: EventItem[] = [];
    for (let j = i - 1; j >= 0; j--) {
      const prev = sorted[j];
      if (isCompactorEvent(prev)) {
        compactorEvents.unshift(prev);
        consumedCompactorIdxs.add(prev.event_idx);
      } else if (compactorEvents.length > 0) {
        break;
      }
    }

    const origIdx = numPayload(e.payload.original_event_idx);
    const originalToolResult =
      origIdx != null ? (byIdx.get(origIdx) ?? null) : null;

    const unit: CompactionUnit = {
      compaction: e,
      compactorEvents,
      originalToolResult,
    };
    units.push(unit);
    unitByCompactionIdx.set(e.event_idx, unit);
  }

  return { units, consumedCompactorIdxs, unitByCompactionIdx };
}

export function filterSubagentLanes(
  lanes: AgentLanes,
  consumedCompactorIdxs: Set<number>,
): AgentLanes {
  const subagents = new Map<string, EventItem[]>();
  for (const [key, evs] of lanes.subagents) {
    const filtered = evs.filter((e) => !consumedCompactorIdxs.has(e.event_idx));
    if (filtered.length > 0) subagents.set(key, filtered);
  }
  return { parent: lanes.parent, subagents };
}

export function prepareTurnAgentLanes(turnEvents: EventItem[]): {
  lanes: AgentLanes;
  unitByCompactionIdx: Map<number, CompactionUnit>;
} {
  const { unitByCompactionIdx, consumedCompactorIdxs } = buildCompactionUnits(turnEvents);
  const lanes = filterSubagentLanes(splitAgentLanes(turnEvents), consumedCompactorIdxs);
  return { lanes, unitByCompactionIdx };
}

export function compactionUnitEventIndices(unit: CompactionUnit): number[] {
  return [unit.compaction.event_idx, ...unit.compactorEvents.map((e) => e.event_idx)];
}
