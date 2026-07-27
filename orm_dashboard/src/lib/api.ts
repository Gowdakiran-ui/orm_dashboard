export const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8000";


const getCache = new Map<string, Promise<Response>>();

// Hardened fetch with retries, exponential backoff, and timeout
async function fetchWithRetry(
  url: string, 
  options: RequestInit = {}, 
  retries = 2, 
  backoff = 500,
  timeoutMs = 15000
): Promise<Response> {
  const isGet = !options.method || options.method.toUpperCase() === "GET";
  if (isGet) {
    const cacheKey = url;
    const cachedPromise = getCache.get(cacheKey);
    if (cachedPromise) {
      try {
        const res = await cachedPromise;
        return res.clone();
      } catch (err) {
        // If the cached request failed, bypass cache and perform a new fetch
      }
    }

    const promise = (async () => {
      const controller = new AbortController();
      const timeoutId = setTimeout(() => controller.abort(), timeoutMs);
      
      const headers = {
        "Content-Type": "application/json",
        ...(options.headers || {})
      };

      let combinedSignal: CombinedSignal | null = null;
      if (options.signal) {
        combinedSignal = anySignal([options.signal, controller.signal]);
      }

      const config: RequestInit = {
        ...options,
        headers,
        signal: combinedSignal ? combinedSignal.signal : controller.signal
      };

      try {
        const res = await fetch(url, config);
        clearTimeout(timeoutId);
        
        // Retry on transient 5xx server errors
        if (!res.ok && res.status >= 500 && retries > 0) {
          await new Promise(resolve => setTimeout(resolve, backoff));
          return fetchWithRetry(url, options, retries - 1, backoff * 2, timeoutMs);
        }
        return res;
      } catch (err: any) {
        clearTimeout(timeoutId);
        if (err.name === "AbortError" && !options.signal?.aborted) {
          throw new Error(`Request timed out after ${timeoutMs}ms`);
        }
        if (retries > 0 && err.name !== "AbortError") {
          await new Promise(resolve => setTimeout(resolve, backoff));
          return fetchWithRetry(url, options, retries - 1, backoff * 2, timeoutMs);
        }
        throw err;
      } finally {
        if (combinedSignal) {
          combinedSignal.cleanup();
        }
      }
    })();

    getCache.set(cacheKey, promise);
    
    // Auto-cleanup from cache immediately after promise completes (resolves or rejects)
    promise.then(
      () => { getCache.delete(cacheKey); },
      () => { getCache.delete(cacheKey); }
    );

    const res = await promise;
    return res.clone();
  }

  // Non-GET requests (e.g. POST/DELETE) path
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), timeoutMs);
  
  const headers = {
    "Content-Type": "application/json",
    ...(options.headers || {})
  };

  let combinedSignal: CombinedSignal | null = null;
  if (options.signal) {
    combinedSignal = anySignal([options.signal, controller.signal]);
  }

  const config: RequestInit = {
    ...options,
    headers,
    signal: combinedSignal ? combinedSignal.signal : controller.signal
  };

  try {
    const res = await fetch(url, config);
    clearTimeout(timeoutId);
    
    // Retry on transient 5xx server errors
    if (!res.ok && res.status >= 500 && retries > 0) {
      await new Promise(resolve => setTimeout(resolve, backoff));
      return fetchWithRetry(url, options, retries - 1, backoff * 2, timeoutMs);
    }
    return res;
  } catch (err: any) {
    clearTimeout(timeoutId);
    if (err.name === "AbortError" && !options.signal?.aborted) {
      throw new Error(`Request timed out after ${timeoutMs}ms`);
    }
    if (retries > 0 && err.name !== "AbortError") {
      await new Promise(resolve => setTimeout(resolve, backoff));
      return fetchWithRetry(url, options, retries - 1, backoff * 2, timeoutMs);
    }
    throw err;
  } finally {
    if (combinedSignal) {
      combinedSignal.cleanup();
    }
  }
}

interface CombinedSignal {
  signal: AbortSignal;
  cleanup: () => void;
}

// Helper to combine multiple AbortSignals
function anySignal(signals: AbortSignal[]): CombinedSignal {
  const controller = new AbortController();
  const onAbort = () => {
    controller.abort();
    cleanup();
  };
  const cleanup = () => {
    for (const signal of signals) {
      signal.removeEventListener("abort", onAbort);
    }
  };
  for (const signal of signals) {
    if (signal.aborted) {
      onAbort();
      break;
    }
    signal.addEventListener("abort", onAbort);
  }
  return { signal: controller.signal, cleanup };
}


