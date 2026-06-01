import type { EventItem } from "../api";

export type LaneTokenSummary = {
  tokensIn: number;
  tokensOut: number;
  childTotalTokens: number | null;
  childCostUsd: number | null;
};

export type TurnStats = {
  tokensIn: number;
  tokensOut: number;
  costUsd: number;
};

export type TurnRollup = {
  total_tokens: number;
  total_cost_usd: number;
};

export type SubagentReturnDetail = {
  summary: string;
  status: string;
  childTotalTokens: number | null;
  childCostUsd: number | null;
};

export type ExpandableSection = {
  heading: string;
  body: string;
};

export type ExpandableEventDetail = {
  toggleLabel: string;
  sections: ExpandableSection[];
};

const MAX_BODY_CHARS = 10_000;

function num(value: unknown): number | null {
  if (typeof value === "number" && !Number.isNaN(value)) return value;
  if (typeof value === "string" && value.trim() !== "") {
    const n = Number(value);
    return Number.isNaN(n) ? null : n;
  }
  return null;
}

export function formatTokenCount(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1000) return `${(n / 1000).toFixed(1)}k`;
  return String(n);
}

export function formatPayloadJson(value: unknown): string {
  if (value === null || value === undefined) return "";
  if (typeof value === "string") return value;
  try {
    return JSON.stringify(value, null, 2);
  } catch {
    return String(value);
  }
}

export function truncateBody(text: string, maxChars = MAX_BODY_CHARS): string {
  if (text.length <= maxChars) return text;
  return `${text.slice(0, maxChars)}\n… [truncated ${text.length - maxChars} chars]`;
}

function section(heading: string, body: unknown): ExpandableSection {
  const text =
    typeof body === "string" ? body : body === null || body === undefined ? "" : formatPayloadJson(body);
  return { heading, body: truncateBody(text.trim() || "(empty)") };
}

export function assistantStepTokens(event: EventItem): {
  tokensIn: number | null;
  tokensOut: number | null;
  costUsd: number | null;
} {
  if (event.kind !== "assistant_step") {
    return { tokensIn: null, tokensOut: null, costUsd: null };
  }
  return {
    tokensIn: event.tokens_in ?? num(event.payload.tokens_in),
    tokensOut: event.tokens_out ?? num(event.payload.tokens_out),
    costUsd: event.cost_usd ?? num(event.payload.cost_usd) ?? num(event.payload.usd),
  };
}

export function summarizeLaneTokens(events: EventItem[]): LaneTokenSummary {
  let tokensIn = 0;
  let tokensOut = 0;
  for (const e of events) {
    if (e.kind !== "assistant_step") continue;
    tokensIn += e.tokens_in ?? num(e.payload.tokens_in) ?? 0;
    tokensOut += e.tokens_out ?? num(e.payload.tokens_out) ?? 0;
  }
  const ret = events.find((e) => e.kind === "subagent_return");
  return {
    tokensIn,
    tokensOut,
    childTotalTokens: ret ? num(ret.payload.child_total_tokens) : null,
    childCostUsd: ret ? num(ret.payload.child_total_cost_usd) : null,
  };
}

export function summarizeTurnStats(events: EventItem[], rollup?: TurnRollup | null): TurnStats {
  let tokensIn = 0;
  let tokensOut = 0;
  let costUsd = 0;
  for (const e of events) {
    if (e.kind === "assistant_step") {
      const t = assistantStepTokens(e);
      tokensIn += t.tokensIn ?? 0;
      tokensOut += t.tokensOut ?? 0;
      costUsd += t.costUsd ?? 0;
    }
  }
  for (const e of events) {
    if (e.kind !== "subagent_return") continue;
    const childCost = num(e.payload.child_total_cost_usd);
    const childTok = num(e.payload.child_total_tokens);
    if (childCost != null) costUsd += childCost;
    if (childTok != null) {
      const lane = summarizeLaneTokens(events.filter((x) => x.agent_id === e.agent_id));
      const extra = childTok - lane.tokensIn - lane.tokensOut;
      if (extra > 0) tokensOut += extra;
    }
  }
  if (rollup) {
    if (rollup.total_cost_usd > costUsd) costUsd = rollup.total_cost_usd;
    const eventTotal = tokensIn + tokensOut;
    if (rollup.total_tokens > eventTotal) {
      tokensOut += rollup.total_tokens - eventTotal;
    }
  }
  return { tokensIn, tokensOut, costUsd };
}

