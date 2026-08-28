import React from "react";
import { useRouter } from "next/navigation";
import {
  Shield, Search, Plus, Trash2, Loader2, Play, Radio, Award,
  ShieldAlert, Users, BarChart3, LineChart, FileText, Cpu, Server,
  BarChart as BarChartIcon, LogOut, ShieldCheck, X
} from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { logout } from "@/lib/api";

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
        className={`fixed inset-y-0 left-0 w-80 border-r border-[#1F2937]/40 bg-[#060B18]/95 backdrop-blur-md flex flex-col justify-between h-screen z-50 shrink-0 transform transition-transform duration-300 ease-in-out ${
          isOpen ? "translate-x-0" : "-translate-x-full"
        } md:translate-x-0 md:sticky md:top-0`}
      >
      <div className="flex flex-col h-full overflow-y-auto no-scrollbar">

        {/* Logo Section */}
        <div className="p-6 border-b border-[#1F2937]/40 flex items-center space-x-3">
          <div className="bg-[#D4AF37]/10 p-2 rounded-lg border border-[#D4AF37]/30 text-[#D4AF37] shadow-[0_0_15px_rgba(212,175,55,0.15)]">
            <Shield className="h-6 w-6" />
          </div>
          <div className="flex-1">
            <h1 className="text-md font-mono font-extrabold tracking-wider text-slate-100 uppercase">
              ORM COMMAND
            </h1>
            <p className="text-[10px] font-mono text-[#D4AF37] uppercase tracking-widest">
              AI Threat Shield v1.2
            </p>
          </div>
          <button
            onClick={onClose}
            title="Close Menu"
            aria-label="Close navigation menu"
            className="md:hidden text-slate-500 hover:text-slate-200 transition-colors"
          >
            <X className="h-4 w-4" />
          </button>
          <button
            onClick={handleLogout}
            title="Sign Out"
            className="text-slate-500 hover:text-red-400 transition-colors"
          >
            <LogOut className="h-4 w-4" />
          </button>
        </div>

        {/* Client Control */}
        <div className="p-4 border-b border-[#1F2937]/40 space-y-3">
          <label className="text-[10px] font-mono text-slate-400 uppercase tracking-wider block">Target Enterprise</label>
          <div className="space-y-2">
            <select 
              value={clientId || ''} 
              onChange={(e) => onSelectCompany(e.target.value)}
              className="w-full px-2 py-1.5 border border-[#1F2937] rounded-md text-sm bg-[#030712] text-slate-100 focus:outline-none focus:ring-1 focus:ring-[#D4AF37] font-mono"
            >
              {filteredClients.map((c: any) => (
                <option key={c.id} value={c.id}>{c.name}</option>
              ))}
            </select>
            
            <div className="relative">
              <Search className="absolute left-2 top-1/2 -translate-y-1/2 h-3 w-3 text-slate-500" />
              <input
                type="text"
                placeholder="Search..."
                value={companySearch}
                onChange={(e) => onSearchChange(e.target.value)}
                className="w-full pl-7 pr-2 py-1.5 border border-[#1F2937] rounded-md text-xs bg-[#060B18] text-slate-100 focus:outline-none focus:ring-1 focus:ring-[#D4AF37] font-mono"
              />
            </div>
          </div>
          
          <div className="flex justify-between items-center pt-1 border-t border-[#1F2937]/40">
            <button
              onClick={onAddCompanyClick}
              className="flex items-center text-[10px] font-mono text-[#D4AF37] hover:text-[#D4AF37]/80 transition-colors"
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
              className="flex items-center text-[10px] font-mono text-[#38BDF8] hover:text-[#38BDF8]/80 disabled:opacity-50 transition-colors"
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
        </div>

        {/* Threat Indicator */}
        <div className="p-6 border-b border-[#1F2937]/40 space-y-2">
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
          <span className="text-[10px] font-mono text-slate-500 uppercase tracking-wider px-2 block mb-2">Systems Menu</span>
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
            return (
              <button
                key={tab.id}
                onClick={() => onSelectTab(tab.id)}
                className={`w-full flex items-center space-x-3 px-3 py-2.5 rounded-md text-xs font-mono transition-all duration-300 relative ${
                  isActive 
                    ? "bg-[#D4AF37]/5 border-l-2 border-l-[#D4AF37] border-y-transparent border-r-transparent text-[#D4AF37] shadow-[0_0_15px_rgba(212,175,55,0.05)]" 
                    : "text-slate-400 hover:text-slate-200 hover:bg-[#1F2937]/10 border-l-2 border-l-transparent"
                }`}
              >
                <Icon className={`h-4 w-4 ${isActive ? "text-[#D4AF37]" : "text-slate-400"}`} />
                <span>{tab.label}</span>
              </button>
            );
          })}
        </div>
      </div>

      {/* Live Telemetry Ingestion Stats */}
      <div className="p-4 border-t border-[#1F2937]/40 bg-[#040811]">
        <div className="flex items-center justify-between mb-2">
          <span className="text-[9px] font-mono text-[#D4AF37] uppercase tracking-wider">Live Ingestion Telemetry</span>
          <div className="h-1.5 w-1.5 rounded-full bg-emerald-500 animate-ping" />
        </div>
        <div className="grid grid-cols-2 gap-2 text-[10px] font-mono text-slate-400">
          <div className="bg-[#030712] p-2 rounded border border-[#1F2937]/40">
            <span className="block text-[8px] text-slate-500">DOCS</span>
            <span className="font-bold text-slate-200">
              {documentsLoading ? "..." : derivedPipelineHealth.documents}
            </span>
          </div>
          <div className="bg-[#030712] p-2 rounded border border-[#1F2937]/40">
            <span className="block text-[8px] text-slate-500">ENTITIES</span>
            <span className="font-bold text-slate-200">
              {documentsLoading ? "..." : derivedPipelineHealth.entity_mentions}
            </span>
          </div>
        </div>
      </div>
      </aside>
    </>
  );
}
