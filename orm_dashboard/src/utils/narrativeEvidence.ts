import { fetchDocumentsByIds } from "@/lib/api";

/**
 * A narrative's real evidence set is the exact document IDs narrative_engine.py
 * put in its cluster (3-day window, title-Jaccard, entity overlap, source-diversity
 * gate) -- stored verbatim in evidence_metadata.supporting_documents. Matching by
 * that ID list (rather than by narrative name/topic string) is the only way the
 * Source Evidence panel's count can agree with mention_count.
 */
export function getNarrativeDocuments(narrative: any, documents: any[]): any[] {
  const supportingIds: string[] = narrative?.evidence_metadata?.supporting_documents || [];
  if (supportingIds.length === 0) return [];
  const idSet = new Set(supportingIds.map((id: any) => String(id)));
  return documents.filter((d) => idSet.has(String(d.id)));
}

// Which of a narrative's real supporting_documents ids aren't in the
// already-loaded `documents` set -- e.g. because they've aged out of the
// client's 500-most-recent-document window by the time this narrative's
// panel is opened. Confirmed live: a 7-document narrative from just before
// the window's current cutoff resolved to 0 local matches even though all
// 7 documents still exist.
export function getMissingSupportingDocumentIds(narrative: any, documents: any[]): string[] {
  const supportingIds: string[] = narrative?.evidence_metadata?.supporting_documents || [];
  if (supportingIds.length === 0) return [];
  const loadedIds = new Set(documents.map((d) => String(d.id)));
  return supportingIds.map((id: any) => String(id)).filter((id) => !loadedIds.has(id));
}

// Targeted, on-demand fallback for a narrative's Source Evidence panel:
// fetches only the specific supporting_documents ids missing from the
// already-loaded `documents` set (not a broader reload, not every
// narrative's evidence -- just this one narrative's gap). Callers should
// only invoke this when a narrative's panel is actually open (lazy), and
// should keep showing whatever getNarrativeDocuments already resolved from
// the local set while this resolves. Returns [] (never throws) when
// nothing is missing or the fetch fails -- an id that's genuinely gone
// (e.g. a deleted document) or a transient network error both mean "show
// what's actually retrievable," not "break the panel."
export async function fetchMissingNarrativeDocuments(
  clientId: string | undefined,
  narrative: any,
  documents: any[],
  signal?: AbortSignal
): Promise<any[]> {
  if (!clientId) return [];
  const missingIds = getMissingSupportingDocumentIds(narrative, documents);
  if (missingIds.length === 0) return [];
  try {
    return await fetchDocumentsByIds(clientId, missingIds, signal);
  } catch {
    return [];
  }
}
