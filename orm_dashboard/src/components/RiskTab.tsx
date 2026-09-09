import React, { useState, useMemo, useEffect } from "react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import {
  AlertTriangle, Shield, ShieldAlert, X, ExternalLink,
  TrendingUp, Calendar, AlertOctagon, Info
} from "lucide-react";
import {
  ResponsiveContainer, PieChart, Pie, Cell, Tooltip,
  BarChart, Bar, XAxis, YAxis, CartesianGrid, LineChart, Line
} from "recharts";
import { TelemetryErrorWidget } from "@/components/TelemetryErrorWidget";
import { getRiskLevel, RISK_THRESHOLDS } from "@/utils/riskLevel";
import { fetchDocumentDetails } from "@/lib/api";
import { useTheme } from "@/components/theme/ThemeProvider";
import { glassCard, glassTokens, glassPill, glassPrimaryButton, mutedText, bodyText, SPECULAR_LINE } from "@/components/theme/tokens";
import { InfoTooltip } from "@/components/ui/InfoTooltip";
import { useTabNavigation } from "@/hooks/useTabNavigation";
import {
  RiskSeverityDefinition,
  AverageRiskScoreTrackedDefinition,
  RiskMatrixAxesDefinition,
  RiskCategoriesDefinition,
} from "@/lib/metricDefinitions";

export interface RiskTabProps {
  alertsLoading: boolean;
  alertsError: string | null;
  alerts: any[];
  documentsLoading: boolean;
  documentsError: string | null;
  documents: any[];
  clientId?: string | null;
  onViewNarrative?: (narrativeName: string) => void;
}

