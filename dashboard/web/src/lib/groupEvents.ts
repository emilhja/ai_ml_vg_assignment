import type { EventItem, ParallelResponse } from "../api";

export type EventViewMode = "flat" | "by-turn" | "turn-agents";

export type TurnGroup = {
  turnIndex: number | null;
  turnId: string;
  label: string;
  prompt: string | null;
  startedAt: string | null;
  endedAt: string | null;
  events: EventItem[];
};

export type AgentLanes = {
  parent: EventItem[];
  subagents: Map<string, EventItem[]>;
};

export type TimeAnchors = {
  sessionStart: string | null;
  turnStart: string | null;
};

export type TimeTags = {
  absolute: string | null;
  relativeToTurn: string | null;
  relativeToSession: string | null;
};

const STORAGE_VIEW = "vg-dashboard-event-view";
const STORAGE_PARALLEL = "vg-dashboard-parallel-columns";

export function loadEventViewMode(): EventViewMode {
  try {
    const v = localStorage.getItem(STORAGE_VIEW);
    if (v === "flat" || v === "by-turn" || v === "turn-agents") return v;
  } catch {
    /* ignore */
  }
  return "by-turn";
}

export function saveEventViewMode(mode: EventViewMode): void {
  try {
    localStorage.setItem(STORAGE_VIEW, mode);
  } catch {
    /* ignore */
  }
}

export function loadParallelColumns(): boolean {
  try {
    return localStorage.getItem(STORAGE_PARALLEL) === "1";
  } catch {
    return false;
  }
}

export function saveParallelColumns(enabled: boolean): void {
  try {
    localStorage.setItem(STORAGE_PARALLEL, enabled ? "1" : "0");
  } catch {
    /* ignore */
  }
}

function parseIsoMs(iso: string | null | undefined): number | null {
  if (!iso) return null;
  const ms = Date.parse(iso);
  return Number.isNaN(ms) ? null : ms;
}

function eventTurnId(e: EventItem): string | null {
  return e.turn_id ?? (typeof e.payload.turn_id === "string" ? e.payload.turn_id : null);
}

function eventTurnIndex(e: EventItem): number | null {
  if (e.turn_index != null) return e.turn_index;
  const raw = e.payload.turn_index;
  return typeof raw === "number" ? raw : null;
}

export function formatDurationMs(ms: number): string {
  if (ms < 1000) return `${Math.round(ms)}ms`;
  const sec = ms / 1000;
  if (sec < 60) return `${sec.toFixed(1)}s`;
  const min = Math.floor(sec / 60);
  const rem = Math.round(sec % 60);
  return `${min}m ${rem}s`;
}

