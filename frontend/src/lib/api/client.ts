/**
 * Shared API Client Utilities
 *
 * Core HTTP utilities for BMS Intelligence API communication:
 * - Authentication token management (access/refresh)
 * - Request limiting and rate limiting handling
 * - Response caching for GET requests
 * - Auth retry logic with token refresh
 */

const API_BASE_URL = import.meta.env.VITE_API_URL || "";
const ACCESS_TOKEN_KEY = "sentinel_token";
const REFRESH_TOKEN_KEY = "sentinel_refresh_token";
export const AUTH_EXPIRED_EVENT = "sentinel:auth-expired";

let refreshInFlight: Promise<string | null> | null = null;
const MAX_RATE_LIMIT_RETRIES = 0;
const BASE_RATE_LIMIT_DELAY_MS = 500;
const MAX_CONCURRENT_API_REQUESTS = 4;
let activeApiRequests = 0;
const apiRequestWaiters: Array<() => void> = [];
const inFlightGetRequests = new Map<string, Promise<Response>>();
const cachedGetResponses = new Map<string, { response: Response; expiresAt: number }>();
const rateLimitedUntilByBucket = new Map<string, number>();
const DEFAULT_RATE_LIMIT_COOLDOWN_MS = 30000;
const DEFAULT_GET_CACHE_TTL_MS = 30000;
const SITES_CACHE_KEY = "sentinel_cached_sites";

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

async function acquireApiRequestSlot(): Promise<void> {
  if (activeApiRequests < MAX_CONCURRENT_API_REQUESTS) {
    activeApiRequests += 1;
    return;
  }

  await new Promise<void>((resolve) => {
    apiRequestWaiters.push(resolve);
  });
}

function releaseApiRequestSlot(): void {
  const nextWaiter = apiRequestWaiters.shift();
  if (nextWaiter) {
    nextWaiter();
    return;
  }

  activeApiRequests = Math.max(0, activeApiRequests - 1);
}

async function performFetchWithLimits(url: string, options?: RequestInit): Promise<Response> {
  await acquireApiRequestSlot();
  try {
    return await fetch(url, options);
  } finally {
    releaseApiRequestSlot();
  }
}

function getRetryAfterMs(response: Response): number | null {
  const retryAfter = response.headers.get("Retry-After");
  if (!retryAfter) return null;

  const seconds = Number(retryAfter);
  if (Number.isFinite(seconds) && seconds >= 0) {
    return seconds * 1000;
  }

  const retryAt = Date.parse(retryAfter);
  if (Number.isNaN(retryAt)) return null;

  const delayMs = retryAt - Date.now();
  return delayMs > 0 ? delayMs : null;
}

function getRateLimitBucket(url: string): string {
  if (url.includes("/safety-status")) return "safety-status";
  if (url.includes("/api/devices") || url.includes("/api/sites") || url.includes("/api/predictions")) {
    return "dashboard-core";
  }
  if (url.includes("/api/integration/")) return "integration";
  if (url.includes("/api/optimization/")) return "optimization";
  if (url.includes("/api/dali/")) return "dali";
  if (url.includes("/api/security/")) return "security";
  if (url.includes("/api/solar/")) return "solar";
  if (url.includes("/api/alerts")) return "alerts";
  if (url.includes("/api/modules/") && url.includes("/recommendations")) return "module-recommendations";
  return url;
}

function createClientRateLimitResponse(bucket: string): Response {
  return new Response(
    JSON.stringify({ detail: `Client cooldown active for ${bucket} after recent 429` }),
    {
      status: 429,
      statusText: "Too Many Requests",
      headers: { "Content-Type": "application/json" },
    }
  );
}

function getAccessToken(): string | null {
  return localStorage.getItem(ACCESS_TOKEN_KEY);
}

function getRefreshToken(): string | null {
  return localStorage.getItem(REFRESH_TOKEN_KEY);
}

function setTokens(accessToken: string, refreshToken?: string): void {
  localStorage.setItem(ACCESS_TOKEN_KEY, accessToken);
  if (refreshToken) {
    localStorage.setItem(REFRESH_TOKEN_KEY, refreshToken);
  }
}

export function clearAuthStorage(): void {
  localStorage.removeItem(ACCESS_TOKEN_KEY);
  localStorage.removeItem(REFRESH_TOKEN_KEY);
  localStorage.removeItem("sentinel_user");
}

function notifyAuthExpired(): void {
  window.dispatchEvent(new Event(AUTH_EXPIRED_EVENT));
}

async function tryRefreshAccessToken(): Promise<string | null> {
  const refreshToken = getRefreshToken();
  if (!refreshToken) return null;
  if (refreshInFlight) return refreshInFlight;

  refreshInFlight = (async () => {
    try {
      const refreshUrl = `${API_BASE_URL}/api/auth/refresh?refresh_token=${encodeURIComponent(refreshToken)}`;
      const response = await fetch(refreshUrl, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
      });
      if (!response.ok) return null;
      const data = await response.json() as { access_token?: string; refresh_token?: string };
      if (!data.access_token) return null;
      setTokens(data.access_token, data.refresh_token);
      return data.access_token;
    } catch {
      return null;
    } finally {
      refreshInFlight = null;
    }
  })();

  return refreshInFlight;
}

