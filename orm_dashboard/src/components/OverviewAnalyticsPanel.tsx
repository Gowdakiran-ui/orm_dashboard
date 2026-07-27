import React, { useMemo } from "react";
import { BarChart3, LineChart, Activity, Smile, TrendingUp, HelpCircle } from "lucide-react";
import { 
  PieChart, Pie, Cell, Tooltip, ResponsiveContainer,
  BarChart, Bar, CartesianGrid, XAxis, YAxis,
  LineChart as RechartsLineChart, Line
} from 'recharts';
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

export interface OverviewAnalyticsPanelProps {
  sentimentDistData: any[];
  topicDistData: any[];
  repHistory: any[];
  sentimentTrendData: any[];
}

export function OverviewAnalyticsPanel({
  sentimentDistData = [],
  topicDistData = [],
  repHistory = [],
  sentimentTrendData = []
}: OverviewAnalyticsPanelProps) {

  // 1. KPI Summaries based on live prop telemetry
  const kpis = useMemo(() => {
    const latestRep = repHistory.length > 0 ? repHistory[0].score : 0;
    const latestRepScore = latestRep > 0 ? latestRep.toFixed(1) : "0.0";
    
    const latestSent = sentimentTrendData.length > 0 ? sentimentTrendData[0].Sentiment : 0.0;
    const latestSentScore = latestSent > 0 ? `+${latestSent.toFixed(2)}` : latestSent.toFixed(2);
    
    const dimensionsCount = topicDistData.length;
    
    const posVal = sentimentDistData.find(d => d.name === "Positive")?.value || 0;
    const totalVal = sentimentDistData.reduce((acc, curr) => acc + (curr.value || 0), 0);
    const posRatio = totalVal > 0 ? `${((posVal / totalVal) * 100).toFixed(0)}%` : "0%";

    return [
      { label: "Avg Reputation", value: latestRepScore, desc: "Global asset rating index", icon: Activity, color: "text-[#D4AF37]" },
      { label: "Sentiment Index", value: latestSentScore, desc: "Polarity score (-1.0 to +1.0)", icon: Smile, color: "text-[#38BDF8]" },
      { label: "Topic Dimensions", value: dimensionsCount, desc: "Active classified vectors", icon: BarChart3, color: "text-purple-400" },
      { label: "Positive Share", value: posRatio, desc: "Favorable media percentage", icon: TrendingUp, color: "text-emerald-400" }
    ];
  }, [repHistory, sentimentTrendData, topicDistData, sentimentDistData]);

  // Premium dark tooltip theme style
  const tooltipStyle = {
    backgroundColor: 'rgba(11, 15, 25, 0.95)',
    borderColor: '#1e293b',
    borderRadius: '8px',
    boxShadow: '0 10px 30px rgba(0, 0, 0, 0.8)',
    color: '#e2e8f0',
    fontFamily: 'monospace',
    fontSize: '11px',
    padding: '12px'
  };

  const cardStyle = "bg-[#060B18]/60 border-[#1F2937]/70 shadow-[inset_0_1.5px_2px_rgba(255,255,255,0.06)] hover:border-[#D4AF37]/35 hover:shadow-[0_0_20px_rgba(212,175,55,0.12)] hover:-translate-y-0.5 transition-all duration-300 rounded-xl";

  return (
    <div className="space-y-6">
      {/* KPI summaries header */}
      <div className="grid gap-4 sm:grid-cols-2 md:grid-cols-4 font-mono">
        {kpis.map((k, idx) => {
          const Icon = k.icon;
          return (
            <div 
              key={idx} 
              className="bg-[#060B18]/60 border border-[#1F2937]/60 shadow-[inset_0_1px_2px_rgba(255,255,255,0.05)] rounded-xl p-4 flex flex-col justify-between hover:border-[#D4AF37]/30 transition-all duration-300"
            >
              <div className="flex justify-between items-start mb-2">
                <span className="text-[10px] text-slate-500 uppercase tracking-wider">{k.label}</span>
                <Icon className={`h-4 w-4 ${k.color}`} />
              </div>
              <div>
                <span className={`text-xl font-bold block ${k.color}`}>{k.value}</span>
                <span className="text-[8px] text-slate-500">{k.desc}</span>
              </div>
            </div>
          );
        })}
      </div>

      <div className="grid gap-6 md:grid-cols-2">
        {/* Sentiment Distribution */}
        <Card className={cardStyle}>
          <CardHeader className="pb-2">
            <CardTitle className="text-xs font-mono uppercase tracking-wider text-slate-400">Sentiment Distribution Matrix</CardTitle>
          </CardHeader>
          <CardContent className="flex justify-center items-center h-[260px]">
            {sentimentDistData.length > 0 ? (
              <ResponsiveContainer width="100%" height="100%">
                <PieChart>
                  <Pie
                    data={sentimentDistData}
                    cx="50%"
                    cy="50%"
                    innerRadius={60}
                    outerRadius={80}
                    paddingAngle={5}
                    dataKey="value"
                    isAnimationActive={true}
                    animationDuration={850}
                  >
                    {sentimentDistData.map((entry, index) => (
                      <Cell key={`cell-${index}`} fill={entry.color} />
                    ))}
                  </Pie>
                  <Tooltip contentStyle={tooltipStyle} />
                </PieChart>
              </ResponsiveContainer>
            ) : (
              <div className="flex flex-col items-center justify-center h-full space-y-2">
                <BarChart3 className="h-6 w-6 text-slate-500 opacity-60" />
                <p className="text-slate-500 font-mono text-xs">No sentiment distribution data.</p>
              </div>
            )}
          </CardContent>
        </Card>

        {/* Topic Frequency */}
        <Card className={cardStyle}>
          <CardHeader className="pb-2">
            <CardTitle className="text-xs font-mono uppercase tracking-wider text-slate-400">Dimension Frequency (Topic Count)</CardTitle>
          </CardHeader>
          <CardContent className="pl-2">
            <div className="h-[260px]">
              {topicDistData.length > 0 ? (
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={topicDistData}>
                    <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#1F2937" strokeOpacity={0.2} />
                    <XAxis dataKey="name" stroke="#94A3B8" fontSize={9} />
                    <YAxis stroke="#94A3B8" fontSize={9} />
                    <Tooltip contentStyle={tooltipStyle} />
                    <Bar dataKey="value" fill="#38BDF8" radius={[3, 3, 0, 0]} isAnimationActive={true} animationDuration={850} />
                  </BarChart>
                </ResponsiveContainer>
              ) : (
                <div className="flex items-center justify-center h-full text-slate-500 font-mono text-xs">No topics mapped.</div>
              )}
            </div>
          </CardContent>
        </Card>

        {/* Reputation Trend Card */}
        <Card className={cardStyle}>
          <CardHeader className="pb-2">
            <CardTitle className="text-xs font-mono uppercase tracking-wider text-slate-400">Reputation Score Trend Timeline</CardTitle>
          </CardHeader>
          <CardContent className="pl-2 h-[260px]">
            {repHistory.length > 0 ? (
              <ResponsiveContainer width="100%" height="100%">
                <RechartsLineChart data={repHistory} margin={{ top: 15, right: 30, bottom: 10, left: 10 }}>
                  <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#1F2937" strokeOpacity={0.2} />
                  <XAxis dataKey="date" stroke="#94A3B8" fontSize={9} tickLine={false} axisLine={false} />
                  <YAxis stroke="#94A3B8" fontSize={9} tickLine={false} axisLine={false} domain={['dataMin - 2', 'dataMax + 2']} />
                  <Tooltip contentStyle={tooltipStyle} />
                  <Line 
                    type="monotone" 
                    dataKey="score" 
                    stroke="#D4AF37" 
                    strokeWidth={2} 
                    dot={{ r: 3.5, stroke: '#D4AF37', fill: '#030712', strokeWidth: 1.5 }} 
                    activeDot={{ r: 6 }}
                    isAnimationActive={true} 
                    animationDuration={850}
                  />
                </RechartsLineChart>
              </ResponsiveContainer>
            ) : (
              <div className="flex flex-col items-center justify-center h-full space-y-2">
                <LineChart className="h-6 w-6 text-slate-500 opacity-60" />
                <p className="text-slate-500 font-mono text-xs">No historical reputation data available.</p>
              </div>
            )}
          </CardContent>
        </Card>

        {/* Sentiment Trend Card */}
        <Card className={cardStyle}>
          <CardHeader className="pb-2">
            <CardTitle className="text-xs font-mono uppercase tracking-wider text-slate-400">Average Sentiment Trend Timeline</CardTitle>
          </CardHeader>
          <CardContent className="pl-2 h-[260px]">
            {sentimentTrendData.length > 0 ? (
              <ResponsiveContainer width="100%" height="100%">
                <RechartsLineChart data={sentimentTrendData} margin={{ top: 15, right: 30, bottom: 10, left: 10 }}>
                  <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#1F2937" strokeOpacity={0.2} />
                  <XAxis dataKey="date" stroke="#94A3B8" fontSize={9} tickLine={false} axisLine={false} />
                  <YAxis stroke="#94A3B8" fontSize={9} tickLine={false} axisLine={false} domain={[-1, 1]} />
                  <Tooltip contentStyle={tooltipStyle} />
                  <Line 
                    type="monotone" 
                    dataKey="Sentiment" 
                    stroke="#38BDF8" 
                    strokeWidth={2} 
                    dot={{ r: 3.5, stroke: '#38BDF8', fill: '#030712', strokeWidth: 1.5 }} 
                    activeDot={{ r: 6 }}
                    isAnimationActive={true} 
                    animationDuration={850}
                  />
                </RechartsLineChart>
              </ResponsiveContainer>
            ) : (
              <div className="flex flex-col items-center justify-center h-full space-y-2">
                <LineChart className="h-6 w-6 text-slate-500 opacity-60" />
                <p className="text-slate-500 font-mono text-xs">No sentiment timeline data.</p>
              </div>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
