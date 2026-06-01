import { useEffect, useState } from "react";
import type { EventItem } from "../api";
import { kindColor } from "../lib/eventKindColor";
import { formatTimeTags, type TimeAnchors } from "../lib/groupEvents";
import CompactionStatsBadge from "./CompactionStatsBadge";
import {
  assistantStepTokens,
  expandableEventDetail,
  formatTokenCount,
  subagentReturnDetail,
} from "../lib/laneStats";

type Props = {
  event: EventItem;
  anchors: TimeAnchors;
  showSessionRelative?: boolean;
  highlightEventIdx?: number | null;
};

function ExpandablePanel({
  detail,
  open,
}: {
  detail: NonNullable<ReturnType<typeof expandableEventDetail>>;
  open: boolean;
}) {
  if (!open) return null;
  return (
    <div className="mt-2 space-y-2">
      {detail.sections.map((section) => (
        <div key={section.heading}>
          <p className="text-[10px] uppercase tracking-wide text-violet-400/90 mb-1">{section.heading}</p>
          <pre className="text-xs text-slate-200 whitespace-pre-wrap max-h-48 overflow-y-auto rounded bg-black/30 border border-violet-500/30 p-2">
            {section.body}
          </pre>
        </div>
      ))}
    </div>
  );
}

export default function EventRow({
  event,
  anchors,
  showSessionRelative = false,
  highlightEventIdx = null,
}: Props) {
  const shouldAutoOpen = highlightEventIdx != null && highlightEventIdx === event.event_idx;
  const [open, setOpen] = useState(shouldAutoOpen);

  useEffect(() => {
    if (shouldAutoOpen) setOpen(true);
  }, [shouldAutoOpen]);

  const tags = formatTimeTags(event.timestamp_iso, anchors);
  const timeParts = [tags.absolute, tags.relativeToTurn];
  if (showSessionRelative && tags.relativeToSession) {
    timeParts.push(tags.relativeToSession);
  }
  const timeLabel = timeParts.filter(Boolean).join(" · ");

  const expandable = expandableEventDetail(event);
  const returnDetail = event.kind === "subagent_return" ? subagentReturnDetail(event) : null;
  const stepTokens = event.kind === "assistant_step" ? assistantStepTokens(event) : null;
  const isExpandable = expandable != null;

  const rowBody = (
    <>
      <div className="flex flex-wrap gap-2 items-center">
        {timeLabel && (
          <span className="text-[10px] font-mono text-slate-500 tabular-nums shrink-0">{timeLabel}</span>
        )}
        <span className="text-muted">#{event.event_idx}</span>
        <span className={kindColor(event.kind)}>{event.kind}</span>
        {event.kind === "compaction" && (
          <>
            <span className="text-[10px] uppercase tracking-wide px-1 py-0.5 rounded bg-amber-500/20 text-amber-300">
              compacted
            </span>
            <CompactionStatsBadge
              before={
                typeof event.payload.before_tokens === "number"
                  ? event.payload.before_tokens
                  : Number(event.payload.before_tokens) || null
              }
              after={
                typeof event.payload.after_tokens === "number"
                  ? event.payload.after_tokens
                  : Number(event.payload.after_tokens) || null
              }
            />
          </>
        )}
        {event.kind === "context_compaction" && (
          <CompactionStatsBadge
            before={
              typeof event.payload.before_tokens === "number"
                ? event.payload.before_tokens
                : Number(event.payload.before_tokens) || null
            }
            after={
              typeof event.payload.after_tokens === "number"
                ? event.payload.after_tokens
                : Number(event.payload.after_tokens) || null
            }
          />
        )}
        {event.agent_id && <span className="text-muted">{event.agent_id}</span>}
        {event.tool && <span>{event.tool}</span>}
        {event.status && event.kind !== "subagent_return" && (
          <span className="text-muted">{event.status}</span>
        )}
        {event.kind === "budget_event" && event.payload.budget_reason != null && (
          <span className="text-amber-300/90">{String(event.payload.budget_reason)}</span>
        )}
        {event.kind === "model_error" && event.payload.retryable === true && (
          <span className="text-amber-300/80 text-[10px]">retryable</span>
        )}
        {returnDetail && returnDetail.status !== "ok" && (
          <span className="text-red-400">{returnDetail.status}</span>
        )}
        {event.latency_ms != null && <span className="text-muted">{event.latency_ms}ms</span>}
        {stepTokens?.tokensIn != null && stepTokens.tokensIn > 0 && (
          <span className="text-amber-200/90 tabular-nums">{formatTokenCount(stepTokens.tokensIn)} in</span>
        )}
        {stepTokens?.tokensOut != null && stepTokens.tokensOut > 0 && (
          <span className="text-amber-200/70 tabular-nums">{formatTokenCount(stepTokens.tokensOut)} out</span>
        )}
        {stepTokens?.costUsd != null && stepTokens.costUsd > 0 && (
          <span className="text-muted tabular-nums">${stepTokens.costUsd.toFixed(4)}</span>
        )}
        {returnDetail?.childTotalTokens != null && (
          <span className="text-amber-200/90 tabular-nums">
            {formatTokenCount(returnDetail.childTotalTokens)} tok
          </span>
        )}
        {returnDetail?.childCostUsd != null && (
          <span className="text-muted tabular-nums">${returnDetail.childCostUsd.toFixed(4)}</span>
        )}
        {isExpandable && (
          <span className="text-violet-400 text-[10px]">
            {open ? "▼ hide" : `▶ ${expandable.toggleLabel}`}
          </span>
        )}
      </div>
      {event.kind === "statusline" && event.payload.text != null && (
        <p className="mt-1 text-emerald-200/90 truncate">{String(event.payload.text)}</p>
      )}
      {event.kind === "user_prompt" && event.payload.prompt != null && (
        <p className="mt-1 text-slate-200 line-clamp-2">{String(event.payload.prompt)}</p>
      )}
      {event.kind === "model_error" && !open && event.payload.message != null && (
        <p className="mt-1 text-red-300/90 text-[11px] line-clamp-3">{String(event.payload.message)}</p>
      )}
      {event.kind === "tool_result" && !open && (
        <p className="mt-1 text-slate-400 line-clamp-1 text-[11px]">
          {String(event.payload.result_summary ?? event.payload.result_full ?? "").slice(0, 200)}
        </p>
      )}
      {isExpandable && <ExpandablePanel detail={expandable} open={open} />}
    </>
  );

  const liClass =
    shouldAutoOpen && open
      ? "ring-1 ring-violet-500/40"
      : "";

  if (isExpandable) {
    return (
      <li id={`event-${event.event_idx}`} className={liClass}>
        <button
          type="button"
          onClick={() => setOpen((v) => !v)}
          className={`w-full text-left bg-panel/60 rounded px-3 py-2 border transition-colors ${
            open
              ? "border-violet-500/50 ring-1 ring-violet-500/20"
              : "border-slate-700/40 hover:border-violet-500/40"
          }`}
        >
          {rowBody}
        </button>
      </li>
    );
  }

  return (
    <li
      id={`event-${event.event_idx}`}
      className={`bg-panel/60 rounded px-3 py-2 border border-slate-700/40 ${liClass}`}
    >
      {rowBody}
    </li>
  );
}
