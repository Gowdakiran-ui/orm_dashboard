"use client";

import React, { useState, useRef, useEffect, useCallback } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { UploadCloud, ScanSearch, Loader2, ShieldAlert, ShieldCheck } from "lucide-react";
import { useTheme, type Theme } from "@/components/theme/ThemeProvider";
import { glassCard, mutedText, bodyText, SPECULAR_LINE, glassPrimaryButton } from "@/components/theme/tokens";
import {
  submitDeepfakeScan,
  submitDomainScan,
  fetchCounterfeitScan,
} from "@/lib/api";

export interface CounterfeitDetectionTabProps {
  clientId?: string | null;
}

const SUPPORTED_IMAGE_TYPES = ["image/jpeg", "image/png", "image/gif", "image/webp"];
const POLL_INTERVAL_MS = 2000;

// Same red/orange/yellow/teal severity convention as RiskTab.tsx's alert
// badges -- reused here, not reinvented, per the brief's "no new visual
// style" requirement.
function severityBadgeClass(isDark: boolean, tier: "critical" | "high" | "low" | "neutral"): string {
  if (tier === "critical") return "bg-red-500/10 text-red-500 border border-red-500/20";
  if (tier === "high") return "bg-orange-500/10 text-orange-500 border border-orange-500/20";
  if (tier === "low") return "bg-teal-500/10 text-teal-500 border border-teal-500/20";
  return isDark ? "bg-zinc-500/10 text-zinc-400 border border-zinc-500/20" : "bg-zinc-500/10 text-zinc-500 border border-zinc-500/20";
}

function deepfakeVerdictTier(verdict: string | undefined): "critical" | "high" | "low" | "neutral" {
  if (verdict === "FAKE") return "critical";
  if (verdict === "SUSPICIOUS") return "high";
  if (verdict === "AUTHENTIC") return "low";
  return "neutral";
}

// Polls GET /counterfeit/scans/{scanId} every POLL_INTERVAL_MS until the
// scan reaches COMPLETE/FAILED. Same "DB row is the source of truth"
// convention as usePipelineManager.ts, simplified (fixed interval, no
// backoff) since this is a single short-lived on-demand scan, not a
// multi-minute pipeline run.
function usePollScan(clientId: string | null | undefined) {
  const [scan, setScan] = useState<any | null>(null);
  const [polling, setPolling] = useState(false);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const unmountedRef = useRef(false);

  useEffect(() => {
    unmountedRef.current = false;
    return () => {
      unmountedRef.current = true;
      if (timerRef.current) clearTimeout(timerRef.current);
    };
  }, []);

  const start = useCallback((scanId: string) => {
    if (!clientId) return;
    setPolling(true);
    setScan(null);

    const poll = async () => {
      if (unmountedRef.current) return;
      try {
        const status = await fetchCounterfeitScan(clientId, scanId);
        if (unmountedRef.current) return;
        setScan(status);
        if (status.status === "COMPLETE" || status.status === "FAILED") {
          setPolling(false);
          return;
        }
      } catch {
        // Transient poll failure -- keep trying, same as pipeline polling's
        // tolerance for a dropped request; the scan row itself is unaffected.
      }
      if (!unmountedRef.current) {
        timerRef.current = setTimeout(poll, POLL_INTERVAL_MS);
      }
    };
    poll();
  }, [clientId]);

  return { scan, polling, start };
}

export function CounterfeitDetectionTab({ clientId }: CounterfeitDetectionTabProps) {
  const { theme } = useTheme();
  const isDark = theme === "dark";
  const accent = isDark ? "#00F5D4" : "#3B82F6";

  return (
    <div className="grid gap-6 md:grid-cols-2">
      <DeepfakePanel clientId={clientId} theme={theme} isDark={isDark} accent={accent} />
      <DomainScanPanel clientId={clientId} theme={theme} isDark={isDark} accent={accent} />
    </div>
  );
}

// ---------------------------------------------------------------------
// Panel 1 — Deepfake Detection (Reality Defender)
// ---------------------------------------------------------------------

