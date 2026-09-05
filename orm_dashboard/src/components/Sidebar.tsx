import React from "react";
import { useRouter } from "next/navigation";
import {
  Shield, Search, Plus, Trash2, Loader2, Play, Radio, Award,
  ShieldAlert, Users, BarChart3, LineChart, FileText, Cpu, Server,
  BarChart as BarChartIcon, LogOut, ShieldCheck, X
} from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { logout } from "@/lib/api";
import { useTheme } from "@/components/theme/ThemeProvider";
import { ThemeToggle } from "@/components/theme/ThemeToggle";
import { glassPill, GRADIENT_HEADING_CLASS, gradientHeadingStyle, mutedText, bodyText } from "@/components/theme/tokens";

export interface SidebarProps {
  clientId: string | null;
  activeTab: string;
  filteredClients: any[];
  companySearch: string;
  threatLevel: string;
  derivedPipelineHealth: { documents: number; entity_mentions: number };
  documentsLoading: boolean;
  pipelineRunning: boolean;
  pipelineStatus?: string;
  lastUpdatedAt?: string;
  clients: any[];
  onSelectCompany: (id: string) => void;
  onSearchChange: (val: string) => void;
  onAddCompanyClick: () => void;
  onDeleteCompanyClick: (client: any) => void;
  onRunPipeline: () => void;
  onSelectTab: (tab: string) => void;
  pipelineError?: string | null;
  isSuperAdmin?: boolean;
  isOpen?: boolean;
  onClose?: () => void;
}