export function formatTimeTags(
  timestampIso: string | null | undefined,
  anchors: TimeAnchors,
): TimeTags {
  const ms = parseIsoMs(timestampIso);
  if (ms == null) {
    return { absolute: null, relativeToTurn: null, relativeToSession: null };
  }
  const d = new Date(ms);
  const base = d.toLocaleTimeString(undefined, {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
  const absolute = `${base}.${String(d.getMilliseconds()).padStart(3, "0")}`;
  const turnMs = parseIsoMs(anchors.turnStart);
  const sessionMs = parseIsoMs(anchors.sessionStart);
  let relativeToTurn: string | null = null;
  let relativeToSession: string | null = null;
  if (turnMs != null) {
    relativeToTurn = `+${formatDurationMs(ms - turnMs)}`;
  }
  if (sessionMs != null) {
    relativeToSession = `+${formatDurationMs(ms - sessionMs)}`;
  }
  return { absolute, relativeToTurn, relativeToSession };
}

export function formatTurnTimeRange(startedAt: string | null, endedAt: string | null): string {
  const startMs = parseIsoMs(startedAt);
  const endMs = parseIsoMs(endedAt);
  if (startMs == null && endMs == null) return "";
  const fmt = (iso: string | null) => {
    const ms = parseIsoMs(iso);
    if (ms == null) return "?";
    return new Date(ms).toLocaleTimeString(undefined, {
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
    });
  };
  if (startMs != null && endMs != null) {
    return `${fmt(startedAt)} → ${fmt(endedAt)} (${formatDurationMs(endMs - startMs)})`;
  }
  return fmt(startedAt ?? endedAt);
}

function turnBoundsFromEvents(events: EventItem[]): { startedAt: string | null; endedAt: string | null } {
  let startedAt: string | null = null;
  let endedAt: string | null = null;
  for (const e of events) {
    const ts = e.timestamp_iso;
    if (!ts) continue;
    if (!startedAt || (parseIsoMs(ts) ?? 0) < (parseIsoMs(startedAt) ?? 0)) startedAt = ts;
    if (!endedAt || (parseIsoMs(ts) ?? 0) > (parseIsoMs(endedAt) ?? 0)) endedAt = ts;
  }
  return { startedAt, endedAt };
}

/** Assign turn_id / turn_index when missing (pre-mirror JSONL). */
export function enrichTurnFields(events: EventItem[]): EventItem[] {
  let currentTurnId: string | null = null;
  let currentTurnIndex = 0;
  const sessionId = events[0]?.session_id ?? events[0]?.run_id ?? "session";
  return events.map((e) => {
    if (e.kind === "user_prompt") {
      currentTurnIndex += 1;
      currentTurnId =
        eventTurnId(e) ?? `${sessionId}:turn:${currentTurnIndex}`;
      return {
        ...e,
        turn_id: currentTurnId,
        turn_index: eventTurnIndex(e) ?? currentTurnIndex,
      };
    }
    if (currentTurnId) {
      return {
        ...e,
        turn_id: eventTurnId(e) ?? currentTurnId,
        turn_index: eventTurnIndex(e) ?? currentTurnIndex,
      };
    }
    return e;
  });
}

export function groupByTurn(events: EventItem[]): TurnGroup[] {
  const sorted = [...events].sort((a, b) => a.event_idx - b.event_idx);
  const enriched = enrichTurnFields(sorted);
  const groups: TurnGroup[] = [];
  let preTurn: EventItem[] = [];

  const flushPreTurn = () => {
    if (!preTurn.length) return;
    const bounds = turnBoundsFromEvents(preTurn);
    groups.push({
      turnIndex: null,
      turnId: "__session_start__",
      label: "Session start",
      prompt: null,
      startedAt: bounds.startedAt,
      endedAt: bounds.endedAt,
      events: preTurn,
    });
    preTurn = [];
  };

  const byTurnId = new Map<string, EventItem[]>();
  const turnMeta = new Map<string, { turnIndex: number | null; prompt: string | null }>();

  for (const e of enriched) {
    const tid = eventTurnId(e);
    if (!tid) {
      preTurn.push(e);
      continue;
    }
    flushPreTurn();
    if (!byTurnId.has(tid)) {
      byTurnId.set(tid, []);
      let prompt: string | null = null;
      if (e.kind === "user_prompt" && e.payload.prompt != null) {
        prompt = String(e.payload.prompt);
      }
      turnMeta.set(tid, { turnIndex: eventTurnIndex(e), prompt });
    }
    const list = byTurnId.get(tid)!;
    if (e.kind === "user_prompt" && !turnMeta.get(tid)!.prompt && e.payload.prompt != null) {
      turnMeta.get(tid)!.prompt = String(e.payload.prompt);
    }
    list.push(e);
  }
  flushPreTurn();

  const turnIds = [...byTurnId.keys()].sort((a, b) => {
    const ia = turnMeta.get(a)?.turnIndex ?? 0;
    const ib = turnMeta.get(b)?.turnIndex ?? 0;
    if (ia !== ib) return ia - ib;
    const ea = byTurnId.get(a)![0]?.event_idx ?? 0;
    const eb = byTurnId.get(b)![0]?.event_idx ?? 0;
    return ea - eb;
  });

  for (const tid of turnIds) {
    const evs = byTurnId.get(tid)!;
    const meta = turnMeta.get(tid)!;
    const bounds = turnBoundsFromEvents(evs);
    const idx = meta.turnIndex;
    groups.push({
      turnIndex: idx,
      turnId: tid,
      label: idx != null ? `Turn ${idx}` : "Turn",
      prompt: meta.prompt,
      startedAt: bounds.startedAt,
      endedAt: bounds.endedAt,
      events: evs,
    });
  }

  return groups;
}

export function isParentAgent(e: EventItem): boolean {
  const id = e.agent_id ?? "";
  if (id === "parent") return true;
  if (!id && (e.agent_type === "parent" || !e.parent_id)) return true;
  return false;
}

function laneKeyForEvent(e: EventItem): string {
  if (isParentAgent(e)) return "parent";
  if (e.kind === "subagent_spawn" || e.kind === "subagent_return") {
    return e.child_agent_id ?? String(e.payload.child_agent_id ?? e.agent_id ?? "subagent");
  }
  return e.agent_id ?? "unknown";
}

export function splitAgentLanes(turnEvents: EventItem[]): AgentLanes {
  const parent: EventItem[] = [];
  const subagents = new Map<string, EventItem[]>();

  for (const e of turnEvents) {
    const key = laneKeyForEvent(e);
    if (key === "parent") {
      parent.push(e);
    } else {
      if (!subagents.has(key)) subagents.set(key, []);
      subagents.get(key)!.push(e);
    }
  }
  return { parent, subagents };
}

export function agentTypeForLane(laneEvents: EventItem[]): string | null {
  for (const e of laneEvents) {
    if (e.agent_type) return e.agent_type;
    const p = e.payload.agent_type;
    if (typeof p === "string") return p;
  }
  return null;
}

function intervalsOverlap(
  aStart: number,
  aEnd: number,
  bStart: number,
  bEnd: number,
): boolean {
  return aStart < bEnd && bStart < aEnd;
}

/** Turn used spawn_subagents with 2+ sub-agent lanes (even before returns). */
export function turnHasParallelSpawnBatch(turnEvents: EventItem[]): boolean {
  const hasSpawnTool = turnEvents.some(
    (e) => e.kind === "tool_call" && e.tool === "spawn_subagents",
  );
  if (!hasSpawnTool) return false;
  const { subagents } = splitAgentLanes(turnEvents);
  if (subagents.size >= 2) return true;
  return turnEvents.filter((e) => e.kind === "subagent_spawn").length >= 2;
}

/** Client heuristic: 2+ sub-agent lanes with overlapping timestamps. */
export function detectParallelOverlapHeuristic(turnEvents: EventItem[]): boolean {
  const { subagents } = splitAgentLanes(turnEvents);
  if (subagents.size < 2) return false;

  const ranges: { start: number; end: number }[] = [];
  for (const lane of subagents.values()) {
    const bounds = turnBoundsFromEvents(lane);
    const start = parseIsoMs(bounds.startedAt);
    const end = parseIsoMs(bounds.endedAt);
    if (start != null && end != null) ranges.push({ start, end });
  }
  if (ranges.length < 2) return false;

  for (let i = 0; i < ranges.length; i++) {
    for (let j = i + 1; j < ranges.length; j++) {
      if (intervalsOverlap(ranges[i].start, ranges[i].end, ranges[j].start, ranges[j].end)) {
        return true;
      }
    }
  }
  return false;
}

export function turnHasParallelOverlap(
  turnIndex: number | null,
  turnEvents: EventItem[],
  parallel: ParallelResponse | null | undefined,
): boolean {
  if (turnIndex != null && parallel?.turns?.length) {
    const pt = parallel.turns.find((t) => t.turn_index === turnIndex);
    if (pt) return pt.overlap;
  }
  return (
    detectParallelOverlapHeuristic(turnEvents) || turnHasParallelSpawnBatch(turnEvents)
  );
}

/** Whether the Events toolbar should offer parallel column layout. */
export function sessionShowsParallelToggle(
  events: EventItem[],
  parallel: ParallelResponse | null | undefined,
): boolean {
  if (parallel?.turns?.some((t) => t.overlap)) return true;
  return groupByTurn(events).some(
    (g) =>
      detectParallelOverlapHeuristic(g.events) || turnHasParallelSpawnBatch(g.events),
  );
}

export function sessionStartIso(events: EventItem[]): string | null {
  const sorted = [...events].sort((a, b) => a.event_idx - b.event_idx);
  for (const e of sorted) {
    if (e.timestamp_iso) return e.timestamp_iso;
  }
  return null;
}