function DeepfakePanel({ clientId, theme, isDark, accent }: { clientId?: string | null; theme: Theme; isDark: boolean; accent: string }) {
  const [file, setFile] = useState<File | null>(null);
  const [dragOver, setDragOver] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const { scan, polling, start } = usePollScan(clientId);

  const pickFile = (f: File | undefined | null) => {
    setSubmitError(null);
    if (!f) return;
    if (!SUPPORTED_IMAGE_TYPES.includes(f.type)) {
      setSubmitError(`Unsupported file type '${f.type || "unknown"}'. Use JPEG, PNG, GIF, or WEBP.`);
      return;
    }
    if (f.size > 50 * 1024 * 1024) {
      setSubmitError("Image exceeds the 50MB size limit.");
      return;
    }
    setFile(f);
  };

  const handleScan = async () => {
    if (!file || !clientId) return;
    setSubmitting(true);
    setSubmitError(null);
    try {
      const res = await submitDeepfakeScan(clientId, file);
      start(res.scan_id);
    } catch (err: any) {
      setSubmitError(err?.message || "Failed to start scan.");
    } finally {
      setSubmitting(false);
    }
  };

  const busy = submitting || polling;

  return (
    <Card className={glassCard(theme)}>
      <div className={SPECULAR_LINE} />
      <CardHeader className={`pb-3 border-b ${isDark ? "border-white/[0.12]" : "border-black/[0.06]"}`}>
        <CardTitle className={`text-xs uppercase tracking-wider ${mutedText(theme)} flex items-center`}>
          <ScanSearch className="h-4 w-4 mr-2" style={{ color: accent }} />
          Deepfake Detection
        </CardTitle>
      </CardHeader>
      <CardContent className="pt-4 space-y-4">
        <p className={`text-xs ${mutedText(theme)}`}>
          Upload an image to check for AI manipulation.
        </p>

        <label
          onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
          onDragLeave={() => setDragOver(false)}
          onDrop={(e) => { e.preventDefault(); setDragOver(false); pickFile(e.dataTransfer.files?.[0]); }}
          className={`flex flex-col items-center justify-center gap-2 rounded-lg border border-dashed px-4 py-8 min-h-[110px] cursor-pointer text-center transition-colors ${
            dragOver ? (isDark ? "border-[#00F5D4]/60 bg-[#00F5D4]/5" : "border-[#3B82F6]/60 bg-[#3B82F6]/5")
                     : (isDark ? "border-white/[0.15] hover:border-white/[0.3]" : "border-black/[0.12] hover:border-black/[0.25]")
          }`}
        >
          <UploadCloud className="h-6 w-6" style={{ color: accent }} />
          <span className={`text-xs font-mono ${bodyText(theme)}`}>
            {file ? file.name : "Click or drag an image here"}
          </span>
          <span className={`text-[10px] ${mutedText(theme)}`}>JPEG, PNG, GIF, WEBP — up to 50MB</span>
          <input
            ref={fileInputRef}
            type="file"
            accept={SUPPORTED_IMAGE_TYPES.join(",")}
            className="hidden"
            onChange={(e) => pickFile(e.target.files?.[0])}
          />
        </label>

        {submitError && (
          <div className={`rounded px-3 py-2 text-xs font-mono ${severityBadgeClass(isDark, "critical")}`}>{submitError}</div>
        )}

        <button
          type="button"
          onClick={handleScan}
          disabled={!file || busy || !clientId}
          className={`w-full disabled:opacity-50 disabled:cursor-not-allowed font-mono text-xs px-4 py-2 min-h-11 ${glassPrimaryButton(theme)}`}
        >
          {busy ? (
            <span className="flex items-center justify-center gap-2"><Loader2 className="h-3 w-3 animate-spin" /> Scanning...</span>
          ) : "Scan for deepfake"}
        </button>

        {scan && scan.status === "FAILED" && (
          <div className={`rounded px-3 py-2 text-xs font-mono ${severityBadgeClass(isDark, "critical")}`}>
            {scan.error_message || "Scan failed."}
          </div>
        )}

        {scan && scan.status === "COMPLETE" && scan.result && (
          <div className={`rounded-lg p-3 space-y-1 ${severityBadgeClass(isDark, deepfakeVerdictTier(scan.result.verdict))}`}>
            <div className="flex items-center gap-2 font-mono text-xs font-bold">
              {deepfakeVerdictTier(scan.result.verdict) === "low" ? <ShieldCheck className="h-3.5 w-3.5" /> : <ShieldAlert className="h-3.5 w-3.5" />}
              {scan.result.verdict || "UNKNOWN"}
            </div>
            <div className="text-xs font-mono">
              Confidence score: {scan.result.confidence_score != null ? `${scan.result.confidence_score}%` : "N/A"}
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  );
}

// ---------------------------------------------------------------------
// Panel 2 — Counterfeit Website Detection (WhoisFreaks + Bolster.ai)
// ---------------------------------------------------------------------

function DomainScanPanel({ clientId, theme, isDark, accent }: { clientId?: string | null; theme: Theme; isDark: boolean; accent: string }) {
  const [keyword, setKeyword] = useState("");
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const { scan, polling, start } = usePollScan(clientId);

  const handleScan = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!clientId) return;
    const trimmed = keyword.trim();
    if (trimmed.length < 3 || trimmed.length > 63) {
      setSubmitError("Keyword must be 3-63 characters.");
      return;
    }
    if (trimmed.includes(" ") || trimmed.includes(".")) {
      setSubmitError("Enter a brand keyword only (e.g. 'acmecorp'), not a full domain — no dots or spaces.");
      return;
    }
    setSubmitting(true);
    setSubmitError(null);
    try {
      const res = await submitDomainScan(clientId, trimmed);
      start(res.scan_id);
    } catch (err: any) {
      setSubmitError(err?.message || "Failed to start scan.");
    } finally {
      setSubmitting(false);
    }
  };

  const busy = submitting || polling;
  const candidates = scan?.status === "COMPLETE" ? (scan.result?.candidates || []) : [];

  return (
    <Card className={glassCard(theme)}>
      <div className={SPECULAR_LINE} />
      <CardHeader className={`pb-3 border-b ${isDark ? "border-white/[0.12]" : "border-black/[0.06]"}`}>
        <CardTitle className={`text-xs uppercase tracking-wider ${mutedText(theme)} flex items-center`}>
          <ScanSearch className="h-4 w-4 mr-2" style={{ color: accent }} />
          Counterfeit Website Detection
        </CardTitle>
      </CardHeader>
      <CardContent className="pt-4 space-y-4">
        <p className={`text-xs ${mutedText(theme)}`}>
          Search a brand keyword for typosquat/lookalike domains.
        </p>

        <form onSubmit={handleScan} className="flex gap-2">
          <input
            type="text"
            value={keyword}
            onChange={(e) => setKeyword(e.target.value)}
            placeholder="Brand keyword, e.g. acmecorp"
            className={`flex-1 rounded px-3 py-2 min-h-11 text-xs font-mono focus:outline-none ${bodyText(theme)} ${isDark ? "bg-zinc-950/60 border border-white/[0.12] placeholder:text-zinc-600 focus:border-[#00F5D4]/50" : "bg-white/60 border border-black/[0.08] placeholder:text-zinc-400 focus:border-[#3B82F6]/50"}`}
          />
          <button
            type="submit"
            disabled={busy || !keyword.trim() || !clientId}
            className={`disabled:opacity-50 disabled:cursor-not-allowed font-mono text-xs px-4 py-2 min-h-11 whitespace-nowrap ${glassPrimaryButton(theme)}`}
          >
            {busy ? <Loader2 className="h-3 w-3 animate-spin" /> : "Scan"}
          </button>
        </form>

        {submitError && (
          <div className={`rounded px-3 py-2 text-xs font-mono ${severityBadgeClass(isDark, "critical")}`}>{submitError}</div>
        )}

        {scan && scan.status === "FAILED" && (
          <div className={`rounded px-3 py-2 text-xs font-mono ${severityBadgeClass(isDark, "critical")}`}>
            {scan.error_message || "Scan failed."}
          </div>
        )}

        {scan && scan.status === "COMPLETE" && (
          <div className="space-y-2">
            <div className={`text-[10px] uppercase tracking-wider ${mutedText(theme)}`}>
              {scan.result?.total_candidates_found ?? 0} candidate{(scan.result?.total_candidates_found ?? 0) === 1 ? "" : "s"} found
              {" — "}live-checked {scan.result?.live_checked ?? 0}
            </div>
            {candidates.length === 0 ? (
              <div className={`text-xs font-mono ${mutedText(theme)}`}>No lookalike domains found for this keyword.</div>
            ) : (
              <div className="space-y-1.5 max-h-72 overflow-y-auto overflow-x-hidden">
                {candidates.map((c: any) => (
                  <div key={c.domain_name} className={`rounded-lg px-3 py-2 text-xs font-mono flex items-center justify-between gap-2 min-h-11 ${isDark ? "bg-zinc-950/40 border border-white/[0.08]" : "bg-white/60 border border-black/[0.06]"}`}>
                    <div className="min-w-0">
                      <div className={`truncate font-bold ${bodyText(theme)}`}>{c.domain_name}</div>
                      <div className={mutedText(theme)}>
                        {c.registrar || "Registrar unknown"}{c.create_date ? ` · registered ${c.create_date}` : ""}
                      </div>
                      <a
                        href={`https://${c.domain_name}`}
                        target="_blank"
                        rel="noopener noreferrer"
                        className={`truncate block underline underline-offset-2 ${isDark ? "text-[#00F5D4]/80 hover:text-[#00F5D4]" : "text-[#3B82F6]/80 hover:text-[#3B82F6]"}`}
                      >
                        Visit site to check manually →
                      </a>
                    </div>
                    <Badge className={`shrink-0 ${severityBadgeClass(isDark, c.malicious ? "critical" : c.live ? "low" : "neutral")}`}>
                      {c.malicious ? "MALICIOUS" : c.live ? "LIVE" : c.error ? "FOUND" : "NOT LIVE"}
                    </Badge>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
