/**
 * Authentication API Client
 *
 * Handles user login, MFA, token verification, and account management.
 */

import { fetchApi, getRefreshToken, type ApiError } from './client';

// Re-export shared error types
export type { ApiError };

// ============= Auth Types =============

export interface AuthUser {
  id: string;
  email: string;
  full_name: string;
  role: "admin" | "operator" | "developer" | "auditor";
}

export interface LoginResponse {
  access_token?: string;
  refresh_token?: string;
  token?: string; // legacy fallback
  user: AuthUser;
  expires_at: string;
  mfa_required?: boolean;
  mfa_enrolled?: boolean;
  mfa_challenge_pending?: boolean;
  session_id?: string;
}

export interface VerifyResponse {
  valid: boolean;
  user?: AuthUser;
}

export interface MFAChallengeResponse {
  session_id: string;
  expires_at: string;
}

export interface MFAVerifyRequest {
  session_id: string;
  totp_code: string;
}

// ============= Auth API Methods =============

export const authApi = {
  /** Login with email address */
  login: (email: string) =>
    fetchApi<LoginResponse>(`/api/auth/login?email=${encodeURIComponent(email)}`, {
      method: "POST",
    }),

  /** Verify a JWT token */
  verify: (token: string) =>
    fetchApi<VerifyResponse>(`/api/auth/verify?token=${encodeURIComponent(token)}`, {
      method: "POST",
    }),

  /** Get current user info */
  me: () =>
    fetchApi<AuthUser>("/api/auth/me", {
      headers: {
        Authorization: `Bearer ${localStorage.getItem("sentinel_token") || ""}`,
      },
    }),

  /** Logout */
  logout: () => {
    const refreshToken = getRefreshToken();
    // SECURITY: Send refresh token in request body, NOT in URL (Phase 75-07)
    const body = refreshToken ? JSON.stringify({ refresh_token: refreshToken }) : undefined;
    return fetchApi<{ message: string }>("/api/auth/logout", {
      method: "POST",
      body,
      headers: body ? { "Content-Type": "application/json" } : {}
    });
  },
};

