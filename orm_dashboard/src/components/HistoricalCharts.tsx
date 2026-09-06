import React from "react";
import { LineChart } from "lucide-react";
import { 
  LineChart as RechartsLineChart, Line, XAxis, YAxis, 
  CartesianGrid, Tooltip, ResponsiveContainer 
} from 'recharts';
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { TelemetryErrorWidget } from "@/components/TelemetryErrorWidget";
import { useTheme } from "@/components/theme/ThemeProvider";
import { glassCard, glassTokens, glassPill, mutedText, SPECULAR_LINE } from "@/components/theme/tokens";

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
  const { theme } = useTheme();
  const isDark = theme === "dark";
  const accent = isDark ? "#00F5D4" : "#3B82F6";

  if (historyLoading) {
    return (
      <Card className={`${glassTokens[theme].card} rounded-3xl h-[340px] animate-pulse`}>
        <CardHeader className="space-y-2">
          <div className={`h-4 rounded w-1/4 ${isDark ? "bg-white/[0.08]" : "bg-black/[0.06]"}`} />
        </CardHeader>
        <CardContent className={`h-[240px] rounded m-4 ${isDark ? "bg-white/[0.04]" : "bg-black/[0.03]"}`} />
      </Card>
    );
  }

  if (historyError) {
    return (
      <Card className={`${glassCard(theme)} border-red-500/20 h-[340px]`}>
        <TelemetryErrorWidget title="History Telemetry Offline" message={historyError} />
      </Card>
    );
  }

  return (
    <Card className={glassCard(theme)}>
      <div className={SPECULAR_LINE} />
      <CardHeader>
        <CardTitle className={`text-xs font-mono uppercase tracking-wider ${mutedText(theme)} flex items-center justify-between`}>
          <span>REPUTATION TREND TIMELINE</span>
          <Badge variant="outline" className={glassPill(theme)} style={{ color: accent, borderColor: `${accent}4D` }}>HISTORICAL RADAR</Badge>
        </CardTitle>
      </CardHeader>
      <CardContent className="pl-2">
        <div className="h-[280px]">
          {repHistory.length > 0 ? (
            <ResponsiveContainer width="100%" height="100%">
              <RechartsLineChart data={repHistory} margin={{ top: 10, right: 30, bottom: 10, left: 10 }}>
                <CartesianGrid strokeDasharray="3 3" vertical={false} stroke={isDark ? "#3f3f46" : "#d4d4d8"} strokeOpacity={0.4} />
                <XAxis dataKey="date" stroke={isDark ? "#a1a1aa" : "#71717a"} fontSize={10} tickLine={false} axisLine={false} />
                <YAxis stroke={isDark ? "#a1a1aa" : "#71717a"} fontSize={10} tickLine={false} axisLine={false} domain={['dataMin - 2', 'dataMax + 2']} />
                <Tooltip contentStyle={{ backgroundColor: isDark ? '#18181b' : '#ffffff', borderColor: isDark ? '#3f3f46' : '#e4e4e7', color: isDark ? '#fff' : '#18181b' }} />
                <Line type="monotone" dataKey="score" stroke={accent} strokeWidth={2} dot={{ r: 3, stroke: accent, fill: isDark ? '#09090b' : '#ffffff' }} activeDot={{ r: 5 }} />
              </RechartsLineChart>
            </ResponsiveContainer>
          ) : (
            <div className="flex flex-col items-center justify-center h-full space-y-3">
              <LineChart className={`h-8 w-8 opacity-60 ${mutedText(theme)}`} />
              <p className={`font-mono text-xs ${mutedText(theme)}`}>No reputation history available yet.</p>
              <p className={`font-mono text-[9px] ${mutedText(theme)}`}>Historical data will populate as reputation scores are calculated over time.</p>
            </div>
          )}
        </div>
      </CardContent>
    </Card>
  );
}
