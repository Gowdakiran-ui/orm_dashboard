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
    let sharedPromise = getCache.get(cacheKey);

    if (!sharedPromise) {
      // Deliberately NOT combined with any individual caller's options.signal:
      // this promise is shared across every concurrent caller for the same
      // cacheKey (dedup), so tying it to one caller's signal meant that
      // caller aborting also killed the request for every other unrelated
      // caller awaiting the same cache entry, and a second caller's own
      // signal was never wired to anything at all. Each caller's own signal
      // is instead raced below, so aborting only affects that caller.
      sharedPromise = (async () => {
        const controller = new AbortController();
        const timeoutId = setTimeout(() => controller.abort(), timeoutMs);

        const headers = {
          "Content-Type": "application/json",
          ...(options.headers || {})
        };

        // credentials: "include" -- auth is now an httpOnly session cookie
        // (core/security.py) set by /auth/login, not a header the client
        // attaches itself. Without this, fetch() silently omits the cookie
        // on the cross-origin (different port) call to the backend.
        const config: RequestInit = { ...options, headers, credentials: "include", signal: controller.signal };

        try {
          const res = await fetch(url, config);
          clearTimeout(timeoutId);

          // Retry on transient 5xx server errors
          if (!res.ok && res.status >= 500 && retries > 0) {
            await new Promise(resolve => setTimeout(resolve, backoff));
            // This GET's own not-yet-settled promise is still the cache entry for
            // cacheKey; recursing into fetchWithRetry without clearing it first
            // makes the recursive call read itself back out of the cache and
            // await itself, deadlocking forever. Clear it so the retry is a
            // fresh cache miss.
            getCache.delete(cacheKey);
            return fetchWithRetry(url, options, retries - 1, backoff * 2, timeoutMs);
          }
          return res;
        } catch (err: any) {
          clearTimeout(timeoutId);
          if (err.name === "AbortError") {
            throw new Error(`Request timed out after ${timeoutMs}ms`);
          }
          if (retries > 0) {
            await new Promise(resolve => setTimeout(resolve, backoff));
            getCache.delete(cacheKey);
            return fetchWithRetry(url, options, retries - 1, backoff * 2, timeoutMs);
          }
          throw err;
        }
      })();

      getCache.set(cacheKey, sharedPromise);

      // Auto-cleanup from cache immediately after promise completes (resolves or rejects)
      sharedPromise.then(
        () => { getCache.delete(cacheKey); },
        () => { getCache.delete(cacheKey); }
      );
    }

    if (!options.signal) {
      const res = await sharedPromise;
      return res.clone();
    }

    // Race this specific caller's own signal against the shared request, so
    // aborting only stops waiting for this caller -- it never cancels the
    // underlying request for other callers sharing the same cache entry.
    const res = await new Promise<Response>((resolve, reject) => {
      const onAbort = () => reject(new DOMException("Aborted", "AbortError"));
      if (options.signal!.aborted) return onAbort();
      options.signal!.addEventListener("abort", onAbort);
      sharedPromise!.then(resolve, reject).finally(() => {
        options.signal!.removeEventListener("abort", onAbort);
      });
    });
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
    credentials: "include",
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

// D2: every fetch* helper below used to swallow non-OK HTTP responses by
// returning an empty/null sentinel, making a 401/404/500 indistinguishable
// from "this client genuinely has no data" — the caller's existing
// .catch()/try-catch error-state wiring (e.g. useDashboardData.ts's
// setXError("Telemetry Offline") calls, feeding TelemetryErrorWidget) could
// then only ever fire for a true network-level exception, not an HTTP error
// response, which is the far more common failure mode. This throws instead,
// so callers' already-built error handling actually receives HTTP failures.
async function parseOrThrow(res: Response): Promise<any> {
  if (!res.ok) {
    let detail = `HTTP ${res.status}`;
    try {
      const body = await res.json();
      if (body && typeof body.detail === "string") detail = body.detail;
    } catch {}
    throw new Error(detail);
  }
  return res.json();
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


// Backend now scopes this to only the clients the logged-in user is
// granted (TASK_AUTH.md fix #4/#5) -- no separate client-side filtering
// needed for the tenant dropdown to show only authorized clients.
export async function fetchClients(search?: string, signal?: AbortSignal) {
  const url = search ? `${API_BASE}/clients/?search=${encodeURIComponent(search)}` : `${API_BASE}/clients/`;
  const res = await fetchWithRetry(url, { signal });
  return parseOrThrow(res);
}

export interface CurrentUser {
  id: string;
  email: string;
  role: string;
  client_ids: string[];
}

export async function login(email: string, password: string): Promise<CurrentUser> {
  const res = await fetchWithRetry(`${API_BASE}/auth/login`, {
    method: "POST",
    body: JSON.stringify({ email, password }),
  }, 0);
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(typeof err.detail === "string" ? err.detail : "Login failed");
  }
  return res.json();
}

