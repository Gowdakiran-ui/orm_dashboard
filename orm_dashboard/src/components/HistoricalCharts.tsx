import React from "react";
import { LineChart } from "lucide-react";
import { 
  LineChart as RechartsLineChart, Line, XAxis, YAxis, 
  CartesianGrid, Tooltip, ResponsiveContainer 
} from 'recharts';
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { TelemetryErrorWidget } from "@/components/TelemetryErrorWidget";

export interface HistoricalChartsProps {
  historyLoading: boolean;
  historyError: string | null;
  repHistory: any[];
}

export function HistoricalCharts({
  historyLoading,
  historyError,
  repHistory
}: HistoricalChartsProps) {
  if (historyLoading) {
    return (
      <Card className="bg-[#060B18]/60 border-[#1F2937]/60 h-[340px] animate-pulse">
        <CardHeader className="space-y-2">
          <div className="h-4 bg-[#1E293B] rounded w-1/4" />
        </CardHeader>
        <CardContent className="h-[240px] bg-[#1E293B]/10 rounded m-4" />
      </Card>
    );
  }

  if (historyError) {
    return (
      <Card className="bg-[#060B18]/60 border-red-500/20 h-[340px]">
        <TelemetryErrorWidget title="History Telemetry Offline" message={historyError} />
      </Card>
    );
  }

  return (
    <Card className="bg-[#060B18]/60 border-[#1F2937]/60 shadow-2xl">
      <CardHeader>
        <CardTitle className="text-xs font-mono uppercase tracking-wider text-slate-400 flex items-center justify-between">
          <span>REPUTATION TREND TIMELINE</span>
          <Badge variant="outline" className="border-[#D4AF37]/30 text-[#D4AF37] font-mono text-[9px]">HISTORICAL RADAR</Badge>
        </CardTitle>
      </CardHeader>
      <CardContent className="pl-2">
        <div className="h-[280px]">
          {repHistory.length > 0 ? (
            <ResponsiveContainer width="100%" height="100%">
              <RechartsLineChart data={repHistory} margin={{ top: 10, right: 30, bottom: 10, left: 10 }}>
                <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#1F2937" strokeOpacity={0.2} />
                <XAxis dataKey="date" stroke="#94A3B8" fontSize={10} tickLine={false} axisLine={false} />
                <YAxis stroke="#94A3B8" fontSize={10} tickLine={false} axisLine={false} domain={['dataMin - 2', 'dataMax + 2']} />
                <Tooltip contentStyle={{ backgroundColor: '#060B18', borderColor: '#1F2937', color: '#fff' }} />
                <Line type="monotone" dataKey="score" stroke="#D4AF37" strokeWidth={2} dot={{ r: 3, stroke: '#D4AF37', fill: '#030712' }} activeDot={{ r: 5 }} />
              </RechartsLineChart>
            </ResponsiveContainer>
          ) : (
            <div className="flex flex-col items-center justify-center h-full space-y-3">
              <LineChart className="h-8 w-8 text-slate-500 opacity-60" />
              <p className="text-slate-500 font-mono text-xs">No reputation history available yet.</p>
              <p className="text-slate-600 font-mono text-[9px]">Historical data will populate as reputation scores are calculated over time.</p>
            </div>
          )}
        </div>
      </CardContent>
    </Card>
  );
}
