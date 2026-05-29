/**
 * EmailEntry Component - Simple email-based authentication screen
 *
 * Features:
 * - Email input with validation
 * - Auto-focus on mount
 * - Submit on Enter key
 * - Error display for failed login
 * - Follows SENTINEL dark theme design
 */

import { useState, useEffect, useRef, useCallback } from "react";
import { Mail, AlertCircle, Loader2, Info } from "lucide-react";
import { authApi, type AuthUser, getAccessToken, setAccessToken, clearAccessToken } from '@/lib/api';

interface EmailEntryProps {
  onSuccess: (user: AuthUser, token: string) => void;
}

export function EmailEntry({ onSuccess }: EmailEntryProps) {
  const [email, setEmail] = useState("");
  const [error, setError] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  // Auto-focus input on mount
  useEffect(() => {
    inputRef.current?.focus();
  }, []);

  // Check for existing valid token on mount
  useEffect(() => {
    const existingToken = getAccessToken();
    if (existingToken) {
      // Verify the token is still valid
      authApi
        .verify(existingToken)
        .then((response) => {
          if (response.valid && response.user) {
            console.log("Existing token valid, logging in:", response.user);
            onSuccess(response.user, existingToken);
          } else {
            // Token invalid, clear it
            clearAccessToken();
            localStorage.removeItem("sentinel_refresh_token");
            localStorage.removeItem("sentinel_user");
          }
        })
        .catch(() => {
          // Token verification failed, clear it
          clearAccessToken();
          localStorage.removeItem("sentinel_refresh_token");
          localStorage.removeItem("sentinel_user");
        });
    }
  }, [onSuccess]);

  const validateEmail = (email: string): boolean => {
    const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
    return emailRegex.test(email);
  };

  const handleSubmit = useCallback(async () => {
    const trimmedEmail = email.trim().toLowerCase();

    if (!trimmedEmail) {
      setError("Please enter your email address");
      return;
    }

    if (!validateEmail(trimmedEmail)) {
      setError("Please enter a valid email address");
      return;
    }

    setIsLoading(true);
    setError("");

    try {
      const response = await authApi.login(trimmedEmail);
      const accessToken = response.access_token || response.token || "";
      const refreshToken = response.refresh_token || "";

      if (!accessToken) {
        throw new Error("Login did not return an access token");
      }

      // Store access token in memory, refresh token in localStorage
      setAccessToken(accessToken);
      if (refreshToken) {
        localStorage.setItem("sentinel_refresh_token", refreshToken);
      } else {
        localStorage.removeItem("sentinel_refresh_token");
      }
      localStorage.setItem("sentinel_user", JSON.stringify(response.user));

      console.log("Login successful:", response.user);
      onSuccess(response.user, accessToken);
    } catch (err: any) {
      console.error("Login failed:", err);
      const msg = err.message || "";
      if (msg.includes("429") || msg.includes("cooldown") || msg.includes("rate limit")) {
        setError("Too many login attempts. Please wait a moment before trying again.");
      } else if (msg.includes("401") || msg.includes("unauthorized") || msg.includes("invalid")) {
        setError("Invalid email. Please check and try again.");
      } else if (msg.includes("network") || msg.includes("fetch") || msg.includes("ERR_CONNECTION")) {
        setError("Network error. Please check your connection and try again.");
      } else {
        setError("Login failed. Please try again.");
      }
    } finally {
      setIsLoading(false);
    }
  }, [email, onSuccess]);

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter") {
      handleSubmit();
    } else if (e.key === "Escape") {
      setEmail("");
      setError("");
    }
  };

  return (
    <div
      className="min-h-screen flex flex-col items-center justify-center p-4"
      style={{ background: "var(--color-sentinel-bg-canvas)" }}
    >
      {/* Brand mark — glowing shield with gradient backing */}
      <div className="mb-8 relative">
        {/* Glow halo */}
        <div
          className="absolute inset-0 blur-2xl rounded-full scale-75"
          style={{
            background: "radial-gradient(circle, rgba(46,134,171,0.35) 0%, transparent 70%)",
          }}
        />
        {/* Logo */}
        <div className="relative w-24 h-24 mx-auto flex items-center justify-center" style={{ background: "linear-gradient(135deg, #0B1D33 0%, #163350 100%)", border: "1px solid rgba(46,134,171,0.3)", borderRadius: "1rem" }}>
          {/* Glow halo */}
          <div className="absolute inset-0 blur-2xl rounded-md scale-90" style={{ background: "radial-gradient(circle, rgba(46,134,171,0.35) 0%, transparent 70%)" }} />
          <img
            src="/images/sentinel-logo.png"
            alt="SENTINEL"
            className="w-16 h-16 object-contain rounded-lg"
            loading="lazy"
          />
        </div>
        {/* Brand name below */}
        <div className="mt-3 text-center">
          <span className="text-lg font-bold tracking-[0.3em] uppercase" style={{ color: "var(--color-sentinel-text-primary)" }}>SENTINEL</span>
        </div>
      </div>

      {/* Title */}
      <div className="flex flex-col items-center mb-8 text-center">
        <p className="text-xs tracking-widest mb-3 uppercase" style={{ color: "var(--color-sentinel-text-disabled)" }}>
          BMS Intelligence
        </p>
        <p
          className="text-sm"
          style={{ color: "var(--color-sentinel-text-secondary)" }}
        >
          Enter your email to continue
        </p>
      </div>

      {/* Email Input Form */}
      <div
        className="w-full max-w-md p-6 rounded-md"
        style={{
          background: "var(--color-sentinel-bg-panel)",
          border: "1px solid var(--color-sentinel-border)",
        }}
      >
        <div className="mb-4">
          <label
            htmlFor="email-input"
            className="block text-sm font-medium mb-2"
            style={{ color: "var(--color-sentinel-text-secondary)" }}
          >
            Email Address
          </label>
          <div className="relative">
            <Mail
              className="absolute left-3 top-1/2 -translate-y-1/2 w-5 h-5"
              style={{ color: "var(--color-sentinel-text-disabled)" }}
            />
            <input
              ref={inputRef}
              id="email-input"
              type="email"
              value={email}
              onChange={(e) => {
                setEmail(e.target.value);
                setError("");
              }}
              onKeyDown={handleKeyDown}
              disabled={isLoading}
              placeholder="your@email.com"
              autoComplete="email"
              className="w-full pl-10 pr-4 py-3 rounded-lg border focus:outline-none focus:ring-2 transition-all"
              style={{
                background: "var(--color-sentinel-bg-secondary)",
                border: error
                  ? "1px solid var(--color-sentinel-red)"
                  : "1px solid var(--color-sentinel-border)",
                color: "var(--color-sentinel-text-primary)",
              }}
            />
            {isLoading && (
              <Loader2
                className="absolute right-3 top-1/2 -translate-y-1/2 w-5 h-5 animate-spin"
                style={{ color: "var(--color-sentinel-blue)" }}
              />
            )}
          </div>
        </div>

        {/* Error Message */}
        {error && (
          <div className="mb-4 flex items-start gap-2 p-3 rounded-lg" style={{ background: "rgba(239, 68, 68, 0.1)" }}>
            <AlertCircle className="w-5 h-5 flex-shrink-0 mt-0.5" style={{ color: "var(--color-sentinel-red)" }} />
            <p
              className="text-sm"
              style={{ color: "var(--color-sentinel-red)" }}
            >
              {error}
            </p>
          </div>
        )}

        {/* Submit Button */}
        <button
          onClick={handleSubmit}
          disabled={isLoading || !email.trim()}
          className="w-full py-3 rounded-lg font-semibold transition-all duration-150 hover:brightness-125 active:scale-[0.98] disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-2"
          style={{
            background: "var(--color-sentinel-blue)",
            color: "white",
          }}
        >
          {isLoading ? (
            <>
              <Loader2 className="w-5 h-5 animate-spin" />
              Signing in...
            </>
          ) : (
            "Sign In"
          )}
        </button>
      </div>

      {/* Hint — icon only (avoid repeating the hero logo, which looked like a duplicate large mark) */}
      <p
        className="mt-6 text-xs flex items-start gap-2 max-w-md text-center sm:text-left"
        style={{ color: "var(--color-sentinel-text-disabled)" }}
      >
        <Info
          className="w-3.5 h-3.5 flex-shrink-0 mt-0.5 opacity-80"
          aria-hidden
          style={{ color: "var(--color-sentinel-text-disabled)" }}
        />
        <span>
          Your email is your login. Session stays active while your token is valid.
        </span>
      </p>
    </div>
  );
}

export default EmailEntry;
