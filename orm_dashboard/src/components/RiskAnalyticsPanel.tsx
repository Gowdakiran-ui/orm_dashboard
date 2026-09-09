import React, { useMemo } from "react";
import { Shield, ShieldAlert, AlertTriangle, CheckCircle, Activity, Info, BarChart3 } from "lucide-react";
import {
  AreaChart, Area, XAxis, YAxis, CartesianGrid,
  Tooltip, ResponsiveContainer, ReferenceLine, ReferenceDot
} from 'recharts';
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { RISK_THRESHOLDS } from "@/utils/riskLevel";
import { TelemetryErrorWidget } from "@/components/TelemetryErrorWidget";
import { useTheme } from "@/components/theme/ThemeProvider";
import { glassCard, glassTokens, glassPill, mutedText, bodyText, SPECULAR_LINE } from "@/components/theme/tokens";
import { InfoTooltip } from "@/components/ui/InfoTooltip";
import { useTabNavigation } from "@/hooks/useTabNavigation";
import {
  RiskSeverityDefinition,
  AverageRiskScoreFeedDefinition,
  RiskMatrixAxesDefinition,
} from "@/lib/metricDefinitions";

export interface RiskAnalyticsPanelProps {
  riskMatrixData: any[];
  alertSeverityData: any[];
  riskHeatmapData: any;
  alertTimelineData: any[];
  loading?: boolean;
  error?: string | null;
}

