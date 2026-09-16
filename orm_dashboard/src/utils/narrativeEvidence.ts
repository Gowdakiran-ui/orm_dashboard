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
