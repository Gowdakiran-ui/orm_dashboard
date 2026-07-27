/**
 * usePipelineManager.ts — Phase 13
 *
 * Pipeline state management for the frontend.
 *
 * Protocol:
 *   1. POST /clients/{clientId}/pipeline/run → receive { run_id, status, progress_pct, stage }
 *   2. Poll GET /clients/{clientId}/pipeline/status every 2s
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
        }
      } catch {
        // Ignore on mount — not critical
      }
    }
    checkStatus();

    return () => {
      controller.abort();
    };
  }, [clientId]);

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
            return;       // Stop polling
          } else if (s === "FAILED") {
            setPipelineRunning(false);
            setPipelineStatus("failed");
            setPipelineError(status.error_detail || "Pipeline failed");
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
