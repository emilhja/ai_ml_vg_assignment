import type { SessionSummary } from "../api";

export type SessionSubagentFilter = "parallel" | "sequential" | "any_subagents" | "no_subagents";

export type SessionCompactionFilter =
  | "tool_compaction"
  | "context_compaction_auto"
  | "context_compaction_manual";

export type SessionHistoryFilter = SessionSubagentFilter | SessionCompactionFilter;

const STORAGE_KEY = "vg-dashboard-history-filters";

const SUBAGENT_FILTERS: SessionSubagentFilter[] = [
  "parallel",
  "sequential",
  "any_subagents",
  "no_subagents",
];

const COMPACTION_FILTERS: SessionCompactionFilter[] = [
  "tool_compaction",
  "context_compaction_auto",
  "context_compaction_manual",
];

const ALL_FILTERS: SessionHistoryFilter[] = [...SUBAGENT_FILTERS, ...COMPACTION_FILTERS];

export function loadSessionFilters(): Set<SessionHistoryFilter> {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return new Set();
    const parsed = JSON.parse(raw) as unknown;
    if (!Array.isArray(parsed)) return new Set();
    return new Set(
      parsed.filter((v): v is SessionHistoryFilter =>
        typeof v === "string" && ALL_FILTERS.includes(v as SessionHistoryFilter),
      ),
    );
  } catch {
    return new Set();
  }
}

export function saveSessionFilters(filters: Set<SessionHistoryFilter>): void {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify([...filters]));
  } catch {
    /* ignore */
  }
}

export function filterSessions(
  items: SessionSummary[],
  active: Set<SessionHistoryFilter>,
): SessionSummary[] {
  if (!active.size) return items;
  return items.filter((s) => {
    if (active.has("parallel") && s.has_parallel_subagents) return true;
    if (active.has("sequential") && s.has_sequential_subagents) return true;
    if (active.has("any_subagents") && s.has_subagents) return true;
    if (active.has("no_subagents") && !s.has_subagents) return true;
    if (active.has("tool_compaction") && s.has_tool_compaction) return true;
    if (active.has("context_compaction_auto") && s.has_context_compaction_auto) return true;
    if (active.has("context_compaction_manual") && s.has_context_compaction_manual) return true;
    return false;
  });
}

export const SESSION_SUBAGENT_FILTER_OPTIONS: {
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

export const SESSION_COMPACTION_FILTER_OPTIONS: {
  id: SessionCompactionFilter;
  label: string;
  hint: string;
}[] = [
  {
    id: "tool_compaction",
    label: "Tool compaction",
    hint: "Automatic tool-result compaction (kind: compaction) when a read exceeds K_COMPACT",
  },
  {
    id: "context_compaction_auto",
    label: "Auto context compaction",
    hint: "Conversation-level auto compaction (context_compaction, reason auto) — forward-compatible",
  },
  {
    id: "context_compaction_manual",
    label: "Manual context compaction",
    hint: "Manual /compact conversation compaction (context_compaction, reason manual) — forward-compatible",
  },
];

/** @deprecated use SESSION_SUBAGENT_FILTER_OPTIONS */
export const SESSION_FILTER_OPTIONS = SESSION_SUBAGENT_FILTER_OPTIONS;
