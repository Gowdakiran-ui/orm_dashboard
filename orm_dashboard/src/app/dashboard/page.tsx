"use client";

import React, { useState, useMemo, useEffect, useCallback } from "react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle, DialogTrigger, DialogFooter } from "@/components/ui/dialog";
import {
  Activity, AlertTriangle, BarChart3, Users, Compass,
  Eye, Play, Loader2, ArrowRight, Search, Plus, Menu
} from "lucide-react";
import Link from 'next/link';

// Fallback / Presentational Components
import { AnalyticsTabHeader } from "@/components/AnalyticsTabHeader";
import { OverviewAnalyticsPanel } from "@/components/OverviewAnalyticsPanel";
import { RiskAnalyticsPanel } from "@/components/RiskAnalyticsPanel";
import { NarrativeAnalyticsPanel } from "@/components/NarrativeAnalyticsPanel";
import { PipelineDiagnosticsPanel } from "@/components/PipelineDiagnosticsPanel";
import { HistoricalCharts } from "@/components/HistoricalCharts";
import { ReputationSummaryCard } from "@/components/ReputationSummaryCard";
import { Sidebar } from "@/components/Sidebar";
import { DashboardHeader } from "@/components/DashboardHeader";
import { TelemetryErrorWidget } from "@/components/TelemetryErrorWidget";
import { ErrorBoundary } from "@/components/ErrorBoundary";

import { NarrativesTab } from "@/components/NarrativesTab";
import { RiskTab } from "@/components/RiskTab";
import { FeedTab } from "@/components/FeedTab";
import { ExecutivesTab } from "@/components/ExecutivesTab";
import { CompetitorsTab } from "@/components/CompetitorsTab";
import { PipelineTab } from "@/components/PipelineTab";
import { AdminUsersPanel } from "@/components/AdminUsersPanel";

// Custom Hooks & Utilities
import { useDashboardData } from "@/hooks/useDashboardData";
import { usePipelineManager } from "@/hooks/usePipelineManager";
import { useExecutiveData } from "@/hooks/useExecutiveData";
import { useCompanyManagement } from "@/hooks/useCompanyManagement";
import { useAnalytics } from "@/hooks/useAnalytics";
import { useCurrentUser } from "@/hooks/useCurrentUser";
import { calculateClientSOV } from "@/utils/shareOfVoice";

