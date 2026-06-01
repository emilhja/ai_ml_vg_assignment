import type { SessionSummary } from "../api";

export type SessionSubagentFilter = "parallel" | "sequential" | "any_subagents" | "no_subagents";

const STORAGE_KEY = "vg-dashboard-history-filters";

export function loadSessionFilters(): Set<SessionSubagentFilter> {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return new Set();
    const parsed = JSON.parse(raw) as unknown;
    if (!Array.isArray(parsed)) return new Set();
    const allowed: SessionSubagentFilter[] = [
      "parallel",
      "sequential",
      "any_subagents",
      "no_subagents",
    ];
    return new Set(
      parsed.filter((v): v is SessionSubagentFilter =>
        typeof v === "string" && allowed.includes(v as SessionSubagentFilter),
      ),
    );
  } catch {
    return new Set();
  }
}

export function saveSessionFilters(filters: Set<SessionSubagentFilter>): void {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify([...filters]));
  } catch {
    /* ignore */
  }
}

export function filterSessions(
  items: SessionSummary[],
  active: Set<SessionSubagentFilter>,
): SessionSummary[] {
  if (!active.size) return items;
  return items.filter((s) => {
    if (active.has("parallel") && s.has_parallel_subagents) return true;
    if (active.has("sequential") && s.has_sequential_subagents) return true;
    if (active.has("any_subagents") && s.has_subagents) return true;
    if (active.has("no_subagents") && !s.has_subagents) return true;
    return false;
  });
}

export const SESSION_FILTER_OPTIONS: {
  id: SessionSubagentFilter;
  label: string;
  hint: string;
}[] = [
  {
    id: "parallel",
    label: "Parallel sub-agents",
    hint: "At least one turn with overlapping explorers",
  },
  {
    id: "sequential",
    label: "Sequential sub-agents",
    hint: "Sub-agents without parallel overlap (single or serial batch)",
  },
  {
    id: "any_subagents",
    label: "Any sub-agents",
    hint: "Session used spawn_subagent or explorers",
  },
  {
    id: "no_subagents",
    label: "No sub-agents",
    hint: "Parent-only session",
  },
];