export function formatTurnStatsLine(stats: TurnStats): string | null {
  if (stats.tokensIn === 0 && stats.tokensOut === 0 && stats.costUsd === 0) return null;
  const parts: string[] = [];
  if (stats.tokensIn > 0) parts.push(`${formatTokenCount(stats.tokensIn)} in`);
  if (stats.tokensOut > 0) parts.push(`${formatTokenCount(stats.tokensOut)} out`);
  if (stats.costUsd > 0) parts.push(`$${stats.costUsd.toFixed(4)}`);
  return parts.length ? parts.join(" · ") : null;
}

export function subagentReturnDetail(event: EventItem): SubagentReturnDetail | null {
  if (event.kind !== "subagent_return") return null;
  const summary = String(event.payload.summary ?? event.status ?? "").trim();
  return {
    summary: summary || "(empty return)",
    status: String(event.payload.status ?? event.status ?? "ok"),
    childTotalTokens: num(event.payload.child_total_tokens),
    childCostUsd: num(event.payload.child_total_cost_usd),
  };
}

function spawnRequestSections(requests: unknown): ExpandableSection[] {
  if (!Array.isArray(requests)) {
    return [{ heading: "Requests", body: "(missing requests array)" }];
  }
  return requests.map((raw, index) => {
    const req = raw && typeof raw === "object" ? (raw as Record<string, unknown>) : {};
    const type = String(req.type ?? req.agent_type ?? "explorer");
    const question = String(req.question ?? "").trim() || "(empty question)";
    return { heading: `Request ${index + 1} · ${type}`, body: question };
  });
}

function spawnToolCallDetail(event: EventItem): ExpandableEventDetail | null {
  const tool = event.tool ?? "";
  if (tool !== "spawn_subagent" && tool !== "spawn_subagents") return null;
  const args =
    event.payload.args && typeof event.payload.args === "object"
      ? (event.payload.args as Record<string, unknown>)
      : event.payload;

  if (tool === "spawn_subagent") {
    const type = String(args.type ?? "explorer");
    const question = String(args.question ?? "").trim() || "(empty question)";
    return {
      toggleLabel: "parent batch",
      sections: [{ heading: `spawn_subagent · ${type}`, body: question }],
    };
  }

  return {
    toggleLabel: "parent batch",
    sections: spawnRequestSections(args.requests),
  };
}

function genericToolCallDetail(event: EventItem): ExpandableEventDetail | null {
  if (event.kind !== "tool_call") return null;
  const spawn = spawnToolCallDetail(event);
  if (spawn) return spawn;
  const args =
    event.payload.args && typeof event.payload.args === "object"
      ? event.payload.args
      : event.payload;
  const sections: ExpandableSection[] = [section("Args", args)];
  const toolUseId = String(event.payload.tool_use_id ?? "").trim();
  if (toolUseId) sections.push({ heading: "tool_use_id", body: toolUseId });
  return { toggleLabel: "args", sections };
}

export function subagentSpawnDetail(event: EventItem): ExpandableEventDetail | null {
  if (event.kind !== "subagent_spawn") return null;
  const question = String(event.payload.question ?? "").trim() || "(empty question)";
  const agentType = String(event.payload.agent_type ?? event.agent_type ?? "subagent");
  const model = String(event.payload.model ?? event.payload.model_id ?? "").trim();
  const childId = String(event.payload.child_agent_id ?? event.agent_id ?? "").trim();
  const sections: ExpandableSection[] = [
    { heading: `Parent instruction · ${agentType}`, body: question },
  ];
  if (childId) sections.push({ heading: "Child agent", body: childId });
  if (model) sections.push({ heading: "Model", body: model });
  return {
    toggleLabel: "instruction",
    sections,
  };
}

function assistantStepDetail(event: EventItem): ExpandableEventDetail | null {
  if (event.kind !== "assistant_step") return null;
  const sections: ExpandableSection[] = [];
  const text = String(event.payload.assistant_text ?? "").trim();
  if (text) sections.push(section("Assistant", text));
  const toolCalls = event.payload.tool_calls;
  if (toolCalls != null && (Array.isArray(toolCalls) ? toolCalls.length > 0 : true)) {
    sections.push(section("tool_calls", toolCalls));
  }
  const model = String(event.payload.model_id ?? event.payload.model ?? "").trim();
  if (model) sections.push({ heading: "Model", body: model });
  if (!sections.length) sections.push(section("Payload", event.payload));
  return { toggleLabel: "step", sections };
}

