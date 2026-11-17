"use client";

import { useEffect, useState } from "react";
import { fetchSeeded } from "@/lib/api";

export interface SeededPayload {
  window: { executive_days: number; benchmark_days: number };
  // "not_set_up": no seeding record and no backfill slices for this client. Absent from an older server.
  setup?: { state: "not_set_up" | "set_up" };
  executives: { entity_id: string; name: string; rank: number; role?: string | null }[];
  competitors: { entity_id: string; name: string; rank: number; context_term?: string | null }[];
}

// The client's seeded executives and competitors, read-only. null until loaded and on any failure: the pages then
// behave exactly as before seeding existed (a failed read must never blank them).
export function useSeeded(clientId?: string | null): SeededPayload | null {
  const [data, setData] = useState<SeededPayload | null>(null);
  useEffect(() => {
    setData(null);
    if (!clientId) return;
    const controller = new AbortController();
    fetchSeeded(clientId, controller.signal)
      .then((d: SeededPayload) => { if (!controller.signal.aborted) setData(d); })
      .catch(() => { /* leave null */ });
    return () => controller.abort();
  }, [clientId]);
  return data;
}
