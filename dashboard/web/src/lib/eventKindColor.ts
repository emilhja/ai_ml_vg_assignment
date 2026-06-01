export function kindColor(kind: string): string {
  if (kind.includes("error") || kind === "budget_event") return "text-red-400";
  if (kind === "compaction" || kind === "context_compaction") return "text-amber-300";
  if (kind === "tool_call" || kind === "tool_result") return "text-cyan-300";
  if (kind === "subagent_spawn" || kind === "subagent_return") return "text-violet-300";
  if (kind === "statusline") return "text-emerald-300";
  if (kind === "user_prompt") return "text-sky-300";
  return "text-slate-300";
}