function llmStartDetail(event: EventItem): ExpandableEventDetail | null {
  if (event.kind !== "llm_start") return null;
  const model = String(event.payload.model_id ?? event.payload.model ?? event.tool ?? "").trim();
  const sections: ExpandableSection[] = [];
  if (model) sections.push({ heading: "Model", body: model });
  const extra = { ...event.payload };
  delete extra.model_id;
  delete extra.model;
  if (Object.keys(extra).length) sections.push(section("Details", extra));
  return { toggleLabel: "llm", sections: sections.length ? sections : [section("Details", event.payload)] };
}

function toolResultDetail(event: EventItem): ExpandableEventDetail | null {
  if (event.kind !== "tool_result") return null;
  const sections: ExpandableSection[] = [];
  const summary = event.payload.result_summary;
  const full = event.payload.result_full;
  if (summary != null) sections.push(section("Summary", summary));
  else if (full != null) sections.push(section("Result", full));
  const stderr = event.payload.stderr;
  if (stderr != null) sections.push(section("stderr", stderr));
  if (!sections.length) sections.push(section("Payload", event.payload));
  return { toggleLabel: "result", sections };
}

function compactionDetail(event: EventItem): ExpandableEventDetail | null {
  if (event.kind !== "compaction") return null;
  const sections: ExpandableSection[] = [];
  const idx = event.payload.original_event_idx;
  if (idx != null) sections.push({ heading: "original_event_idx", body: String(idx) });
  const sha = event.payload.original_sha256;
  if (sha != null) sections.push({ heading: "original_sha256", body: String(sha) });
  const marker = event.payload.compacted_marker ?? event.payload.marker;
  if (marker != null) sections.push(section("Marker", marker));
  if (!sections.length) sections.push(section("Payload", event.payload));
  return { toggleLabel: "compacted", sections };
}

function budgetEventDetail(event: EventItem): ExpandableEventDetail | null {
  if (event.kind !== "budget_event") return null;
  const reason = String(event.payload.budget_reason ?? event.status ?? "").trim();
  const sections: ExpandableSection[] = [];
  if (reason) sections.push({ heading: "Reason", body: reason });
  sections.push(section("Counters", event.payload));
  return { toggleLabel: "budget", sections };
}

function approvalDetail(event: EventItem): ExpandableEventDetail | null {
  if (event.kind !== "approval") return null;
  const sections: ExpandableSection[] = [];
  const tool = String(event.payload.tool ?? event.tool ?? "").trim();
  const path = String(event.payload.path ?? "").trim();
  if (tool) sections.push({ heading: "Tool", body: tool });
  if (path) sections.push({ heading: "Path", body: path });
  sections.push(section("Decision", event.payload));
  return { toggleLabel: "approval", sections };
}

function userPromptDetail(event: EventItem): ExpandableEventDetail | null {
  if (event.kind !== "user_prompt") return null;
  const prompt = String(event.payload.prompt ?? "").trim();
  if (!prompt) return null;
  if (prompt.length <= 120 && !prompt.includes("\n")) return null;
  return {
    toggleLabel: "prompt",
    sections: [{ heading: "Full prompt", body: prompt }],
  };
}

function egressOrRedactionDetail(event: EventItem): ExpandableEventDetail | null {
  if (event.kind !== "egress_blocked" && event.kind !== "redaction") return null;
  return {
    toggleLabel: event.kind,
    sections: [section("Details", event.payload)],
  };
}

export function expandableEventDetail(event: EventItem): ExpandableEventDetail | null {
  if (event.kind === "subagent_return") {
    const detail = subagentReturnDetail(event);
    if (!detail) return null;
    return {
      toggleLabel: "payload",
      sections: [{ heading: "Return summary", body: detail.summary }],
    };
  }
  if (event.kind === "subagent_spawn") return subagentSpawnDetail(event);
  if (event.kind === "tool_call") return genericToolCallDetail(event);
  if (event.kind === "assistant_step") return assistantStepDetail(event);
  if (event.kind === "llm_start") return llmStartDetail(event);
  if (event.kind === "tool_result") return toolResultDetail(event);
  if (event.kind === "compaction") return compactionDetail(event);
  if (event.kind === "budget_event") return budgetEventDetail(event);
  if (event.kind === "approval") return approvalDetail(event);
  if (event.kind === "user_prompt") return userPromptDetail(event);
  if (event.kind === "egress_blocked" || event.kind === "redaction") return egressOrRedactionDetail(event);
  return null;
}
