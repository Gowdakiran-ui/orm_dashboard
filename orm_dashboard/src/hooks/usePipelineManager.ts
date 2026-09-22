/**
 * usePipelineManager.ts — Phase 13
 *
 * Pipeline state management for the frontend.
 *
 * Protocol:
 *   1. POST /clients/{clientId}/pipeline/run → receive { run_id, status, progress_pct, stage }
 *   2. Poll GET /clients/{clientId}/pipeline/status every 2s (nominal --
 *      each cycle waits 2s after the previous poll resolves, so actual
 *      cadence is closer to ~3-4s under Render's DB round-trip latency)
 *   3. Stop polling when status === "SUCCESS" or "FAILED"
 *   4. Trigger onComplete() exactly once on SUCCESS
 *
 * The status endpoint reads ONLY from PostgreSQL (pipeline_runs table).
 * No Redis parsing. No Celery inspection. No special-case handling.
 *
 * Progress states:
 *   idle → QUEUED(0%) → COLLECTING(5%) → PROCESSING(20%) → TREND(40%)
 *   → RISK(50%) → ALERT(60%) → NARRATIVE(70%) → REPUTATION(80%)
 *   → EXECUTIVE(85%) → BENCHMARK(90%) → FINALIZING(95%) → SUCCESS(100%)
 *   or → FAILED (at whatever % it was at)
 */
import { useState, useEffect, useRef } from "react";
import { fetchPipelineStatus, runClientPipeline } from "@/lib/api";

export interface PipelineStageInfo {
  stage: string;
  progress_pct: number;
  log_tail: string | null;
  duration_s: number | null;
  run_id: string | null;
  current_worker: string | null;
}

// Missed-completion-notification fix: sessionStorage-scoped marker recording
// "this browser tab started or resumed watching run X for this client".
// Per-tab (sessionStorage, not localStorage) so it never surfaces a
// notification for a run a different tab or a different user watched/
// started, and clears itself once shown so a stale terminal run from days
// ago never replays on a later visit. Wrapped in try/catch -- sessionStorage
// can throw (private browsing, disabled storage); losing the marker only
// means the completion notification won't resurface after navigating away,
// it never affects the pipeline itself.
function activeRunStorageKey(clientId: string): string {
  return `pipeline_active_run:${clientId}`;
}

function getActiveRunMarker(clientId: string): string | null {
  try {
    return typeof window !== "undefined" ? window.sessionStorage.getItem(activeRunStorageKey(clientId)) : null;
  } catch {
    return null;
  }
}

function setActiveRunMarker(clientId: string, runId: string): void {
  try {
    if (typeof window !== "undefined") window.sessionStorage.setItem(activeRunStorageKey(clientId), runId);
  } catch {
    // see comment above
  }
}

function clearActiveRunMarker(clientId: string): void {
  try {
    if (typeof window !== "undefined") window.sessionStorage.removeItem(activeRunStorageKey(clientId));
  } catch {
    // see comment above
  }
}