export function RiskAnalyticsPanel({
  riskMatrixData = [],
  alertSeverityData = [],
  riskHeatmapData = { categories: [], severities: [], grid: {} },
  alertTimelineData = [],
  loading = false,
  error = null
}: RiskAnalyticsPanelProps) {
  const { theme } = useTheme();
  const isDark = theme === "dark";
  const accent = isDark ? "#00F5D4" : "#3B82F6";
  const accentColor = isDark ? "text-[#00F5D4]" : "text-[#3B82F6]";
  const { navigateTo } = useTabNavigation();

  // 1. KPI summary data
  const kpis = useMemo(() => {
    const totalIncidents = riskMatrixData.length;
    const avgRiskVal = totalIncidents > 0
      ? (riskMatrixData.reduce((sum, d) => sum + (d.impact || 0), 0) / totalIncidents)
      : 0.0;

    const criticalCount = riskMatrixData.filter(d => (d.impact || 0) > RISK_THRESHOLDS.HIGH_TO_CRITICAL).length;
    const alertsStatus = alertTimelineData.length === 0 ? "System Stable" : "Active Alerts";

    return [
      { label: "Total Incidents", value: totalIncidents, desc: "Monitored threat vectors", icon: Shield, color: accentColor, def: undefined as React.ReactNode },
      { label: "Avg Risk Rating", value: avgRiskVal.toFixed(2), desc: "Average severity score", icon: Activity, color: "text-amber-500", def: <AverageRiskScoreFeedDefinition /> },
      { label: "Critical Incidents", value: criticalCount, desc: `Risk score ${RISK_THRESHOLDS.HIGH_TO_CRITICAL + 1}+`, icon: ShieldAlert, color: "text-red-500", def: <RiskSeverityDefinition /> },
      { label: "Ingestion Status", value: alertsStatus, desc: alertTimelineData.length === 0 ? "0 Critical Alerts" : "Trigger thresholds crossed", icon: CheckCircle, color: alertTimelineData.length === 0 ? "text-emerald-400" : "text-orange-400", def: undefined as React.ReactNode }
    ];
  }, [riskMatrixData, alertTimelineData, accentColor]);

  // 2. 3x3 SOC Heatmap grouping
  const matrixData = useMemo(() => {
    const grid: Record<string, Record<string, any[]>> = {
      HIGH: { LOW: [], MEDIUM: [], HIGH: [] },
      MEDIUM: { LOW: [], MEDIUM: [], HIGH: [] },
      LOW: { LOW: [], MEDIUM: [], HIGH: [] }
    };
    (riskMatrixData || []).forEach(item => {
      const imp = item.impact >= 67 ? "HIGH" : item.impact >= 33 ? "MEDIUM" : "LOW";
      const lik = item.likelihood >= 67 ? "HIGH" : item.likelihood >= 33 ? "MEDIUM" : "LOW";
      if (grid[imp] && grid[imp][lik]) {
        grid[imp][lik].push(item);
      }
    });
    return grid;
  }, [riskMatrixData]);

  // 3. Threat Concentration Heatmap totals and percentages
  const { rowTotals, colTotals, grandTotal } = useMemo(() => {
    const rowTotals: Record<string, number> = {};
    const colTotals: Record<string, number> = {};
    let grandTotal = 0;
    
    if (riskHeatmapData && riskHeatmapData.categories) {
      riskHeatmapData.categories.forEach((cat: string) => {
        rowTotals[cat] = 0;
        riskHeatmapData.severities.forEach((sev: string) => {
          const count = riskHeatmapData.grid[cat]?.[sev]?.count || 0;
          rowTotals[cat] += count;
          colTotals[sev] = (colTotals[sev] || 0) + count;
          grandTotal += count;
        });
      });
    }
    return { rowTotals, colTotals, grandTotal };
  }, [riskHeatmapData]);

  // 4. Force timeline mapping even if empty to prevent empty panel
  const activeTimelineData = useMemo(() => {
    if (alertTimelineData && alertTimelineData.length > 0) return alertTimelineData;
    // Last 7 days flat baseline
    const list = [];
    for (let i = 6; i >= 0; i--) {
      const d = new Date();
      d.setDate(d.getDate() - i);
      list.push({
        date: d.toLocaleDateString(undefined, { month: 'short', day: 'numeric' }),
        count: 0
      });
    }
    return list;
  }, [alertTimelineData]);

  // Alerts timeline statistics
  const alertStats = useMemo(() => {
    if (!alertTimelineData || alertTimelineData.length === 0) return { avg: 0, peakDate: "", peakCount: 0 };
    const counts = alertTimelineData.map(d => d.count || 0);
    const sum = counts.reduce((a, b) => a + b, 0);
    const avg = Number((sum / alertTimelineData.length).toFixed(1));
    let maxIdx = 0;
    for (let i = 1; i < counts.length; i++) {
      if (counts[i] > counts[maxIdx]) {
        maxIdx = i;
      }
    }
    return {
      avg,
      peakDate: alertTimelineData[maxIdx]?.date || "",
      peakCount: alertTimelineData[maxIdx]?.count || 0
    };
  }, [alertTimelineData]);

  const tooltipStyle = {
    backgroundColor: isDark ? 'rgba(24, 24, 27, 0.95)' : 'rgba(255, 255, 255, 0.95)',
    borderColor: isDark ? '#3f3f46' : '#e4e4e7',
    borderRadius: '8px',
    boxShadow: isDark ? '0 10px 30px rgba(0, 0, 0, 0.8)' : '0 10px 30px rgba(0, 0, 0, 0.1)',
    color: isDark ? '#e4e4e7' : '#18181b',
    fontFamily: 'monospace',
    fontSize: '11px',
    padding: '12px'
  };

  const cardStyle = `${glassCard(theme)} hover:-translate-y-0.5`;
  const gridStroke = isDark ? "#3f3f46" : "#d4d4d8";
  const axisStroke = isDark ? "#a1a1aa" : "#71717a";

  if (loading) {
    return (
      <div className="grid gap-6 md:grid-cols-2 animate-pulse">
        {[1, 2].map(x => (
          <div key={x} className={`h-[300px] rounded-3xl ${glassTokens[theme].card}`} />
        ))}
      </div>
    );
  }

  if (error) {
    return (
      <Card className={`${glassCard(theme)} border-red-500/20 h-96`}>
        <TelemetryErrorWidget title="Risk Analytics Telemetry Offline" message={error} />
      </Card>
    );
  }

  return (
    <div className="space-y-6">
      {/* Top KPI row */}
      <div className="grid gap-4 sm:grid-cols-2 md:grid-cols-4 font-mono">
        {kpis.map((k, idx) => {
          const Icon = k.icon;
          return (
            <div
              key={idx}
              className={`${glassCard(theme)} p-4 flex flex-col justify-between`}
            >
              <div className={SPECULAR_LINE} />
              <div className="flex justify-between items-start mb-2">
                <span className={`text-[10px] uppercase tracking-wider flex items-center gap-1 ${mutedText(theme)}`}>
                  {k.label}
                  {k.def && <InfoTooltip label={`About ${k.label}`}>{k.def}</InfoTooltip>}
                </span>
                <Icon className={`h-4 w-4 ${k.color}`} />
              </div>
              <div>
                {k.label === "Avg Risk Rating" ? (
                  <button
                    type="button"
                    onClick={() => navigateTo("feed")}
                    className={`text-xl font-bold block text-left hover:underline ${k.color}`}
                  >
                    {k.value}
                  </button>
                ) : (
                  <span className={`text-xl font-bold block ${k.color}`}>{k.value}</span>
                )}
                <span className={`text-[8px] ${mutedText(theme)}`}>{k.desc}</span>
              </div>
            </div>
          );
        })}
      </div>

      <div className="grid gap-6 md:grid-cols-12">
        {/* 1. Redesigned 3x3 SOC-style Risk Matrix */}
        <Card className={`${cardStyle} md:col-span-6`}>
          <div className={SPECULAR_LINE} />
          <CardHeader className="pb-2">
            <CardTitle className={`text-xs font-mono uppercase tracking-wider flex items-center gap-1 ${mutedText(theme)}`}>
              SOC Risk Matrix (Impact × Likelihood)
              <InfoTooltip label="About Impact and Likelihood"><RiskMatrixAxesDefinition /></InfoTooltip>
            </CardTitle>
          </CardHeader>
          <CardContent className="p-4">
            <div className="grid grid-cols-12 gap-2 font-mono text-[9px]">
              {/* Y Axis Label */}
              <div className="col-span-1 flex items-center justify-center">
                <span className={`transform -rotate-90 origin-center whitespace-nowrap uppercase tracking-widest font-bold font-mono ${mutedText(theme)}`}>IMPACT</span>
              </div>

              {/* Matrix Grid */}
              <div className={`col-span-11 grid grid-rows-3 gap-1.5 p-2 rounded border ${isDark ? "bg-black/30 border-white/[0.08]" : "bg-black/[0.03] border-black/[0.06]"}`}>
                {["HIGH", "MEDIUM", "LOW"].map((rowKey) => (
                  <div key={rowKey} className="grid grid-cols-3 gap-1.5 h-[65px]">
                    {["LOW", "MEDIUM", "HIGH"].map((colKey) => {
                      const cellDocs = matrixData[rowKey]?.[colKey] || [];
                      const count = cellDocs.length;
                      
                      let avgRisk = "0.0";
                      let maxRisk = "0.0";
                      if (count > 0) {
                        const sum = cellDocs.reduce((acc, val) => acc + val.impact, 0);
                        avgRisk = (sum / count).toFixed(1);
                        maxRisk = Math.max(...cellDocs.map(d => d.impact)).toFixed(0);
                      }

                      let bgClass = "bg-[#030712]/40 border-[#1F2937]/35 text-slate-600";
                      if (count > 0) {
                        if (count <= 2) {
                          bgClass = "bg-red-950/20 border-red-900/40 text-red-400 hover:border-red-500/50 hover:bg-red-950/30";
                        } else if (count <= 5) {
                          bgClass = "bg-red-900/40 border-red-750/50 text-red-300 hover:border-red-500 hover:bg-red-900/50";
                        } else {
                          bgClass = "bg-red-800 border-red-500 text-red-100 hover:bg-red-700 hover:shadow-[0_0_12px_rgba(239,68,68,0.25)]";
                        }
                      }

                      return (
                        <div
                          key={colKey}
                          onClick={() => count > 0 && navigateTo("risk", { impact: rowKey, likelihood: colKey })}
                          className={`rounded p-2 flex flex-col items-center justify-center transition-all duration-300 cursor-pointer relative group text-center border ${bgClass}`}
                        >
                          {count > 0 ? (
                            <span className="text-[10px] font-bold block">🔴 {count} {count === 1 ? "Incident" : "Incidents"}</span>
                          ) : (
                            <span className={`text-[9px] block ${mutedText(theme)}`}>0</span>
                          )}

                          {/* Hover diagnostics tooltip -- kept solid for legibility over an
                              already-colored matrix cell, same reasoning as Risk Center. */}
                          <div className={`absolute z-50 hidden group-hover:block p-3 rounded-xl shadow-2xl font-mono text-[9px] w-48 text-left space-y-1.5 left-1/2 -translate-x-1/2 bottom-full mb-2 pointer-events-none border ${isDark ? "bg-zinc-950 border-white/[0.12]" : "bg-white border-black/[0.08]"}`}>
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
            </div>
          </CardContent>
        </Card>

        {/* 2. Daily Alerts Timeline (Styled for green baseline success if empty) */}
        <Card className={`${cardStyle} md:col-span-6`}>
          <div className={SPECULAR_LINE} />
          <CardHeader className="pb-1">
            <div className="flex justify-between items-start">
              <CardTitle className={`text-xs font-mono uppercase tracking-wider ${mutedText(theme)}`}>Daily Alerts Trigger Volume Timeline</CardTitle>
              {alertTimelineData.length === 0 && (
                <Badge className="bg-emerald-500/10 text-emerald-500 border border-emerald-500/20 font-mono text-[9px]">
                  System Stable
                </Badge>
              )}
            </div>
          </CardHeader>
          <CardContent className="pl-2 h-[240px] relative">
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={activeTimelineData} margin={{ top: 15, right: 30, left: 0, bottom: 5 }}>
                <defs>
                  <linearGradient id="colorAlert" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor={alertTimelineData.length === 0 ? "#10B981" : "#EF4444"} stopOpacity={0.35}/>
                    <stop offset="95%" stopColor={alertTimelineData.length === 0 ? "#10B981" : "#EF4444"} stopOpacity={0}/>
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" vertical={false} stroke={gridStroke} strokeOpacity={0.4} />
                <XAxis dataKey="date" stroke={axisStroke} fontSize={9} />
                <YAxis stroke={axisStroke} fontSize={9} />
                <Tooltip contentStyle={tooltipStyle} />
                <Area
                  type="monotone"
                  dataKey="count"
                  stroke={alertTimelineData.length === 0 ? "#10B981" : "#EF4444"}
                  fillOpacity={1}
                  fill="url(#colorAlert)"
                  strokeWidth={2}
                  isAnimationActive={true}
                  animationDuration={850}
                />

                {alertTimelineData.length > 0 && (
                  <>
                    <ReferenceLine
                      y={alertStats.avg}
                      stroke={axisStroke}
                      strokeDasharray="4 4"
                      label={{ value: `Avg (${alertStats.avg})`, fill: axisStroke, fontSize: 8, position: 'insideBottomRight' }}
                    />
                    <ReferenceDot
                      x={alertStats.peakDate}
                      y={alertStats.peakCount}
                      r={4}
                      fill="#EF4444"
                      stroke={isDark ? "#09090b" : "#ffffff"}
                      label={{ value: `Peak: ${alertStats.peakCount}`, fill: '#EF4444', fontSize: 9, position: 'top' }}
                    />
                  </>
                )}
              </AreaChart>
            </ResponsiveContainer>

            {alertTimelineData.length === 0 && (
              <div className="absolute inset-0 top-12 flex flex-col items-center justify-center pointer-events-none text-center bg-transparent space-y-1">
                <span className="text-[11px] font-bold font-mono text-emerald-500">System Stable</span>
                <span className={`text-[9px] font-mono ${mutedText(theme)}`}>0 Critical Alerts | Monitoring Active</span>
                <span className={`text-[8px] font-mono ${mutedText(theme)}`}>Window: Last 7 Days</span>
              </div>
            )}
          </CardContent>
        </Card>

        {/* 3. Improved Threat Concentration Heatmap */}
        <Card className={`${cardStyle} md:col-span-12`}>
          <div className={SPECULAR_LINE} />
          <CardHeader>
            <CardTitle className={`text-xs font-mono uppercase tracking-wider ${mutedText(theme)}`}>Threat Concentration Heatmap (Severity × Topic)</CardTitle>
          </CardHeader>
          <CardContent className="overflow-x-auto p-6">
            {riskHeatmapData && riskHeatmapData.categories && riskHeatmapData.categories.length > 0 ? (
              <div className="min-w-[700px] space-y-3 font-mono text-xs">
                {/* Headers */}
                <div className={`grid grid-cols-7 border-b pb-3 text-[10px] font-bold ${mutedText(theme)} ${isDark ? "border-white/[0.12]" : "border-black/[0.06]"}`}>
                  <div>TOPIC CATEGORY</div>
                  <div className="text-center">LOW</div>
                  <div className="text-center">MEDIUM</div>
                  <div className="text-center">HIGH</div>
                  <div className="text-center">CRITICAL</div>
                  <div className="text-center" style={{ color: accent }}>ROW TOTAL</div>
                  <div className={`text-center ${mutedText(theme)}`}>DIST %</div>
                </div>

                {/* Rows */}
                {riskHeatmapData.categories.map((cat: string, idx: number) => {
                  const rowTot = rowTotals[cat] || 0;
                  const rowPercent = grandTotal > 0 ? ((rowTot / grandTotal) * 100).toFixed(0) : "0";

                  return (
                    <div key={idx} className={`grid grid-cols-7 py-3 items-center border-b transition-colors ${isDark ? "border-white/[0.08] hover:bg-white/[0.03]" : "border-black/[0.06] hover:bg-black/[0.02]"}`}>
                      <div className={`font-bold truncate pr-2 ${bodyText(theme)}`}>{cat}</div>
                      {riskHeatmapData.severities.map((sev: string, sIdx: number) => {
                        const cellData = riskHeatmapData.grid[cat]?.[sev] || { count: 0, avgRisk: 0, avgSentiment: 0 };
                        const cellPercent = rowTot > 0 ? ((cellData.count / rowTot) * 100).toFixed(0) : "0";

                        const bgStyle = cellData.count > 0 ? {
                          backgroundColor: sev === "CRITICAL" ? `rgba(239, 68, 68, ${Math.min(0.12 + cellData.count * 0.15, 0.85)})` :
                                           sev === "HIGH" ? `rgba(249, 115, 22, ${Math.min(0.12 + cellData.count * 0.15, 0.85)})` :
                                           sev === "MEDIUM" ? `rgba(234, 179, 8, ${Math.min(0.12 + cellData.count * 0.15, 0.85)})` :
                                           `rgba(16, 185, 129, ${Math.min(0.12 + cellData.count * 0.15, 0.85)})`
                        } : undefined;

                        return (
                          <div
                            key={sIdx}
                            style={bgStyle}
                            className={`text-center py-3 rounded font-bold hover:opacity-85 transition-all relative group h-12 flex flex-col justify-center mx-1 shadow-sm border ${bodyText(theme)} ${isDark ? "border-white/[0.08]" : "border-black/[0.06]"} ${!bgStyle ? (isDark ? "bg-black/20" : "bg-black/[0.02]") : ""}`}
                            title={`Topic: ${cat}\nSeverity: ${sev}\nDocument Count: ${cellData.count}\nAvg Risk Score: ${cellData.avgRisk.toFixed(1)}\nAvg Sentiment: ${cellData.avgSentiment.toFixed(2)}`}
                          >
                            <span className="text-[10px] font-bold">
                              {cellData.count > 0 ? `${cellData.count} (${cellPercent}%)` : "0"}
                            </span>
                            {cellData.count > 0 && (
                              <span className={`text-[7.5px] mt-0.5 font-normal font-mono ${mutedText(theme)}`}>
                                R:{cellData.avgRisk.toFixed(0)} S:{cellData.avgSentiment.toFixed(1)}
                              </span>
                            )}
                          </div>
                        );
                      })}

                      {/* Row Total */}
                      <div className="text-center font-bold" style={{ color: accent }}>{rowTot}</div>
                      {/* Row Distribution % */}
                      <div className={`text-center font-bold ${mutedText(theme)}`}>{rowPercent}%</div>
                    </div>
                  );
                })}

                {/* Column Totals Row */}
                <div className={`grid grid-cols-7 pt-3 border-t-2 font-bold text-[10px] ${isDark ? "border-white/[0.12]" : "border-black/[0.08]"}`}>
                  <div className={`uppercase ${mutedText(theme)}`}>COLUMN TOTALS</div>
                  {riskHeatmapData.severities.map((sev: string, idx: number) => {
                    const colTot = colTotals[sev] || 0;
                    const colPercent = grandTotal > 0 ? ((colTot / grandTotal) * 100).toFixed(0) : "0";
                    return (
                      <div key={idx} className={`text-center ${bodyText(theme)}`}>
                        <div>{colTot}</div>
                        <div className={`text-[8px] font-normal ${mutedText(theme)}`}>{colPercent}%</div>
                      </div>
                    );
                  })}
                  <div className="text-center font-black" style={{ color: accent }}>{grandTotal}</div>
                  <div className={`text-center font-black ${mutedText(theme)}`}>100%</div>
                </div>
              </div>
            ) : (
              <div className={`text-center py-8 font-mono text-xs flex flex-col items-center space-y-2 ${mutedText(theme)}`}>
                <ShieldAlert className={`h-6 w-6 opacity-60 ${mutedText(theme)}`} />
                <span>No active risk events.</span>
              </div>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
