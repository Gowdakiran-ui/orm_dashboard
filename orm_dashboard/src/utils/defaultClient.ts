/**
 * Which client the dashboard opens on: the one already open, else the one remembered in this browser, else the client
 * with the most recent successful pipeline run (`last_successful_run_at` on GET /clients/), else the first in the list.
 */
export function pickDefaultClientId(clients: any[], currentId: string | null, savedId: string | null): string | null {
  if (!clients || clients.length === 0) return null;
  const has = (id: string | null) => !!id && clients.some(c => c.id === id);
  if (has(currentId)) return currentId;
  if (has(savedId)) return savedId;
  let best: any = null;
  let bestT = -Infinity;
  for (const c of clients) {
    const t = typeof c?.last_successful_run_at === "string" ? Date.parse(c.last_successful_run_at) : NaN;
    if (Number.isFinite(t) && t > bestT) { best = c; bestT = t; }
  }
  return (best ?? clients[0]).id;
}