export function usePipelineManager(clientId: string | null, onComplete: () => void) {
  const [pipelineRunning, setPipelineRunning] = useState(false);
  const [pipelineStatus, setPipelineStatus] = useState<string>("idle");
  const [pipelineError, setPipelineError] = useState<string | null>(null);
  const [pipelineResult, setPipelineResult] = useState<string | null>(null);
  const [stageInfo, setStageInfo] = useState<PipelineStageInfo>({
    stage: "idle",
    progress_pct: 0,
    log_tail: null,
    duration_s: null,
    run_id: null,
    current_worker: null,
  });

  const abortControllerRef = useRef<AbortController | null>(null);
  const timerRef = useRef<NodeJS.Timeout | null>(null);
  const consecutiveFailuresRef = useRef<number>(0);
  const currentDelayRef = useRef<number>(2000);

  // Helper to abort any pending requests
  const abortPendingRequests = () => {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
      abortControllerRef.current = null;
    }
  };

  // Helper to clear any pending timers
  const clearPendingTimers = () => {
    if (timerRef.current) {
      clearTimeout(timerRef.current);
      timerRef.current = null;
    }
  };

  // Reset state on client change
  useEffect(() => {
    abortPendingRequests();
    clearPendingTimers();
    setPipelineRunning(false);
    setPipelineStatus("idle");
    setPipelineError(null);
    setPipelineResult(null);
    setStageInfo({ stage: "idle", progress_pct: 0, log_tail: null, duration_s: null, run_id: null, current_worker: null });
    consecutiveFailuresRef.current = 0;
    currentDelayRef.current = 2000;

    if (!clientId) return;

    // Check if there's an active run when switching clients
    const controller = new AbortController();
    abortControllerRef.current = controller;

    async function checkStatus() {
      try {
        const status = await fetchPipelineStatus(clientId!, controller.signal);
        if (controller.signal.aborted) return;
        if (status && status.status && !["idle", "SUCCESS", "FAILED"].includes(status.status)) {
          // There's an active run — resume polling
          setPipelineRunning(true);
          setPipelineStatus(status.status);
          setStageInfo({
            stage: status.stage || status.status,
            progress_pct: status.progress_pct ?? 0,
            log_tail: status.log_tail ?? null,
            duration_s: status.duration_s ?? null,
            run_id: status.run_id ?? null,
            current_worker: status.current_worker ?? null,
          });
          if (status.run_id) setActiveRunMarker(clientId!, status.run_id);
        } else if (status && (status.status === "SUCCESS" || status.status === "FAILED")) {
          // Terminal run on record for this client -- only surface it if
          // this tab was actually watching it (marker set by handleRunPipeline
          // or the resume branch above matches this exact run_id). Otherwise
          // this is just whatever this client's last run happened to be,
          // possibly from days ago, and stays silent exactly like today.
          const watchedRunId = getActiveRunMarker(clientId!);
          if (watchedRunId && status.run_id && watchedRunId === status.run_id) {
            setStageInfo({
              stage: status.stage || status.status,
              progress_pct: status.progress_pct ?? 0,
              log_tail: status.log_tail ?? null,
              duration_s: status.duration_s ?? null,
              run_id: status.run_id ?? null,
              current_worker: status.current_worker ?? null,
            });
            if (status.status === "SUCCESS") {
              setPipelineStatus("success");
              setPipelineResult("Pipeline completed successfully.");
              onComplete(); // Same dashboard-refresh trigger the live-polling path already fires on SUCCESS
            } else {
              setPipelineStatus("failed");
              setPipelineError(status.error_detail || "Pipeline failed");
            }
            clearActiveRunMarker(clientId!);
          }
        }
      } catch {
        // Ignore on mount — not critical
      }
    }
    checkStatus();

    return () => {
      controller.abort();
    };
  }, [clientId, onComplete]);

  // Main polling loop
  useEffect(() => {
    if (!pipelineRunning || !clientId) {
      clearPendingTimers();
      return;
    }

    let isUnmounted = false;

    const poll = async () => {
      if (isUnmounted) return;

      abortPendingRequests();
      const controller = new AbortController();
      abortControllerRef.current = controller;

      try {
        const status = await fetchPipelineStatus(clientId, controller.signal);
        if (isUnmounted || controller.signal.aborted) return;

        if (status) {
          // Reset backoff on successful response
          consecutiveFailuresRef.current = 0;
          currentDelayRef.current = 2000;
          setPipelineError(null);

          // Update stage info on every poll
          setStageInfo({
            stage: status.stage || status.status,
            progress_pct: status.progress_pct ?? 0,
            log_tail: status.log_tail ?? null,
            duration_s: status.duration_s ?? null,
            run_id: status.run_id ?? null,
            current_worker: status.current_worker ?? null,
          });

          const s = status.status;

          if (s === "SUCCESS") {
            setPipelineRunning(false);
            setPipelineStatus("success");
            setPipelineResult("Pipeline completed successfully.");
            onComplete(); // Trigger dashboard refresh exactly once
            clearActiveRunMarker(clientId); // Already shown live -- don't replay on a later visit
            return;       // Stop polling
          } else if (s === "FAILED") {
            setPipelineRunning(false);
            setPipelineStatus("failed");
            setPipelineError(status.error_detail || "Pipeline failed");
            clearActiveRunMarker(clientId); // Already shown live -- don't replay on a later visit
            return;       // Stop polling
          } else if (s === "idle" || !s) {
            // No active run — stop polling
            setPipelineRunning(false);
            setPipelineStatus("idle");
            return;
          } else {
            // Still running (QUEUED, COLLECTING, PROCESSING, etc.)
            setPipelineStatus(s.toLowerCase());
          }
        } else {
          handleFailure();
        }
      } catch (err: any) {
        if (err.name === "AbortError" || isUnmounted) return;
        handleFailure();
      }

      // Schedule next poll if still running
      if (!isUnmounted && pipelineRunning) {
        scheduleNextPoll();
      }
    };

    const handleFailure = () => {
      consecutiveFailuresRef.current += 1;
      if (consecutiveFailuresRef.current >= 5) {
        setPipelineRunning(false);
        setPipelineStatus("failed");
        setPipelineError("Connection to pipeline lost after 5 consecutive failures.");
        clearPendingTimers();
      } else {
        // Exponential backoff: 2s → 4s → 8s → 16s → 30s max
        currentDelayRef.current = Math.min(currentDelayRef.current * 2, 30000);
      }
    };

    const scheduleNextPoll = () => {
      clearPendingTimers();
      const isHidden = typeof document !== "undefined" && document.visibilityState === "hidden";
      const delay = isHidden ? 15000 : currentDelayRef.current;
      timerRef.current = setTimeout(poll, delay);
    };

    scheduleNextPoll();

    const handleVisibilityChange = () => {
      if (document.visibilityState === "visible" && pipelineRunning) {
        clearPendingTimers();
        poll();
      }
    };
    if (typeof document !== "undefined") {
      document.addEventListener("visibilitychange", handleVisibilityChange);
    }

    return () => {
      isUnmounted = true;
      clearPendingTimers();
      abortPendingRequests();
      if (typeof document !== "undefined") {
        document.removeEventListener("visibilitychange", handleVisibilityChange);
      }
    };
  }, [pipelineRunning, clientId, onComplete]);

  async function handleRunPipeline() {
    if (!clientId || pipelineRunning) return;

    abortPendingRequests();
    clearPendingTimers();

    setPipelineError(null);
    setPipelineResult(null);
    setPipelineStatus("starting");
    setPipelineRunning(true);
    consecutiveFailuresRef.current = 0;
    currentDelayRef.current = 2000;

    const controller = new AbortController();
    abortControllerRef.current = controller;

    try {
      const response = await runClientPipeline(clientId, controller.signal);
      if (controller.signal.aborted) return;

      // Update stage info from the POST /run response immediately
      if (response) {
        setStageInfo({
          stage: response.stage || "QUEUED",
          progress_pct: response.progress_pct ?? 0,
          log_tail: null,
          duration_s: null,
          run_id: response.run_id ?? null,
          current_worker: null,
        });
        setPipelineStatus(response.status?.toLowerCase() || "queued");
        if (response.run_id) setActiveRunMarker(clientId, response.run_id);
      }
    } catch (e: any) {
      if (controller.signal.aborted) return;
      setPipelineRunning(false);
      setPipelineStatus("failed");
      setPipelineError(e.message || "Failed to start pipeline");
    }
  }

  return {
    pipelineRunning,
    pipelineStatus,
    pipelineError,
    pipelineResult,
    stageInfo,
    handleRunPipeline,
    setPipelineRunning,
    setPipelineStatus,
    setPipelineError,
    setPipelineResult,
  };
}
