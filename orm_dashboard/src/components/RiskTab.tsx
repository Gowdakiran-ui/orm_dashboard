import React, { useState, useMemo } from "react";
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

export interface RiskTabProps {
  alertsLoading: boolean;
  alertsError: string | null;
  alerts: any[];
  documentsLoading: boolean;
  documentsError: string | null;
  documents: any[];
}

export function RiskTab({
  alertsLoading,
  alertsError,
  alerts,
  documentsLoading,
  documentsError,
  documents
}: RiskTabProps) {
  const [selectedDocId, setSelectedDocId] = useState<string | null>(null);
  const [selectedCell, setSelectedCell] = useState<{ impact: string; likelihood: string } | null>(null);

  // Filter out documents with valid risk scores
  const riskDocs = useMemo(() => {
    return (documents || [])
      .filter(d => d && typeof d.risk === "number")
      .map(d => {
        const likelihood = Math.round(((1 - (d.sentiment ?? 0)) / 2) * 100);
        return {
          ...d,
          likelihood,
          severity: getRiskLevel(d.risk)
        };
      })
      .sort((a, b) => b.risk - a.risk);
  }, [documents]);

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
            <div key={x} className="h-20 bg-[#1E293B]/20 border border-[#1F2937]/60 rounded-lg" />
          ))}
        </div>
        <div className="grid gap-6 md:grid-cols-2">
          <div className="h-60 bg-[#1E293B]/10 border border-[#1F2937]/60 rounded-lg" />
          <div className="h-60 bg-[#1E293B]/10 border border-[#1F2937]/60 rounded-lg" />
        </div>
      </div>
    );
  }

  if (documentsError) {
    return (
      <Card className="bg-[#060B18]/60 border-red-500/20 col-span-4 h-96">
        <TelemetryErrorWidget title="Risk Telemetry Offline" message={documentsError} />
      </Card>
    );
  }

  return (
    <div className="space-y-8 relative">
      
      {/* 1. Risk Summary Cards */}
      <div className="grid gap-4 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-7 font-mono">
        {[
          { label: "Total Risks", value: stats.total, color: "text-[#D4AF37]" },
          { label: "Critical Risks", value: stats.critical, color: "text-red-500" },
          { label: "High Risks", value: stats.high, color: "text-orange-500" },
          { label: "Medium Risks", value: stats.medium, color: "text-yellow-500" },
          { label: "Low Risks", value: stats.low, color: "text-emerald-500" },
          { label: "Avg Risk Score", value: stats.avg, color: "text-slate-200" },
          { label: "Highest Risk", value: stats.highest, color: "text-red-650 font-black" }
        ].map((card, idx) => (
          <div key={idx} className="bg-[#060B18]/60 border border-[#1F2937]/60 rounded-lg p-4 flex flex-col justify-between hover:border-[#D4AF37]/30 transition-all duration-300">
            <span className="text-[9px] text-slate-500 uppercase tracking-wider block mb-2">{card.label}</span>
            <span className={`text-xl font-bold ${card.color}`}>{card.value}</span>
          </div>
        ))}
      </div>

      {/* 1b. Active Alerts */}
      <Card className="bg-[#060B18]/60 border-[#1F2937]/60 shadow-2xl">
        <CardHeader>
          <CardTitle className="text-xs font-mono uppercase tracking-wider text-slate-400 flex items-center justify-between">
            <span className="flex items-center">
              <AlertTriangle className="h-4 w-4 text-orange-500 mr-2" />
              ACTIVE ALERTS
            </span>
            {!alertsLoading && !alertsError && (
              <Badge className="bg-orange-500/10 text-orange-400 border border-orange-500/30 font-mono text-[9px]">{alerts.length} Active</Badge>
            )}
          </CardTitle>
        </CardHeader>
        <CardContent>
          {alertsLoading ? (
            <div className="space-y-2 animate-pulse">
              {[1, 2, 3].map(x => (
                <div key={x} className="h-10 bg-[#1E293B]/20 border border-[#1F2937]/60 rounded-lg" />
              ))}
            </div>
          ) : alertsError ? (
            <TelemetryErrorWidget title="Alert Feed Offline" message={alertsError} />
          ) : alerts.length === 0 ? (
            <div className="text-center py-6 text-slate-500 font-mono text-xs">No active alerts.</div>
          ) : (
            <div className="space-y-2 max-h-[220px] overflow-y-auto pr-1">
              {alerts.map((alert) => (
                <div key={alert.id} className="flex items-center justify-between bg-[#030712] border border-[#1F2937]/50 rounded p-3 font-mono text-xs">
                  <div className="flex items-center space-x-3 min-w-0">
                    <Badge className={`font-mono text-[8px] shrink-0 ${
                      alert.severity === "CRITICAL" ? "bg-red-500/10 text-red-400 border border-red-500/20" :
                      alert.severity === "HIGH" ? "bg-orange-500/10 text-orange-400 border border-orange-500/20" :
                      alert.severity === "WARNING" ? "bg-yellow-500/10 text-yellow-550 border border-yellow-500/20" :
                      "bg-slate-500/10 text-slate-400 border border-slate-500/20"
                    }`}>
                      {alert.severity}
                    </Badge>
                    <span className="text-slate-200 font-bold truncate">{alert.title}</span>
                    <span className="text-slate-500 text-[10px] shrink-0 hidden sm:inline">{alert.alert_type}</span>
                  </div>
                  <span className="text-slate-500 text-[10px] shrink-0 ml-3">
                    {alert.created_at ? new Date(alert.created_at).toLocaleString(undefined, { dateStyle: 'short', timeStyle: 'short' }) : "N/A"}
                  </span>
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>

      {/* Grid containing Severity pie & Likelihood Matrix */}
      <div className="grid gap-6 md:grid-cols-12">
        
        {/* 2. Risk Severity Distribution (Donut Chart) */}
        <Card className="bg-[#060B18]/60 border-[#1F2937]/60 shadow-2xl md:col-span-4">
          <CardHeader className="pb-2">
            <CardTitle className="text-xs font-mono uppercase tracking-wider text-slate-400">Severity Profile</CardTitle>
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
                  <Tooltip contentStyle={{ backgroundColor: '#060B18', borderColor: '#1F2937', color: '#fff', fontFamily: 'monospace', fontSize: 10 }} />
                </PieChart>
              </ResponsiveContainer>
            ) : (
              <div className="text-slate-500 font-mono text-[10px] flex items-center justify-center">No risk profile details.</div>
            )}
            <div className="absolute flex flex-col items-center justify-center font-mono">
              <span className="text-[8px] text-slate-500 uppercase">Avg Rating</span>
              <span className="text-lg font-bold text-slate-200">{stats.avg}</span>
            </div>
          </CardContent>
        </Card>

        {/* 3. 3x3 Risk Matrix */}
        <Card className="bg-[#060B18]/60 border-[#1F2937]/60 shadow-2xl md:col-span-8">
          <CardHeader className="pb-2">
            <CardTitle className="text-xs font-mono uppercase tracking-wider text-slate-400">Analyst Risk Matrix (Likelihood × Impact)</CardTitle>
          </CardHeader>
          <CardContent className="p-4">
            <div className="grid grid-cols-12 gap-2 font-mono text-[9px]">
              
              {/* Y Axis Label */}
              <div className="col-span-1 flex items-center justify-center">
                <span className="transform -rotate-90 origin-center whitespace-nowrap text-slate-500 uppercase tracking-widest font-bold">IMPACT (RISK)</span>
              </div>

              {/* 3x3 Matrix Grid */}
              <div className="col-span-11 grid grid-rows-3 gap-1 bg-[#030712] p-1.5 rounded border border-[#1F2937]/40">
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
                          onClick={() => count > 0 && setSelectedCell({ impact: rowKey, likelihood: colKey })}
                          className={`rounded p-2 flex flex-col items-center justify-center transition-all duration-300 cursor-pointer relative group text-center ${bgClass}`}
                        >
                          {count > 0 ? (
                            <span className="text-[10px] font-bold block">🔴 {count} {count === 1 ? "Incident" : "Incidents"}</span>
                          ) : (
                            <span className="text-[10px] text-slate-600 block">No incidents</span>
                          )}
                          
                          {/* Hover diagnostics tooltip */}
                          <div className="absolute z-50 hidden group-hover:block bg-[#030712] border border-[#1F2937] p-3 rounded shadow-2xl font-mono text-[9px] w-48 text-left space-y-1.5 left-1/2 -translate-x-1/2 bottom-full mb-2 pointer-events-none">
                            <div className="font-bold border-b border-[#1F2937] pb-1 text-[#D4AF37] mb-1">Cell Diagnostics</div>
                            <div className="flex justify-between">
                              <span className="text-slate-500">Impact:</span>
                              <span className="text-slate-200">{rowKey}</span>
                            </div>
                            <div className="flex justify-between">
                              <span className="text-slate-500">Likelihood:</span>
                              <span className="text-slate-200">{colKey}</span>
                            </div>
                            <div className="flex justify-between">
                              <span className="text-slate-500">Incidents:</span>
                              <span className="text-slate-200 font-bold">{count}</span>
                            </div>
                            <div className="flex justify-between">
                              <span className="text-slate-500">Avg Risk Score:</span>
                              <span className="text-slate-250 font-bold">{count > 0 ? avgRisk : "N/A"}</span>
                            </div>
                            <div className="flex justify-between">
                              <span className="text-slate-500">Highest Risk:</span>
                              <span className="text-red-400 font-bold">{count > 0 ? maxRisk : "N/A"}</span>
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
              <div className="col-span-11 grid grid-cols-3 text-center text-slate-500 uppercase tracking-wider font-bold mt-1 text-[8px]">
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
        <Card className="bg-[#060B18]/60 border-[#1F2937]/60 shadow-2xl">
          <CardHeader className="pb-2">
            <CardTitle className="text-xs font-mono uppercase tracking-wider text-slate-400 flex items-center">
              <Calendar className="h-4 w-4 text-[#D4AF37] mr-2" />
              Risk Ingestion Timeline
            </CardTitle>
          </CardHeader>
          <CardContent className="h-[200px] pl-2">
            {timelineChartData.length > 0 ? (
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={timelineChartData} margin={{ top: 10, right: 10, left: -20, bottom: 0 }}>
                  <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#1F2937" strokeOpacity={0.2} />
                  <XAxis dataKey="date" stroke="#64748B" fontSize={8} tickLine={false} />
                  <YAxis stroke="#64748B" fontSize={8} tickLine={false} allowDecimals={false} />
                  <Tooltip contentStyle={{ backgroundColor: '#060B18', borderColor: '#1F2937', color: '#fff', fontFamily: 'monospace', fontSize: 10 }} />
                  <Line type="monotone" dataKey="count" name="Risks Detected" stroke="#EF4444" strokeWidth={2} dot={{ r: 3, fill: '#EF4444' }} />
                </LineChart>
              </ResponsiveContainer>
            ) : (
              <div className="flex items-center justify-center h-full text-slate-500 font-mono text-xs">No historical risks tracked.</div>
            )}
          </CardContent>
        </Card>

        {/* 5. Risk Categories */}
        <Card className="bg-[#060B18]/60 border-[#1F2937]/60 shadow-2xl">
          <CardHeader className="pb-2">
            <CardTitle className="text-xs font-mono uppercase tracking-wider text-slate-400 flex items-center">
              <TrendingUp className="h-4 w-4 text-[#D4AF37] mr-2" />
              Incident Categories
            </CardTitle>
          </CardHeader>
          <CardContent className="h-[200px] pl-2">
            {categoryData.length > 0 ? (
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={categoryData} layout="vertical" margin={{ top: 5, right: 15, left: 10, bottom: 5 }}>
                  <CartesianGrid strokeDasharray="3 3" horizontal={false} stroke="#1F2937" strokeOpacity={0.2} />
                  <XAxis type="number" stroke="#64748B" fontSize={8} tickLine={false} />
                  <YAxis dataKey="name" type="category" stroke="#64748B" fontSize={8} tickLine={false} width={80} />
                  <Tooltip contentStyle={{ backgroundColor: '#060B18', borderColor: '#1F2937', color: '#fff', fontFamily: 'monospace', fontSize: 10 }} />
                  <Bar dataKey="count" name="Incidents" fill="#D4AF37" radius={[0, 4, 4, 0]} barSize={12} />
                </BarChart>
              </ResponsiveContainer>
            ) : (
              <div className="flex items-center justify-center h-full text-slate-500 font-mono text-xs">No category metrics loaded.</div>
            )}
          </CardContent>
        </Card>
      </div>

      {/* 6. High Risk Incidents Table */}
      <Card className="bg-[#060B18]/60 border-[#1F2937]/60 shadow-2xl">
        <CardHeader>
          <CardTitle className="text-xs font-mono uppercase tracking-wider text-slate-400 flex items-center justify-between">
            <span className="flex items-center">
              <ShieldAlert className="h-4 w-4 text-red-500 mr-2" />
              INCIDENT COMMAND REGISTER
            </span>
            <Badge className="bg-red-500/10 text-red-400 border border-red-500/30 font-mono text-[9px]">{riskDocs.length} Incidents</Badge>
          </CardTitle>
        </CardHeader>
        <CardContent>
          <Table>
            <TableHeader className="border-[#1F2937]/40 bg-[#030712]/50">
              <TableRow className="border-[#1F2937]/40">
                <TableHead className="text-slate-500 font-mono text-[10px]">INCIDENT HEADLINE</TableHead>
                <TableHead className="text-slate-500 font-mono text-[10px] text-center">RISK SCORE</TableHead>
                <TableHead className="text-slate-500 font-mono text-[10px] text-center">SEVERITY</TableHead>
                <TableHead className="text-slate-500 font-mono text-[10px] text-center">CORE TOPIC</TableHead>
                <TableHead className="text-slate-500 font-mono text-[10px]">SOURCE</TableHead>
                <TableHead className="text-slate-500 font-mono text-[10px]">PUBLISHED DATE</TableHead>
                <TableHead className="text-slate-500 font-mono text-[10px] text-right">ACTION</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {riskDocs.map((doc, idx) => (
                <TableRow key={doc.id} className="border-[#1F2937]/40 hover:bg-[#060B18] transition-colors cursor-pointer" onClick={() => setSelectedDocId(doc.id)}>
                  <TableCell className="font-mono text-xs font-bold text-slate-200 max-w-[320px] truncate">
                    {doc.title}
                  </TableCell>
                  <TableCell className={`text-center font-mono text-xs font-black ${
                    doc.risk > RISK_THRESHOLDS.HIGH_TO_CRITICAL ? "text-red-500" : doc.risk > RISK_THRESHOLDS.MEDIUM_TO_HIGH ? "text-orange-500" : "text-yellow-500"
                  }`}>
                    {doc.risk}
                  </TableCell>
                  <TableCell className="text-center">
                    <Badge className={`font-mono text-[8px] ${
                      doc.severity === "CRITICAL" ? "bg-red-500/10 text-red-400 border border-red-500/20" :
                      doc.severity === "HIGH" ? "bg-orange-500/10 text-orange-400 border border-orange-500/20" :
                      "bg-yellow-500/10 text-yellow-550 border border-yellow-500/20"
                    }`}>
                      {doc.severity}
                    </Badge>
                  </TableCell>
                  <TableCell className="text-center">
                    <Badge variant="outline" className="border-[#D4AF37]/30 text-[#D4AF37] font-mono text-[9px]">
                      {doc.topic}
                    </Badge>
                  </TableCell>
                  <TableCell className="font-mono text-xs text-slate-400 truncate max-w-[120px]">
                    {doc.source || "Unknown Source"}
                  </TableCell>
                  <TableCell className="font-mono text-[10px] text-slate-500">
                    {doc.timestamp ? new Date(doc.timestamp).toLocaleString(undefined, { dateStyle: 'short', timeStyle: 'short' }) : "N/A"}
                  </TableCell>
                  <TableCell className="text-right">
                    <button 
                      onClick={(e) => { e.stopPropagation(); setSelectedDocId(doc.id); }}
                      className="bg-blue-600 hover:bg-blue-700 cursor-pointer text-white font-mono text-[9px] rounded py-1 px-2.5"
                    >
                      TRACE
                    </button>
                  </TableCell>
                </TableRow>
              ))}
              {riskDocs.length === 0 && (
                <TableRow>
                  <TableCell colSpan={7} className="text-center py-10 text-slate-500 font-mono text-xs">
                    No risk incidents flagged.
                  </TableCell>
                </TableRow>
              )}
            </TableBody>
          </Table>
        </CardContent>
      </Card>

      {/* 7. Risk Details Drawer (Slide-Over Panel) */}
      {selectedDoc && (
        <div className="fixed inset-0 z-50 overflow-hidden font-mono">
          {/* Overlay backdrop */}
          <div className="absolute inset-0 bg-black/60 backdrop-blur-sm transition-opacity" onClick={() => setSelectedDocId(null)} />
          
          <div className="absolute inset-y-0 right-0 max-w-full flex pl-10">
            <div className="w-[600px] bg-[#060B18] border-l border-[#1F2937]/80 text-slate-200 flex flex-col justify-between shadow-2xl animate-in slide-in-from-right duration-300">
              
              {/* Header */}
              <div className="p-6 border-b border-[#1F2937]/80 flex items-center justify-between">
                <div className="flex items-center space-x-3">
                  <AlertOctagon className="h-5 w-5 text-red-500" />
                  <span className="text-sm font-bold uppercase text-[#D4AF37]">Tactical Trace Examiner</span>
                </div>
                <button onClick={() => setSelectedDocId(null)} className="text-slate-500 hover:text-slate-200 transition-colors">
                  <X className="h-5 w-5" />
                </button>
              </div>

              {/* Content Panel */}
              <div className="flex-1 overflow-y-auto p-6 space-y-6">
                
                {/* Headline & Meta */}
                <div className="space-y-2">
                  <h3 className="text-sm font-bold text-slate-100 leading-snug">{selectedDoc.title}</h3>
                  <div className="flex flex-wrap gap-2 text-[10px]">
                    <span className="bg-[#030712] border border-[#1F2937]/65 px-2 py-0.5 rounded text-slate-400">Source: {selectedDoc.source}</span>
                    <span className="bg-[#030712] border border-[#1F2937]/65 px-2 py-0.5 rounded text-slate-400">Topic: {selectedDoc.topic}</span>
                  </div>
                </div>

                {/* Risk score calculation breakdown */}
                <div className="bg-[#030712] p-4 rounded border border-red-500/20 space-y-3">
                  <div className="flex justify-between items-center border-b border-[#1F2937] pb-2">
                    <span className="text-xs font-bold text-red-400">RISK COMMAND RATING</span>
                    <span className="text-lg font-black text-red-500">{selectedDoc.risk} / 100</span>
                  </div>
                  <div className="space-y-1.5 text-[10px]">
                    <div className="flex justify-between">
                      <span className="text-slate-500">Heuristic Impact Score:</span>
                      <span className="text-slate-300">{selectedDoc.risk}</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-slate-500">Sentiment Polarity (Multiplier):</span>
                      <span className="text-slate-350">{selectedDoc.sentiment?.toFixed(2) || "0.00"}</span>
                    </div>
                    <div className="flex justify-between border-t border-[#1F2937]/50 pt-1.5">
                      <span className="text-slate-400">Calculated Likelihood Index:</span>
                      <span className="text-slate-200 font-bold">{selectedDoc.likelihood}%</span>
                    </div>
                  </div>
                </div>

                {/* Original Article Content */}
                <div className="space-y-2">
                  <span className="text-[10px] text-slate-500 uppercase font-bold flex items-center">
                    <Info className="h-3.5 w-3.5 mr-1 text-[#D4AF37]" /> Original Article Snippet
                  </span>
                  <div className="bg-[#030712] border border-[#1F2937]/40 p-4 rounded text-[11px] text-slate-400 leading-relaxed max-h-48 overflow-y-auto whitespace-pre-wrap">
                    {selectedDoc.original_content || "No original content available."}
                  </div>
                </div>

                {/* Detected Entities */}
                <div className="space-y-2">
                  <span className="text-[10px] text-slate-500 uppercase font-bold">Extracted Named Entities</span>
                  <div className="flex flex-wrap gap-2">
                    {selectedDoc.extracted_entities && selectedDoc.extracted_entities.length > 0 ? (
                      selectedDoc.extracted_entities.map((ent: any, idx: number) => (
                        <Badge key={idx} variant="outline" className="border-blue-500/30 text-blue-400 text-[9px] bg-blue-500/5">
                          {ent.name} ({ent.entity_type})
                        </Badge>
                      ))
                    ) : (
                      <span className="text-[10px] text-slate-500">No matching corporate entities identified.</span>
                    )}
                  </div>
                </div>

                {/* Related Narratives */}
                <div className="space-y-2">
                  <span className="text-[10px] text-slate-500 uppercase font-bold">Related Narrative Tracks</span>
                  <div className="bg-[#030712] border border-[#1F2937]/40 p-3 rounded text-[11px] text-slate-300">
                    {selectedDoc.narrative || "General Narrative"}
                  </div>
                </div>

              </div>

              {/* Drawer Footer */}
              <div className="p-4 border-t border-[#1F2937]/80 bg-[#030712]/50 flex justify-end space-x-3">
                {selectedDoc.url && (
                  <a 
                    href={selectedDoc.url} 
                    target="_blank" 
                    rel="noopener noreferrer" 
                    className="flex items-center space-x-1.5 bg-[#D4AF37] hover:bg-[#bfa032] text-black font-bold font-mono text-[10px] rounded px-4 py-2"
                  >
                    <span>View Source Article</span>
                    <ExternalLink className="h-3 w-3" />
                  </a>
                )}
                <button 
                  onClick={() => setSelectedDocId(null)} 
                  className="bg-transparent border border-[#1F2937] hover:border-slate-500 text-slate-400 hover:text-slate-200 text-[10px] rounded px-4 py-2"
                >
                  Close
                </button>
              </div>

            </div>
          </div>
      </div>
      )}

      {/* 8. Risk Cell Incidents Drawer */}
      {selectedCell && (
        <div className="fixed inset-0 z-50 overflow-hidden font-mono">
          <div className="absolute inset-0 bg-black/60 backdrop-blur-sm transition-opacity" onClick={() => setSelectedCell(null)} />
          <div className="absolute inset-y-0 right-0 max-w-full flex pl-10">
            <div className="w-[600px] bg-[#060B18] border-l border-[#1F2937]/80 text-slate-200 flex flex-col justify-between shadow-2xl animate-in slide-in-from-right duration-300">
              
              {/* Header */}
              <div className="p-6 border-b border-[#1F2937]/80 flex items-center justify-between">
                <div className="flex items-center space-x-3">
                  <ShieldAlert className="h-5 w-5 text-red-500" />
                  <span className="text-sm font-bold uppercase text-[#D4AF37]">
                    Incidents: {selectedCell.impact} Impact / {selectedCell.likelihood} Likelihood
                  </span>
                </div>
                <button onClick={() => setSelectedCell(null)} className="text-slate-500 hover:text-slate-200 transition-colors">
                  <X className="h-5 w-5" />
                </button>
              </div>

              {/* Content List */}
              <div className="flex-1 overflow-y-auto p-6 space-y-4">
                {(() => {
                  const cellDocs = matrixData[selectedCell.impact]?.[selectedCell.likelihood] || [];
                  if (cellDocs.length === 0) {
                    return <div className="text-center py-10 text-slate-500 text-xs">No incidents in this cell.</div>;
                  }
                  return cellDocs.map((doc, idx) => (
                    <div key={doc.id ?? idx} className="bg-[#030712] p-4 rounded border border-[#1F2937]/65 space-y-3 hover:border-[#D4AF37]/45 transition-colors">
                      <div className="flex justify-between items-start">
                        <span className="text-[10px] text-slate-500">Source: {doc.source}</span>
                        <Badge className={`font-mono text-[8px] ${
                          doc.risk > RISK_THRESHOLDS.HIGH_TO_CRITICAL ? "bg-red-500/10 text-red-400 border border-red-500/20" :
                          doc.risk > RISK_THRESHOLDS.MEDIUM_TO_HIGH ? "bg-orange-500/10 text-orange-400 border border-orange-500/20" :
                          "bg-yellow-500/10 text-yellow-450 border border-yellow-500/20"
                        }`}>
                          Risk Score: {doc.risk}
                        </Badge>
                      </div>
                      <h4 className="text-xs font-bold text-slate-200 leading-snug">{doc.title}</h4>
                      <div className="flex justify-between items-center text-[10px] pt-1 border-t border-[#1F2937]/40">
                        <span className="text-slate-400">Topic: {doc.topic}</span>
                        <span className="text-slate-500">
                          {doc.timestamp ? new Date(doc.timestamp).toLocaleString(undefined, { dateStyle: 'short', timeStyle: 'short' }) : "N/A"}
                        </span>
                      </div>
                      <div className="flex justify-end pt-1">
                        <button
                          onClick={() => { setSelectedDocId(doc.id); setSelectedCell(null); }}
                          className="bg-blue-650 hover:bg-blue-750 text-white font-mono text-[9px] rounded py-1 px-3"
                        >
                          TRACE EXAMINER &rarr;
                        </button>
                      </div>
                    </div>
                  ));
                })()}
              </div>

              {/* Footer */}
              <div className="p-4 border-t border-[#1F2937]/80 bg-[#030712]/50 flex justify-end">
                <button 
                  onClick={() => setSelectedCell(null)} 
                  className="bg-transparent border border-[#1F2937] hover:border-slate-500 text-slate-400 hover:text-slate-200 text-[10px] rounded px-4 py-2"
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
