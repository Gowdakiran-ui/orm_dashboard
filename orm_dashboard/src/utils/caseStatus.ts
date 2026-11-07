// Case status (allegation / probe / charged / ...) and incident grouping for the Risk Center. Pure logic, no React,
// so every sentence and count they state can be unit-tested.
//
// The status is the risk stage's own label, stored in each document's `risk_explainability.case_status`. The incidents
// come from the server's `document_risk.incidents` block (documents about the same story are one incident). Anything
// missing yields null / the old per-document behaviour, never a believable default.

export type CaseStatus = "allegation" | "probe" | "charged" | "penalty_or_order" | "settled" | "dismissed_or_closed" | "unrelated";

export const CASE_STATUS_LABEL: Record<CaseStatus, string> = {
  allegation: "Allegation",
  probe: "Probe",
  charged: "Charged",
  penalty_or_order: "Penalty / order",
  settled: "Settled",
  dismissed_or_closed: "Dismissed / closed",
  unrelated: "Unrelated",
};

// What each status means, in plain words (chip tooltip).
export const CASE_STATUS_MEANING: Record<CaseStatus, string> = {
  allegation: "A claim or complaint; no authority has acted yet.",
  probe: "An investigation, raid, FIR or notice is under way; nothing formally charged.",
  charged: "Formal charges or a chargesheet have been filed.",
  penalty_or_order: "A fine, penalty, refund or adverse order was issued.",
  settled: "Settled with the authority; the case ended by payment.",
  dismissed_or_closed: "Dropped, dismissed, cleared or closed.",
  unrelated: "Not a legal or regulatory event about the company.",
};

export function isCaseStatus(v: unknown): v is CaseStatus {
  return typeof v === "string" && Object.prototype.hasOwnProperty.call(CASE_STATUS_LABEL, v);
}

// The stored label of a document, or null when it has none (older scores, or the label step was off or failed).
export function caseStatusOf(d: any): CaseStatus | null {
  const s = d?.risk_explainability?.case_status;
  return isCaseStatus(s) ? s : null;
}

export function statusSentence(d: any): string | null {
  const s = caseStatusOf(d);
  if (!s) return null;
  const base = `The story is at the ${CASE_STATUS_LABEL[s].toLowerCase()} stage.`;
  return d?.risk_explainability?.case_status_cap_applied === true
    ? `${base} Stories at this stage are held at Medium and do not reach High.`
    : base;
}

// ---- Incidents ---------------------------------------------------------------------------------------------------
export interface IncidentItem {
  id: string;
  title: string;
  severity: "CRITICAL" | "HIGH" | "MEDIUM";
  score: number;
  status: CaseStatus | null;
  documents: number;
  sources: number;
  docIds: string[];
}

export interface IncidentBlock {
  total: number;
  critical: number;
  high: number;
  medium: number;
  items: IncidentItem[];
}

// Reads `document_risk.incidents`; null when absent or malformed (an older server), so callers fall back to documents.
export function incidentBlockFromSummary(block: any): IncidentBlock | null {
  const inc = block?.incidents;
  if (!inc || typeof inc !== "object") return null;
  const n = (v: any) => (typeof v === "number" && Number.isFinite(v) ? v : null);
  const total = n(inc.total), critical = n(inc.critical), high = n(inc.high), medium = n(inc.medium);
  if (total === null || critical === null || high === null || medium === null || !Array.isArray(inc.items)) return null;
  const items: IncidentItem[] = [];
  for (const it of inc.items) {
    if (!it || typeof it.id !== "string" || typeof it.title !== "string" || typeof it.documents !== "number" || !Array.isArray(it.doc_ids)) continue;
    const severity = it.severity === "CRITICAL" || it.severity === "HIGH" || it.severity === "MEDIUM" ? it.severity : null;
    if (!severity) continue;
    items.push({
      id: it.id, title: it.title, severity, score: typeof it.score === "number" ? it.score : 0,
      status: isCaseStatus(it.status) ? it.status : null,
      documents: it.documents,
      sources: typeof it.sources === "number" ? it.sources : it.documents,
      docIds: it.doc_ids.filter((x: any) => typeof x === "string"),
    });
  }
  return { total, critical, high, medium, items };
}

export interface IncidentRef {
  id: string;
  documents: number;       // every document in the incident, from the server
  sources: number;         // distinct outlets
  others: any[];           // the other documents of this incident that are in the loaded list
}

// One row per incident: the highest-scoring document that is in the loaded list leads, the rest of that incident's
// loaded documents hang off it as `incident.others`. Documents in no incident stay single rows (`incident: null`).
// `flagged` must already be sorted highest score first (flaggedDocs does that), so the lead is the strongest one.
export function collapseByIncident(flagged: any[], items: IncidentItem[] | null | undefined): any[] {
  if (!items || items.length === 0) return flagged.map(d => ({ ...d, incident: null }));
  const byDoc = new Map<string, IncidentItem>();
  for (const it of items) for (const id of it.docIds) byDoc.set(id, it);
  const rowOf = new Map<string, any>();
  const rows: any[] = [];
  for (const d of flagged) {
    const it = byDoc.get(d.id);
    if (!it) { rows.push({ ...d, incident: null }); continue; }
    const lead = rowOf.get(it.id);
    if (lead) { lead.incident.others.push(d); continue; }
    const row = { ...d, incident: { id: it.id, documents: it.documents, sources: it.sources, others: [] } as IncidentRef };
    rowOf.set(it.id, row);
    rows.push(row);
  }
  return rows;
}

// "5 sources" when the incident was reported by more than one outlet, "2 articles" when several articles came from one.
export function incidentBadgeText(inc: { documents: number; sources: number } | null | undefined): string | null {
  if (!inc || inc.documents <= 1) return null;
  if (inc.sources > 1) return `${inc.sources} sources`;
  return `${inc.documents} articles`;
}

export function documentsNote(n: number): string {
  return `${n} ${n === 1 ? "document" : "documents"}`;
}