export function RiskTab({
  alertsLoading,
  alertsError,
  alerts,
  documentsLoading,
  documentsError,
  documents,
  clientId,
  onViewNarrative
}: RiskTabProps) {
  const { theme } = useTheme();
  const isDark = theme === "dark";
  const accent = isDark ? "#00F5D4" : "#3B82F6";
  const { navigateTo, searchParams } = useTabNavigation();
  const [selectedDocId, setSelectedDocId] = useState<string | null>(null);
  const [expandedAlertId, setExpandedAlertId] = useState<string | null>(null);

  // Matrix-cell drill-down (Part B/C: filter-carrying navigation) --
  // sourced from the URL (?tab=risk&impact=..&likelihood=..) instead of
  // local state, so a cell click from this tab's own matrix and from the
  // SOC Risk Matrix in Executive Analytics land on the exact same,
  // shareable/back-navigable filtered view. Same shape the old local
  // useState carried, so the drawer JSX below is unchanged.
  const impactParam = searchParams.get("impact");
  const likelihoodParam = searchParams.get("likelihood");
  const selectedCell = impactParam && likelihoodParam ? { impact: impactParam, likelihood: likelihoodParam } : null;
  const clearCellFilter = () => navigateTo("risk", { severity: searchParams.get("severity") ?? undefined, date: searchParams.get("date") ?? undefined });

  // Severity/date filters (Part C drill-throughs): narrow only the Risk
  // Events table below, not the summary charts above it -- those are
  // meant to show the whole picture, the table is the drill-through
  // target. Only one of these is normally set at a time (a fresh
  // navigateTo() call replaces the whole query string), but both are
  // read independently so either can filter on its own.
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

  // Filter out documents with valid risk scores. Also requires risk above
  // the LOW band: `risk` defaults to 0 for any matched document with no
  // RiskEvent row at all, and 0 is a number -- an unfiltered `typeof
  // d.risk === "number"` check let every matched document into the
  // Incident Command Register, LOW-severity or not. Combined with
  // trend velocity being direction-agnostic (risk_engine.py), that meant
  // routine Positive/Neutral news (a profit surge, a land acquisition)
  // sat in the register at equal visual weight to genuine incidents --
  // confirmed live at ~80-90% of every client's risk events. Only
  // MEDIUM+ is an actual incident; LOW-severity items still exist in the
  // data (e.g. for Executive Reputation's own per-entity view) but don't
  // belong in a register titled "incidents".
  const riskDocs = useMemo(() => {
    return (documents || [])
      .filter(d => d && typeof d.risk === "number" && d.risk > RISK_THRESHOLDS.LOW_TO_MEDIUM)
      .map(d => {
        // D3/A4: previously derived from sentiment via an invented
        // ((1 - sentiment) / 2) * 100 formula that risk_engine.py never
        // computes -- a separately-fabricated number, not the real
        // likelihood/confidence the backend actually calculated. Use the
        // real confidence_modifier the engine stores in explainability.confidence
        // (topic_conf + entity_sentiment_conf) / 2, falling back to 0 --
        // same "no fabricated signal" convention risk_engine.py itself uses
        // when an input is missing.
        const likelihood = Math.round((d.risk_explainability?.confidence ?? 0) * 100);
        return {
          ...d,
          likelihood,
          severity: getRiskLevel(d.risk)
        };
      })
      .sort((a, b) => b.risk - a.risk);
  }, [documents]);

  // Risk Events table filter (severity=.. / date=.. from the URL) -- narrows
  // only the table, matching exactly how the pie chart's severity bands and
  // the timeline's date buckets are already computed above, so a filtered
  // list here is always the same set of items the CEO clicked from.
  const filteredRiskDocs = useMemo(() => {
    return riskDocs.filter(d => {
      if (severityParam && d.severity.toLowerCase() !== severityParam) return false;
      if (dateParam) {
        const docDate = d.timestamp
          ? new Date(d.timestamp).toLocaleDateString(undefined, { month: 'short', day: 'numeric' })
          : null;
        if (docDate !== dateParam) return false;
      }
      return true;
    });
  }, [riskDocs, severityParam, dateParam]);

  const selectedDoc = useMemo(() => {
    if (!selectedDocId) return null;
    return riskDocs.find(d => d.id === selectedDocId) || null;
  }, [selectedDocId, riskDocs]);

  // 1. Risk Summary Statistics
  // D3: previously only tracked critical/medium/low with thresholds that
  // didn't match risk_engine.py, and had no "high" bucket at all — any
  // document scoring 50-79 matched none of the three conditions and
  // silently vanished from critical+medium+low while still counting toward
  // `total`. Now uses the canonical 4-band classification.
  const stats = useMemo(() => {
    const total = riskDocs.length;
    let critical = 0;
    let high = 0;
    let medium = 0;
    let low = 0;
    let sumScore = 0;
    let highest = 0;

    riskDocs.forEach(d => {
      const level = getRiskLevel(d.risk);
      if (level === "CRITICAL") critical++;
      else if (level === "HIGH") high++;
      else if (level === "MEDIUM") medium++;
      else low++;

      sumScore += d.risk;
      if (d.risk > highest) highest = d.risk;
    });

    const avg = total > 0 ? (sumScore / total).toFixed(1) : "0.0";

    return { total, critical, high, medium, low, avg, highest };
  }, [riskDocs]);

  // 2. Severity Distribution Chart Data
  const severityChartData = useMemo(() => {
    let lowCount = 0, medCount = 0, highCount = 0, critCount = 0;
    riskDocs.forEach(d => {
      const level = getRiskLevel(d.risk);
      if (level === "CRITICAL") critCount++;
      else if (level === "HIGH") highCount++;
      else if (level === "MEDIUM") medCount++;
      else lowCount++;
    });
    return [
      { name: "Critical", value: critCount, color: "#EF4444" },
      { name: "High", value: highCount, color: "#F97316" },
      { name: "Medium", value: medCount, color: "#EAB308" },
      { name: "Low", value: lowCount, color: "#10B981" }
    ].filter(d => d.value > 0);
  }, [riskDocs]);

  // 3. 3x3 Matrix Grid Buckets
  const matrixData = useMemo(() => {
    const grid: Record<string, Record<string, any[]>> = {
      HIGH: { LOW: [], MEDIUM: [], HIGH: [] },
      MEDIUM: { LOW: [], MEDIUM: [], HIGH: [] },
      LOW: { LOW: [], MEDIUM: [], HIGH: [] }
    };

    riskDocs.forEach(d => {
      const impBucket = d.risk >= 67 ? "HIGH" : d.risk >= 33 ? "MEDIUM" : "LOW";
      const likBucket = d.likelihood >= 67 ? "HIGH" : d.likelihood >= 33 ? "MEDIUM" : "LOW";
      grid[impBucket][likBucket].push(d);
    });

    return grid;
  }, [riskDocs]);

  // 4. Timeline Data
  const timelineChartData = useMemo(() => {
    const buckets: Record<string, number> = {};
    riskDocs.forEach(d => {
      if (d.timestamp) {
        const dateStr = new Date(d.timestamp).toLocaleDateString(undefined, { month: 'short', day: 'numeric' });
        buckets[dateStr] = (buckets[dateStr] || 0) + 1;
      }
    });
    return Object.entries(buckets)
      .map(([date, count]) => ({ date, count }))
      .reverse();
  }, [riskDocs]);

  // 5. Category Distribution
  const categoryData = useMemo(() => {
    const counts: Record<string, number> = {};
    riskDocs.forEach(d => {
      const t = d.topic || "General";
      counts[t] = (counts[t] || 0) + 1;
    });
    return Object.entries(counts)
      .map(([name, count]) => ({ name, count }))
      .sort((a, b) => b.count - a.count);
  }, [riskDocs]);

  if (documentsLoading) {
    return (
      <div className="space-y-6 animate-pulse">
        <div className="grid gap-6 md:grid-cols-6">
          {[1, 2, 3, 4, 5, 6].map(x => (
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

  return (
    <div className="space-y-8 relative">
      
      {/* 1. Risk Summary Cards -- Total/Critical get slightly larger type so
          the two numbers an exec most needs land first, at a glance. */}
      <div className="space-y-3">
        <span className={`text-xs font-mono uppercase tracking-wider block ${mutedText(theme)}`}>At a Glance</span>
        <div className="grid gap-4 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-7 font-mono">
          {[
            { label: "Total Risks", value: stats.total, color: isDark ? "text-[#00F5D4]" : "text-[#3B82F6]", highlight: true },
            { label: "Critical Risks", value: stats.critical, color: "text-red-500", highlight: true },
            { label: "High Risks", value: stats.high, color: "text-orange-500" },
            { label: "Medium Risks", value: stats.medium, color: "text-yellow-500" },
            { label: "Low Risks", value: stats.low, color: "text-emerald-500" },
            { label: "Avg Risk Score", value: stats.avg, color: bodyText(theme) },
            { label: "Highest Risk", value: stats.highest, color: "text-red-500 font-black" }
          ].map((card, idx) => (
            <div key={idx} className={`${glassCard(theme)} p-4 flex flex-col justify-between`}>
              <div className={SPECULAR_LINE} />
              <span className={`text-xs ${mutedText(theme)} uppercase tracking-wider block mb-2`}>{card.label}</span>
              <span className={`${card.highlight ? "text-2xl" : "text-xl"} font-bold ${card.color}`}>{card.value}</span>
            </div>
          ))}
        </div>
      </div>

      {/* 1b. Active Alerts */}
      <Card className={glassCard(theme)}>
        <div className={SPECULAR_LINE} />
        <CardHeader>
          <CardTitle className={`text-xs font-mono uppercase tracking-wider ${mutedText(theme)} flex items-center justify-between`}>
            <span className="flex items-center">
              <AlertTriangle className="h-4 w-4 text-orange-500 mr-2" />
              ACTIVE ALERTS
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
            <div className={`text-center py-6 ${mutedText(theme)} font-mono text-xs`}>No active alerts.</div>
          ) : (
            <div className="space-y-2 max-h-[420px] overflow-y-auto pr-1">
              {alerts.map((alert) => {
                const isExpanded = expandedAlertId === alert.id;
                const aiSummary = alert.ai_summary;
                return (
                  <div key={alert.id} className={`rounded-2xl font-mono text-xs overflow-hidden ${glassPill(theme)}`}>
                    <button
                      type="button"
                      onClick={() => setExpandedAlertId(isExpanded ? null : alert.id)}
                      className="w-full flex items-center justify-between p-3 min-h-[44px] text-left"
                    >
                      <div className="flex items-center space-x-3 min-w-0">
                        <Badge className={`font-mono text-xs shrink-0 ${
                          alert.severity === "CRITICAL" ? "bg-red-500/10 text-red-500 border border-red-500/20" :
                          alert.severity === "HIGH" ? "bg-orange-500/10 text-orange-500 border border-orange-500/20" :
                          alert.severity === "WARNING" ? "bg-yellow-500/10 text-yellow-600 border border-yellow-500/20" :
                          `${isDark ? "bg-zinc-500/10 text-zinc-400 border border-zinc-500/20" : "bg-zinc-500/10 text-zinc-500 border border-zinc-500/20"}`
                        }`}>
                          {alert.severity}
                        </Badge>
                        <span className={`font-bold truncate ${bodyText(theme)}`}>{alert.title}</span>
                        <span className={`text-xs shrink-0 hidden sm:inline ${mutedText(theme)}`}>{alert.alert_type}</span>
                      </div>
                      <span className={`text-xs shrink-0 ml-3 ${mutedText(theme)}`}>
                        {alert.created_at ? new Date(alert.created_at).toLocaleString(undefined, { dateStyle: 'short', timeStyle: 'short' }) : "N/A"}
                      </span>
                    </button>

                    {/* AI Summary -- same What/When/How-to-solve pattern as
                        the Risk Event drawer above and the narrative
                        drawer's Root Cause Analysis section, generated
                        per-alert by ai_summary_engine.py. Alerts have no
                        existing full drill-through drawer, so this expands
                        inline instead of opening a second drawer type. */}
                    {isExpanded && (
                      <div className={`px-3 pb-3 space-y-2.5 border-t ${isDark ? "border-white/[0.08]" : "border-black/[0.06]"}`}>
                        {aiSummary ? (
                          <>
                            <div className="flex items-center justify-between pt-2.5">
                              <span className={`text-xs uppercase font-bold flex items-center ${mutedText(theme)}`}>
                                <Info className="h-3.5 w-3.5 mr-1" style={{ color: accent }} /> AI Summary
                              </span>
                              {aiSummary.source === "narrative" && (
                                <InfoTooltip label="About this AI Summary">
                                  Reused from this alert&apos;s linked narrative&apos;s own
                                  root-cause analysis, not freshly generated for this
                                  alert alone.
                                </InfoTooltip>
                              )}
                            </div>
                            <div className="space-y-2">
                              <div className="space-y-0.5">
                                <span className={`block uppercase text-xs ${mutedText(theme)}`}>What</span>
                                <p className={`leading-relaxed ${bodyText(theme)}`}>{aiSummary.what}</p>
                              </div>
                              <div className="space-y-0.5">
                                <span className={`block uppercase text-xs ${mutedText(theme)}`}>When</span>
                                <p className={`leading-relaxed ${bodyText(theme)}`}>{aiSummary.when || "Unknown"}</p>
                              </div>
                              <div className="space-y-0.5">
                                <span className={`block uppercase text-xs ${mutedText(theme)}`}>How to solve</span>
                                <p className={`leading-relaxed ${bodyText(theme)}`}>{aiSummary.how_to_solve}</p>
                              </div>
                            </div>
                            {aiSummary.source === "narrative" && (
                              <button
                                type="button"
                                onClick={() => onViewNarrative?.(aiSummary.narrative_name)}
                                disabled={!onViewNarrative}
                                className={`w-full text-left px-3 py-2.5 rounded-xl border text-xs min-h-[44px] transition-colors ${bodyText(theme)} ${
                                  isDark ? "bg-black/30 border-[#00F5D4]/30 hover:border-[#00F5D4]/60" : "bg-black/[0.03] border-[#3B82F6]/30 hover:border-[#3B82F6]/60"
                                } ${onViewNarrative ? "cursor-pointer" : "cursor-default"}`}
                              >
                                <span className={`font-bold ${isDark ? "text-[#00F5D4]" : "text-[#3B82F6]"}`}>Via linked narrative:</span>{" "}
                                {aiSummary.narrative_name}
                              </button>
                            )}
                          </>
                        ) : (
                          <div className={`pt-2.5 text-xs italic ${mutedText(theme)}`}>
                            AI summary not yet generated for this alert.
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

      {/* Grid containing Severity pie & Likelihood Matrix */}
      <div className="grid gap-6 md:grid-cols-12">
        
        {/* 2. Risk Severity Distribution (Donut Chart) */}
        <Card className={`${glassCard(theme)} md:col-span-4`}>
          <div className={SPECULAR_LINE} />
          <CardHeader className="pb-2">
            <CardTitle className={`text-xs font-mono uppercase tracking-wider flex items-center gap-1 ${mutedText(theme)}`}>
              Severity Profile
              <InfoTooltip label="About Severity and Avg Rating">
                <RiskSeverityDefinition />
                <span className="mt-2 block" />
                <AverageRiskScoreTrackedDefinition />
              </InfoTooltip>
            </CardTitle>
          </CardHeader>
          <CardContent className="h-[220px] flex justify-center items-center relative">
            {severityChartData.length > 0 ? (
              <ResponsiveContainer width="100%" height="100%">
                <PieChart>
                  <Pie
                    data={severityChartData}
                    cx="50%"
                    cy="50%"
                    innerRadius={55}
                    outerRadius={75}
                    paddingAngle={3}
                    dataKey="value"
                  >
                    {severityChartData.map((entry, index) => (
                      <Cell key={`cell-${index}`} fill={entry.color} />
                    ))}
                  </Pie>
                  <Tooltip contentStyle={{ backgroundColor: isDark ? '#18181b' : '#ffffff', borderColor: isDark ? '#3f3f46' : '#e4e4e7', color: isDark ? '#fff' : '#18181b', fontFamily: 'monospace', fontSize: 10 }} />
                </PieChart>
              </ResponsiveContainer>
            ) : (
              <div className={`font-mono text-xs flex items-center justify-center ${mutedText(theme)}`}>No risk profile details.</div>
            )}
            <div className="absolute flex flex-col items-center justify-center font-mono">
              <span className={`text-xs uppercase ${mutedText(theme)}`}>Avg Rating</span>
              <span className={`text-lg font-bold ${bodyText(theme)}`}>{stats.avg}</span>
            </div>
          </CardContent>
        </Card>

        {/* 3. 3x3 Risk Matrix */}
        <Card className={`${glassCard(theme)} md:col-span-8`}>
          <div className={SPECULAR_LINE} />
          <CardHeader className="pb-2">
            <CardTitle className={`text-xs font-mono uppercase tracking-wider flex items-center gap-1 ${mutedText(theme)}`}>
              Risk Matrix (Likelihood × Impact)
              <InfoTooltip label="About Impact and Likelihood"><RiskMatrixAxesDefinition /></InfoTooltip>
            </CardTitle>
          </CardHeader>
          <CardContent className="p-4">
            <div className="grid grid-cols-12 gap-2 font-mono text-xs">

              {/* Y Axis Label */}
              <div className="col-span-1 flex items-center justify-center">
                <span className={`transform -rotate-90 origin-center whitespace-nowrap uppercase tracking-widest font-bold ${mutedText(theme)}`}>IMPACT (RISK)</span>
              </div>

              {/* 3x3 Matrix Grid */}
              <div className={`col-span-11 grid grid-rows-3 gap-1 p-1.5 rounded border ${isDark ? "bg-black/30 border-white/[0.08]" : "bg-black/[0.03] border-black/[0.06]"}`}>
                {["HIGH", "MEDIUM", "LOW"].map((rowKey) => (
                  <div key={rowKey} className="grid grid-cols-3 gap-1 h-[55px]">
                    {["LOW", "MEDIUM", "HIGH"].map((colKey) => {
                      const cellDocs = matrixData[rowKey]?.[colKey] || [];
                      const count = cellDocs.length;
                      
                      let avgRisk = "0.0";
                      let maxRisk = "0.0";
                      if (count > 0) {
                        const sum = cellDocs.reduce((acc, val) => acc + val.risk, 0);
                        avgRisk = (sum / count).toFixed(1);
                        maxRisk = Math.max(...cellDocs.map(d => d.risk)).toFixed(0);
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
                          onClick={() => count > 0 && navigateTo("risk", { impact: rowKey, likelihood: colKey })}
                          className={`rounded p-2 flex flex-col items-center justify-center transition-all duration-300 cursor-pointer relative group text-center ${bgClass}`}
                        >
                          {count > 0 ? (
                            <span className="text-xs font-bold block">🔴 {count} {count === 1 ? "Incident" : "Incidents"}</span>
                          ) : (
                            <span className={`text-xs block ${mutedText(theme)}`}>No incidents</span>
                          )}

                          {/* Hover diagnostics tooltip -- kept solid (not glass-translucent) so
                              it stays unambiguous over an already-colored matrix cell */}
                          <div className={`absolute z-50 hidden group-hover:block p-3 rounded-xl shadow-2xl font-mono text-xs w-48 text-left space-y-1.5 left-1/2 -translate-x-1/2 bottom-full mb-2 pointer-events-none border ${isDark ? "bg-zinc-950 border-white/[0.12]" : "bg-white border-black/[0.08]"}`}>
                            <div className={`font-bold border-b pb-1 mb-1 ${isDark ? "border-white/[0.12] text-[#00F5D4]" : "border-black/[0.06] text-[#3B82F6]"}`}>Cell Diagnostics</div>
                            <div className="flex justify-between">
                              <span className={mutedText(theme)}>Impact:</span>
                              <span className={bodyText(theme)}>{rowKey}</span>
                            </div>
                            <div className="flex justify-between">
                              <span className={mutedText(theme)}>Likelihood:</span>
                              <span className={bodyText(theme)}>{colKey}</span>
                            </div>
                            <div className="flex justify-between">
                              <span className={mutedText(theme)}>Incidents:</span>
                              <span className={`font-bold ${bodyText(theme)}`}>{count}</span>
                            </div>
                            <div className="flex justify-between">
                              <span className={mutedText(theme)}>Avg Risk Score:</span>
                              <span className={`font-bold ${bodyText(theme)}`}>{count > 0 ? avgRisk : "N/A"}</span>
                            </div>
                            <div className="flex justify-between">
                              <span className={mutedText(theme)}>Highest Risk:</span>
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
              <div className="col-span-1" />
              <div className={`col-span-11 grid grid-cols-3 text-center uppercase tracking-wider font-bold mt-1 text-xs ${mutedText(theme)}`}>
                <span>LOW LIKELIHOOD</span>
                <span>MED LIKELIHOOD</span>
                <span>HIGH LIKELIHOOD</span>
              </div>
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Grid containing timeline & categories */}
      <div className="grid gap-6 md:grid-cols-2">
        
        {/* 4. Risk Timeline */}
        <Card className={glassCard(theme)}>
          <div className={SPECULAR_LINE} />
          <CardHeader className="pb-2">
            <CardTitle className={`text-xs font-mono uppercase tracking-wider ${mutedText(theme)} flex items-center`}>
              <Calendar className="h-4 w-4 mr-2" style={{ color: accent }} />
              Risk Ingestion Timeline
            </CardTitle>
          </CardHeader>
          <CardContent className="h-[200px] pl-2">
            {timelineChartData.length > 0 ? (
              <ResponsiveContainer width="100%" height="100%">
                <LineChart
                  data={timelineChartData}
                  margin={{ top: 10, right: 10, left: -20, bottom: 0 }}
                  onClick={(e) => { if (e?.activeLabel) navigateTo("risk", { date: String(e.activeLabel) }); }}
                  style={{ cursor: "pointer" }}
                >
                  <CartesianGrid strokeDasharray="3 3" vertical={false} stroke={isDark ? "#3f3f46" : "#d4d4d8"} strokeOpacity={0.4} />
                  <XAxis dataKey="date" stroke={isDark ? "#a1a1aa" : "#71717a"} fontSize={8} tickLine={false} />
                  <YAxis stroke={isDark ? "#a1a1aa" : "#71717a"} fontSize={8} tickLine={false} allowDecimals={false} />
                  <Tooltip contentStyle={{ backgroundColor: isDark ? '#18181b' : '#ffffff', borderColor: isDark ? '#3f3f46' : '#e4e4e7', color: isDark ? '#fff' : '#18181b', fontFamily: 'monospace', fontSize: 10 }} />
                  <Line type="monotone" dataKey="count" name="Risks Detected" stroke="#EF4444" strokeWidth={2} dot={{ r: 3, fill: '#EF4444' }} />
                </LineChart>
              </ResponsiveContainer>
            ) : (
              <div className={`flex items-center justify-center h-full font-mono text-xs ${mutedText(theme)}`}>No historical risks tracked.</div>
            )}
          </CardContent>
        </Card>

        {/* 5. Risk Categories */}
        <Card className={glassCard(theme)}>
          <div className={SPECULAR_LINE} />
          <CardHeader className="pb-2">
            <CardTitle className={`text-xs font-mono uppercase tracking-wider ${mutedText(theme)} flex items-center gap-1`}>
              <TrendingUp className="h-4 w-4 mr-2" style={{ color: accent }} />
              Incident Categories
              <InfoTooltip label="About Incident Categories"><RiskCategoriesDefinition /></InfoTooltip>
            </CardTitle>
          </CardHeader>
          <CardContent className="h-[200px] pl-2">
            {categoryData.length > 0 ? (
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={categoryData} layout="vertical" margin={{ top: 5, right: 15, left: 10, bottom: 5 }}>
                  <CartesianGrid strokeDasharray="3 3" horizontal={false} stroke={isDark ? "#3f3f46" : "#d4d4d8"} strokeOpacity={0.4} />
                  <XAxis type="number" stroke={isDark ? "#a1a1aa" : "#71717a"} fontSize={8} tickLine={false} />
                  <YAxis dataKey="name" type="category" stroke={isDark ? "#a1a1aa" : "#71717a"} fontSize={8} tickLine={false} width={80} />
                  <Tooltip contentStyle={{ backgroundColor: isDark ? '#18181b' : '#ffffff', borderColor: isDark ? '#3f3f46' : '#e4e4e7', color: isDark ? '#fff' : '#18181b', fontFamily: 'monospace', fontSize: 10 }} />
                  <Bar dataKey="count" name="Incidents" fill={accent} radius={[0, 4, 4, 0]} barSize={12} />
                </BarChart>
              </ResponsiveContainer>
            ) : (
              <div className={`flex items-center justify-center h-full font-mono text-xs ${mutedText(theme)}`}>No category metrics loaded.</div>
            )}
          </CardContent>
        </Card>
      </div>

      {/* 6. High Risk Incidents Table -- the dense data view: risk score,
          severity, and topic badges below intentionally use full-strength
          semantic colors (red/orange/yellow, solid badge borders) rather
          than the muted glass-pill treatment, since these are the actual
          product signal and must stay unambiguous over the translucent
          background, not just decorative tags. See redesign report. */}
      <Card className={glassCard(theme)}>
        <div className={SPECULAR_LINE} />
        <CardHeader>
          <CardTitle className={`text-xs font-mono uppercase tracking-wider ${mutedText(theme)} flex items-center justify-between`}>
            <span className="flex items-center">
              <ShieldAlert className="h-4 w-4 text-red-500 mr-2" />
              Risk Events
            </span>
            <Badge className="bg-red-500/10 text-red-500 border border-red-500/30 font-mono text-xs">{filteredRiskDocs.length} Incidents</Badge>
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
          <Table>
            <TableHeader className={isDark ? "border-white/[0.12] bg-black/20" : "border-black/[0.06] bg-black/[0.02]"}>
              <TableRow className={isDark ? "border-white/[0.12]" : "border-black/[0.06]"}>
                <TableHead className={`font-mono text-xs ${mutedText(theme)}`}>INCIDENT HEADLINE</TableHead>
                <TableHead className={`font-mono text-xs text-center ${mutedText(theme)}`}>RISK SCORE</TableHead>
                <TableHead className={`font-mono text-xs text-center ${mutedText(theme)}`}>SEVERITY</TableHead>
                <TableHead className={`font-mono text-xs text-center ${mutedText(theme)}`}>CORE TOPIC</TableHead>
                <TableHead className={`font-mono text-xs ${mutedText(theme)}`}>SOURCE</TableHead>
                <TableHead className={`font-mono text-xs ${mutedText(theme)}`}>PUBLISHED DATE</TableHead>
                <TableHead className={`font-mono text-xs text-right ${mutedText(theme)}`}>ACTION</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {filteredRiskDocs.map((doc, idx) => (
                <TableRow
                  key={doc.id}
                  className={`transition-colors cursor-pointer ${isDark ? "border-white/[0.08] hover:bg-white/[0.04]" : "border-black/[0.06] hover:bg-black/[0.02]"}`}
                  onClick={() => setSelectedDocId(doc.id)}
                >
                  <TableCell className={`font-mono text-xs font-bold max-w-[320px] truncate ${bodyText(theme)}`}>
                    {doc.title}
                  </TableCell>
                  <TableCell className={`text-center font-mono text-xs font-black ${
                    doc.risk > RISK_THRESHOLDS.HIGH_TO_CRITICAL ? "text-red-500" : doc.risk > RISK_THRESHOLDS.MEDIUM_TO_HIGH ? "text-orange-500" : "text-yellow-600"
                  }`}>
                    {Math.round(doc.risk || 0)}
                  </TableCell>
                  <TableCell className="text-center">
                    <Badge className={`font-mono text-xs ${
                      doc.severity === "CRITICAL" ? "bg-red-500/10 text-red-500 border border-red-500/20" :
                      doc.severity === "HIGH" ? "bg-orange-500/10 text-orange-500 border border-orange-500/20" :
                      "bg-yellow-500/10 text-yellow-600 border border-yellow-500/20"
                    }`}>
                      {doc.severity}
                    </Badge>
                  </TableCell>
                  <TableCell className="text-center">
                    <Badge variant="outline" className={isDark ? "border-[#00F5D4]/30 text-[#00F5D4] font-mono text-xs" : "border-[#3B82F6]/30 text-[#3B82F6] font-mono text-xs"}>
                      {doc.topic}
                    </Badge>
                  </TableCell>
                  <TableCell className={`font-mono text-xs truncate max-w-[120px] ${mutedText(theme)}`}>
                    {doc.source || "Unknown Source"}
                  </TableCell>
                  <TableCell className={`font-mono text-xs ${mutedText(theme)}`}>
                    {doc.timestamp ? new Date(doc.timestamp).toLocaleString(undefined, { dateStyle: 'short', timeStyle: 'short' }) : "N/A"}
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
              ))}
              {filteredRiskDocs.length === 0 && (
                <TableRow>
                  <TableCell colSpan={7} className={`text-center py-10 font-mono text-xs ${mutedText(theme)}`}>
                    {hasListFilter ? "No risk incidents match this filter." : "No risk incidents flagged."}
                  </TableCell>
                </TableRow>
              )}
            </TableBody>
          </Table>
        </CardContent>
      </Card>

      {/* 7. Risk Details Drawer (Slide-Over Panel) -- kept high-opacity
          (bg-zinc-950/95 dark, bg-white/95 light) rather than the standard
          glass alpha: at full page height over the dimmed backdrop, the
          spec's translucency read as illegible on long paragraph text
          (Original Article Snippet) in review, so this is the one place we
          backed off transparency for legibility per Part 3 of the brief. */}
      {selectedDoc && (
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
              <div className="flex-1 overflow-y-auto p-6 space-y-6">

                {/* Headline & Meta */}
                <div className="space-y-2">
                  <h3 className={`text-sm font-bold leading-snug ${bodyText(theme)}`}>{selectedDoc.title}</h3>
                  <div className="flex flex-wrap gap-2 text-xs">
                    <span className={`${glassPill(theme)} px-2 py-0.5 ${mutedText(theme)}`}>Source: {selectedDoc.source}</span>
                    <span className={`${glassPill(theme)} px-2 py-0.5 ${mutedText(theme)}`}>Topic: {selectedDoc.topic}</span>
                  </div>
                </div>

                {/* Risk score calculation breakdown */}
                <div className={`p-4 rounded-2xl border border-red-500/20 space-y-3 ${isDark ? "bg-black/30" : "bg-black/[0.03]"}`}>
                  <div className={`flex justify-between items-center border-b pb-2 ${isDark ? "border-white/[0.12]" : "border-black/[0.06]"}`}>
                    <span className="text-xs font-bold text-red-500">Risk Rating</span>
                    <span className="text-lg font-black text-red-500">{selectedDoc.risk} / 100</span>
                  </div>
                  <div className="space-y-1.5 text-xs">
                    <div className="flex justify-between">
                      <span className={mutedText(theme)}>Impact Score:</span>
                      {/* A4: previously re-displayed selectedDoc.risk (the
                          overall score, already shown above) instead of the
                          topic/heuristic component that actually feeds it --
                          risk_engine.py's own explainability.topic_contribution. */}
                      <span className={bodyText(theme)}>{selectedDoc.risk_explainability?.topic_contribution ?? 0}</span>
                    </div>
                    <div className="flex justify-between">
                      <span className={mutedText(theme)}>Sentiment:</span>
                      {/* A4: previously the raw sentiment_score (-1..1), not
                          the sentiment_contribution weight risk_engine.py
                          actually used in the score. */}
                      <span className={bodyText(theme)}>{(selectedDoc.risk_explainability?.sentiment_contribution ?? 0).toFixed(2)}</span>
                    </div>
                    <div className={`flex justify-between border-t pt-1.5 ${isDark ? "border-white/[0.08]" : "border-black/[0.06]"}`}>
                      <span className={mutedText(theme)}>Likelihood:</span>
                      <span className={`font-bold ${bodyText(theme)}`}>{selectedDoc.likelihood}%</span>
                    </div>
                    {selectedDoc.risk_explainability?.role_classification_source && selectedDoc.risk_explainability.role_classification_source !== "not_evaluated" && (
                      <div className={`flex justify-between border-t pt-1.5 ${isDark ? "border-white/[0.08]" : "border-black/[0.06]"}`}>
                        <span className={mutedText(theme)}>Attribution:</span>
                        <span className={
                          selectedDoc.risk_explainability.role_classification === "BYSTANDER" || selectedDoc.risk_explainability.role_classification === "EXONERATED"
                            ? "text-emerald-500 font-bold"
                            : bodyText(theme)
                        }>
                          {selectedDoc.risk_explainability.role_classification ?? "SELF (unchanged)"}
                          {selectedDoc.risk_explainability.role_classification_source === "fallback_unchanged" && " (fallback)"}
                        </span>
                      </div>
                    )}
                  </div>
                  {selectedDoc.risk_explainability?.decision_reason && (
                    <p className={`text-xs leading-relaxed border-t pt-2 ${mutedText(theme)} ${isDark ? "border-white/[0.08]" : "border-black/[0.06]"}`}>
                      {selectedDoc.risk_explainability.decision_reason}
                    </p>
                  )}
                </div>

                {/* Original Article Content */}
                <div className="space-y-2">
                  <span className={`text-xs uppercase font-bold flex items-center ${mutedText(theme)}`}>
                    <Info className="h-3.5 w-3.5 mr-1" style={{ color: accent }} /> Original Article Snippet
                  </span>
                  <div className={`p-4 rounded-2xl border text-xs leading-relaxed max-h-48 overflow-y-auto whitespace-pre-wrap ${mutedText(theme)} ${isDark ? "bg-black/30 border-white/[0.08]" : "bg-black/[0.03] border-black/[0.06]"}`}>
                    {selectedDoc.original_content || "No original content available."}
                  </div>
                </div>

                {/* Detected Entities */}
                <div className="space-y-2">
                  <span className={`text-xs uppercase font-bold ${mutedText(theme)}`}>Extracted Named Entities</span>
                  <div className="flex flex-wrap gap-2">
                    {selectedDoc.extracted_entities && selectedDoc.extracted_entities.length > 0 ? (
                      selectedDoc.extracted_entities.map((ent: any, idx: number) => (
                        <Badge key={idx} variant="outline" className="border-blue-500/30 text-blue-500 text-xs bg-blue-500/5">
                          {ent.name} ({ent.entity_type})
                        </Badge>
                      ))
                    ) : (
                      <span className={`text-xs ${mutedText(theme)}`}>No matching corporate entities identified.</span>
                    )}
                  </div>
                </div>

                {/* Related Narratives -- real cluster membership from the
                    backend (documents.py joins against each narrative's
                    evidence_metadata.supporting_documents), not a topic-name
                    guess. No badge when this document isn't part of any
                    narrative's cluster -- an expected state, not an error. */}
                <div className="space-y-2">
                  <span className={`text-xs uppercase font-bold ${mutedText(theme)}`}>Related Narrative Tracks</span>
                  {selectedDoc.narrative ? (
                    <button
                      type="button"
                      onClick={() => onViewNarrative?.(selectedDoc.narrative)}
                      disabled={!onViewNarrative}
                      className={`w-full text-left p-3 rounded-2xl border text-xs min-h-[44px] transition-colors ${bodyText(theme)} ${
                        isDark ? "bg-black/30 border-white/[0.08] hover:border-[#00F5D4]/40" : "bg-black/[0.03] border-black/[0.06] hover:border-[#3B82F6]/40"
                      } ${onViewNarrative ? "cursor-pointer" : "cursor-default"}`}
                    >
                      <span className={`font-bold ${isDark ? "text-[#00F5D4]" : "text-[#3B82F6]"}`}>Part of:</span>{" "}
                      {selectedDoc.narrative}
                    </button>
                  ) : (
                    <div className={`p-3 rounded-2xl border text-xs italic ${mutedText(theme)} ${isDark ? "bg-black/30 border-white/[0.08]" : "bg-black/[0.03] border-black/[0.06]"}`}>
                      Not part of a tracked narrative.
                    </div>
                  )}
                </div>

                {/* AI Summary -- same What/When/How-to-solve pattern as the
                    narrative drawer's Root Cause Analysis section
                    (NarrativesTab.tsx), generated per-item by
                    ai_summary_engine.py and stored in this item's own
                    risk_explainability.ai_summary. Absent (not rendered) for
                    LOW-severity items, which never get one, and for any
                    item whose first summary hasn't run yet. */}
                {selectedDoc.risk_explainability?.ai_summary && (
                  <div className={`space-y-2.5 p-4 rounded-2xl border ${isDark ? "bg-black/30 border-white/[0.08]" : "bg-black/[0.03] border-black/[0.06]"}`}>
                    <div className="flex items-center justify-between">
                      <span className={`text-xs uppercase font-bold flex items-center ${mutedText(theme)}`}>
                        <Info className="h-3.5 w-3.5 mr-1" style={{ color: accent }} /> AI Summary
                      </span>
                      {selectedDoc.risk_explainability.ai_summary.source === "narrative" && (
                        <InfoTooltip label="About this AI Summary">
                          Reused from this item&apos;s linked narrative&apos;s own root-cause
                          analysis, not freshly generated for this item alone -- avoids a
                          second, potentially-conflicting explanation of the same story.
                        </InfoTooltip>
                      )}
                    </div>
                    <div className="space-y-2 text-xs">
                      <div className="space-y-0.5">
                        <span className={`block uppercase text-xs ${mutedText(theme)}`}>What</span>
                        <p className={`leading-relaxed ${bodyText(theme)}`}>{selectedDoc.risk_explainability.ai_summary.what}</p>
                      </div>
                      <div className="space-y-0.5">
                        <span className={`block uppercase text-xs ${mutedText(theme)}`}>When</span>
                        <p className={`leading-relaxed ${bodyText(theme)}`}>{selectedDoc.risk_explainability.ai_summary.when || "Unknown"}</p>
                      </div>
                      <div className="space-y-0.5">
                        <span className={`block uppercase text-xs ${mutedText(theme)}`}>How to solve</span>
                        <p className={`leading-relaxed ${bodyText(theme)}`}>{selectedDoc.risk_explainability.ai_summary.how_to_solve}</p>
                      </div>
                    </div>
                    {selectedDoc.risk_explainability.ai_summary.source === "narrative" && (
                      <button
                        type="button"
                        onClick={() => onViewNarrative?.(selectedDoc.risk_explainability.ai_summary.narrative_name)}
                        disabled={!onViewNarrative}
                        className={`w-full text-left px-3 py-2.5 rounded-xl border text-xs min-h-[44px] transition-colors ${bodyText(theme)} ${
                          isDark ? "bg-black/30 border-[#00F5D4]/30 hover:border-[#00F5D4]/60" : "bg-black/[0.03] border-[#3B82F6]/30 hover:border-[#3B82F6]/60"
                        } ${onViewNarrative ? "cursor-pointer" : "cursor-default"}`}
                      >
                        <span className={`font-bold ${isDark ? "text-[#00F5D4]" : "text-[#3B82F6]"}`}>Via linked narrative:</span>{" "}
                        {selectedDoc.risk_explainability.ai_summary.narrative_name}
                      </button>
                    )}
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
      )}

      {/* 8. Risk Cell Incidents Drawer -- same high-opacity backing as the
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
                    Incidents: {selectedCell.impact} Impact / {selectedCell.likelihood} Likelihood
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
              <div className="flex-1 overflow-y-auto p-6 space-y-4">
                {(() => {
                  const cellDocs = matrixData[selectedCell.impact]?.[selectedCell.likelihood] || [];
                  if (cellDocs.length === 0) {
                    return <div className={`text-center py-10 text-xs ${mutedText(theme)}`}>No incidents in this cell.</div>;
                  }
                  return cellDocs.map((doc, idx) => (
                    <div key={doc.id ?? idx} className={`p-4 rounded-2xl border space-y-3 transition-colors ${isDark ? "bg-black/30 border-white/[0.08] hover:border-[#00F5D4]/40" : "bg-black/[0.03] border-black/[0.06] hover:border-[#3B82F6]/40"}`}>
                      <div className="flex justify-between items-start">
                        <span className={`text-xs ${mutedText(theme)}`}>Source: {doc.source}</span>
                        <Badge className={`font-mono text-xs ${
                          doc.risk > RISK_THRESHOLDS.HIGH_TO_CRITICAL ? "bg-red-500/10 text-red-500 border border-red-500/20" :
                          doc.risk > RISK_THRESHOLDS.MEDIUM_TO_HIGH ? "bg-orange-500/10 text-orange-500 border border-orange-500/20" :
                          "bg-yellow-500/10 text-yellow-600 border border-yellow-500/20"
                        }`}>
                          Risk Score: {Math.round(doc.risk || 0)}
                        </Badge>
                      </div>
                      <h4 className={`text-xs font-bold leading-snug ${bodyText(theme)}`}>{doc.title}</h4>
                      <div className={`flex justify-between items-center text-xs pt-1 border-t ${isDark ? "border-white/[0.08]" : "border-black/[0.06]"}`}>
                        <span className={mutedText(theme)}>Topic: {doc.topic}</span>
                        <span className={mutedText(theme)}>
                          {doc.timestamp ? new Date(doc.timestamp).toLocaleString(undefined, { dateStyle: 'short', timeStyle: 'short' }) : "N/A"}
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
                  ));
                })()}
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
