// Mocked API for the theme/contrast tests. Shapes follow the real endpoint
// outputs (see report_samples/fixes/harness/scenarios.ts); all values are synthetic.
import type { Page } from "@playwright/test";

export const CID = "99999999-0000-4000-8000-000000000001";
const TOPICS = ["General", "Innovation", "Legal Risk", "Market Share", "Financial Results", "Competition", "Executive Leadership"];
const LEVELS = ["LOW", "MEDIUM", "HIGH", "CRITICAL"];

function doc(i: number, level = "LOW") {
  const risk = { LOW: 12, MEDIUM: 38, HIGH: 62, CRITICAL: 88 }[level]!;
  return {
    id: `d-${i}`, title: `Article ${i} about the company and its quarterly outlook`, source: "Example RSS Source",
    document_type: "rss", timestamp: new Date(Date.UTC(2026, 9, 1 + (i % 28), 6 + (i % 12))).toISOString(),
    status: "COMPLETED", sentiment: [0, 0.5, -0.6, 0, 1][i % 5], risk, scored: true, risk_level: level, risk_exact: risk,
    risk_sentiment: level === "LOW" ? "Neutral" : "Negative", date_basis: "published",
    risk_explainability: { confidence: [0.3, 0.5, 0.8][i % 3] }, original_content: "",
    extracted_entities: [], topic: TOPICS[i % TOPICS.length], reputation_impact: "+0.0",
    url: "https://example.com/a", summary: "Synthetic summary text for the details drawer.",
  };
}
const docs = Array.from({ length: 60 }, (_, i) => doc(i, LEVELS[i % 4]));
const flagged = docs.filter((d) => d.risk_level !== "LOW");

const alerts = [1, 2, 3].map((i) => ({
  id: `al-${i}`, alert_type: "Multi-Signal Incident", severity: i % 2 ? "HIGH" : "CRITICAL",
  title: `Multi-Signal Incident: Entity ${i}`, is_acknowledged: false,
  created_at: new Date(Date.UTC(2026, 9, 1 + i, 5)).toISOString(), entity_type: ["brand", "person", "product"][i % 3],
  ai_summary: { what: `${i + 1} risk signals.`, when: "Oct 08, 2026 11:14 UTC", how_to_solve: "Review the linked documents.", source: "generated" },
}));
const bench = Array.from({ length: 5 }, (_, i) => ({
  id: `b${i}`, competitor_id: `c${i}`, competitor_name: `Competitor ${i}`, rank: i + 1, sov: 0.5 + (i % 3),
  reputation: 60 + i * 4, sentiment: 0.1, risk: 10 + i, visibility: 5, health_status: "OK", confidence_score: 0.5,
  data_coverage: 0.5, client_comparable_score: 70, client_rank: 3, client_share_of_voice: 90,
}));
const execs = Array.from({ length: 5 }, (_, i) => ({
  id: `e${i}`, entity_id: `en${i}`, name: `Person Number ${i}`, score: 45 + i * 11, grade: ["D", "C", "B", "B", "A"][i],
  confidence_score: 0.5, data_coverage: 0.5, health_status: "OK", as_of: "2026-10-02T15:02:27+00:00", document_count: 3 + i,
}));

const GET: Record<string, unknown> = {
  "/auth/me": { id: "u1", email: "audit@example.com", role: "super_admin", client_ids: [CID] },
  "/clients/": [{ id: CID, name: "Audit Test Co", industry: "Technology", status: "ACTIVE", created_at: "2026-09-01T00:00:00Z" }],
  [`/client-intelligence/${CID}/reputation`]: { score: 74.2, grade: "B", confidence_score: 0.6, data_coverage: 0.5 },
  [`/client-intelligence/${CID}/reputation-summary`]: {
    reputation: { score: 74.2, grade: "B", status: "ok", computed_at: "2026-10-02T15:02:27+00:00" },
    document_risk: { visible_documents: 60, scored_documents: 60, unscored_documents: 0, total: flagged.length, critical: 15, high: 15, medium: 15, average: 55, highest: 88, as_of: "2026-10-03T05:55:00+00:00", top: flagged.slice(0, 2).map((d) => ({ title: d.title, risk: d.risk })) },
    sentiment: { positive: 12, neutral: 30, negative: 6, dominant: "neutral" }, executive_alert: { open: false, alert: null },
    last_pipeline_run: { finished_at: "2026-11-05T14:55:59+00:00" },
  },
  [`/client-intelligence/${CID}/plan-advisory`]: { lead: "Two high-risk stories need review this week.", flagged: true },
  [`/client-intelligence/${CID}/benchmark`]: bench,
  [`/client-intelligence/${CID}/executives`]: execs,
  [`/client-intelligence/${CID}/active-alerts`]: alerts,
  [`/client-intelligence/${CID}/risks`]: { client_id: CID, average_recent_risk_score: 41.5, recent_critical_events: 3, recent_high_events: 5 },
  [`/client-intelligence/${CID}/reputation-history`]: Array.from({ length: 14 }, (_, i) => ({ date: new Date(Date.UTC(2026, 9, 1 + i)).toISOString(), score: 68 + (i % 7) })),
  [`/client-intelligence/${CID}/reputation-breakdown`]: { sentiment: 72, risk: 65, source: 80, visibility: 58 },
  [`/documents/client/${CID}`]: docs,
  [`/documents/client/${CID}/counts`]: { total: 60, scored: 60, unscored: 0 },
  [`/client-intelligence/${CID}/telemetry`]: { errors: [], last_run: "2026-10-02T15:02:27+00:00" },
  [`/client-intelligence/${CID}/executive-candidates`]: [],
  [`/client-intelligence/${CID}/competitor-candidates`]: [],
  [`/client-intelligence/${CID}/seeded`]: { executives: [], competitors: [] },
  [`/client-intelligence/${CID}/topic-distribution`]: TOPICS.map((t, i) => ({ topic: t, count: 10 - i })),
  [`/client-intelligence/${CID}/counterfeit/scans`]: [],
  "/admin/users/": [
    { id: "u1", email: "audit@example.com", role: "super_admin", client_ids: [CID] },
    { id: "u2", email: "viewer@example.com", role: "viewer", client_ids: [CID] },
  ],
  [`/clients/${CID}/pipeline/status`]: { status: "idle", stage: null },
};

export async function mockApi(page: Page) {
  await page.route(/^http:\/\/(localhost|127\.0\.0\.1):8000\//, async (route) => {
    const url = new URL(route.request().url());
    const key = url.pathname;
    const single = key.startsWith("/documents/") && !key.startsWith("/documents/client/");
    const body = single
      ? { ...docs[2], original_content: "Synthetic article body used for the drawer." }
      : GET[key] ?? (route.request().method() === "GET" ? [] : {});
    await route.fulfill({
      status: 200, contentType: "application/json", body: JSON.stringify(body),
      headers: { "access-control-allow-origin": "http://localhost:3101", "access-control-allow-credentials": "true" },
    });
  });
}
