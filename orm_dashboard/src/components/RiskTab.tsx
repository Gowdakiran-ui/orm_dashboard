import React, { useState, useMemo, useEffect, useRef } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import {
  AlertTriangle, ShieldAlert, X, ExternalLink,
  AlertOctagon, Info
} from "lucide-react";
import { TelemetryErrorWidget } from "@/components/TelemetryErrorWidget";
import { fetchDocumentDetails } from "@/lib/api";
import { useTheme } from "@/components/theme/ThemeProvider";
import { glassCard, glassTokens, glassPill, glassPrimaryButton, mutedText, bodyText, SPECULAR_LINE } from "@/components/theme/tokens";
import { InfoTooltip } from "@/components/ui/InfoTooltip";
import { useTabNavigation } from "@/hooks/useTabNavigation";
import {
  RiskMatrixSeverityConfidenceDefinition,
  CriticalRisksVsActiveAlertsDefinition,
  FlaggedArticlesDefinition,
} from "@/lib/metricDefinitions";
import { riskStatsFromSummary, sourceState, formatAsOf } from "@/utils/brandEquity";
import {
  flaggedDocs, buildMatrix, legacyCellDocs, tilesFromSummary, reasonSentence, dateLabel,
  localDateKey, windowNote, unscoredNote, confidencePercent, formatScore, levelWord,
  MATRIX_BANDS, MATRIX_CONFIDENCE,
} from "@/utils/riskCenter";

// Entity-type prefix for an alert's "Multi-Signal Incident: X" title, so a
// person, a product, and the client's own brand don't all read as
// equivalent "incidents" at the same visual tier (ui_redesign_plan.md #5).
// Reuses the `entity_type` field client_intelligence.py's active-alerts
// endpoint now serializes -- no guessing from the title text.
const ALERT_ENTITY_TYPE_LABEL: Record<string, string> = {
  person: "Executive",
  product: "Product",
  brand: "Company",
  competitor: "Competitor",
};

const UNAVAILABLE = "—";

const SEVERITY_BADGE: Record<string, string> = {
  CRITICAL: "bg-red-500/10 text-red-500 border border-red-500/20",
  HIGH: "bg-orange-500/10 text-orange-500 border border-orange-500/20",
  MEDIUM: "bg-yellow-500/10 text-yellow-600 border border-yellow-500/20",
};
const SEVERITY_TEXT: Record<string, string> = {
  CRITICAL: "text-red-500",
  HIGH: "text-orange-500",
  MEDIUM: "text-yellow-600",
};

export interface RiskTabProps {
  alertsLoading: boolean;
  alertsError: string | null;
  alerts: any[];
  documentsLoading: boolean;
  documentsError: string | null;
  documents: any[];
  // Server-computed counts over every visible article (reputation-summary's
  // `document_risk` block); the tiles read these, not the 500-article table.
  reputationSummary?: any;
  reputationSummaryLoading?: boolean;
  reputationSummaryError?: string | null;
  clientId?: string | null;
}

