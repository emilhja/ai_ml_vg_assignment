/** Token compaction before/after display (matches chat_ui context_compaction % logic). */

export type CompactionStats = {
  before: number;
  after: number;
  percentRemaining: number;
  percentReduced: number;
};

export function compactionStatsFromTokens(
  before: number | null | undefined,
  after: number | null | undefined,
): CompactionStats | null {
  if (before == null || after == null || before <= 0 || after < 0) return null;
  const percentRemaining = (after / before) * 100;
  const percentReduced = 100 - percentRemaining;
  return { before, after, percentRemaining, percentReduced };
}

export function formatTokenCount(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 10_000) return `${(n / 1_000).toFixed(1)}k`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(2)}k`;
  return n.toLocaleString();
}

/** e.g. "4.1k → 287 tok · 7% of original (93% reduced)" */
export function formatCompactionLine(
  before: number | null | undefined,
  after: number | null | undefined,
): string | null {
  const stats = compactionStatsFromTokens(before, after);
  if (!stats) return null;
  const rem = stats.percentRemaining;
  const red = stats.percentReduced;
  return (
    `${formatTokenCount(stats.before)} → ${formatTokenCount(stats.after)} tok · ` +
    `${rem < 10 ? rem.toFixed(1) : Math.round(rem)}% of original ` +
    `(${red < 10 ? red.toFixed(1) : Math.round(red)}% reduced)`
  );
}

export function formatCompactionShort(
  before: number | null | undefined,
  after: number | null | undefined,
): string | null {
  const stats = compactionStatsFromTokens(before, after);
  if (!stats) return null;
  const rem = stats.percentRemaining;
  return `${formatTokenCount(stats.before)}→${formatTokenCount(stats.after)} · ${rem < 10 ? rem.toFixed(1) : Math.round(rem)}% left`;
}