export function Sidebar({
  clientId,
  activeTab,
  filteredClients,
  companySearch,
  threatLevel,
  derivedPipelineHealth,
  documentsLoading,
  pipelineRunning,
  pipelineStatus,
  lastUpdatedAt,
  clients,
  onSelectCompany,
  onSearchChange,
  onAddCompanyClick,
  onDeleteCompanyClick,
  onRunPipeline,
  onSelectTab,
  pipelineError,
  isSuperAdmin,
  isOpen = false,
  onClose
}: SidebarProps) {
  const router = useRouter();
  const { theme } = useTheme();
  const isDark = theme === "dark";

  async function handleLogout() {
    await logout();
    router.push("/login");
    router.refresh();
  }

  return (
    <>
      {/* Mobile backdrop — dims content and closes the drawer on tap */}
      {isOpen && (
        <div
          className="fixed inset-0 z-40 bg-black/60 md:hidden"
          onClick={onClose}
          aria-hidden="true"
        />
      )}

      <aside
        className={`fixed inset-y-0 left-0 w-80 backdrop-blur-2xl flex flex-col justify-between h-screen z-50 shrink-0 transform transition-transform duration-300 ease-in-out border-r ${
          isDark ? "border-white/[0.12] bg-zinc-900/60" : "border-white/70 bg-white/60"
        } ${
          isOpen ? "translate-x-0" : "-translate-x-full"
        } md:translate-x-0 md:sticky md:top-0`}
      >
      <div className="flex flex-col h-full overflow-y-auto no-scrollbar">

        {/* Logo Section */}
        <div className={`p-6 border-b flex items-center space-x-3 ${isDark ? "border-white/[0.12]" : "border-black/[0.06]"}`}>
          <div className={`p-2 rounded-lg border ${isDark ? "bg-[#00F5D4]/10 border-[#00F5D4]/30 text-[#00F5D4]" : "bg-[#3B82F6]/10 border-[#3B82F6]/30 text-[#3B82F6]"}`}>
            <Shield className="h-6 w-6" />
          </div>
          <div className="flex-1">
            <h1 className={`text-md font-mono font-extrabold tracking-wider uppercase ${GRADIENT_HEADING_CLASS}`} style={gradientHeadingStyle(theme)}>
              ORM COMMAND
            </h1>
            <p className={`text-[10px] font-mono uppercase tracking-widest ${mutedText(theme)}`}>
              AI Threat Shield v1.2
            </p>
          </div>
          <ThemeToggle />
          <button
            onClick={onClose}
            title="Close Menu"
            aria-label="Close navigation menu"
            className={`md:hidden transition-colors ${isDark ? "text-zinc-500 hover:text-zinc-200" : "text-zinc-400 hover:text-zinc-700"}`}
          >
            <X className="h-4 w-4" />
          </button>
          <button
            onClick={handleLogout}
            title="Sign Out"
            className={`transition-colors ${isDark ? "text-zinc-500 hover:text-red-400" : "text-zinc-400 hover:text-red-500"}`}
          >
            <LogOut className="h-4 w-4" />
          </button>
        </div>

        {/* Client Control */}
        <div className={`p-4 border-b space-y-3 ${isDark ? "border-white/[0.12]" : "border-black/[0.06]"}`}>
          <label className={`text-[10px] font-mono uppercase tracking-wider block ${mutedText(theme)}`}>Target Enterprise</label>
          <div className="space-y-2">
            <select
              value={clientId || ''}
              onChange={(e) => onSelectCompany(e.target.value)}
              className={`w-full px-2 py-1.5 rounded-md text-sm font-mono focus:outline-none focus:ring-1 ${
                isDark
                  ? "border border-white/[0.12] bg-zinc-900/70 text-zinc-100 focus:ring-[#00F5D4]"
                  : "border border-black/[0.06] bg-white/70 text-zinc-900 focus:ring-[#3B82F6]"
              }`}
            >
              {filteredClients.map((c: any) => (
                <option key={c.id} value={c.id}>{c.name}</option>
              ))}
            </select>

            <div className="relative">
              <Search className={`absolute left-2 top-1/2 -translate-y-1/2 h-3 w-3 ${mutedText(theme)}`} />
              <input
                type="text"
                placeholder="Search..."
                value={companySearch}
                onChange={(e) => onSearchChange(e.target.value)}
                className={`w-full pl-7 pr-2 py-1.5 rounded-md text-xs font-mono focus:outline-none focus:ring-1 ${
                  isDark
                    ? "border border-white/[0.12] bg-zinc-900/50 text-zinc-100 focus:ring-[#00F5D4]"
                    : "border border-black/[0.06] bg-white/50 text-zinc-900 focus:ring-[#3B82F6]"
                }`}
              />
            </div>
          </div>

          <div className={`flex justify-between items-center pt-1 border-t ${isDark ? "border-white/[0.12]" : "border-black/[0.06]"}`}>
            <button
              onClick={onAddCompanyClick}
              className={`flex items-center text-[10px] font-mono transition-colors ${isDark ? "text-[#00F5D4] hover:text-[#00F5D4]/80" : "text-[#3B82F6] hover:text-[#3B82F6]/80"}`}
              title="Add Company"
            >
              <Plus className="h-3 w-3 mr-1" /> Add
            </button>
            <button
              onClick={() => onDeleteCompanyClick(clients.find((c: any) => c.id === clientId))}
              className="flex items-center text-[10px] font-mono text-red-400 hover:text-red-300 transition-colors"
              title="Delete Company"
            >
              <Trash2 className="h-3 w-3 mr-1" /> Delete
            </button>
            <button
              onClick={onRunPipeline}
              disabled={pipelineRunning}
              className={`flex items-center text-[10px] font-mono disabled:opacity-50 transition-colors ${isDark ? "text-[#7B2CBF] hover:text-[#7B2CBF]/80" : "text-[#8B5CF6] hover:text-[#8B5CF6]/80"}`}
              title="Run Pipeline"
            >
              {pipelineRunning ? <Loader2 className="h-3 w-3 mr-1 animate-spin" /> : <Play className="h-3 w-3 mr-1" />}
              {pipelineRunning
                ? (pipelineStatus === "queued" ? "Queued (waiting for a worker)..." : "Running Pipeline...")
                : "Run Pipeline"}
            </button>
          </div>
          {pipelineError && (
            <div className="mt-2 text-xs text-red-500 font-mono bg-red-500/10 p-2 rounded border border-red-500/20 break-words">
              {pipelineError}
            </div>
          )}
          {/* Phase 15: collection/processing is now Run-Pipeline-gated, not
              continuous -- these numbers only move when this button is
              clicked. Without this, a frozen number between runs reads as
              broken rather than as the intended behavior. */}
          {!pipelineRunning && (
            <div className={`mt-2 text-[10px] font-mono ${mutedText(theme)}`} title="Data only updates when Run Pipeline is triggered">
              {lastUpdatedAt && lastUpdatedAt !== "N/A"
                ? <>Last updated: {lastUpdatedAt} — click Run Pipeline for fresh data</>
                : <>No data yet — click Run Pipeline to collect and process</>}
            </div>
          )}
        </div>

        {/* Threat Indicator */}
        <div className={`p-6 border-b space-y-2 ${isDark ? "border-white/[0.12]" : "border-black/[0.06]"}`}>
          <span className="text-[10px] font-mono text-slate-400 uppercase tracking-wider block">Active Threat Level</span>
          <div className={`flex items-center space-x-3 p-3 rounded-lg border ${
            threatLevel === "CRITICAL" ? "bg-red-950/20 border-red-500/30 text-red-400" :
            threatLevel === "ELEVATED" ? "bg-orange-950/20 border-orange-500/30 text-orange-400" :
            "bg-emerald-950/20 border-emerald-500/30 text-emerald-400"
          }`}>
            <Radio className="h-4 w-4 animate-pulse" />
            <span className="font-mono text-xs font-bold tracking-widest">{threatLevel}</span>
          </div>
        </div>

        {/* Navigation Links */}
        <div className="flex-1 p-4 space-y-1">
          <span className={`text-[10px] font-mono uppercase tracking-wider px-2 block mb-2 ${mutedText(theme)}`}>Systems Menu</span>
          {[
            { id: "reputation", label: "Brand Equity", icon: Award },
            { id: "risk", label: "Risk Center", icon: ShieldAlert },
            { id: "competitors", label: "Competitor Compare", icon: BarChart3 },
            { id: "executives", label: "Executive Reputation", icon: Users },
            { id: "analytics", label: "Executive Analytics", icon: BarChartIcon },
            { id: "narratives", label: "Narrative Cluster", icon: LineChart },
            { id: "feed", label: "Intelligence Stream", icon: FileText },
            { id: "pipeline", label: "AI Pipeline Health", icon: Cpu },
            ...(isSuperAdmin ? [{ id: "admin", label: "Access Control", icon: ShieldCheck }] : [])
          ].map(tab => {
            const Icon = tab.icon;
            const isActive = activeTab === tab.id;
            const activeClass = isDark
              ? "bg-[#00F5D4]/5 border-l-2 border-l-[#00F5D4] border-y-transparent border-r-transparent text-[#00F5D4]"
              : "bg-[#3B82F6]/5 border-l-2 border-l-[#3B82F6] border-y-transparent border-r-transparent text-[#3B82F6]";
            const inactiveClass = isDark
              ? "text-zinc-400 hover:text-zinc-200 hover:bg-white/[0.04] border-l-2 border-l-transparent"
              : "text-zinc-500 hover:text-zinc-800 hover:bg-black/[0.03] border-l-2 border-l-transparent";
            return (
              <button
                key={tab.id}
                onClick={() => onSelectTab(tab.id)}
                className={`w-full flex items-center space-x-3 px-3 py-2.5 rounded-md text-xs font-mono transition-all duration-300 relative ${
                  isActive ? activeClass : inactiveClass
                }`}
              >
                <Icon className={`h-4 w-4 ${isActive ? "" : mutedText(theme)}`} style={isActive ? { color: isDark ? "#00F5D4" : "#3B82F6" } : undefined} />
                <span>{tab.label}</span>
              </button>
            );
          })}
        </div>
      </div>

      {/* Live Telemetry Ingestion Stats */}
      <div className={`p-4 border-t ${isDark ? "border-white/[0.12] bg-black/20" : "border-black/[0.06] bg-white/40"}`}>
        <div className="flex items-center justify-between mb-2">
          <span className={`text-[9px] font-mono uppercase tracking-wider ${isDark ? "text-[#00F5D4]" : "text-[#3B82F6]"}`}>Live Ingestion Telemetry</span>
          <div className="h-1.5 w-1.5 rounded-full bg-emerald-500 animate-ping" />
        </div>
        <div className={`grid grid-cols-2 gap-2 text-[10px] font-mono ${mutedText(theme)}`}>
          <div className={glassPill(theme) + " p-2"}>
            <span className={`block text-[8px] ${mutedText(theme)}`}>DOCS</span>
            <span className={`font-bold ${bodyText(theme)}`}>
              {documentsLoading ? "..." : derivedPipelineHealth.documents}
            </span>
          </div>
          <div className={glassPill(theme) + " p-2"}>
            <span className={`block text-[8px] ${mutedText(theme)}`}>ENTITIES</span>
            <span className={`font-bold ${bodyText(theme)}`}>
              {documentsLoading ? "..." : derivedPipelineHealth.entity_mentions}
            </span>
          </div>
        </div>
      </div>
      </aside>
    </>
  );
}