async function fetchWithAuthRetry(
  url: string,
  options?: RequestInit,
  allowRetry: boolean = true,
  rateLimitRetryCount: number = 0
): Promise<Response> {
  const token = getAccessToken();
  const response = await performFetchWithLimits(url, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...options?.headers,
    },
  });

  const isRefreshEndpoint = url.includes("/api/auth/refresh");
  if (response.status === 401 && allowRetry && !isRefreshEndpoint) {
    const refreshedToken = await tryRefreshAccessToken();
    if (refreshedToken) {
      return performFetchWithLimits(url, {
        ...options,
        headers: {
          "Content-Type": "application/json",
          ...(refreshedToken ? { Authorization: `Bearer ${refreshedToken}` } : {}),
          ...options?.headers,
        },
      });
    }

    clearAuthStorage();
    notifyAuthExpired();
  }

  const requestMethod = (options?.method || "GET").toUpperCase();
  const isSafeMethod = requestMethod === "GET" || requestMethod === "HEAD" || requestMethod === "OPTIONS";
  if (
    response.status === 429 &&
    isSafeMethod &&
    rateLimitRetryCount < MAX_RATE_LIMIT_RETRIES
  ) {
    const retryAfterMs = getRetryAfterMs(response);
    const fallbackDelayMs = BASE_RATE_LIMIT_DELAY_MS * (2 ** rateLimitRetryCount);
    const jitterMs = Math.floor(Math.random() * 200);
    await sleep((retryAfterMs ?? fallbackDelayMs) + jitterMs);

    return fetchWithAuthRetry(url, options, allowRetry, rateLimitRetryCount + 1);
  }

  return response;
}

export async function authorizedFetch(
  endpoint: string,
  options?: RequestInit,
  absoluteUrl: boolean = false
): Promise<Response> {
  const url = absoluteUrl ? endpoint : `${API_BASE_URL}${endpoint}`;
  const bucket = getRateLimitBucket(url);
  const method = (options?.method || "GET").toUpperCase();
  const canDeduplicateGet = method === "GET" && (!options?.body || options.body === undefined);
  const dedupeKey = `${method}:${url}`;

  if (canDeduplicateGet) {
    const cachedEntry = cachedGetResponses.get(dedupeKey);
    if (cachedEntry && cachedEntry.expiresAt > Date.now()) {
      return cachedEntry.response.clone();
    }
  }

  const rateLimitedUntil = rateLimitedUntilByBucket.get(bucket);
  if (rateLimitedUntil && rateLimitedUntil > Date.now()) {
    if (canDeduplicateGet) {
      const cachedEntry = cachedGetResponses.get(dedupeKey);
      if (cachedEntry && cachedEntry.expiresAt > Date.now()) {
        return cachedEntry.response.clone();
      }
    }
    return createClientRateLimitResponse(bucket);
  }

  if (!canDeduplicateGet) {
    const response = await fetchWithAuthRetry(url, options, true);
    if (response.status === 429) {
      const retryAfterMs = getRetryAfterMs(response) ?? DEFAULT_RATE_LIMIT_COOLDOWN_MS;
      rateLimitedUntilByBucket.set(bucket, Date.now() + retryAfterMs);
    }
    return response;
  }

  const existing = inFlightGetRequests.get(dedupeKey);
  if (existing) {
    return existing.then((response) => response.clone());
  }

  const requestPromise = fetchWithAuthRetry(url, options, true);
  inFlightGetRequests.set(dedupeKey, requestPromise);

  try {
    const response = await requestPromise;
    if (response.status === 429) {
      const retryAfterMs = getRetryAfterMs(response) ?? DEFAULT_RATE_LIMIT_COOLDOWN_MS;
      rateLimitedUntilByBucket.set(bucket, Date.now() + retryAfterMs);
      const cachedEntry = cachedGetResponses.get(dedupeKey);
      if (cachedEntry && cachedEntry.expiresAt > Date.now()) {
        return cachedEntry.response.clone();
      }
    }
    if (response.ok) {
      cachedGetResponses.set(dedupeKey, {
        response: response.clone(),
        expiresAt: Date.now() + DEFAULT_GET_CACHE_TTL_MS,
      });
    }
    return response.clone();
  } finally {
    inFlightGetRequests.delete(dedupeKey);
  }
}

// ============= Shared Error Types =============

export interface HealthResponse {
  status: string;
  version: string;
}

export interface ApiError {
  message: string;
  status: number;
}

export function isExpectedApiError(error: unknown): error is ApiError {
  const maybeError = error as { status?: number; message?: string } | null;
  if (maybeError?.status === 401 || maybeError?.status === 429) return true;
  const message = (maybeError?.message || "").toLowerCase();
  return message.includes("status 401") || message.includes("status 429");
}

// ============= Core fetchApi Helper =============

/**
 * Generic fetch helper for all API calls
 * Wraps authorizedFetch with JSON parsing and error handling
 */
export async function fetchApi<T>(
  endpoint: string,
  options?: RequestInit
): Promise<T> {
  const response = await authorizedFetch(endpoint, options);

  if (!response.ok) {
    let errorMessage = response.statusText;
    try {
      const errorData = await response.json();
      // Handle Pydantic validation errors (detail is an array)
      if (Array.isArray(errorData.detail)) {
        errorMessage = errorData.detail.map((e: { msg?: string; loc?: string[] }) =>
          `${e.loc?.join('.') || 'field'}: ${e.msg || 'invalid'}`
        ).join(', ');
      } else {
        errorMessage = errorData.detail || errorData.message || JSON.stringify(errorData);
      }
    } catch {
      // If response isn't JSON, use statusText
    }
    const error: ApiError = {
      message: `API Error: ${errorMessage}`,
      status: response.status,
    };
    throw error;
  }

  return response.json();
}

// Export constants and keys for use in domain modules
export { API_BASE_URL, SITES_CACHE_KEY };
export { getRefreshToken, setTokens, notifyAuthExpired, tryRefreshAccessToken };