export async function logout(): Promise<void> {
  await fetchWithRetry(`${API_BASE}/auth/logout`, { method: "POST" }, 0);
}

export async function fetchCurrentUser(signal?: AbortSignal): Promise<CurrentUser | null> {
  const res = await fetchWithRetry(`${API_BASE}/auth/me`, { signal }, 0);
  if (res.status === 401) return null;
  return parseOrThrow(res);
}

// --- Admin: user management (super_admin only; backend enforces via
// require_super_admin -- these calls 403 for any other role) ---

export interface AdminUser {
  id: string;
  email: string;
  role: string;
  is_active: boolean;
  client_ids: string[];
}

export async function fetchAdminUsers(signal?: AbortSignal): Promise<AdminUser[]> {
  const res = await fetchWithRetry(`${API_BASE}/admin/users/`, { signal });
  return parseOrThrow(res);
}

export interface CreateUserPayload {
  email: string;
  role: "super_admin" | "client_user";
  client_ids: string[];
}

export interface PasswordReveal {
  id: string;
  email: string;
  // Plaintext -- returned exactly once by the backend, never persisted or
  // logged anywhere (TASK_ONBOARDING.md). Show it to the admin and discard.
  password: string;
}

export async function createUser(payload: CreateUserPayload, signal?: AbortSignal): Promise<PasswordReveal> {
  const res = await fetchWithRetry(`${API_BASE}/admin/users`, {
    method: "POST",
    body: JSON.stringify(payload),
    signal,
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(typeof err.detail === "string" ? err.detail : "Failed to create user");
  }
  return res.json();
}

export async function resetUserPassword(userId: string, signal?: AbortSignal): Promise<PasswordReveal> {
  const res = await fetchWithRetry(`${API_BASE}/admin/users/${userId}/reset-password`, {
    method: "POST",
    signal,
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(typeof err.detail === "string" ? err.detail : "Failed to reset password");
  }
  return res.json();
}

export async function deleteAdminUser(userId: string, signal?: AbortSignal) {
  const res = await fetchWithRetry(`${API_BASE}/admin/users/${userId}`, { method: "DELETE", signal });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(typeof err.detail === "string" ? err.detail : "Failed to delete user");
  }
  return res.json();
}

export async function updateAdminUserClients(userId: string, clientIds: string[], signal?: AbortSignal) {
  const res = await fetchWithRetry(`${API_BASE}/admin/users/${userId}/clients`, {
    method: "PATCH",
    body: JSON.stringify({ client_ids: clientIds }),
    signal,
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(typeof err.detail === "string" ? err.detail : "Failed to update client access");
  }
  return res.json();
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
  // Phase 13: returns { run_id, status, stage, progress_pct, started_at, finished_at,
  //                      duration_s, current_worker, log_tail, client_id, error_detail? }
  return parseOrThrow(res);
}


export async function fetchReputation(clientId: string, signal?: AbortSignal) {
  const res = await fetchWithRetry(`${API_BASE}/client-intelligence/${clientId}/reputation`, { signal });
  return parseOrThrow(res);
}

export async function fetchReputationHistory(clientId: string, signal?: AbortSignal) {
  const res = await fetchWithRetry(`${API_BASE}/client-intelligence/${clientId}/reputation-history`, { signal });
  return parseOrThrow(res);
}

export async function fetchReputationBreakdown(clientId: string, signal?: AbortSignal) {
  const res = await fetchWithRetry(`${API_BASE}/client-intelligence/${clientId}/reputation-breakdown`, { signal });
  return parseOrThrow(res);
}

export async function fetchReputationSummary(clientId: string, signal?: AbortSignal) {
  const res = await fetchWithRetry(`${API_BASE}/client-intelligence/${clientId}/reputation-summary`, { signal });
  return parseOrThrow(res);
}

export async function fetchActiveAlerts(clientId: string, signal?: AbortSignal) {
  const res = await fetchWithRetry(`${API_BASE}/client-intelligence/${clientId}/active-alerts`, { signal });
  return parseOrThrow(res);
}

/**
 * @reserved
 * Reserved for future dashboard Top Narratives widget.
 * Currently unused by the frontend but maintained for backwards compatibility.
 */
export async function fetchTopNarratives(clientId: string, signal?: AbortSignal) {
  const res = await fetchWithRetry(`${API_BASE}/client-intelligence/${clientId}/top-narratives`, { signal });
  return parseOrThrow(res);
}

export async function fetchNarratives(clientId: string, signal?: AbortSignal) {
  const res = await fetchWithRetry(`${API_BASE}/client-intelligence/${clientId}/narratives`, { signal });
  return parseOrThrow(res);
}

/**
 * @reserved
 * Reserved for future Share of Voice (SOV) analytics view.
 * Currently unused by the frontend but maintained for backwards compatibility.
 */
export async function fetchShareOfVoice(clientId: string, signal?: AbortSignal) {
  const res = await fetchWithRetry(`${API_BASE}/client-intelligence/${clientId}/share-of-voice`, { signal });
  return parseOrThrow(res);
}

export async function fetchCompetitorBenchmarks(clientId: string, signal?: AbortSignal) {
  const res = await fetchWithRetry(`${API_BASE}/client-intelligence/${clientId}/benchmark`, { signal });
  return parseOrThrow(res);
}

export async function fetchRisks(clientId: string, signal?: AbortSignal) {
  const res = await fetchWithRetry(`${API_BASE}/client-intelligence/${clientId}/risks`, { signal });
  return parseOrThrow(res);
}

export async function fetchExecutives(clientId: string, signal?: AbortSignal) {
  const res = await fetchWithRetry(`${API_BASE}/client-intelligence/${clientId}/executives`, { signal });
  return parseOrThrow(res);
}

export async function fetchExecutiveHistory(clientId: string, signal?: AbortSignal) {
  const res = await fetchWithRetry(`${API_BASE}/client-intelligence/${clientId}/executive-history`, { signal });
  return parseOrThrow(res);
}

export async function fetchSystemStatus(clientId: string, signal?: AbortSignal) {
  const res = await fetchWithRetry(`${API_BASE}/collection/status?client_id=${encodeURIComponent(clientId)}`, { signal });
  return parseOrThrow(res);
}

export async function fetchClientTelemetry(clientId: string, signal?: AbortSignal) {
  const res = await fetchWithRetry(`${API_BASE}/client-intelligence/${clientId}/telemetry`, { signal });
  return parseOrThrow(res);
}

export async function fetchDocuments(clientId: string, signal?: AbortSignal) {
  // D5: no explicit limit meant the backend's default of 100 silently hid
  // the majority of a large client's corpus (Tesla: 463 documents,
  // confirmed live) from every tab that consumes `documents`. The endpoint
  // already enforces a hard ceiling of 500 regardless of what's requested
  // here, so 500 is the real maximum this call can ever return — not an
  // arbitrary bigger magic number.
  const res = await fetchWithRetry(`${API_BASE}/documents/client/${clientId}?limit=500`, { signal });
  return parseOrThrow(res);
}

export async function fetchDocumentDetails(clientId: string, documentId: string, signal?: AbortSignal) {
  const res = await fetchWithRetry(`${API_BASE}/documents/${documentId}?client_id=${encodeURIComponent(clientId)}`, { signal });
  return parseOrThrow(res);
}

// Not client-scoped -- /sources/ is a global endpoint. This function has no
// callers anywhere in the codebase (confirmed via grep); kept as-is pending
// use, but the clientId param it previously had was removed since it was
// silently unused and misleadingly implied client scoping that doesn't exist.
export async function fetchSources(signal?: AbortSignal) {
  const res = await fetchWithRetry(`${API_BASE}/sources/`, { signal });
  return parseOrThrow(res);
}

export async function fetchIntelligenceFeed(clientId: string, signal?: AbortSignal) {
  const res = await fetchWithRetry(`${API_BASE}/client-intelligence/${clientId}/trend-events`, { signal });
  return parseOrThrow(res);
}

export async function fetchCommandCenterStats(clientId: string, signal?: AbortSignal) {
  const res = await fetchWithRetry(`${API_BASE}/collection/status?client_id=${encodeURIComponent(clientId)}`, { signal });
  return parseOrThrow(res);
}

/**
 * @hidden — AI Strategic Advisory
 * Preserved for future use. Re-enable by: importing this in useDashboardData.ts,
 * restoring the AIAdvisorPanel component in page.tsx, and supplying a GROQ_API_KEY.
 */
export async function fetchReputationAdvice(clientId: string, signal?: AbortSignal) {
  const res = await fetchWithRetry(`${API_BASE}/client-intelligence/${clientId}/reputation-advice`, { signal });
  return parseOrThrow(res);
}

/**
 * @hidden — AI Crisis Command Center
 * Preserved for future use. Re-enable by: importing this in useDashboardData.ts,
 * restoring the CrisisPlannerPanel component in page.tsx, and supplying a GROQ_API_KEY.
 */
export async function fetchCrisisPlan(clientId: string, signal?: AbortSignal) {
  const res = await fetchWithRetry(`${API_BASE}/client-intelligence/${clientId}/crisis-plan`, { signal });
  return parseOrThrow(res);
}

export async function fetchExecutiveCandidates(clientId: string, signal?: AbortSignal) {
  const res = await fetchWithRetry(`${API_BASE}/client-intelligence/${clientId}/executive-candidates`, { signal });
  return parseOrThrow(res);
}

export async function fetchCompetitorCandidates(clientId: string, signal?: AbortSignal) {
  const res = await fetchWithRetry(`${API_BASE}/client-intelligence/${clientId}/competitor-candidates`, { signal });
  return parseOrThrow(res);
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