export function RiskTab({
  alertsLoading,
  alertsError,
  alerts,
  documentsLoading,
  documentsError,
  documents,
  reputationSummary,
  reputationSummaryLoading,
  reputationSummaryError,
  clientId
}: RiskTabProps) {
  const { theme } = useTheme();
  const isDark = theme === "dark";
  const accent = isDark ? "#00F5D4" : "#3B82F6";
  const { navigateTo, searchParams } = useTabNavigation();
  const [selectedDocId, setSelectedDocId] = useState<string | null>(null);
  const [expandedAlertId, setExpandedAlertId] = useState<string | null>(null);

  // Matrix-cell drill-down -- sourced from the URL (?tab=risk&band=..&confidence=..)
  // so a cell click lands on a shareable, back-navigable filtered view.
  // The older ?impact=..&likelihood=.. form is still read because Executive
  // Analytics' own matrix links to it with its own score tiers.
  const bandParam = searchParams.get("band");
  const confidenceParam = searchParams.get("confidence");
  const impactParam = searchParams.get("impact");
  const likelihoodParam = searchParams.get("likelihood");
  const selectedCell = bandParam && confidenceParam
    ? { kind: "severity" as const, row: bandParam, col: confidenceParam }
    : impactParam && likelihoodParam
      ? { kind: "scoreTier" as const, row: impactParam, col: likelihoodParam }
      : null;
  const clearCellFilter = () => navigateTo("risk", { severity: searchParams.get("severity") ?? undefined, date: searchParams.get("date") ?? undefined });

  // Severity/date filters (drill-throughs): narrow only the table below, not
  // the tiles or matrix above it.
  const severityParam = searchParams.get("severity");
  const dateParam = searchParams.get("date");
  const hasListFilter = Boolean(severityParam || dateParam);
  const clearListFilter = () => navigateTo("risk");

  // The /documents/client/{id} list (source of `documents`) doesn't include
  // `url` -- fetch it per-selection the same way FeedTab does, since the
  // single-document detail endpoint does return it.
  const [selectedDocUrl, setSelectedDocUrl] = useState<string | null>(null);

  useEffect(() => {
    if (!selectedDocId || !clientId) {
      setSelectedDocUrl(null);
      return;
    }
    let cancelled = false;
    fetchDocumentDetails(clientId, selectedDocId)
      .then(details => { if (!cancelled) setSelectedDocUrl(details?.url || null); })
      .catch(() => { if (!cancelled) setSelectedDocUrl(null); });
    return () => { cancelled = true; };
  }, [selectedDocId, clientId]);

  // Flagged = risk-scored and above the LOW band, banded on the backend's
  // own unrounded `risk_level`. An article with no RiskEvent is "not scored",
  // never a score of 0 (utils/riskCenter.ts). LOW-severity items exist in
  // the data but are not incidents.
  const riskDocs = useMemo(() => flaggedDocs(documents), [documents]);

  const filteredRiskDocs = useMemo(() => {
    return riskDocs.filter(d => {
      if (severityParam && d.severity.toLowerCase() !== severityParam) return false;
      if (dateParam && localDateKey(d.timestamp) !== dateParam) return false;
      return true;
    });
  }, [riskDocs, severityParam, dateParam]);

  // Risk Events table horizontal-scroll affordance (tablet-width finding,
  // ui_redesign_plan_tablet.md Section 4): the shared <Table> primitive's
  // own overflow-x-auto wrapper gives no visual cue that columns are
  // scrolled off-screen, so on a touch device (where scrollbars are
  // invisible until touched) the "Details" action link can go undiscovered.
  // Reads the table's own container div (Table's `data-slot="table-container"`)
  // rather than modifying that shared primitive, since it's reused by five
  // other tables that don't have this problem.
  const riskTableWrapperRef = useRef<HTMLDivElement | null>(null);
  const [riskTableScrollable, setRiskTableScrollable] = useState(false);

  useEffect(() => {
    const container = riskTableWrapperRef.current?.querySelector('[data-slot="table-container"]') as HTMLElement | null;
    if (!container) return;

    const checkScrollable = () => {
      setRiskTableScrollable(container.scrollWidth > container.clientWidth + 1);
    };

    checkScrollable();
    const resizeObserver = new ResizeObserver(checkScrollable);
    resizeObserver.observe(container);
    window.addEventListener("resize", checkScrollable);
    return () => {
      resizeObserver.disconnect();
      window.removeEventListener("resize", checkScrollable);
    };
  }, [filteredRiskDocs]);

  const selectedDoc = useMemo(() => {
    if (!selectedDocId) return null;
    return riskDocs.find(d => d.id === selectedDocId) || null;
  }, [selectedDocId, riskDocs]);

  // Tiles: server counts over every visible article. null = unavailable.
  const summaryState = sourceState(reputationSummaryLoading, reputationSummaryError);
  const tiles = useMemo(
    () => (summaryState === "ready" ? tilesFromSummary(riskStatsFromSummary(reputationSummary?.document_risk)) : null),
    [summaryState, reputationSummary]
  );

  const matrix = useMemo(() => buildMatrix(riskDocs), [riskDocs]);

  if (documentsLoading) {
    return (
      <div className="space-y-6 animate-pulse">
        <div className="grid gap-6 md:grid-cols-5">
          {[1, 2, 3, 4, 5].map(x => (
            <div key={x} className={`h-20 rounded-3xl ${glassTokens[theme].card}`} />
          ))}
        </div>
        <div className="grid gap-6 md:grid-cols-2">
          <div className={`h-60 rounded-3xl ${glassTokens[theme].card}`} />
          <div className={`h-60 rounded-3xl ${glassTokens[theme].card}`} />
        </div>
      </div>
    );
  }

  if (documentsError) {
    return (
      <Card className={`${glassCard(theme)} border-red-500/20 col-span-4 h-96`}>
        <TelemetryErrorWidget title="Risk Telemetry Offline" message={documentsError} />
      </Card>
    );
  }

  const tileValue = (v: number | null | undefined) => (tiles && v !== null && v !== undefined ? v : UNAVAILABLE);
  const tileScore = (v: number | null | undefined) => (tiles && v !== null && v !== undefined ? formatScore(v) : UNAVAILABLE);
  const asOfText = tiles?.asOf ? formatAsOf(tiles.asOf) : null;
  const tableWindowNote = windowNote(riskDocs.length, tiles ? tiles.flagged : null);
  const notChecked = unscoredNote(tiles?.unscored);

  const selectedCellDocs = (() => {
    if (!selectedCell) return [];
    if (selectedCell.kind === "severity") {
      return (matrix.grid as any)[selectedCell.row]?.[selectedCell.col] || [];
    }
    return legacyCellDocs(riskDocs, selectedCell.row, selectedCell.col);
  })();

  return (
    <div className="space-y-8 relative">

      {/* 1. Summary tiles -- server counts over every article. Flagged and
          Critical get slightly larger type so the two numbers an exec most
          needs land first, at a glance. */}
      <div className="space-y-3">
        <span className={`text-xs font-mono uppercase tracking-wider block ${mutedText(theme)}`}>
          At a Glance · all-time counts{asOfText ? ` · scores as of ${asOfText}` : ""}
        </span>
        <div className="grid gap-4 items-start sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-5 font-mono">
          {[
            { label: "Flagged Articles", value: tileValue(tiles?.flagged), color: isDark ? "text-[#00F5D4]" : "text-[#3B82F6]", highlight: true, def: <FlaggedArticlesDefinition /> },
            { label: "Critical", value: tileValue(tiles?.critical), color: "text-red-500", highlight: true, def: <CriticalRisksVsActiveAlertsDefinition /> },
            { label: "High", value: tileValue(tiles?.high), color: "text-orange-500" },
            { label: "Medium", value: tileValue(tiles?.medium), color: "text-yellow-500" },
            { label: "Highest Score", value: tileScore(tiles?.highest), color: tiles && tiles.highest !== null ? "text-red-500 font-black" : mutedText(theme) }
          ].map((card, idx) => (
            <div
              key={idx}
              className={`${glassCard(theme)} p-4 flex flex-col justify-between`}
            >
              <div className={SPECULAR_LINE} />
              {/* Label stays plain, single-line text -- the (i) trigger is
                  pinned to the card's corner instead of sharing the flex row
                  with it. Inline placement (fine on wide headers like the
                  Risk Matrix) forced a wrap here: these tiles are narrow,
                  too narrow for label text + the tooltip's 44px touch target
                  on one line. */}
              {'def' in card && card.def && (
                // Wrapper div carries the absolute positioning -- passing
                // "absolute" straight into InfoTooltip's own className prop
                // fights the "relative" class already hardcoded on that
                // same element (Tailwind's cascade order doesn't guarantee
                // which wins), which left the button sitting in normal flow
                // and inflating this tile's height instead of escaping it.
                <div className="absolute top-3 right-3">
                  <InfoTooltip label={`About ${card.label}`}>{card.def}</InfoTooltip>
                </div>
              )}
              <span className={`text-xs ${mutedText(theme)} uppercase tracking-wider block truncate pr-6 mb-2`}>
                {card.label}
              </span>
              <span className={`${card.highlight ? "text-2xl" : "text-xl"} font-bold ${card.color}`}>{card.value}</span>
            </div>
          ))}
        </div>
        {summaryState === "loading" && (
          <p className={`text-xs font-mono ${mutedText(theme)}`}>Loading counts…</p>
        )}
        {summaryState !== "loading" && !tiles && (
          <p className={`text-xs font-mono ${mutedText(theme)}`}>Counts are unavailable right now.</p>
        )}
        {notChecked && <p className={`text-xs font-mono ${mutedText(theme)}`}>{notChecked}</p>}
      </div>

      {/* 1b. Active Alerts */}
      <Card id="active-alerts-section" className={glassCard(theme)}>
        <div className={SPECULAR_LINE} />
        <CardHeader>
          <CardTitle className={`text-xs font-mono uppercase tracking-wider ${mutedText(theme)} flex items-center justify-between`}>
            <span className="flex items-center">
              <AlertTriangle className="h-4 w-4 text-orange-500 mr-2" />
              ACTIVE ALERTS
              <InfoTooltip label="About Active Alerts vs. Critical Risks"><CriticalRisksVsActiveAlertsDefinition /></InfoTooltip>
            </span>
            {!alertsLoading && !alertsError && (
              <Badge className={`${glassPill(theme)} text-orange-500 font-mono text-xs`}>{alerts.length} Active</Badge>
            )}
          </CardTitle>
        </CardHeader>
        <CardContent>
          {alertsLoading ? (
            <div className="space-y-2 animate-pulse">
              {[1, 2, 3].map(x => (
                <div key={x} className={`h-10 rounded-lg ${glassTokens[theme].card}`} />
              ))}
            </div>
          ) : alertsError ? (
            <TelemetryErrorWidget title="Alert Feed Offline" message={alertsError} />
          ) : alerts.length === 0 ? (
            <div className={`text-center py-6 ${mutedText(theme)} font-mono text-xs`}>No unacknowledged alerts.</div>
          ) : (
            <div className="space-y-2 max-h-[420px] overflow-y-auto overflow-x-hidden pr-1">
              {alerts.map((alert) => {
                const isExpanded = expandedAlertId === alert.id;
                const aiSummary = alert.ai_summary;
                return (
                  // A4 fix: glassPill() applies rounded-full, meant for
                  // short one-line pill badges -- reusing it as the wrapper
                  // for this whole (multi-line once expanded) card turned
                  // it into a stadium/oval shape that clipped the AI
                  // Summary text at the curved sides. Uses the pill's own
                  // bg/border/shadow token directly instead, with a normal
                  // rounded-2xl corner radius that works at any height.
                  <div key={alert.id} className={`rounded-2xl font-mono text-xs overflow-hidden ${glassTokens[theme].pill}`}>
                    <button
                      type="button"
                      onClick={() => setExpandedAlertId(isExpanded ? null : alert.id)}
                      className="w-full flex flex-col sm:flex-row sm:items-center sm:justify-between gap-1 sm:gap-0 p-3 min-h-[44px] text-left"
                    >
                      <div className="flex items-center space-x-3 min-w-0 w-full sm:w-auto">
                        <Badge className={`font-mono text-xs shrink-0 ${
                          alert.severity === "CRITICAL" ? "bg-red-500/10 text-red-500 border border-red-500/20" :
                          alert.severity === "HIGH" ? "bg-orange-500/10 text-orange-500 border border-orange-500/20" :
                          alert.severity === "WARNING" ? "bg-yellow-500/10 text-yellow-600 border border-yellow-500/20" :
                          `${isDark ? "bg-zinc-500/10 text-zinc-400 border border-zinc-500/20" : "bg-zinc-500/10 text-zinc-500 border border-zinc-500/20"}`
                        }`}>
                          {alert.severity}
                        </Badge>
                        <span className={`font-bold truncate ${bodyText(theme)}`}>
                          {ALERT_ENTITY_TYPE_LABEL[alert.entity_type] && (
                            <span className={mutedText(theme)}>{ALERT_ENTITY_TYPE_LABEL[alert.entity_type]}: </span>
                          )}
                          {alert.title}
                        </span>
                        <span className={`text-xs shrink-0 hidden sm:inline ${mutedText(theme)}`}>{alert.alert_type}</span>
                      </div>
                      <span className={`text-xs shrink-0 sm:ml-3 ${mutedText(theme)}`}>
                        {alert.created_at ? new Date(alert.created_at).toLocaleString(undefined, { dateStyle: 'short', timeStyle: 'short' }) : "N/A"}
                      </span>
                    </button>

                    {/* Expanded alert: the deterministic "why" (what/when,
                        built from the alert's own stored evidence) and the
                        one AI-generated field (how_to_solve) are labelled
                        separately -- only the latter is LLM text. */}
                    {isExpanded && (
                      <div className={`px-3 pb-3 border-t ${isDark ? "border-white/[0.08]" : "border-black/[0.06]"}`}>
                        {aiSummary ? (
                          // Solid opaque panel, not the glass/translucent
                          // convention used elsewhere -- this sits on top
                          // of the row above it once expanded, and a
                          // translucent background let that row's text
                          // bleed through and become unreadable.
                          <div className={`mt-2.5 space-y-2.5 p-3 rounded-xl border ${isDark ? "bg-zinc-900 border-white/[0.08]" : "bg-white border-black/[0.08]"}`}>
                            <div className="space-y-2">
                              <div className="space-y-0.5">
                                <span className={`block uppercase text-xs ${mutedText(theme)}`}>Why this was flagged</span>
                                <p className={`leading-relaxed ${bodyText(theme)}`}>{aiSummary.what}</p>
                              </div>
                              <div className="space-y-0.5">
                                <span className={`block uppercase text-xs ${mutedText(theme)}`}>When</span>
                                <p className={`leading-relaxed ${bodyText(theme)}`}>{aiSummary.when || "Unknown"}</p>
                              </div>
                              <div className="space-y-0.5">
                                <span className={`uppercase text-xs flex items-center ${mutedText(theme)}`}>
                                  <Info className="h-3.5 w-3.5 mr-1" style={{ color: accent }} /> Suggested next step (AI-generated)
                                  {aiSummary.source === "narrative" && (
                                    <InfoTooltip label="About this suggestion">
                                      Reused from this alert&apos;s linked narrative&apos;s own
                                      root-cause analysis, not freshly generated for this
                                      alert alone.
                                    </InfoTooltip>
                                  )}
                                </span>
                                <p className={`leading-relaxed ${bodyText(theme)}`}>{aiSummary.how_to_solve}</p>
                              </div>
                            </div>
                          </div>
                        ) : (
                          <div className={`pt-2.5 text-xs italic ${mutedText(theme)}`}>
                            Suggested next step not yet generated for this alert.
                          </div>
                        )}
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          )}
        </CardContent>
      </Card>

      {/* 3. Risk Matrix: severity band (platform bands) x confidence */}
      <div className="grid gap-6 md:grid-cols-12">
        <Card className={`${glassCard(theme)} md:col-span-12`}>
          <div className={SPECULAR_LINE} />
          <CardHeader className="pb-2">
            <CardTitle className={`text-xs font-mono uppercase tracking-wider flex items-center gap-1 ${mutedText(theme)}`}>
              Risk Matrix (Severity × Confidence)
              <InfoTooltip label="About Severity and Confidence"><RiskMatrixSeverityConfidenceDefinition /></InfoTooltip>
            </CardTitle>
          </CardHeader>
          <CardContent className="p-4">
            <div className="grid grid-cols-[56px_1fr] gap-2 font-mono text-xs">

              {/* Y axis: the severity band of each row (same bands as the
                  table and tiles). Fixed 56px label column so the labels
                  stay legible at any screen width. */}
              <div className="grid grid-rows-3 gap-1">
                {MATRIX_BANDS.map((rowKey) => (
                  <div key={rowKey} className="h-[55px] flex items-center justify-center text-center">
                    <span className={`uppercase tracking-widest font-bold text-[10px] leading-tight ${mutedText(theme)}`}>{rowKey}</span>
                  </div>
                ))}
              </div>

              {/* 3x3 Matrix Grid */}
              <div className={`grid grid-rows-3 gap-1 p-1.5 rounded border ${isDark ? "bg-black/30 border-white/[0.08]" : "bg-black/[0.03] border-black/[0.06]"}`}>
                {MATRIX_BANDS.map((rowKey) => (
                  <div key={rowKey} className="grid grid-cols-3 gap-1 h-[55px]">
                    {MATRIX_CONFIDENCE.map((colKey) => {
                      const cellDocs = matrix.grid[rowKey][colKey];
                      const count = cellDocs.length;

                      let avgRisk = "";
                      let maxRisk = "";
                      if (count > 0) {
                        const scores = cellDocs.map(d => (typeof d.risk_exact === "number" ? d.risk_exact : d.risk));
                        avgRisk = (Math.round((scores.reduce((a, b) => a + b, 0) / count) * 10) / 10).toString();
                        maxRisk = formatScore(Math.max(...scores));
                      }

                      let bgClass = "bg-[#030712]/40 border-[#1F2937]/35 text-slate-600";
                      if (count > 0) {
                        if (count <= 2) {
                          bgClass = "bg-red-950/20 border-red-900/40 text-red-400 hover:border-red-500/50 hover:bg-red-950/30";
                        } else if (count <= 5) {
                          bgClass = "bg-red-900/40 border-red-750/50 text-red-300 hover:border-red-500 hover:bg-red-900/50";
                        } else {
                          bgClass = "bg-red-750 border-red-500 text-red-100 hover:bg-red-650 hover:shadow-[0_0_12px_rgba(239,68,68,0.25)]";
                        }
                      }

                      return (
                        <div
                          key={colKey}
                          onClick={() => count > 0 && navigateTo("risk", { band: rowKey, confidence: colKey })}
                          className={`rounded p-2 flex flex-col items-center justify-center transition-all duration-300 cursor-pointer relative group text-center ${bgClass}`}
                        >
                          {count > 0 ? (
                            <span className="text-xs font-bold block">{count} {count === 1 ? "article" : "articles"}</span>
                          ) : (
                            <span className={`text-xs block ${mutedText(theme)}`}>No articles</span>
                          )}

                          {/* Hover diagnostics tooltip -- kept solid (not glass-translucent) so
                              it stays unambiguous over an already-colored matrix cell */}
                          <div className={`absolute z-50 hidden group-hover:block p-3 rounded-xl shadow-2xl font-mono text-xs w-48 text-left space-y-1.5 left-1/2 -translate-x-1/2 bottom-full mb-2 pointer-events-none border ${isDark ? "bg-zinc-950 border-white/[0.12]" : "bg-white border-black/[0.08]"}`}>
                            <div className={`font-bold border-b pb-1 mb-1 ${isDark ? "border-white/[0.12] text-[#00F5D4]" : "border-black/[0.06] text-[#3B82F6]"}`}>Cell details</div>
                            <div className="flex justify-between">
                              <span className={mutedText(theme)}>Severity:</span>
                              <span className={bodyText(theme)}>{levelWord(rowKey)}</span>
                            </div>
                            <div className="flex justify-between">
                              <span className={mutedText(theme)}>Confidence:</span>
                              <span className={bodyText(theme)}>{levelWord(colKey)}</span>
                            </div>
                            <div className="flex justify-between">
                              <span className={mutedText(theme)}>Articles:</span>
                              <span className={`font-bold ${bodyText(theme)}`}>{count}</span>
                            </div>
                            <div className="flex justify-between">
                              <span className={mutedText(theme)}>Average score:</span>
                              <span className={`font-bold ${bodyText(theme)}`}>{count > 0 ? avgRisk : "N/A"}</span>
                            </div>
                            <div className="flex justify-between">
                              <span className={mutedText(theme)}>Highest score:</span>
                              <span className="text-red-500 font-bold">{count > 0 ? maxRisk : "N/A"}</span>
                            </div>
                          </div>
                        </div>
                      );
                    })}
                  </div>
                ))}
              </div>

              {/* X Axis Labels */}
              <div />
              <div className={`grid grid-cols-3 text-center uppercase tracking-wider font-bold mt-1 text-xs ${mutedText(theme)}`}>
                <span className="min-w-0 break-words">LOW CONFIDENCE</span>
                <span className="min-w-0 break-words">MED CONFIDENCE</span>
                <span className="min-w-0 break-words">HIGH CONFIDENCE</span>
              </div>
            </div>
            {matrix.unplaced > 0 && (
              <p className={`mt-3 text-xs font-mono ${mutedText(theme)}`}>
                {matrix.unplaced} flagged {matrix.unplaced === 1 ? "article has" : "articles have"} no confidence value and {matrix.unplaced === 1 ? "is" : "are"} not shown in the grid.
              </p>
            )}
          </CardContent>
        </Card>
      </div>

      {/* 6. Flagged Articles table -- the dense data view: score and
          severity badges below intentionally use full-strength semantic
          colors (red/orange/yellow, solid badge borders) rather than the
          muted glass-pill treatment, since these are the actual product
          signal and must stay unambiguous over the translucent
          background, not just decorative tags. See redesign report. */}
      <Card className={glassCard(theme)}>
        <div className={SPECULAR_LINE} />
        <CardHeader>
          <CardTitle className={`text-xs font-mono uppercase tracking-wider ${mutedText(theme)} flex items-center justify-between`}>
            <span className="flex items-center">
              <ShieldAlert className="h-4 w-4 text-red-500 mr-2" />
              Flagged Articles
            </span>
            <Badge className="bg-red-500/10 text-red-500 border border-red-500/30 font-mono text-xs">
              {filteredRiskDocs.length} {filteredRiskDocs.length === 1 ? "article" : "articles"}
            </Badge>
          </CardTitle>
        </CardHeader>
        <CardContent>
          {hasListFilter && (
            <div className={`mb-3 flex items-center justify-between rounded-lg border px-3 py-2 text-xs font-mono ${isDark ? "bg-black/30 border-white/[0.08]" : "bg-black/[0.03] border-black/[0.06]"}`}>
              <span className={mutedText(theme)}>
                Filtered by{severityParam ? ` severity: ${severityParam}` : ""}{dateParam ? ` date: ${dateParam}` : ""}
              </span>
              <button type="button" onClick={clearListFilter} className="hover:underline" style={{ color: accent }}>
                Clear Filter
              </button>
            </div>
          )}
          {tableWindowNote && (
            <p className={`mb-3 text-xs font-mono ${mutedText(theme)}`}>{tableWindowNote}</p>
          )}
          <div ref={riskTableWrapperRef} className="relative">
            <Table>
              <TableHeader className={isDark ? "border-white/[0.12] bg-black/20" : "border-black/[0.06] bg-black/[0.02]"}>
                <TableRow className={isDark ? "border-white/[0.12]" : "border-black/[0.06]"}>
                  <TableHead className={`font-mono text-xs ${mutedText(theme)}`}>HEADLINE</TableHead>
                  <TableHead className={`font-mono text-xs text-center ${mutedText(theme)}`}>RISK SCORE</TableHead>
                  {/* Reduced default column set at tablet widths (<lg, matching
                      the sidebar's own breakpoint) -- SEVERITY/SOURCE stay
                      reachable via the existing row-level "Details" modal
                      instead of squeezing every column into the scroll
                      container (ui_redesign_plan_tablet.md Section 4/8). */}
                  <TableHead className={`hidden lg:table-cell font-mono text-xs text-center ${mutedText(theme)}`}>SEVERITY</TableHead>
                  <TableHead className={`hidden lg:table-cell font-mono text-xs ${mutedText(theme)}`}>SOURCE</TableHead>
                  <TableHead className={`font-mono text-xs ${mutedText(theme)}`}>DATE</TableHead>
                  <TableHead className={`font-mono text-xs text-right ${mutedText(theme)}`}>ACTION</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {filteredRiskDocs.map((doc) => {
                  const when = dateLabel(doc);
                  return (
                    <TableRow
                      key={doc.id}
                      className={`transition-colors cursor-pointer ${isDark ? "border-white/[0.08] hover:bg-white/[0.04]" : "border-black/[0.06] hover:bg-black/[0.02]"}`}
                      onClick={() => setSelectedDocId(doc.id)}
                    >
                      <TableCell className={`font-mono text-xs font-bold max-w-[320px] truncate ${bodyText(theme)}`}>
                        {doc.title}
                      </TableCell>
                      <TableCell className={`text-center font-mono text-xs font-black ${SEVERITY_TEXT[doc.severity]}`}>
                        {formatScore(doc.risk_exact ?? doc.risk)}
                      </TableCell>
                      <TableCell className="hidden lg:table-cell text-center">
                        <Badge className={`font-mono text-xs ${SEVERITY_BADGE[doc.severity]}`}>
                          {doc.severity}
                        </Badge>
                      </TableCell>
                      <TableCell className={`hidden lg:table-cell font-mono text-xs truncate max-w-[120px] ${mutedText(theme)}`}>
                        {doc.source || "Unknown Source"}
                      </TableCell>
                      <TableCell className={`font-mono text-xs ${mutedText(theme)}`}>
                        {when.text}{when.collected ? " (collected)" : ""}
                      </TableCell>
                      <TableCell className="text-right">
                        <button
                          onClick={(e) => { e.stopPropagation(); setSelectedDocId(doc.id); }}
                          className="bg-blue-600 hover:bg-blue-700 cursor-pointer text-white font-mono text-xs rounded px-3 min-h-[44px] inline-flex items-center justify-center"
                        >
                          Details
                        </button>
                      </TableCell>
                    </TableRow>
                  );
                })}
                {filteredRiskDocs.length === 0 && (
                  <TableRow>
                    <TableCell colSpan={6} className={`text-center py-10 font-mono text-xs ${mutedText(theme)}`}>
                      {hasListFilter ? "No flagged articles match this filter." : "No flagged articles."}
                    </TableCell>
                  </TableRow>
                )}
              </TableBody>
            </Table>
            {/* Horizontal-scroll affordance: only rendered when the table's own
                container actually overflows (ResizeObserver-driven), so it
                doesn't appear once the reduced column set already fits. */}
            {riskTableScrollable && (
              <div
                aria-hidden="true"
                className={`pointer-events-none absolute top-0 right-0 bottom-0 w-10 bg-gradient-to-l ${
                  isDark ? "from-zinc-900/90 to-transparent" : "from-white/90 to-transparent"
                }`}
              />
            )}
          </div>
        </CardContent>
      </Card>

      {/* 7. Details Drawer (Slide-Over Panel) -- kept high-opacity
          (bg-zinc-950/95 dark, bg-white/95 light) rather than the standard
          glass alpha: at full page height over the dimmed backdrop, the
          spec's translucency read as illegible on long paragraph text
          (Original Article Snippet) in review, so this is the one place we
          backed off transparency for legibility per Part 3 of the brief. */}
      {selectedDoc && (() => {
        const when = dateLabel(selectedDoc);
        const conf = confidencePercent(selectedDoc);
        const exp = selectedDoc.risk_explainability;
        const reason = reasonSentence(selectedDoc);
        const topicContributed = typeof exp?.topic_contribution === "number" && exp.topic_contribution > 0;
        const nextStep = exp?.ai_summary?.how_to_solve;
        return (
        <div className="fixed inset-0 z-50 overflow-hidden font-mono">
          {/* Overlay backdrop */}
          <div className="absolute inset-0 bg-black/60 backdrop-blur-sm transition-opacity" onClick={() => setSelectedDocId(null)} />

          <div className="absolute inset-y-0 right-0 max-w-full flex pl-10">
            <div className={`w-[600px] backdrop-blur-2xl border-l flex flex-col justify-between shadow-2xl animate-in slide-in-from-right duration-300 ${bodyText(theme)} ${isDark ? "bg-zinc-950/95 border-white/[0.12]" : "bg-white/95 border-black/[0.06]"}`}>

              {/* Header */}
              <div className={`p-6 border-b flex items-center justify-between ${isDark ? "border-white/[0.12]" : "border-black/[0.06]"}`}>
                <div className="flex items-center space-x-3">
                  <AlertOctagon className="h-5 w-5 text-red-500" />
                  <span className="text-sm font-bold uppercase" style={{ color: accent }}>Details</span>
                </div>
                <button
                  onClick={() => setSelectedDocId(null)}
                  className={`flex items-center gap-1.5 text-xs min-h-[44px] transition-colors ${mutedText(theme)} ${isDark ? "hover:text-zinc-100" : "hover:text-zinc-900"}`}
                >
                  <X className="h-5 w-5" />
                  <span>Close</span>
                </button>
              </div>

              {/* Content Panel */}
              <div className="flex-1 overflow-y-auto overflow-x-hidden p-6 space-y-6">

                {/* Headline & Meta */}
                <div className="space-y-2">
                  <h3 className={`text-sm font-bold leading-snug ${bodyText(theme)}`}>{selectedDoc.title}</h3>
                  <div className="flex flex-wrap gap-2 text-xs">
                    <span className={`${glassPill(theme)} px-2 py-0.5 ${mutedText(theme)}`}>Source: {selectedDoc.source}</span>
                    <span className={`${glassPill(theme)} px-2 py-0.5 ${mutedText(theme)}`}>
                      {when.collected ? "Collected" : "Published"}: {when.text}
                    </span>
                    {topicContributed && selectedDoc.topic && (
                      <span className={`${glassPill(theme)} px-2 py-0.5 ${mutedText(theme)}`}>Subject: {selectedDoc.topic}</span>
                    )}
                  </div>
                </div>

                {/* Why this was flagged -- plain sentence from stored
                    explainability (no engine words, no raw floats). */}
                <div className={`p-4 rounded-2xl border border-red-500/20 space-y-3 ${isDark ? "bg-black/30" : "bg-black/[0.03]"}`}>
                  <div className={`flex justify-between items-center border-b pb-2 ${isDark ? "border-white/[0.12]" : "border-black/[0.06]"}`}>
                    <span className={`text-xs font-bold ${SEVERITY_TEXT[selectedDoc.severity]}`}>Risk Rating · {levelWord(selectedDoc.severity)}</span>
                    <span className={`text-lg font-black ${SEVERITY_TEXT[selectedDoc.severity]}`}>
                      {formatScore(typeof selectedDoc.risk_exact === "number" ? selectedDoc.risk_exact : selectedDoc.risk)} / 100
                    </span>
                  </div>
                  <div className="space-y-1.5 text-xs">
                    <div className="flex justify-between">
                      <span className={mutedText(theme)}>Tone of the article:</span>
                      <span className={bodyText(theme)}>{selectedDoc.risk_sentiment ?? "Unavailable"}</span>
                    </div>
                    <div className="flex justify-between">
                      <span className={mutedText(theme)}>Confidence:</span>
                      <span className={`font-bold ${bodyText(theme)}`}>{conf === null ? "Unavailable" : `${conf}%`}</span>
                    </div>
                    {exp?.role_classification_source === "llm" && exp.role_classification === "SELF" && (
                      <div className={`flex justify-between border-t pt-1.5 ${isDark ? "border-white/[0.08]" : "border-black/[0.06]"}`}>
                        <span className={mutedText(theme)}>AI check:</span>
                        <span className={bodyText(theme)}>Company is the subject of the article</span>
                      </div>
                    )}
                  </div>
                  <p className={`text-xs leading-relaxed border-t pt-2 ${mutedText(theme)} ${isDark ? "border-white/[0.08]" : "border-black/[0.06]"}`}>
                    {reason ?? "Details unavailable."}
                  </p>
                </div>

                {/* Original Article Content */}
                <div className="space-y-2">
                  <span className={`text-xs uppercase font-bold flex items-center ${mutedText(theme)}`}>
                    <Info className="h-3.5 w-3.5 mr-1" style={{ color: accent }} /> Original Article Snippet
                  </span>
                  <div className={`p-4 rounded-2xl border text-xs leading-relaxed max-h-48 overflow-y-auto overflow-x-hidden whitespace-pre-wrap ${mutedText(theme)} ${isDark ? "bg-black/30 border-white/[0.08]" : "bg-black/[0.03] border-black/[0.06]"}`}>
                    {selectedDoc.original_content || "No original content available."}
                  </div>
                </div>

                {/* Suggested next step: the only LLM-generated text in this
                    drawer (ai_summary_engine.py's how_to_solve), so it is the
                    only part labelled AI. Absent until the first summary run
                    has produced one for this item. */}
                {nextStep && (
                  // Solid opaque panel (not the translucent glass
                  // convention used elsewhere in this drawer) -- reported
                  // unreadable against the drawer's own background.
                  <div className={`space-y-2.5 p-4 rounded-2xl border ${isDark ? "bg-zinc-900 border-white/[0.08]" : "bg-white border-black/[0.08]"}`}>
                    <div className="flex items-center justify-between">
                      <span className={`text-xs uppercase font-bold flex items-center ${mutedText(theme)}`}>
                        <Info className="h-3.5 w-3.5 mr-1" style={{ color: accent }} /> Suggested next step (AI-generated)
                      </span>
                      {exp?.ai_summary?.source === "narrative" && (
                        <InfoTooltip label="About this suggestion">
                          Reused from this item&apos;s linked narrative&apos;s own root-cause
                          analysis, not freshly generated for this item alone -- avoids a
                          second, potentially-conflicting explanation of the same story.
                        </InfoTooltip>
                      )}
                    </div>
                    <p className={`text-xs leading-relaxed ${bodyText(theme)}`}>{nextStep}</p>
                  </div>
                )}

              </div>

              {/* Drawer Footer */}
              <div className={`p-4 border-t flex justify-end space-x-3 ${isDark ? "border-white/[0.12] bg-black/20" : "border-black/[0.06] bg-black/[0.02]"}`}>
                {selectedDocUrl && (
                  <a
                    href={selectedDocUrl}
                    target="_blank"
                    rel="noopener noreferrer"
                    className={`flex items-center space-x-1.5 font-mono text-xs px-4 py-2 ${glassPrimaryButton(theme)}`}
                  >
                    <span>View Source Article</span>
                    <ExternalLink className="h-3 w-3" />
                  </a>
                )}
                <button
                  onClick={() => setSelectedDocId(null)}
                  className={`bg-transparent border text-xs rounded px-4 py-2 transition-colors ${mutedText(theme)} ${isDark ? "border-white/[0.12] hover:border-zinc-500 hover:text-zinc-100" : "border-black/[0.08] hover:border-zinc-400 hover:text-zinc-900"}`}
                >
                  Close
                </button>
              </div>

            </div>
          </div>
        </div>
        );
      })()}

      {/* 8. Matrix Cell Drawer -- same high-opacity backing as the
          drawer above, for the same legibility reason. */}
      {selectedCell && (
        <div className="fixed inset-0 z-50 overflow-hidden font-mono">
          <div className="absolute inset-0 bg-black/60 backdrop-blur-sm transition-opacity" onClick={() => clearCellFilter()} />
          <div className="absolute inset-y-0 right-0 max-w-full flex pl-10">
            <div className={`w-[600px] backdrop-blur-2xl border-l flex flex-col justify-between shadow-2xl animate-in slide-in-from-right duration-300 ${bodyText(theme)} ${isDark ? "bg-zinc-950/95 border-white/[0.12]" : "bg-white/95 border-black/[0.06]"}`}>

              {/* Header */}
              <div className={`p-6 border-b flex items-center justify-between ${isDark ? "border-white/[0.12]" : "border-black/[0.06]"}`}>
                <div className="flex items-center space-x-3">
                  <ShieldAlert className="h-5 w-5 text-red-500" />
                  <span className="text-sm font-bold uppercase" style={{ color: accent }}>
                    {selectedCell.kind === "severity"
                      ? `Flagged articles: ${selectedCell.row} severity / ${selectedCell.col} confidence`
                      : `Flagged articles: ${selectedCell.row} score tier / ${selectedCell.col} confidence`}
                  </span>
                </div>
                <button
                  onClick={() => clearCellFilter()}
                  className={`flex items-center gap-1.5 text-xs min-h-[44px] transition-colors ${mutedText(theme)} ${isDark ? "hover:text-zinc-100" : "hover:text-zinc-900"}`}
                >
                  <X className="h-5 w-5" />
                  <span>Close</span>
                </button>
              </div>

              {/* Content List */}
              <div className="flex-1 overflow-y-auto overflow-x-hidden p-6 space-y-4">
                {selectedCellDocs.length === 0 ? (
                  <div className={`text-center py-10 text-xs ${mutedText(theme)}`}>No articles in this cell.</div>
                ) : selectedCellDocs.map((doc: any, idx: number) => {
                  const when = dateLabel(doc);
                  return (
                    <div key={doc.id ?? idx} className={`p-4 rounded-2xl border space-y-3 transition-colors ${isDark ? "bg-black/30 border-white/[0.08] hover:border-[#00F5D4]/40" : "bg-black/[0.03] border-black/[0.06] hover:border-[#3B82F6]/40"}`}>
                      <div className="flex justify-between items-start">
                        <span className={`text-xs ${mutedText(theme)}`}>Source: {doc.source}</span>
                        <Badge className={`font-mono text-xs ${SEVERITY_BADGE[doc.severity]}`}>
                          {levelWord(doc.severity)} · {formatScore(doc.risk_exact ?? doc.risk)}
                        </Badge>
                      </div>
                      <h4 className={`text-xs font-bold leading-snug ${bodyText(theme)}`}>{doc.title}</h4>
                      <div className={`flex justify-between items-center text-xs pt-1 border-t ${isDark ? "border-white/[0.08]" : "border-black/[0.06]"}`}>
                        <span className={mutedText(theme)}>
                          Confidence: {confidencePercent(doc) === null ? "N/A" : `${confidencePercent(doc)}%`}
                        </span>
                        <span className={mutedText(theme)}>
                          {when.text}{when.collected ? " (collected)" : ""}
                        </span>
                      </div>
                      <div className="flex justify-end pt-1">
                        <button
                          onClick={() => { setSelectedDocId(doc.id); clearCellFilter(); }}
                          className="bg-blue-600 hover:bg-blue-700 text-white font-mono text-xs rounded px-3 min-h-[44px] inline-flex items-center justify-center"
                        >
                          View Details &rarr;
                        </button>
                      </div>
                    </div>
                  );
                })}
              </div>

              {/* Footer */}
              <div className={`p-4 border-t flex justify-end ${isDark ? "border-white/[0.12] bg-black/20" : "border-black/[0.06] bg-black/[0.02]"}`}>
                <button
                  onClick={() => clearCellFilter()}
                  className={`bg-transparent border text-xs rounded px-4 py-2 transition-colors ${mutedText(theme)} ${isDark ? "border-white/[0.12] hover:border-zinc-500 hover:text-zinc-100" : "border-black/[0.08] hover:border-zinc-400 hover:text-zinc-900"}`}
                >
                  Close Window
                </button>
              </div>

            </div>
          </div>
        </div>
      )}

    </div>
  );
}
