// The client isn't scored on share-of-voice directly — it's the remainder
// after every tracked competitor's SOV is subtracted from 100, floored at 0
// so a data glitch pushing competitor SOV over 100 can't go negative.
export function calculateClientSOV(benchmarks: { sov?: number | null }[] | null | undefined): number {
  const totalCompSOV = (benchmarks || []).reduce((sum, b) => sum + (b?.sov ?? 0), 0);
  return Math.max(0, 100 - totalCompSOV);
}
