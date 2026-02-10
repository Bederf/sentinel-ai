/**
 * Shared API Client Utilities
 *
 * Core HTTP utilities for BMS Intelligence API communication:
 * - Authentication token management (access/refresh)
 * - Auth retry logic with token refresh
 * - Basic fetch utilities
 *
 * Rate limiting and request batching are now handled by:
 * - React Query (automatic request deduplication)
 * - Batch aggregators in batchers.ts (50ms window, ID deduplication)
 * - Backend batch endpoints (POST /api/devices/batch/*)
 */

const API_BASE_URL = import.meta.env.VITE_API_URL || "";
const ACCESS_TOKEN_KEY = "sentinel_token";
const REFRESH_TOKEN_KEY = "sentinel_refresh_token";
export const AUTH_EXPIRED_EVENT = "sentinel:auth-expired";

let refreshInFlight: Promise<string | null> | null = null;

// ============= Auth Token Management =============

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

// ============= Token Refresh with In-Flight Deduplication =============

async function tryRefreshAccessToken(): Promise<string | null> {
  const refreshToken = getRefreshToken();
  if (!refreshToken) return null;
  if (refreshInFlight) return refreshInFlight;

  refreshInFlight = (async () => {
    try {
      const refreshUrl = `${API_BASE_URL}/api/auth/refresh?refresh_token=${encodeURIComponent(
        refreshToken
      )}`;
      const response = await fetch(refreshUrl, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
      });
      if (!response.ok) return null;
      const data = (await response.json()) as {
        access_token?: string;
        refresh_token?: string;
      };
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

// ============= Auth Retry Logic =============

async function fetchWithAuthRetry(
  url: string,
  options?: RequestInit,
  allowRetry: boolean = true
): Promise<Response> {
  const token = getAccessToken();
  const response = await fetch(url, {
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
      return fetch(url, {
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

  return response;
}

// ============= Core Fetch API =============

/**
 * Authorized fetch wrapper - adds auth token and retries on 401
 * Uses React Query for deduplication and caching
 * Uses batch aggregators for high-traffic endpoints
 */
export async function authorizedFetch(
  endpoint: string,
  options?: RequestInit,
  absoluteUrl: boolean = false
): Promise<Response> {
  const url = absoluteUrl ? endpoint : `${API_BASE_URL}${endpoint}`;
  return fetchWithAuthRetry(url, options, true);
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

// ============= Generic Fetch Helper =============

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
        errorMessage = errorData.detail
          .map((e: { msg?: string; loc?: string[] }) =>
            `${e.loc?.join(".") || "field"}: ${e.msg || "invalid"}`
          )
          .join(", ");
      } else {
        errorMessage =
          errorData.detail || errorData.message || JSON.stringify(errorData);
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

// ============= Exports =============

export { API_BASE_URL };
export { getRefreshToken, setTokens, notifyAuthExpired, tryRefreshAccessToken };
