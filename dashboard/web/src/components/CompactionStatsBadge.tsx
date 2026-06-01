import { formatCompactionLine, formatCompactionShort } from "../lib/compactionStats";

type Props = {
  before: number | null | undefined;
  after: number | null | undefined;
  variant?: "inline" | "block";
};

export default function CompactionStatsBadge({ before, after, variant = "inline" }: Props) {
  const line = variant === "block" ? formatCompactionLine(before, after) : formatCompactionShort(before, after);
  if (!line) return null;
  return (
    <span
      className={
        variant === "block"
          ? "block mt-1 text-xs text-amber-200/90 font-mono tabular-nums"
          : "text-[10px] font-mono tabular-nums px-1.5 py-0.5 rounded bg-amber-500/15 text-amber-200/90"
      }
      title={formatCompactionLine(before, after) ?? undefined}
    >
      {line}
    </span>
  );
}
