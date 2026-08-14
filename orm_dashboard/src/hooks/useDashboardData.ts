import { useEffect, useState, useRef } from "react";
import { 
  fetchClients, fetchReputation, fetchReputationHistory, fetchReputationBreakdown,
  fetchActiveAlerts, fetchNarratives, fetchCompetitorBenchmarks, fetchRisks, 
  fetchExecutives, fetchExecutiveHistory, fetchSystemStatus, fetchDocuments, fetchIntelligenceFeed,
  fetchCommandCenterStats,
  fetchExecutiveCandidates, fetchCompetitorCandidates, fetchClientTelemetry
} from "@/lib/api";
import { formatChartDate } from "@/utils/formatChartDate";

export function useDashboardData() {
  const [clients, setClients] = useState<any[]>([]);
  const [clientId, setClientId] = useState<string | null>(null);
  const [clientsLoading, setClientsLoading] = useState(true);
  const [clientsError, setClientsError] = useState<string | null>(null);

  // Data states & individual loading/error states
  const [reputation, setReputation] = useState<any>({ score: 0, grade: 'N/A', trend: 'STABLE' });
  const [reputationLoading, setReputationLoading] = useState(true);
  const [reputationError, setReputationError] = useState<string | null>(null);

  const [repHistory, setRepHistory] = useState<any[]>([]);
  const [historyLoading, setHistoryLoading] = useState(true);
  const [historyError, setHistoryError] = useState<string | null>(null);

  const [repBreakdown, setRepBreakdown] = useState<any>({ sentiment: 0, risk: 0, narrative: 0, trend: 0, source: 0, visibility: 0 });
  const [breakdownLoading, setBreakdownLoading] = useState(true);
  const [breakdownError, setBreakdownError] = useState<string | null>(null);

  const [alerts, setAlerts] = useState<any[]>([]);
  const [alertsLoading, setAlertsLoading] = useState(true);
  const [alertsError, setAlertsError] = useState<string | null>(null);

  const [narratives, setNarratives] = useState<any[]>([]);
  const [narrativesLoading, setNarrativesLoading] = useState(true);
  const [narrativesError, setNarrativesError] = useState<string | null>(null);

  const [benchmarks, setBenchmarks] = useState<any[]>([]);
  const [benchmarksLoading, setBenchmarksLoading] = useState(true);
  const [benchmarksError, setBenchmarksError] = useState<string | null>(null);

  const [risks, setRisks] = useState<any>({ average_recent_risk_score: 0.0, recent_critical_events: 0, recent_high_events: 0 });
  const [risksLoading, setRisksLoading] = useState(true);
  const [risksError, setRisksError] = useState<string | null>(null);

  const [executives, setExecutives] = useState<any[]>([]);
  const [executivesLoading, setExecutivesLoading] = useState(true);
  const [executivesError, setExecutivesError] = useState<string | null>(null);

  const [execHistory, setExecHistory] = useState<Record<string, any[]>>({});
  const [execHistoryLoading, setExecHistoryLoading] = useState(false);

  const [systemStatus, setSystemStatus] = useState<any>({ status: 'offline', active_feeds: 0, total_documents_collected: 0, total_documents_matched: 0 });
  const [systemStatusLoading, setSystemStatusLoading] = useState(true);
  const [systemStatusError, setSystemStatusError] = useState<string | null>(null);
  
  const [documents, setDocuments] = useState<any[]>([]);
  const [documentsLoading, setDocumentsLoading] = useState(true);
  const [documentsError, setDocumentsError] = useState<string | null>(null);
  const [trendEvents, setTrendEvents] = useState<any[]>([]);

  const [commandStats, setCommandStats] = useState<any>({});
  const [commandStatsLoading, setCommandStatsLoading] = useState(true);
  const [commandStatsError, setCommandStatsError] = useState<string | null>(null);


  const [executiveCandidates, setExecutiveCandidates] = useState<any[]>([]);
  const [executiveCandidatesLoading, setExecutiveCandidatesLoading] = useState(true);
  const [executiveCandidatesError, setExecutiveCandidatesError] = useState<string | null>(null);

  const [competitorCandidates, setCompetitorCandidates] = useState<any[]>([]);
  const [competitorCandidatesLoading, setCompetitorCandidatesLoading] = useState(true);
  const [competitorCandidatesError, setCompetitorCandidatesError] = useState<string | null>(null);

  const [telemetry, setTelemetry] = useState<any>(null);
  const [telemetryLoading, setTelemetryLoading] = useState(true);
  const [telemetryError, setTelemetryError] = useState<string | null>(null);

  const [selectedNarrative, setSelectedNarrative] = useState<string | null>(null);
  const [dashboardRefreshKey, setDashboardRefreshKey] = useState(0);
  const [clientsRefreshKey, setClientsRefreshKey] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    async function init() {
      try {
        const fetchedClients = await fetchClients(undefined, controller.signal);
        setClientsError(null);
        if (fetchedClients && fetchedClients.length > 0) {
          setClients(fetchedClients);
          setClientId((currentId) => {
            const stillExists = currentId && fetchedClients.some((c: any) => c.id === currentId);
            if (stillExists) return currentId;
            const savedId = typeof window !== "undefined" ? localStorage.getItem("activeClientId") : null;
            const validSaved = savedId && fetchedClients.some((c: any) => c.id === savedId);
            return validSaved ? savedId : fetchedClients[0].id;
          });
        } else {
          setClients([]);
          setClientId(null);
          setReputationLoading(false);
          setHistoryLoading(false);
          setBreakdownLoading(false);
          setAlertsLoading(false);
          setNarrativesLoading(false);
          setBenchmarksLoading(false);
          setRisksLoading(false);
          setExecutivesLoading(false);
          setSystemStatusLoading(false);
          setDocumentsLoading(false);
          setCommandStatsLoading(false);
          setExecutiveCandidatesLoading(false);
          setCompetitorCandidatesLoading(false);
          setTelemetryLoading(false);
        }
      } catch (e: any) {
        if (e.name !== "AbortError") {
          console.error("Failed to fetch clients", e);
          setClients([]);
          setClientId(null);
          setClientsError(e.message || "Unable to reach the backend");
          setReputationLoading(false);
          setHistoryLoading(false);
          setBreakdownLoading(false);
          setAlertsLoading(false);
          setNarrativesLoading(false);
          setBenchmarksLoading(false);
          setRisksLoading(false);
          setExecutivesLoading(false);
          setSystemStatusLoading(false);
          setDocumentsLoading(false);
          setCommandStatsLoading(false);
          setExecutiveCandidatesLoading(false);
          setCompetitorCandidatesLoading(false);
          setTelemetryLoading(false);
        }
      } finally {
        setClientsLoading(false);
      }
    }
    init();
    return () => controller.abort();
  }, [clientsRefreshKey]);

  const lastClientIdRef = useRef<string | null>(null);
  const activeFetchController = useRef<AbortController | null>(null);

  // Helper to check if state has actually changed to prevent redundant re-renders
  const hasChanged = (prev: any, next: any): boolean => {
    if (prev === next) return false;
    if (prev == null || next == null) return true;
    if (Array.isArray(prev) && Array.isArray(next)) {
      if (prev.length !== next.length) return true;
      return JSON.stringify(prev) !== JSON.stringify(next);
    }
    if (typeof prev === 'object' && typeof next === 'object') {
      return JSON.stringify(prev) !== JSON.stringify(next);
    }
    return prev !== next;
  };

  useEffect(() => {
    if (!clientId) return;
    const activeClientId = clientId;

    const controller = new AbortController();
    activeFetchController.current = controller;
    const signal = controller.signal;

    // Check if client switched. If so, reset data states. Otherwise (on refresh key change), keep cards visible!
    const isClientSwitch = lastClientIdRef.current !== activeClientId;
    if (isClientSwitch) {
      lastClientIdRef.current = activeClientId;
      
      // Clear stale data immediately when switching companies
      setReputation({ score: 0, grade: 'N/A', trend: 'STABLE' });
      setRepHistory([]);
      setRepBreakdown({ sentiment: 0, risk: 0, narrative: 0, trend: 0, source: 0, visibility: 0 });
      setAlerts([]);
      setNarratives([]);
      setBenchmarks([]);
      setRisks({ average_recent_risk_score: 0.0, recent_critical_events: 0, recent_high_events: 0 });
      setExecutives([]);
      setExecHistory({});
      setDocuments([]);
      setTrendEvents([]);
      setSelectedNarrative(null);
      setTelemetry(null);
      setSystemStatus(null);
    }

    // Reset Loading & Error States for Asynchronous Fetching
    setReputationLoading(true);
    setHistoryLoading(true);
    setBreakdownLoading(true);
    setAlertsLoading(true);
    setNarrativesLoading(true);
    setBenchmarksLoading(true);
    setRisksLoading(true);
    setExecutivesLoading(true);
    setExecHistoryLoading(true);
    setSystemStatusLoading(true);
    setDocumentsLoading(true);
    setCommandStatsLoading(true);
    setExecutiveCandidatesLoading(true);
    setCompetitorCandidatesLoading(true);
    setTelemetryLoading(true);

    setReputationError(null);
    setHistoryError(null);
    setBreakdownError(null);
    setAlertsError(null);
    setNarrativesError(null);
    setBenchmarksError(null);
    setRisksError(null);
    setExecutivesError(null);
    setSystemStatusError(null);
    setDocumentsError(null);
    setCommandStatsError(null);
    setExecutiveCandidatesError(null);
    setCompetitorCandidatesError(null);
    setTelemetryError(null);

    // Coordinated Staged/Batched Refreshes
    async function executeCoordinatedRefreshes() {
      // BATCH 1: Critical Telemetry & Pipeline Status Data
      try {
        await Promise.allSettled([
          fetchClientTelemetry(activeClientId, signal)
            .then(data => {
              if (!signal.aborted && hasChanged(telemetry, data)) {
                setTelemetry(data);
              }
            })
            .catch(() => { if (!signal.aborted) { setTelemetry(null); setTelemetryError("Telemetry Offline"); } })
            .finally(() => { if (!signal.aborted) setTelemetryLoading(false); }),
          
          fetchSystemStatus(signal)
            .then(data => {
              if (!signal.aborted && hasChanged(systemStatus, data)) {
                setSystemStatus(data);
              }
            })
            .catch(() => { if (!signal.aborted) { setSystemStatus(null); setSystemStatusError("Telemetry Offline"); } })
            .finally(() => { if (!signal.aborted) setSystemStatusLoading(false); }),

          fetchCommandCenterStats(activeClientId, signal)
            .then(data => {
              if (!signal.aborted) {
                const nextVal = data || {};
                if (hasChanged(commandStats, nextVal)) {
                  setCommandStats(nextVal);
                }
              }
            })
            .catch(() => { if (!signal.aborted) { setCommandStats({}); setCommandStatsError("Telemetry Offline"); } })
            .finally(() => { if (!signal.aborted) setCommandStatsLoading(false); }),
        ]);
      } catch (err) {}

      if (signal.aborted) return;

      // BATCH 2: Core Metrics, Narratives, Risks, Alerts, Benchmarks
      try {
        await Promise.allSettled([
          fetchReputation(activeClientId, signal)
            .then(data => {
              if (!signal.aborted) {
                const nextVal = data || { score: 0, grade: 'N/A', trend: 'STABLE' };
                if (hasChanged(reputation, nextVal)) {
                  setReputation(nextVal);
                }
              }
            })
            .catch(() => { if (!signal.aborted) { setReputation(null); setReputationError("Telemetry Offline"); } })
            .finally(() => { if (!signal.aborted) setReputationLoading(false); }),

          fetchNarratives(activeClientId, signal)
            .then(data => {
              if (!signal.aborted) {
                const seen = new Set<string>();
                const uniqueNarrs = (data || []).filter((n: any) => n && n.id && !seen.has(n.id) && seen.add(n.id));
                if (hasChanged(narratives, uniqueNarrs)) {
                  setNarratives(uniqueNarrs);
                }
              }
            })
            .catch(() => { if (!signal.aborted) { setNarratives([]); setNarrativesError("Telemetry Offline"); } })
            .finally(() => { if (!signal.aborted) setNarrativesLoading(false); }),

          fetchCompetitorBenchmarks(activeClientId, signal)
            .then(data => {
              if (!signal.aborted) {
                if (data && data.length === 1 && data[0].message === "No competitor intelligence available.") {
                  if (hasChanged(benchmarks, [])) {
                    setBenchmarks([]);
                  }
                  return;
                }
                const seen = new Set<string>();
                const uniqueBms = (data || []).filter((b: any) => b && b.competitor_name && !seen.has(b.competitor_name) && seen.add(b.competitor_name));
                uniqueBms.sort((a: any, b: any) => (b.reputation ?? 0) - (a.reputation ?? 0));
                if (hasChanged(benchmarks, uniqueBms)) {
                  setBenchmarks(uniqueBms);
                }
              }
            })
            .catch(() => { if (!signal.aborted) { setBenchmarks([]); setBenchmarksError("Telemetry Offline"); } })
            .finally(() => { if (!signal.aborted) setBenchmarksLoading(false); }),

          fetchExecutives(activeClientId, signal)
            .then(data => {
              if (!signal.aborted) {
                const nextVal = data || [];
                if (hasChanged(executives, nextVal)) {
                  setExecutives(nextVal);
                }
              }
            })
            .catch(() => { if (!signal.aborted) { setExecutives([]); setExecutivesError("Telemetry Offline"); } })
            .finally(() => { if (!signal.aborted) setExecutivesLoading(false); }),

          fetchActiveAlerts(activeClientId, signal)
            .then(data => {
              if (!signal.aborted) {
                const nextVal = data || [];
                if (hasChanged(alerts, nextVal)) {
                  setAlerts(nextVal);
                }
              }
            })
            .catch(() => { if (!signal.aborted) { setAlerts([]); setAlertsError("Telemetry Offline"); } })
            .finally(() => { if (!signal.aborted) setAlertsLoading(false); }),

          fetchRisks(activeClientId, signal)
            .then(data => {
              if (!signal.aborted) {
                const nextVal = data || { average_recent_risk_score: 0.0, recent_critical_events: 0, recent_high_events: 0 };
                if (hasChanged(risks, nextVal)) {
                  setRisks(nextVal);
                }
              }
            })
            .catch(() => { if (!signal.aborted) { setRisks(null); setRisksError("Telemetry Offline"); } })
            .finally(() => { if (!signal.aborted) setRisksLoading(false); }),
        ]);
      } catch (err) {}

      if (signal.aborted) return;

      // BATCH 3: Long-term history, timelines, advice engine, candidates
      try {
        await Promise.allSettled([
          fetchReputationHistory(activeClientId, signal)
            .then(data => {
              if (!signal.aborted) {
                const formattedHist = (data || []).map((h: any) => ({
                  ...h,
                  date: formatChartDate(h.date, true)
                })).reverse();
                if (hasChanged(repHistory, formattedHist)) {
                  setRepHistory(formattedHist);
                }
              }
            })
            .catch(() => { if (!signal.aborted) { setRepHistory([]); setHistoryError("Telemetry Offline"); } })
            .finally(() => { if (!signal.aborted) setHistoryLoading(false); }),

          fetchReputationBreakdown(activeClientId, signal)
            .then(data => {
              if (!signal.aborted) {
                const nextVal = data || { sentiment: 0, risk: 0, narrative: 0, trend: 0, source: 0, visibility: 0 };
                if (hasChanged(repBreakdown, nextVal)) {
                  setRepBreakdown(nextVal);
                }
              }
            })
            .catch(() => { if (!signal.aborted) { setRepBreakdown(null); setBreakdownError("Telemetry Offline"); } })
            .finally(() => { if (!signal.aborted) setBreakdownLoading(false); }),

          fetchDocuments(activeClientId, signal)
            .then(data => {
              if (!signal.aborted) {
                const nextVal = data || [];
                if (hasChanged(documents, nextVal)) {
                  setDocuments(nextVal);
                }
              }
            })
            .catch(() => { if (!signal.aborted) { setDocuments([]); setDocumentsError("Telemetry Offline"); } })
            .finally(() => { if (!signal.aborted) setDocumentsLoading(false); }),

          fetchExecutiveHistory(activeClientId, signal)
            .then(data => {
              if (!signal.aborted) {
                const nextVal = data || {};
                if (hasChanged(execHistory, nextVal)) {
                  setExecHistory(nextVal);
                }
              }
            })
            .catch(() => { if (!signal.aborted) { setExecHistory({}); } })
            .finally(() => { if (!signal.aborted) setExecHistoryLoading(false); }),

          fetchIntelligenceFeed(activeClientId, signal)
            .then(data => {
              if (!signal.aborted) {
                const nextVal = data || [];
                if (hasChanged(trendEvents, nextVal)) {
                  setTrendEvents(nextVal);
                }
              }
            })
            .catch(() => {})
            .finally(() => {}),

          fetchExecutiveCandidates(activeClientId, signal)
            .then(data => {
              if (!signal.aborted) {
                const nextVal = data || [];
                if (hasChanged(executiveCandidates, nextVal)) {
                  setExecutiveCandidates(nextVal);
                }
              }
            })
            .catch(() => { if (!signal.aborted) { setExecutiveCandidates([]); setExecutiveCandidatesError("Discovery Engine Offline"); } })
            .finally(() => { if (!signal.aborted) setExecutiveCandidatesLoading(false); }),

          fetchCompetitorCandidates(activeClientId, signal)
            .then(data => {
              if (!signal.aborted) {
                const nextVal = data || [];
                if (hasChanged(competitorCandidates, nextVal)) {
                  setCompetitorCandidates(nextVal);
                }
              }
            })
            .catch(() => { if (!signal.aborted) { setCompetitorCandidates([]); setCompetitorCandidatesError("Discovery Engine Offline"); } })
            .finally(() => { if (!signal.aborted) setCompetitorCandidatesLoading(false); }),
        ]);
      } catch (err) {}
    }

    executeCoordinatedRefreshes();

    return () => controller.abort();
  }, [clientId, dashboardRefreshKey]);

  // LIVE Refresh Polling Hook
  useEffect(() => {
    if (!clientId) return;
    
    let isActive = true;
    let timeoutId: NodeJS.Timeout;
    let currentController: AbortController | null = null;

    const poll = async () => {
      if (!isActive) return;
      
      currentController = new AbortController();
      const signal = currentController.signal;
      
      try {
        await Promise.allSettled([
          fetchReputation(clientId, signal).then(data => { if (!signal.aborted) setReputation(data); }),
          fetchActiveAlerts(clientId, signal).then(data => { if (!signal.aborted) setAlerts(data || []); }),
          fetchRisks(clientId, signal).then(data => { if (!signal.aborted) setRisks(data || { average_recent_risk_score: 0.0, recent_critical_events: 0, recent_high_events: 0 }); }),
          fetchClientTelemetry(clientId, signal).then(data => { if (!signal.aborted) setTelemetry(data); }), // Poll telemetry
          fetchNarratives(clientId, signal).then(data => { 
            if (!signal.aborted && data) {
              const seen = new Set<string>();
              setNarratives(data.filter((n: any) => { if (n?.id && !seen.has(n.id)) { seen.add(n.id); return true; } return false; }));
            }
          }),
          fetchDocuments(clientId, signal).then(data => { if (!signal.aborted) setDocuments(data || []); }),
          fetchIntelligenceFeed(clientId, signal).then(data => { if (!signal.aborted) setTrendEvents(data || []); }),
          fetchSystemStatus(signal).then(data => { if (!signal.aborted) setSystemStatus(data || { status: 'offline', active_feeds: 0, total_documents_collected: 0, total_documents_matched: 0 }); })
        ]);
      } finally {
        currentController = null;
        if (isActive) {
          timeoutId = setTimeout(poll, 45000); // 45s interval
        }
      }
    };

    timeoutId = setTimeout(poll, 45000);

    return () => {
      isActive = false;
      clearTimeout(timeoutId);
      if (currentController) {
        currentController.abort();
      }
    };
  }, [clientId]);

  const handleSelectCompany = (id: string | null) => {
    // Clear all dashboard data states BEFORE setting loading or clientId
    setReputation(null);
    setRepHistory([]);
    setRepBreakdown(null);
    setAlerts([]);
    setNarratives([]);
    setBenchmarks([]);
    setRisks(null);
    setExecutives([]);
    setExecHistory({});
    setDocuments([]);
    setTrendEvents([]);
    setCommandStats(null);
    setExecutiveCandidates([]);
    setCompetitorCandidates([]);
    setTelemetry(null); // Clear telemetry
    setSystemStatus(null);
    
    // Reset loading states AFTER clearing data
    const isLoading = id !== null;
    setReputationLoading(isLoading);
    setHistoryLoading(isLoading);
    setBreakdownLoading(isLoading);
    setAlertsLoading(isLoading);
    setNarrativesLoading(isLoading);
    setBenchmarksLoading(isLoading);
    setRisksLoading(isLoading);
    setExecutivesLoading(isLoading);
    setExecHistoryLoading(isLoading);
    setDocumentsLoading(isLoading);
    setCommandStatsLoading(isLoading);
    setExecutiveCandidatesLoading(isLoading);
    setCompetitorCandidatesLoading(isLoading);
    setTelemetryLoading(isLoading); // Reset telemetry loading
    setSystemStatusLoading(isLoading);
    
    // Reset error states
    setReputationError(null);
    setHistoryError(null);
    setBreakdownError(null);
    setAlertsError(null);
    setNarrativesError(null);
    setBenchmarksError(null);
    setRisksError(null);
    setExecutivesError(null);
    setDocumentsError(null);
    setCommandStatsError(null);
    setExecutiveCandidatesError(null);
    setCompetitorCandidatesError(null);
    setTelemetryError(null); // Reset telemetry error
    setSystemStatusError(null);
    
    // Set new client ID LAST
    setClientId(id);
    if (typeof window !== "undefined") {
      if (id) {
        localStorage.setItem("activeClientId", id);
      } else {
        localStorage.removeItem("activeClientId");
      }
    }
  };


  return {
    clients,
    clientId,
    clientsLoading,
    clientsError,
    reputation,
    reputationLoading,
    reputationError,
    repHistory,
    historyLoading,
    historyError,
    repBreakdown,
    breakdownLoading,
    breakdownError,
    alerts,
    alertsLoading,
    alertsError,
    narratives,
    narrativesLoading,
    narrativesError,
    benchmarks,
    benchmarksLoading,
    benchmarksError,
    risks,
    risksLoading,
    risksError,
    executives,
    executivesLoading,
    executivesError,
    execHistory,
    execHistoryLoading,
    systemStatus,
    systemStatusLoading,
    systemStatusError,
    documents,
    documentsLoading,
    documentsError,
    trendEvents,
    commandStats,
    commandStatsLoading,
    commandStatsError,
    executiveCandidates,
    executiveCandidatesLoading,
    executiveCandidatesError,
    competitorCandidates,
    competitorCandidatesLoading,
    competitorCandidatesError,
    telemetry,
    telemetryLoading,
    telemetryError,
    selectedNarrative,
    setSelectedNarrative,
    dashboardRefreshKey,
    setDashboardRefreshKey,
    clientsRefreshKey,
    setClientsRefreshKey,
    handleSelectCompany,
    
    setReputation,
    setRepHistory,
    setRepBreakdown,
    setAlerts,
    setNarratives,
    setBenchmarks,
    setRisks,
    setExecutives,
    setExecHistory,
    setDocuments,
    setTrendEvents,
    setTelemetry,
    setReputationLoading,
    setHistoryLoading,
    setBreakdownLoading,
    setAlertsLoading,
    setNarrativesLoading,
    setBenchmarksLoading,
    setRisksLoading,
    setExecutivesLoading,
    setExecHistoryLoading,
    setSystemStatusLoading,
    setDocumentsLoading,
    setCommandStatsLoading,
    setExecutiveCandidatesLoading,
    setCompetitorCandidatesLoading,
    setReputationError,
    setHistoryError,
    setBreakdownError,
    setAlertsError,
    setNarrativesError,
    setBenchmarksError,
    setRisksError,
    setExecutivesError,
    setSystemStatusError,
    setDocumentsError,
    setCommandStatsError,
    setExecutiveCandidatesError,
    setCompetitorCandidatesError,
    setClients,
    setClientId,
    setClientsLoading,
    abortCurrentFetches: () => {
      if (activeFetchController.current) {
        activeFetchController.current.abort();
      }
    }
  };
}
