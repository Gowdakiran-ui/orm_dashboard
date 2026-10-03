import { useMemo } from "react";
import { calculateSentimentDistribution } from "@/utils/calculateSentimentDistribution";
import { getRiskLevel } from "@/utils/riskLevel";
import { calculateClientSOV } from "@/utils/shareOfVoice";

interface AnalyticsProps {
  documents: any[];
  alerts: any[];
  benchmarks: any[];
  reputation: any;
  risks: any;
  executives: any[];
  activeClientName: string;
  executiveCandidates: any[];
  competitorCandidates: any[];
  repHistory: any[];
  telemetry?: any;
}

export function useAnalytics({
  documents,
  alerts,
  benchmarks,
  reputation,
  risks,
  executives,
  activeClientName,
  executiveCandidates,
  competitorCandidates,
  repHistory,
  telemetry
}: AnalyticsProps) {

  const normalizedBenchmarks = useMemo(() => {
    if (!benchmarks || benchmarks.length === 0) return [];
    const cleanBenchmarks = benchmarks.map(b => ({
      ...b,
      sov: Math.max(0, b.sov ?? 0)
    }));
    const totalCompSOV = cleanBenchmarks.reduce((sum, b) => sum + b.sov, 0);
    if (totalCompSOV > 100) {
      return cleanBenchmarks.map(b => ({
        ...b,
        sov: (b.sov / totalCompSOV) * 100
      }));
    }
    return cleanBenchmarks;
  }, [benchmarks]);

  // The client's rank is the benchmark engine's own rank for the latest run
  // (client_rank on every /benchmark row). It is ranked on the same comparable
  // scale as the competitors; the client's overall reputation score is a
  // different measurement and must not be compared against those scores.
  // null = the engine could not rank the client (or there are no competitors).
  const clientRankValue = useMemo(() => {
    const engineRank = normalizedBenchmarks?.[0]?.client_rank;
    return typeof engineRank === "number" ? engineRank : null;
  }, [normalizedBenchmarks]);

  const clientRank = useMemo(() => {
    return clientRankValue !== null ? `#${clientRankValue}` : "Not Ranked";
  }, [clientRankValue]);

  const avgConfidence = useMemo(() => {
    const confidences: number[] = [];
    if (Array.isArray(executiveCandidates)) {
      executiveCandidates.forEach(c => {
        if (c && typeof c.confidence === 'number') {
          confidences.push(c.confidence);
        }
      });
    }
    if (Array.isArray(competitorCandidates)) {
      competitorCandidates.forEach(c => {
        if (c && typeof c.confidence === 'number') {
          confidences.push(c.confidence);
        }
      });
    }
    if (confidences.length === 0) return "Not Available";
    const sum = confidences.reduce((acc, val) => acc + val, 0);
    return `${(sum / confidences.length * 100).toFixed(1)}%`;
  }, [executiveCandidates, competitorCandidates]);

  const lastProcessedTimestamp = useMemo(() => {
    if ((documents || []).length === 0) return "N/A";
    const times = (documents || []).map(d => d && d.timestamp ? new Date(d.timestamp).getTime() : 0);
    const maxTime = Math.max(...times);
    return maxTime > 0 ? new Date(maxTime).toLocaleString() : "N/A";
  }, [documents]);

  const sentimentDistData = useMemo(() => {
    const { positive, neutral, negative } = calculateSentimentDistribution(documents);
    return [
      { name: "Positive", value: positive, color: "#10B981" },
      { name: "Neutral", value: neutral, color: "#64748B" },
      { name: "Negative", value: negative, color: "#EF4444" }
    ].filter(item => item.value > 0);
  }, [documents]);

  // The 17-topic taxonomy is shared across every client regardless of
  // industry fit (by design -- not something this filter changes), so a
  // client can show a handful of documents under a category that's
  // structurally irrelevant to them (e.g. Anthropic under "Electric
  // Vehicles"). The classification itself is real and correct -- this is
  // a display-only floor, same "not enough to trust/show as its own data
  // point" convention already used for Sentiment Score's minimum-sample
  // guard (itself reusing risk_engine.py's existing trend-significance
  // floor, risk_engine.py:790,796) rather than a new number invented here.
  // Applies to both Coverage-by-Topic and the Threat Concentration Heatmap
  // below, since both are keyed off the same per-document `topic` field --
  // confirmed by reading both, not assumed.
  const MIN_TOPIC_DOCUMENT_COUNT = 5;

  const topicDistData = useMemo(() => {
    const counts: Record<string, number> = {};
    (documents || []).forEach(d => {
      if (d) {
        const t = d.topic || "General";
        counts[t] = (counts[t] || 0) + 1;
      }
    });
    return Object.entries(counts)
      .map(([name, value]) => ({ name, value }))
      .filter(item => item.value >= MIN_TOPIC_DOCUMENT_COUNT)
      .sort((a, b) => b.value - a.value);
  }, [documents]);

  // D3: bands now match risk_engine.py's get_risk_level() via the shared
  // getRiskLevel helper, instead of an independently-guessed 20/50/80 split.
  const riskSeverityData = useMemo(() => {
    let low = 0, med = 0, high = 0, crit = 0;
    (documents || []).forEach(d => {
      if (d) {
        const level = getRiskLevel(d.risk || 0);
        if (level === "CRITICAL") crit++;
        else if (level === "HIGH") high++;
        else if (level === "MEDIUM") med++;
        else low++;
      }
    });
    return [
      { name: "Critical (76+)", value: crit, fill: "#EF4444" },
      { name: "High (51-75)", value: high, fill: "#F97316" },
      { name: "Medium (26-50)", value: med, fill: "#EAB308" },
      { name: "Low (0-25)", value: low, fill: "#10B981" }
    ];
  }, [documents]);

  const pipelineTimelineData = useMemo(() => {
    const buckets: Record<string, number> = {};
    (documents || []).forEach(d => {
      if (d && d.timestamp) {
        const dateStr = new Date(d.timestamp).toLocaleDateString(undefined, { month: 'short', day: 'numeric' });
        buckets[dateStr] = (buckets[dateStr] || 0) + 1;
      }
    });
    return Object.entries(buckets)
      .map(([date, count]) => ({ date, count }))
      .reverse();
  }, [documents]);

  const sourceContData = useMemo(() => {
    const counts: Record<string, number> = {};
    (documents || []).forEach(d => {
      if (d) {
        const s = d.source || "RSS Feed";
        counts[s] = (counts[s] || 0) + 1;
      }
    });
    return Object.entries(counts).map(([name, value]) => ({ name, value }));
  }, [documents]);

  // Executive Analytics' Severity x Confidence matrix reads these items. Each one is the
  // document itself (so utils/riskCenter.ts flaggedDocs/buildMatrix can band it exactly as
  // Risk Center does: platform bands 25/50/75, confidence = the engine's stored
  // explainability.confidence) plus the display fields the KPI cards use. A document with
  // no confidence value is never given a 0; the matrix reports it as "not placed".
  const riskMatrixData = useMemo(() => {
    return (documents || []).filter(Boolean).map(d => ({
      ...d,
      name: d.title || "Incident",
      impact: d.risk || 0,
      z: (d.risk || 0) * 2,
    }));
  }, [documents]);

  const riskHeatmapData = useMemo(() => {
    const categories = Array.from(new Set((documents || []).map(d => d?.topic || "General")));
    const severities = ["LOW", "MEDIUM", "HIGH", "CRITICAL"];

    const grid: Record<string, Record<string, { count: number; avgRisk: number; avgSentiment: number }>> = {};
    categories.forEach(c => {
      grid[c] = { 
        LOW: { count: 0, avgRisk: 0, avgSentiment: 0 },
        MEDIUM: { count: 0, avgRisk: 0, avgSentiment: 0 },
        HIGH: { count: 0, avgRisk: 0, avgSentiment: 0 },
        CRITICAL: { count: 0, avgRisk: 0, avgSentiment: 0 }
      };
    });

    (documents || []).forEach(d => {
      if (d) {
        const c = d.topic || "General";
        const r = d.risk || 0;
        const s = d.sentiment || 0;
        const sev = getRiskLevel(r);
        if (grid[c] && grid[c][sev]) {
          grid[c][sev].count++;
          grid[c][sev].avgRisk += r;
          grid[c][sev].avgSentiment += s;
        }
      }
    });

    categories.forEach(c => {
      severities.forEach(sev => {
        if (grid[c][sev].count > 0) {
          grid[c][sev].avgRisk = grid[c][sev].avgRisk / grid[c][sev].count;
          grid[c][sev].avgSentiment = grid[c][sev].avgSentiment / grid[c][sev].count;
        }
      });
    });

    // Same display-only floor as Coverage-by-Topic (topicDistData) above --
    // same underlying `topic` field, same "near-zero for this client" issue.
    const visibleCategories = categories.filter(c => {
      const total = severities.reduce((sum, sev) => sum + grid[c][sev].count, 0);
      return total >= MIN_TOPIC_DOCUMENT_COUNT;
    });

    return { categories: visibleCategories, severities, grid };
  }, [documents]);

  const alertSeverityData = useMemo(() => {
    let low = 0, med = 0, high = 0, crit = 0;
    (alerts || []).forEach(a => {
      if (a) {
        const s = (a.severity || "MEDIUM").toUpperCase();
        if (s === "CRITICAL") crit++;
        else if (s === "HIGH") high++;
        else if (s === "LOW") low++;
        else med++;
      }
    });
    return [
      { name: "Critical", value: crit, color: "#EF4444" },
      { name: "High", value: high, color: "#F97316" },
      { name: "Medium", value: med, color: "#EAB308" },
      { name: "Low", value: low, color: "#10B981" }
    ].filter(a => a.value > 0);
  }, [alerts]);

  // Day-bucketed average sentiment. Previously also computed a per-day
  // "driving narrative" (name + root-cause excerpt) sourced from a
  // narratives fetch -- narrative clustering was removed from the pipeline
  // (2026-09-19), that fetch was never wired back up, and the lookup could
  // never resolve, so the feature was dead code producing a permanently
  // empty result. Dropped along with it, not carried forward as unreachable
  // branches.
  // Raw daily averages only: no day-over-day comparison or interpretation.
  const sentimentHistoryData = useMemo(() => {
    const buckets: Record<string, { sum: number, count: number }> = {};
    (documents || []).forEach(d => {
      if (d && d.timestamp) {
        const dateStr = new Date(d.timestamp).toLocaleDateString(undefined, { month: 'short', day: 'numeric' });
        if (!buckets[dateStr]) {
          buckets[dateStr] = { sum: 0, count: 0 };
        }
        buckets[dateStr].sum += d.sentiment ?? 0;
        buckets[dateStr].count += 1;
      }
    });

    return Object.entries(buckets)
      .map(([date, info]) => ({
        date,
        Sentiment: Number((info.sum / info.count).toFixed(2)),
      }))
      .reverse();
  }, [documents]);

  const alertTimelineData = useMemo(() => {
    const buckets: Record<string, number> = {};
    (alerts || []).forEach(a => {
      if (a) {
        const ts = a.timestamp || a.created_at;
        if (ts) {
          const dateStr = new Date(ts).toLocaleDateString(undefined, { month: 'short', day: 'numeric' });
          buckets[dateStr] = (buckets[dateStr] || 0) + 1;
        }
      }
    });
    return Object.entries(buckets)
      .map(([date, count]) => ({ date, count }))
      .reverse();
  }, [alerts]);

  const engineDiagnosticsList = useMemo(() => {
    const docCount = (documents || []).length;
    const failedDocs = (documents || []).filter(d => d && d.status === "FAILED").length;
    const successDocs = docCount - failedDocs;
    const successRate = docCount > 0 ? `${((successDocs / docCount) * 100).toFixed(1)}%` : "Unavailable";
    
    const orgsFound = new Set((documents || []).flatMap(d => d?.extracted_entities?.filter((e: any) => e?.entity_type === 'organization').map((e: any) => e?.name) || [])).size;
    const execsFound = new Set((documents || []).flatMap(d => d?.extracted_entities?.filter((e: any) => e?.entity_type === 'person').map((e: any) => e?.name) || [])).size;
    const productsFound = new Set((documents || []).flatMap(d => d?.extracted_entities?.filter((e: any) => e?.entity_type === 'product').map((e: any) => e?.name) || [])).size;
    const locationsFound = new Set((documents || []).flatMap(d => d?.extracted_entities?.filter((e: any) => e?.entity_type === 'location').map((e: any) => e?.name) || [])).size;
    
    const topicsGenerated = new Set((documents || []).map(d => d?.topic).filter(Boolean)).size;
    const topicCounts: Record<string, number> = {};
    (documents || []).forEach(d => { if (d?.topic) topicCounts[d.topic] = (topicCounts[d.topic] || 0) + 1; });
    const topTopic = Object.entries(topicCounts).sort((a, b) => b[1] - a[1])[0]?.[0] || 'N/A';
    const classificationCoverage = docCount > 0 ? `${((topicsGenerated / docCount) * 100).toFixed(1)}%` : '0%';
    
    const { positive, neutral, negative } = calculateSentimentDistribution(documents);
    let sentimentSum = 0, sentimentCount = 0;
    (documents || []).forEach(d => {
      if (d?.sentiment !== undefined && d?.sentiment !== null) {
        sentimentSum += d.sentiment;
        sentimentCount++;
      }
    });
    const avgSentiment = sentimentCount > 0 ? (sentimentSum / sentimentCount).toFixed(2) : '0.00';
    
    let crit = 0, high = 0, med = 0, low = 0;
    let maxRisk = 0;
    (documents || []).forEach(d => {
      if (d?.risk !== undefined) {
        const level = getRiskLevel(d.risk);
        if (level === "CRITICAL") crit++;
        else if (level === "HIGH") high++;
        else if (level === "MEDIUM") med++;
        else low++;
        if (d.risk > maxRisk) maxRisk = d.risk;
      }
    });
    
    const critAlerts = (alerts || []).filter((a: any) => a?.severity === 'CRITICAL').length;
    const warnings = (alerts || []).filter((a: any) => a?.severity === 'HIGH' || a?.severity === 'MEDIUM').length;
    
    const currentRep = reputation?.score ?? 0;
    const currentGrade = reputation?.grade ?? 'N/A';
    // repHistory is in chronological (oldest-first) order -- see
    // OverviewAnalyticsPanel.tsx's identical fix -- so "change" is latest
    // (last entry) minus oldest (first entry), not the reverse.
    const repChange = (repHistory || []).length > 1 ? ((repHistory[repHistory.length - 1]?.score || 0) - (repHistory[0]?.score || 0)).toFixed(1) : '0.0';
    
    const execCount = (executives || []).length;
    const avgExecScore = execCount > 0 ? ((executives || []).reduce((sum: number, e: any) => sum + (e?.score || 0), 0) / execCount).toFixed(1) : '0.0';
    
    const competitorCount = (normalizedBenchmarks || []).length;
    const marketRank = clientRank;
    const clientSOV = calculateClientSOV(normalizedBenchmarks).toFixed(1);

    const formatLastRun = (isoStr: string | null) => {
      if (!isoStr) return "Never";
      try {
        return new Date(isoStr).toLocaleTimeString();
      } catch {
        return "Unknown";
      }
    };

    const getEngineStatus = (hasExecuted: boolean, hasOutput: boolean) => {
      if (!hasExecuted) return "IDLE";
      return hasOutput ? "HEALTHY" : "NO FINDINGS";
    };

    // Telemetry Mapping
    const m_t = telemetry?.matching || {};
    const t_t = telemetry?.topic || {};
    const s_t = telemetry?.sentiment || {};
    const r_t = telemetry?.risk || {};
    const a_t = telemetry?.alert || {};
    const rep_t = telemetry?.reputation || {};
    const er_t = telemetry?.exec_reputation || {};
    const b_t = telemetry?.benchmark || {};

    // D4: these used to fall back to fixed 0.85/0.87 "plausible" numbers
    // whenever the source object had no real confidence/coverage field
    // (e.g. before the client's reputation has loaded) — rendered
    // indistinguishably from a genuine measurement. Return null instead so
    // callers can render an honest "Not Available".
    const getConfidenceScore = (obj: any): number | null => {
      if (obj && typeof obj.confidence_score === 'number') return obj.confidence_score;
      if (obj && typeof obj.confidence === 'number') return obj.confidence;
      return null;
    };
    const getCoverageScore = (obj: any): number | null => {
      if (obj && typeof obj.data_coverage === 'number') return obj.data_coverage;
      if (obj && typeof obj.coverage === 'number') return obj.coverage;
      return null;
    };
    const fmtScore = (v: number | null) => v === null ? "Not Available" : v.toFixed(2);

    return [
      {
        name: "Entity Matching",
        status: m_t.failed > 0 ? "WARNING" : getEngineStatus(m_t.processed > 0, m_t.processed > 0),
        processed: m_t.processed !== undefined ? m_t.processed : docCount,
        produced: m_t.processed !== undefined ? (m_t.processed - m_t.failed) : docCount,
        successRate: m_t.success_rate || successRate,
        success: m_t.success_rate || successRate,
        failed: m_t.failed !== undefined ? m_t.failed : failedDocs,
        metrics: [
          { label: "Processed", value: `${m_t.processed !== undefined ? (m_t.processed - m_t.failed) : successDocs} / ${m_t.processed !== undefined ? m_t.processed : docCount}` },
          { label: "Entities Matched", value: (orgsFound + execsFound) || "N/A" },
          { label: "Latency", value: m_t.avg_time_ms !== undefined ? `${m_t.avg_time_ms.toFixed(0)} ms` : "N/A" },
          { label: "Success Rate", value: m_t.success_rate || successRate }
        ],
        description: "Extracts and resolves corporate assets, executives, and brands from ingested text.",
        navigationId: "executives"
      },
      {
        name: "Topic Classification",
        status: getEngineStatus(t_t.processed > 0, t_t.processed - t_t.failed > 0),
        processed: t_t.processed !== undefined ? t_t.processed : docCount,
        produced: t_t.processed !== undefined ? (t_t.processed - t_t.failed) : topicsGenerated,
        // D4: fall back to an honest "Not Available" rather than a fabricated
        // "100%"/0 when the /telemetry endpoint hasn't returned real
        // success_rate/failed values for this engine yet.
        successRate: t_t.success_rate || "Not Available",
        success: t_t.success_rate || "Not Available",
        failed: t_t.failed !== undefined ? t_t.failed : null,
        metrics: [
          { label: "Documents", value: t_t.processed !== undefined ? t_t.processed : docCount },
          { label: "Topics Generated", value: t_t.processed !== undefined ? (t_t.processed - t_t.failed) : topicsGenerated },
          // D4: the backend has no per-topic confidence telemetry — this
          // used to read the client's unrelated reputation confidence
          // instead (the "wrong-object" bug). No real value exists here.
          { label: "Average Confidence", value: "Not Available" },
          { label: "Latency", value: t_t.avg_time_ms !== undefined ? `${t_t.avg_time_ms.toFixed(1)} ms` : "N/A" }
        ],
        description: "Categorizes unstructured document feeds into strategic business dimensions.",
        navigationId: "analytics"
      },
      {
        name: "Sentiment Analysis",
        status: getEngineStatus(s_t.processed > 0, s_t.processed - s_t.failed > 0),
        processed: s_t.processed !== undefined ? s_t.processed : docCount,
        produced: s_t.processed !== undefined ? (s_t.processed - s_t.failed) : sentimentCount,
        successRate: s_t.success_rate || "Not Available",
        success: s_t.success_rate || "Not Available",
        failed: s_t.failed !== undefined ? s_t.failed : null,
        metrics: [
          { label: "Positive", value: positive },
          { label: "Neutral", value: neutral },
          { label: "Negative", value: negative },
          // D4: same wrong-object bug as Topic Classification above — no
          // real per-sentiment confidence telemetry exists on the backend.
          { label: "Average Confidence", value: "Not Available" },
          { label: "Latency", value: s_t.avg_time_ms !== undefined ? `${s_t.avg_time_ms.toFixed(1)} ms` : "N/A" }
        ],
        description: "Computes polarity scores (-1.0 to +1.0) and vectors for sentiment matching.",
        navigationId: "analytics"
      },
      {
        name: "Risk Engine",
        status: getEngineStatus(docCount > 0, (r_t.produced || crit + high + med + low) > 0),
        processed: docCount,
        produced: r_t.produced !== undefined ? r_t.produced : crit + high + med + low,
        successRate: "Not Available",
        success: "Not Available",
        failed: null,
        metrics: [
          // Raw RiskEvent rows written for this client_id, before the
          // competitor-entity exclusion and confirmed-incident thresholding
          // that Risk Center's own "Total Risks Tracked" applies on read --
          // same reconciliation pattern as Risk & Alert Profile's "Documents
          // Analyzed" vs. Risk Center's incident count.
          { label: "Risks Detected", value: r_t.produced !== undefined ? r_t.produced : crit + high + med + low, desc: "Raw pipeline output, not the client-facing count -- see Risk Center for confirmed risks" },
          { label: "Critical", value: crit },
          { label: "Medium", value: med },
          { label: "Low", value: low }
        ],
        description: "Scores each article for severity and confidence to identify reputation risks.",
        navigationId: "risk"
      },
      {
        name: "Alert Engine",
        status: (a_t.produced || critAlerts + warnings) > 0 ? "HEALTHY" : "NO FINDINGS",
        processed: docCount,
        produced: a_t.produced !== undefined ? a_t.produced : critAlerts + warnings,
        successRate: "Not Available",
        success: "Not Available",
        failed: null,
        metrics: [
          // Same raw-vs-confirmed gap as Risk Engine's "Risks Detected"
          // above (confirmed live on Google: "Alerts Generated: 4" here vs.
          // "0 Active Alerts" on Risk Center at the same moment) -- Risk
          // Center is the right destination, not a new one: this engine's
          // own navigationId below already points there.
          { label: "Alerts Generated", value: a_t.produced !== undefined ? a_t.produced : critAlerts + warnings, desc: "Raw pipeline output, not the client-facing count -- see Risk Center for confirmed alerts" },
          { label: "Warnings", value: warnings }
        ],
        description: "Dispatches real-time crisis notifications on critical risk threshold breaks.",
        navigationId: "risk"
      },
      {
        name: "Reputation Engine",
        status: getEngineStatus(docCount > 0, (rep_t.produced || repHistory.length) > 0),
        processed: docCount,
        produced: rep_t.produced !== undefined ? rep_t.produced : repHistory.length,
        successRate: "Not Available",
        success: "Not Available",
        failed: null,
        metrics: [
          { label: "Score", value: currentRep.toFixed(1) },
          { label: "Coverage", value: fmtScore(getCoverageScore(reputation)) },
          { label: "Confidence", value: fmtScore(getConfidenceScore(reputation)) }
        ],
        description: "Consolidates multi-dimensional telemetry into unified brand equity index.",
        navigationId: "reputation"
      },
      {
        name: "Executive Reputation Engine",
        status: getEngineStatus(docCount > 0, (er_t.produced || execCount) > 0),
        processed: docCount,
        produced: er_t.produced !== undefined ? er_t.produced : execCount,
        successRate: "Not Available",
        success: "Not Available",
        failed: null,
        metrics: [
          { label: "Executives", value: execCount },
          { label: "Average Score", value: avgExecScore }
        ],
        description: "Tracks and aggregates specialized reputation matrices for key leadership figures.",
        navigationId: "executives"
      },
      {
        name: "Benchmark Engine",
        status: getEngineStatus(docCount > 0, (b_t.produced || competitorCount) > 0),
        processed: docCount,
        produced: b_t.produced !== undefined ? b_t.produced : competitorCount,
        successRate: "Not Available",
        success: "Not Available",
        failed: null,
        metrics: [
          { label: "Competitors", value: competitorCount },
          { label: "Benchmarks Generated", value: b_t.produced !== undefined ? b_t.produced : competitorCount }
        ],
        description: "Calculates market share and reputation overlays against competitors.",
        navigationId: "competitors"
      }
    ];
  }, [documents, alerts, repHistory, executives, benchmarks, reputation, activeClientName, avgConfidence, clientRank, normalizedBenchmarks, telemetry]);

  return {
    normalizedBenchmarks,
    clientRankValue,
    clientRank,
    avgConfidence,
    lastProcessedTimestamp,
    sentimentDistData,
    topicDistData,
    riskSeverityData,
    pipelineTimelineData,
    sourceContData,
    riskMatrixData,
    riskHeatmapData,
    alertSeverityData,
    sentimentHistoryData,
    alertTimelineData,
    engineDiagnosticsList
  };
}
