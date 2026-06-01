import type { EventViewMode } from "../lib/groupEvents";
import WideScreenToggle from "./WideScreenToggle";

type Props = {
  viewMode: EventViewMode;
  onViewModeChange: (mode: EventViewMode) => void;
  parallelColumns: boolean;
  onParallelColumnsChange: (enabled: boolean) => void;
  showParallelToggle: boolean;
};

const MODES: { id: EventViewMode; label: string }[] = [
  { id: "flat", label: "Flat" },
  { id: "by-turn", label: "By turn" },
  { id: "turn-agents", label: "Turn + agents" },
];

export default function EventStreamToolbar({
  viewMode,
  onViewModeChange,
  parallelColumns,
  onParallelColumnsChange,
  showParallelToggle,
}: Props) {
  return (
    <div className="flex flex-wrap items-center gap-2 mb-3">
      <div className="flex flex-wrap gap-1 rounded-md border border-slate-700/50 p-0.5 bg-panel/40">
        {MODES.map((m) => (
          <button
            key={m.id}
            type="button"
            onClick={() => onViewModeChange(m.id)}
            className={`px-3 py-1.5 rounded text-xs font-medium ${
              viewMode === m.id ? "bg-accent/25 text-accent" : "text-muted hover:text-white"
            }`}
          >
            {m.label}
          </button>
        ))}
      </div>
      {showParallelToggle && viewMode === "turn-agents" && (
        <button
          type="button"
          onClick={() => onParallelColumnsChange(!parallelColumns)}
          className={`px-3 py-1.5 rounded text-xs border ${
            parallelColumns
              ? "border-violet-500/50 bg-violet-500/20 text-violet-300"
              : "border-slate-700/50 text-muted hover:text-white"
          }`}
        >
          Parallel columns
        </button>
      )}
      <WideScreenToggle className="ml-auto" />
    </div>
  );
}
