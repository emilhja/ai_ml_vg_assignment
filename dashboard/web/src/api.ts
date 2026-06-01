const API = "/api/v1";

export type SessionSummary = {
  session_id: string;
  display_name?: string | null;
  first_seen_at?: string | null;
  last_seen_at?: string | null;
  status?: string | null;
  run_count: number;
  total_turns: number;
  total_tokens: number;
  total_cost_usd: number;
  last_prompt_snippet?: string | null;
  has_subagents?: boolean;
  has_parallel_subagents?: boolean;
  has_sequential_subagents?: boolean;
};

export type EventItem = {
  run_id: string;
  session_id?: string | null;
  event_idx: number;
  kind: string;
  timestamp_iso?: string | null;
  turn_id?: string | null;
  turn_index?: number | null;
  agent_id?: string | null;
  agent_type?: string | null;
  parent_id?: string | null;
  child_agent_id?: string | null;
  tool?: string | null;
  status?: string | null;
  tokens_in?: number | null;
  tokens_out?: number | null;
  cost_usd?: number | null;
  latency_ms?: number | null;
  payload: Record<string, unknown>;
};

export type SessionDetail = {
  session: SessionSummary;
  runs: {
    run_id: string;
    final_status?: string | null;
    total_tokens: number;
    total_cost_usd: number;
  }[];
  turns: {
    turn_id: string;
    run_id?: string | null;
    turn_index?: number | null;
    prompt?: string | null;
    status?: string | null;
    total_tokens: number;
    total_cost_usd: number;
    total_tool_calls: number;
  }[];
  jsonl_path: string;
};

export type Timeline = {
  run_id: string;
  turns: SessionDetail["turns"];
  model_calls: {
    model_call_id: string;
    agent_id?: string | null;
    step_idx?: number | null;
    model_id?: string | null;
    latency_ms?: number | null;
    cost_usd?: number | null;
    status?: string | null;
  }[];
  tool_calls: {
    tool_call_id: string;
    tool?: string | null;
    args_summary?: string | null;
    latency_ms?: number | null;
    status?: string | null;
    error_type?: string | null;
    error_message?: string | null;
    started_at?: string | null;
    ended_at?: string | null;
  }[];
  subagents: {
    subagent_id: string;
    agent_type?: string | null;
    question?: string | null;
    duration_ms?: number | null;
    status?: string | null;
    started_at?: string | null;
    ended_at?: string | null;
  }[];
};

export type ContextResponse = {
  run_id: string;
  step_idx: number;
  messages: {
    role: string;
    content?: string | null;
    compacted?: boolean | null;
    tool?: string | null;
    step_idx?: number | null;
  }[];
};

export type ParallelResponse = {
  run_id: string;
  turns: {
    turn_index: number;
    overlap: boolean;
    returns: {
      child_agent_id: string;
      agent_type: string;
      duration_sec?: number | null;
      status: string;
      payload_snippet: string;
    }[];
  }[];
};

export type SafetyResponse = {
  run_id: string;
  approvals: { approval_id: string; tool?: string | null; decision?: string | null }[];
  compactions: {
    compaction_id: string;
    original_event_idx?: number | null;
    before_tokens?: number | null;
    after_tokens?: number | null;
    summary?: string | null;
  }[];
  redactions: { redaction_id: string; pattern?: string | null; count?: number | null }[];
  budget_events: { event_idx: number; budget_reason?: string | null }[];
};

export type ToolUsageItem = {
  tool: string;
  count: number;
  error_count: number;
  avg_latency_ms: number | null;
};

export type PromptLeaderboardItem = {
  label: string;
  count: number;
  sample_session_id: string | null;
};

export type ExpensiveTurnItem = {
  turn_id: string;
  session_id: string;
  run_id: string;
  turn_index: number | null;
  prompt_snippet: string;
  total_cost_usd: number;
  total_tokens: number;
  started_at: string | null;
};

export type ToolErrorOccurrence = {
  tool_call_id: string;
  session_id: string;
  run_id: string;
  turn_id: string | null;
  error_type: string | null;
  error_message: string | null;
  started_at: string | null;
};

export type ToolErrorGroup = {
  tool: string;
  count: number;
  occurrences: ToolErrorOccurrence[];
};

export type StatsResponse = {
  range: string;
  total_runs: number;
  total_turns: number;
  total_tokens: number;
  total_cost_usd: number;
  error_rate: number;
  by_day: { date: string; tokens: number; cost_usd: number; runs: number }[];
  by_agent_type: { label: string; tokens: number; cost_usd: number; count: number }[];
  by_model: { label: string; tokens: number; cost_usd: number; count: number }[];
  tool_errors: { label: string; count: number }[];
  by_tool: ToolUsageItem[];
  top_user_prompts: PromptLeaderboardItem[];
  top_subagent_questions: PromptLeaderboardItem[];
  top_expensive_turns: ExpensiveTurnItem[];
  tool_error_groups: ToolErrorGroup[];
};

export type ToolErrorsDrillResponse = {
  tool: string;
  range: string;
  total: number;
  items: ToolErrorOccurrence[];
};

async function get<T>(path: string): Promise<T> {
  const res = await fetch(`${API}${path}`);
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
  return res.json() as Promise<T>;
}

async function patch<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(`${API}${path}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(text || `${res.status} ${res.statusText}`);
  }
  return res.json() as Promise<T>;
}

export type HealthResponse = {
  ok: boolean;
  workspace_root: string;
  sqlite_path: string;
  traces_dir: string;
  traces_dirs?: string[];
  schema_ready: boolean;
  hint?: string | null;
};

export const api = {
  health: () => get<HealthResponse>("/health"),
  sessions: (limit = 50) => get<{ items: SessionSummary[]; total: number }>(`/sessions?limit=${limit}`),
  activeSession: () =>
    get<{
      session_id: string | null;
      session: SessionDetail | null;
      recent_events: EventItem[];
    }>("/sessions/active"),
  session: (id: string) => get<SessionDetail>(`/sessions/${id}`),
  renameSession: (id: string, display_name: string | null) =>
    patch<SessionSummary>(`/sessions/${id}`, { display_name }),
  events: (id: string, from = -1, limit = 200) =>
    get<{ items: EventItem[]; has_more: boolean }>(
      `/sessions/${id}/events?from_event_idx=${from}&limit=${limit}`,
    ),
  timeline: (runId: string) => get<Timeline>(`/runs/${runId}/timeline`),
  context: (runId: string, stepIdx: number) =>
    get<ContextResponse>(`/runs/${runId}/context?step_idx=${stepIdx}`),
  maxStep: (runId: string) => get<{ max_step_idx: number }>(`/runs/${runId}/context/max-step`),
  parallel: (runId: string) => get<ParallelResponse>(`/runs/${runId}/parallel`),
  safety: (runId: string) => get<SafetyResponse>(`/runs/${runId}/safety`),
  stats: (range: string) => get<StatsResponse>(`/stats?range=${range}`),
  statsToolErrors: (range: string, tool: string, limit = 50, offset = 0) =>
    get<ToolErrorsDrillResponse>(
      `/stats/tool-errors?range=${range}&tool=${encodeURIComponent(tool)}&limit=${limit}&offset=${offset}`,
    ),
  finops: () =>
    get<{ today_spent_usd: number; daily_cap_usd: number; remaining_usd: number }>(
      "/finops/daily",
    ),
};