export async function fetchClients(search?: string, signal?: AbortSignal) {
  try {
    const url = search ? `${API_BASE}/clients?search=${encodeURIComponent(search)}` : `${API_BASE}/clients`;
    const res = await fetchWithRetry(url, { signal });
    if (!res.ok) return [];
    return res.json();
  } catch (e) {
    return [];
  }
}

export interface ClientOnboardingPayload {
  name: string;
  industry?: string;
  primary_entity_name: string;
  website?: string;
  domain?: string;
  ticker_symbol?: string;
}

export async function onboardClient(payload: ClientOnboardingPayload, signal?: AbortSignal) {
  const res = await fetchWithRetry(`${API_BASE}/clients/onboard`, {
    method: "POST",
    body: JSON.stringify(payload),
    signal,
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || "Failed to create company");
  }
  return res.json();
}

export async function deleteClient(clientId: string, signal?: AbortSignal) {
  const res = await fetchWithRetry(`${API_BASE}/clients/${clientId}`, {
    method: "DELETE",
    signal,
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(typeof err.detail === "string" ? err.detail : "Failed to delete company");
  }
  return res.json();
}

export async function runClientPipeline(clientId: string, signal?: AbortSignal) {
  const res = await fetchWithRetry(`${API_BASE}/clients/${clientId}/pipeline/run`, {
    method: "POST",
    signal,
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(typeof err.detail === "string" ? err.detail : "Failed to start pipeline");
  }
  // Phase 13: returns { run_id, status, stage, progress_pct, client_id, client_name, message }
  return res.json();
}

export async function fetchPipelineStatus(clientId: string, signal?: AbortSignal) {
  const res = await fetchWithRetry(`${API_BASE}/clients/${clientId}/pipeline/status`, { signal });
  if (!res.ok) return null;
  // Phase 13: returns { run_id, status, stage, progress_pct, started_at, finished_at,
  //                      duration_s, current_worker, log_tail, client_id, error_detail? }
  return res.json();
}


export async function fetchReputation(clientId: string, signal?: AbortSignal) {
  const res = await fetchWithRetry(`${API_BASE}/client-intelligence/${clientId}/reputation`, { signal });
  if (!res.ok) return null;
  return res.json();
}

export async function fetchReputationHistory(clientId: string, signal?: AbortSignal) {
  const res = await fetchWithRetry(`${API_BASE}/client-intelligence/${clientId}/reputation-history`, { signal });
  if (!res.ok) return [];
  return res.json();
}

export async function fetchReputationBreakdown(clientId: string, signal?: AbortSignal) {
  const res = await fetchWithRetry(`${API_BASE}/client-intelligence/${clientId}/reputation-breakdown`, { signal });
  if (!res.ok) return null;
  return res.json();
}

export async function fetchActiveAlerts(clientId: string, signal?: AbortSignal) {
  const res = await fetchWithRetry(`${API_BASE}/client-intelligence/${clientId}/active-alerts`, { signal });
  if (!res.ok) return [];
  return res.json();
}

/**
 * @reserved
 * Reserved for future dashboard Top Narratives widget.
 * Currently unused by the frontend but maintained for backwards compatibility.
 */
export async function fetchTopNarratives(clientId: string, signal?: AbortSignal) {
  const res = await fetchWithRetry(`${API_BASE}/client-intelligence/${clientId}/top-narratives`, { signal });
  if (!res.ok) return [];
  return res.json();
}

export async function fetchNarratives(clientId: string, signal?: AbortSignal) {
  const res = await fetchWithRetry(`${API_BASE}/client-intelligence/${clientId}/narratives`, { signal });
  if (!res.ok) return [];
  return res.json();
}

/**
 * @reserved
 * Reserved for future Share of Voice (SOV) analytics view.
 * Currently unused by the frontend but maintained for backwards compatibility.
 */
export async function fetchShareOfVoice(clientId: string, signal?: AbortSignal) {
  const res = await fetchWithRetry(`${API_BASE}/client-intelligence/${clientId}/share-of-voice`, { signal });
  if (!res.ok) return [];
  return res.json();
}

export async function fetchCompetitorBenchmarks(clientId: string, signal?: AbortSignal) {
  const res = await fetchWithRetry(`${API_BASE}/client-intelligence/${clientId}/benchmark`, { signal });
  if (!res.ok) return [];
  return res.json();
}

export async function fetchRisks(clientId: string, signal?: AbortSignal) {
  const res = await fetchWithRetry(`${API_BASE}/client-intelligence/${clientId}/risks`, { signal });
  if (!res.ok) return null;
  return res.json();
}

export async function fetchExecutives(clientId: string, signal?: AbortSignal) {
  const res = await fetchWithRetry(`${API_BASE}/client-intelligence/${clientId}/executives`, { signal });
  if (!res.ok) return [];
  return res.json();
}

export async function fetchSystemStatus(signal?: AbortSignal) {
  const res = await fetchWithRetry(`${API_BASE}/collection/status`, { signal });
  if (!res.ok) return null;
  return res.json();
}

export async function fetchClientTelemetry(clientId: string, signal?: AbortSignal) {
  const res = await fetchWithRetry(`${API_BASE}/client-intelligence/${clientId}/telemetry`, { signal });
  if (!res.ok) return null;
  return res.json();
}

export async function fetchDocuments(clientId: string, signal?: AbortSignal) {
  const res = await fetchWithRetry(`${API_BASE}/documents/client/${clientId}`, { signal });
  if (!res.ok) return [];
  return res.json();
}

export async function fetchDocumentDetails(clientId: string, documentId: string, signal?: AbortSignal) {
  const res = await fetchWithRetry(`${API_BASE}/documents/${documentId}`, { signal });
  if (!res.ok) return null;
  return res.json();
}

export async function fetchSources(clientId: string, signal?: AbortSignal) {
  const res = await fetchWithRetry(`${API_BASE}/sources/`, { signal });
  if (!res.ok) return null;
  return res.json();
}

export async function fetchIntelligenceFeed(clientId: string, signal?: AbortSignal) {
  const res = await fetchWithRetry(`${API_BASE}/client-intelligence/${clientId}/trend-events`, { signal });
  if (!res.ok) return [];
  return res.json();
}

export async function fetchCommandCenterStats(clientId: string, signal?: AbortSignal) {
  const res = await fetchWithRetry(`${API_BASE}/collection/status`, { signal });
  if (!res.ok) return null;
  return res.json();
}

/**
 * @hidden — AI Strategic Advisory
 * Preserved for future use. Re-enable by: importing this in useDashboardData.ts,
 * restoring the AIAdvisorPanel component in page.tsx, and supplying a GROQ_API_KEY.
 */
export async function fetchReputationAdvice(clientId: string, signal?: AbortSignal) {
  const res = await fetchWithRetry(`${API_BASE}/client-intelligence/${clientId}/reputation-advice`, { signal });
  if (!res.ok) return null;
  return res.json();
}

/**
 * @hidden — AI Crisis Command Center
 * Preserved for future use. Re-enable by: importing this in useDashboardData.ts,
 * restoring the CrisisPlannerPanel component in page.tsx, and supplying a GROQ_API_KEY.
 */
export async function fetchCrisisPlan(clientId: string, signal?: AbortSignal) {
  const res = await fetchWithRetry(`${API_BASE}/client-intelligence/${clientId}/crisis-plan`, { signal });
  if (!res.ok) return null;
  return res.json();
}

export async function fetchExecutiveCandidates(clientId: string, signal?: AbortSignal) {
  const res = await fetchWithRetry(`${API_BASE}/client-intelligence/${clientId}/executive-candidates`, { signal });
  if (!res.ok) return [];
  return res.json();
}

export async function fetchCompetitorCandidates(clientId: string, signal?: AbortSignal) {
  const res = await fetchWithRetry(`${API_BASE}/client-intelligence/${clientId}/competitor-candidates`, { signal });
  if (!res.ok) return [];
  return res.json();
}

export async function promoteCompetitorCandidates(clientId: string, signal?: AbortSignal) {
  const res = await fetchWithRetry(`${API_BASE}/client-intelligence/${clientId}/promote-competitors`, {
    method: "POST",
    signal,
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || "Failed to promote competitors");
  }
  return res.json();
}

export async function promoteExecutiveCandidates(clientId: string, signal?: AbortSignal) {
  const res = await fetchWithRetry(`${API_BASE}/client-intelligence/${clientId}/promote-executives`, {
    method: "POST",
    signal,
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || "Failed to promote executives");
  }
  return res.json();
}