export default function Home() {
  const [activeTab, setActiveTab] = useState("reputation");
  const [analyticsSubTab, setAnalyticsSubTab] = useState("overview");
  const [currentTime, setCurrentTime] = useState("");
  const [sidebarOpen, setSidebarOpen] = useState(false);

  useEffect(() => {
    setCurrentTime(new Date().toLocaleTimeString());
    const timer = setInterval(() => {
      setCurrentTime(new Date().toLocaleTimeString());
    }, 1000);
    return () => clearInterval(timer);
  }, []);

  // 1. Data Layer
  const data = useDashboardData();
  const { isSuperAdmin } = useCurrentUser();

  // 2. Pipeline Manager
  // D1: usePipelineManager's polling effect depends on this callback's
  // identity. An inline arrow here would be recreated every render, and
  // this component re-renders every second (the currentTime clock tick
  // above), which tore the poll effect down and rebuilt it before its
  // 2s setTimeout could ever fire. setDashboardRefreshKey is a raw useState
  // setter (stable forever), so useCallback with it as the only dependency
  // gives a permanently stable onComplete.
  const handlePipelineComplete = useCallback(() => {
    data.setDashboardRefreshKey((k) => k + 1);
  }, [data.setDashboardRefreshKey]);
  const pipeline = usePipelineManager(data.clientId, handlePipelineComplete);

  // 3. Executive / Entity Promotion Logic
  const exec = useExecutiveData(data.clientId, () => {
    data.setDashboardRefreshKey((k) => k + 1);
  });

  // 4. Company Management
  const company = useCompanyManagement(
    data.clientId,
    data.clients,
    data.setClientsRefreshKey,
    data.handleSelectCompany,
    data.abortCurrentFetches
  );

  // Client Search filter (UI-only helper)
  const [companySearch, setCompanySearch] = useState("");
  const filteredClients = useMemo(() => 
    data.clients.filter((c: any) => c.name.toLowerCase().includes(companySearch.toLowerCase())),
    [data.clients, companySearch]
  );

  const activeClientName = data.clients.find(c => c.id === data.clientId)?.name || "ORM";
  const highRiskDocs = [...data.documents].sort((a, b) => b.risk - a.risk).slice(0, 5);
  const threatLevel = data.risks?.average_recent_risk_score > 70 ? "CRITICAL" : 
                       data.risks?.average_recent_risk_score > 40 ? "ELEVATED" : "STABLE";

  // Derived Ingestion Telemetry (UI-only helper)
  const derivedPipelineHealth = {
    documents: data.documents.length,
    entity_mentions: data.documents.reduce((acc: any, d: any) => acc + (d.extracted_entities?.length || 0), 0),
    document_topics: data.documents.length,
    document_sentiments: data.documents.length,
    risk_events: (data.risks?.recent_critical_events || 0) + (data.risks?.recent_high_events || 0),
    narratives: data.narratives.length,
    reputation_scores: data.repHistory.length
  };

  // 5. Analytics Transformations
  const analytics = useAnalytics({
    documents: data.documents,
    narratives: data.narratives,
    alerts: data.alerts,
    benchmarks: data.benchmarks,
    reputation: data.reputation,
    risks: data.risks,
    executives: data.executives,
    execHistory: data.execHistory,
    activeClientName,
    trendEvents: data.trendEvents,
    executiveCandidates: data.executiveCandidates,
    competitorCandidates: data.competitorCandidates,
    repHistory: data.repHistory,
    telemetry: data.telemetry
  });

  if (data.clientsLoading) {
    return (
      <div className="flex h-screen w-full flex-col items-center justify-center bg-[#030712] text-[#D4AF37]">
        <div className="relative flex items-center justify-center">
          <div className="h-24 w-24 rounded-full border-t-2 border-b-2 border-[#D4AF37] animate-spin absolute" />
          <Compass className="h-10 w-10 text-[#D4AF37] animate-pulse" />
        </div>
        <p className="text-md font-mono tracking-widest mt-16 text-[#D4AF37] animate-pulse">CONNECTING SECURE SESSION...</p>
      </div>
    );
  }

  return (
    <div className="flex bg-[#030712] text-slate-100 min-h-screen font-sans selection:bg-[#D4AF37] selection:text-[#030712]">

      <Sidebar
        clientId={data.clientId}
        activeTab={activeTab}
        filteredClients={filteredClients}
        companySearch={companySearch}
        threatLevel={threatLevel}
        derivedPipelineHealth={derivedPipelineHealth}
        documentsLoading={data.documentsLoading}
        pipelineRunning={pipeline.pipelineRunning}
        pipelineStatus={pipeline.pipelineStatus}
        lastUpdatedAt={analytics.lastProcessedTimestamp}
        clients={data.clients}
        onSelectCompany={data.handleSelectCompany}
        onSearchChange={setCompanySearch}
        onAddCompanyClick={() => { company.setAddOpen(true); company.setAddError(null); }}
        onDeleteCompanyClick={company.setDeleteTarget}
        onRunPipeline={pipeline.handleRunPipeline}
        onSelectTab={(tab) => { setActiveTab(tab); setSidebarOpen(false); }}
        pipelineError={pipeline.pipelineError}
        isSuperAdmin={isSuperAdmin}
        isOpen={sidebarOpen}
        onClose={() => setSidebarOpen(false)}
      />

      {/* 2. MAIN CONTENT PANEL */}
      <main className="flex-1 flex flex-col min-w-0">

        {/* Mobile top bar — hamburger trigger for the off-canvas sidebar, hidden at md+ */}
        <div className="md:hidden sticky top-0 z-30 flex items-center gap-3 h-14 px-4 border-b border-[#1F2937]/40 bg-[#040812]/90 backdrop-blur-md">
          <button
            onClick={() => setSidebarOpen(true)}
            title="Open Menu"
            aria-label="Open navigation menu"
            className="text-slate-300 hover:text-[#D4AF37] transition-colors"
          >
            <Menu className="h-5 w-5" />
          </button>
          <span className="text-xs font-mono font-extrabold tracking-wider text-slate-200 uppercase truncate">
            ORM Command
          </span>
        </div>

        <DashboardHeader
          activeClientName={activeClientName}
          activeTab={activeTab}
          currentTime={currentTime}
          liveDegraded={data.livePollDegraded}
        />

        {/* Dashboard View Container */}
        <div className="flex-1 space-y-4 p-4 lg:p-6 max-w-[1900px] mx-auto w-full">
          
          {!data.clientId && data.clientsError ? (
            <div className="flex flex-col items-center justify-center min-h-[400px] border border-dashed border-red-500/30 rounded-2xl bg-[#060B18]/30 p-8 text-center font-mono my-8">
              <AlertTriangle className="h-12 w-12 text-red-500/60 opacity-80 mb-4 animate-pulse" />
              <h2 className="text-md uppercase tracking-wider text-red-400 font-bold mb-2">Backend Unreachable</h2>
              <p className="text-xs text-slate-400 max-w-md mx-auto leading-relaxed">
                Could not load the client list from the backend. This is not the empty-account state — the intelligence platform's API did not respond.
              </p>
              <p className="text-[10px] text-slate-500 mt-2">{data.clientsError}</p>
            </div>
          ) : !data.clientId ? (
            <div className="flex flex-col items-center justify-center min-h-[400px] border border-dashed border-[#1F2937]/60 rounded-2xl bg-[#060B18]/30 p-8 text-center font-mono my-8">
              <Compass className="h-12 w-12 text-[#D4AF37]/60 opacity-80 mb-4 animate-pulse" />
              <h2 className="text-md uppercase tracking-wider text-[#D4AF37] font-bold mb-2">No Enterprise Selected</h2>
              <p className="text-xs text-slate-400 max-w-md mx-auto leading-relaxed">
                There are no active corporate entities monitored at the moment. Please select or onboard a company to view the reputation intelligence indices.
              </p>
              <button
                onClick={() => { company.setAddOpen(true); company.setAddError(null); }}
                className="mt-6 px-5 py-2.5 bg-[#D4AF37] hover:bg-[#F3C63F] text-[#030712] font-bold text-xs uppercase tracking-wider rounded-lg transition-colors duration-200 shadow-lg shadow-[#D4AF37]/10"
              >
                Onboard Company
              </button>
            </div>
          ) : (
            <>
              {/* A. REPUTATION INTELLIGENCE VIEW */}
              {activeTab === "reputation" && (
                <div className="space-y-8">
                  
                  {/* Tactical Overview Panels */}
                  <div className="space-y-6">

                    {/* 1. Front Page Highlights: stat-card grid + deterministic digest */}
                    <ErrorBoundary fallback={<TelemetryErrorWidget title="Reputation Summary Error" />}>
                      <ReputationSummaryCard
                        reputationSummaryLoading={data.reputationSummaryLoading}
                        reputationSummaryError={data.reputationSummaryError}
                        reputationSummary={data.reputationSummary}
                        documents={data.documents}
                        narratives={data.narratives}
                        executives={data.executives}
                        clientRank={analytics.clientRank}
                        clientSOV={calculateClientSOV(analytics.normalizedBenchmarks)}
                        activeClientName={activeClientName}
                        normalizedBenchmarks={analytics.normalizedBenchmarks}
                        repHistory={data.repHistory}
                      />
                    </ErrorBoundary>
                  </div>

                  {/* Historical Reputation Trend Chart */}
                  <ErrorBoundary fallback={<TelemetryErrorWidget title="History Chart Error" />}>
                    <HistoricalCharts
                      historyLoading={data.historyLoading}
                      historyError={data.historyError}
                      repHistory={data.repHistory}
                    />
                  </ErrorBoundary>
                </div>
              )}

              {/* B. EXECUTIVE ANALYTICS VIEW */}
              {activeTab === "analytics" && (
                <div className="space-y-6">
                  {/* Analytics Tab Header */}
                  <AnalyticsTabHeader
                    analyticsSubTab={analyticsSubTab}
                    onSelectSubTab={setAnalyticsSubTab}
                  />

                  {/* Sub-tab 1: Overview (Reputation & Sentiment) */}
                  {analyticsSubTab === "overview" && (
                    <ErrorBoundary fallback={<TelemetryErrorWidget title="Overview Analytics Error" />}>
                      <OverviewAnalyticsPanel
                        sentimentDistData={analytics.sentimentDistData}
                        topicDistData={analytics.topicDistData}
                        repHistory={data.repHistory}
                        sentimentTrendData={analytics.sentimentTrendData}
                        loading={data.documentsLoading || data.historyLoading}
                        error={data.documentsError || data.historyError}
                      />
                    </ErrorBoundary>
                  )}

                  {/* Sub-tab 2: Risk & Alerts */}
                  {analyticsSubTab === "risk" && (
                    <ErrorBoundary fallback={<TelemetryErrorWidget title="Risk Analytics Error" />}>
                      <RiskAnalyticsPanel
                        riskMatrixData={analytics.riskMatrixData}
                        alertSeverityData={analytics.alertSeverityData}
                        riskHeatmapData={analytics.riskHeatmapData}
                        alertTimelineData={analytics.alertTimelineData}
                        loading={data.documentsLoading || data.alertsLoading}
                        error={data.documentsError || data.alertsError}
                      />
                    </ErrorBoundary>
                  )}

                  {/* Sub-tab 3: Narratives & Ingestion */}
                  {analyticsSubTab === "narratives" && (
                    <ErrorBoundary fallback={<TelemetryErrorWidget title="Narrative Analytics Error" />}>
                      <NarrativeAnalyticsPanel
                        narrativeBubbleData={analytics.narrativeBubbleData}
                        competitorRadarData={analytics.competitorRadarData}
                        execTrendChartData={analytics.execTrendChartData}
                        pipelineTimelineData={analytics.pipelineTimelineData}
                        sourceContData={analytics.sourceContData}
                        activeClientName={activeClientName}
                        normalizedBenchmarks={analytics.normalizedBenchmarks}
                        execHistory={data.execHistory}
                        documents={data.documents}
                        loading={data.narrativesLoading || data.benchmarksLoading || data.documentsLoading}
                        error={data.narrativesError || data.benchmarksError || data.documentsError}
                      />
                    </ErrorBoundary>
                  )}

                  {/* Sub-tab 4: AI Ingestion Pipeline Diagnostics */}
                  {analyticsSubTab === "pipeline" && (
                    <ErrorBoundary fallback={<TelemetryErrorWidget title="Pipeline Diagnostics Error" />}>
                      <PipelineDiagnosticsPanel
                        pipelineDiagnostics={analytics.engineDiagnosticsList}
                        documents={data.documents}
                        lastProcessedTimestamp={data.systemStatus?.last_processed_timestamp || ""}
                        loading={data.documentsLoading || data.telemetryLoading || data.alertsLoading || data.narrativesLoading}
                        error={data.documentsError || data.telemetryError || data.alertsError || data.narrativesError}
                      />
                    </ErrorBoundary>
                  )}
                </div>
              )}

              {/* C. RISK CENTER VIEW */}
              {activeTab === "risk" && (
                <ErrorBoundary fallback={<TelemetryErrorWidget title="Risk Center Error" />}>
                  <RiskTab
                    alertsLoading={data.alertsLoading}
                    alertsError={data.alertsError}
                    alerts={data.alerts}
                    documentsLoading={data.documentsLoading}
                    documentsError={data.documentsError}
                    documents={data.documents}
                    clientId={data.clientId}
                  />
                </ErrorBoundary>
              )}

              {/* D. COMPETITOR COMPARE VIEW */}
              {activeTab === "competitors" && (
                <ErrorBoundary fallback={<TelemetryErrorWidget title="Competitor Compare Error" />}>
                  <CompetitorsTab
                    benchmarksLoading={data.benchmarksLoading}
                    benchmarksError={data.benchmarksError}
                    benchmarks={data.benchmarks}
                    competitorRadarData={analytics.competitorRadarData}
                    activeClientName={activeClientName}
                    normalizedBenchmarks={analytics.normalizedBenchmarks}
                    reputation={data.reputation}
                    repBreakdown={data.repBreakdown}
                    clientRank={analytics.clientRank}
                    documents={data.documents}
                    clientId={data.clientId}
                    competitorCandidates={data.competitorCandidates}
                    onPromoteCompetitors={exec.handlePromoteCompetitors}
                    promotingCompetitors={exec.promotingCompetitors}
                  />
                </ErrorBoundary>
              )}

              {/* E. EXECUTIVE REPUTATION VIEW */}
              {activeTab === "executives" && (
                <ErrorBoundary fallback={<TelemetryErrorWidget title="Executive Reputation Error" />}>
                  <ExecutivesTab
                    execHistoryLoading={data.execHistoryLoading}
                    execHistory={data.execHistory}
                    execTrendChartData={analytics.execTrendChartData}
                    executivesLoading={data.executivesLoading}
                    executivesError={data.executivesError}
                    executives={data.executives}
                    lastProcessedTimestamp={data.systemStatus?.last_processed_timestamp || ""}
                    documents={data.documents}
                    narratives={data.narratives}
                    clientId={data.clientId}
                    executiveCandidates={data.executiveCandidates}
                    onPromoteExecutives={exec.handlePromoteExecutives}
                    promotingExecutives={exec.promotingExecutives}
                  />
                </ErrorBoundary>
              )}

              {/* F. NARRATIVE CLUSTER VIEW */}
              {activeTab === "narratives" && (
                <ErrorBoundary fallback={<TelemetryErrorWidget title="Narrative Cluster Error" />}>
                  <NarrativesTab
                    documentsLoading={data.documentsLoading}
                    executivesLoading={data.executivesLoading}
                    narrativesLoading={data.narrativesLoading}
                    documents={data.documents}
                    executives={data.executives}
                    narratives={data.narratives}
                    activeClientName={activeClientName}
                    selectedNarrative={data.selectedNarrative}
                    setSelectedNarrative={data.setSelectedNarrative}
                    narrativesError={data.narrativesError}
                    clientId={data.clientId}
                  />
                </ErrorBoundary>
              )}

              {/* G. INTELLIGENCE STREAM VIEW */}
              {activeTab === "feed" && (
                <ErrorBoundary fallback={<TelemetryErrorWidget title="Intelligence Stream Error" />}>
                  <FeedTab
                    documentsLoading={data.documentsLoading}
                    documentsError={data.documentsError}
                    documents={data.documents}
                    narratives={data.narratives}
                    executives={data.executives}
                    systemStatus={data.systemStatus}
                    clientId={data.clientId}
                  />
                </ErrorBoundary>
              )}

              {/* H. AI PIPELINE HEALTH VIEW */}
              {activeTab === "pipeline" && (
                <ErrorBoundary fallback={<TelemetryErrorWidget title="Pipeline Health Error" />}>
                  <PipelineTab
                    commandStats={data.commandStats}
                    documents={data.documents}
                    trendEvents={data.trendEvents}
                    alerts={data.alerts}
                    narratives={data.narratives}
                    repHistory={data.repHistory}
                    executives={data.executives}
                    benchmarks={data.benchmarks}
                    engineDiagnosticsList={analytics.engineDiagnosticsList}
                    onSelectTab={setActiveTab}
                  />
                </ErrorBoundary>
              )}

              {/* I. ACCESS CONTROL VIEW (super_admin only) */}
              {activeTab === "admin" && isSuperAdmin && (
                <ErrorBoundary fallback={<TelemetryErrorWidget title="User Management Error" />}>
                  <AdminUsersPanel />
                </ErrorBoundary>
              )}
            </>
          )}

        </div>
      </main>

      {/* Onboarding / Onboarding Client Form Dialog */}
      <Dialog open={company.addOpen} onOpenChange={company.setAddOpen}>
        <DialogContent className="bg-[#060B18] border-[#1F2937] text-slate-100">
          <DialogHeader>
            <DialogTitle className="font-mono text-[#D4AF37]">Onboard Target Enterprise</DialogTitle>
            <DialogDescription className="text-slate-400 font-mono text-xs">
              Initialize real-time intelligence feeds and narrative modeling for a new corporate entity.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4 py-4 font-mono text-xs">
            <div className="space-y-2">
              <label className="text-slate-400">Enterprise Name</label>
              <input
                type="text"
                placeholder="e.g. Acme Corp"
                value={company.addName}
                onChange={(e) => company.setAddName(e.target.value)}
                className="w-full bg-[#030712] border border-[#1F2937] rounded px-3 py-2 text-slate-100 focus:outline-none focus:border-[#D4AF37]"
              />
            </div>
            <div className="space-y-2">
              <label className="text-slate-400">Industry / Sector</label>
              <input
                type="text"
                placeholder="e.g. Technology"
                value={company.addIndustry}
                onChange={(e) => company.setAddIndustry(e.target.value)}
                className="w-full bg-[#030712] border border-[#1F2937] rounded px-3 py-2 text-slate-100 focus:outline-none focus:border-[#D4AF37]"
              />
            </div>
            {company.addError && (
              <p className="text-red-500 text-[11px]">{company.addError}</p>
            )}
          </div>
          <DialogFooter>
            <button
              onClick={() => company.setAddOpen(false)}
              className="font-mono text-xs px-4 py-2 text-slate-400 hover:text-slate-200"
            >
              Cancel
            </button>
            <button
              onClick={company.handleAddCompany}
              disabled={company.addLoading}
              className="bg-[#D4AF37] text-black font-bold font-mono text-xs px-4 py-2 rounded disabled:opacity-50"
            >
              {company.addLoading ? "Initializing..." : "Start Onboarding"}
            </button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Delete Confirmation Dialog */}
      <Dialog open={company.deleteTarget !== null} onOpenChange={(open) => { if (!open) { company.setDeleteTarget(null); company.setDeleteError(null); } }}>
        <DialogContent className="bg-[#060B18] border-[#1F2937] text-slate-100">
          <DialogHeader>
            <DialogTitle className="font-mono text-red-500">Decommission Enterprise Telemetry</DialogTitle>
            <DialogDescription className="text-slate-400 font-mono text-xs">
              Are you sure you want to stop all active crawling, index tables, and narrative calculations for{" "}
              <span className="text-slate-200 font-bold">{company.deleteTarget?.name}</span>? This action is permanent and deletes all historical indices.
            </DialogDescription>
          </DialogHeader>
          {company.deleteError && (
            <p className="text-red-500 text-[11px]">{company.deleteError}</p>
          )}
          <DialogFooter>
            <button
              onClick={() => { company.setDeleteTarget(null); company.setDeleteError(null); }}
              className="font-mono text-xs px-4 py-2 text-slate-300 hover:text-white"
            >
              Cancel
            </button>
            <button
              onClick={company.handleDeleteCompany}
              disabled={company.deleteLoading}
              className="bg-red-600 text-white hover:bg-red-700 font-mono text-xs px-4 py-2 rounded-md disabled:opacity-50"
            >
              {company.deleteLoading ? "Deleting..." : "Delete"}
            </button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
