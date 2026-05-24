/**
 * InviteAcceptPage — magic link invite acceptance screen.
 *
 * Route: /invite?token=xxx
 * Flow: user clicks email link → form to set password → JWT issued → redirect.
 */

import { useState, useEffect, useCallback, useRef } from "react";
import { useSearchParams } from "react-router-dom";
import { AlertCircle, Loader2, CheckCircle2, Shield } from "lucide-react";
import { setAccessToken, clearAccessToken } from "@/lib/api";

interface AcceptResult {
  access_token: string;
  refresh_token: string;
  user: {
    user_id: string;
    email: string;
    full_name: string;
    role: string;
  };
  session_id: string;
}

export function InviteAcceptPage() {
  const [searchParams] = useSearchParams();
  const token = searchParams.get("token") || "";

  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [error, setError] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [success, setSuccess] = useState(false);

  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    inputRef.current?.focus();
  }, []);

  const validatePassword = (pwd: string): string | null => {
    if (!pwd) return "Please enter a password";
    if (pwd.length < 8) return "Password must be at least 8 characters";
    return null;
  };

  const handleSubmit = useCallback(async () => {
    setError("");

    if (password !== confirmPassword) {
      setError("Passwords do not match");
      return;
    }

    const pwdError = validatePassword(password);
    if (pwdError) {
      setError(pwdError);
      return;
    }

    if (!token) {
      setError("Invalid invite link — no token found");
      return;
    }

    setIsLoading(true);

    try {
      const apiUrl = import.meta.env.VITE_API_URL || "";
      const response = await fetch(`${apiUrl}/api/auth/invite/accept`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ token, password }),
        credentials: "include",
      });

      if (!response.ok) {
        let message = "Failed to accept invite";
        try {
          const data = await response.json();
          message = data.detail || data.message || message;
        } catch { /* ignore parse errors */ }
        throw new Error(message);
      }

      const result: AcceptResult = await response.json();

      // Store tokens — access in memory, refresh in localStorage
      setAccessToken(result.access_token);
      localStorage.setItem("sentinel_refresh_token", result.refresh_token);
      localStorage.setItem("sentinel_user", JSON.stringify(result.user));

      setSuccess(true);

      // Redirect to dashboard after 2 seconds
      setTimeout(() => {
        window.location.href = "/";
      }, 2000);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to accept invite. Please try again.");
    } finally {
      setIsLoading(false);
    }
  }, [password, confirmPassword, token]);

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !isLoading && !success) {
      void handleSubmit();
    }
  };

  if (!token) {
    return (
      <div
        className="min-h-screen flex flex-col items-center justify-center p-4"
        style={{ background: "var(--color-sentinel-bg-canvas)" }}
      >
        <div
          className="w-full max-w-md p-6 rounded-xl"
          style={{
            background: "var(--color-sentinel-bg-panel)",
            border: "1px solid var(--color-sentinel-border)",
          }}
        >
          <div className="flex flex-col items-center text-center">
            <div
              className="p-3 rounded-full mb-4"
              style={{ background: "rgba(220, 38, 38, 0.15)" }}
            >
              <AlertCircle className="h-8 w-8" style={{ color: "var(--color-sentinel-red)" }} />
            </div>
            <h1
              className="text-lg font-semibold mb-2"
              style={{ color: "var(--color-sentinel-text-primary)" }}
            >
              Invalid Invite Link
            </h1>
            <p className="text-sm" style={{ color: "var(--color-sentinel-text-secondary)" }}>
              This invite link is missing a token. Please request a new invite from your administrator.
            </p>
          </div>
        </div>
      </div>
    );
  }

  if (success) {
    return (
      <div
        className="min-h-screen flex flex-col items-center justify-center p-4"
        style={{ background: "var(--color-sentinel-bg-canvas)" }}
      >
        <div
          className="w-full max-w-md p-6 rounded-xl"
          style={{
            background: "var(--color-sentinel-bg-panel)",
            border: "1px solid rgba(34, 197, 94, 0.3)",
          }}
        >
          <div className="flex flex-col items-center text-center">
            <div
              className="p-3 rounded-full mb-4"
              style={{ background: "rgba(34, 197, 94, 0.15)" }}
            >
              <CheckCircle2 className="h-8 w-8" style={{ color: "var(--color-sentinel-green)" }} />
            </div>
            <h1
              className="text-lg font-semibold mb-2"
              style={{ color: "var(--color-sentinel-text-primary)" }}
            >
              Account Created
            </h1>
            <p className="text-sm" style={{ color: "var(--color-sentinel-text-secondary)" }}>
              Your account has been activated. Redirecting to Sentinel...
            </p>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div
      className="min-h-screen flex flex-col items-center justify-center p-4"
      style={{ background: "var(--color-sentinel-bg-canvas)" }}
    >
      {/* Brand mark */}
      <div className="mb-8 relative">
        <div
          className="absolute inset-0 blur-2xl rounded-full scale-75"
          style={{
            background: "radial-gradient(circle, rgba(46,134,171,0.35) 0%, transparent 70%)",
          }}
        />
        <div
          className="relative w-24 h-24 mx-auto flex items-center justify-center"
          style={{
            background: "linear-gradient(135deg, #0B1D33 0%, #163350 100%)",
            border: "1px solid rgba(46,134,171,0.3)",
            borderRadius: "1rem",
          }}
        >
          <div
            className="absolute inset-0 blur-2xl rounded-2xl scale-90"
            style={{ background: "radial-gradient(circle, rgba(46,134,171,0.35) 0%, transparent 70%)" }}
          />
          <img
            src="/images/sentinel-logo.png"
            alt="SENTINEL"
            className="w-16 h-16 object-contain rounded-lg"
            loading="lazy"
          />
        </div>
        <div className="mt-3 text-center">
          <span
            className="text-lg font-bold tracking-[0.3em] uppercase"
            style={{ color: "var(--color-sentinel-text-primary)" }}
          >
            SENTINEL
          </span>
        </div>
      </div>

      {/* Title */}
      <div className="flex flex-col items-center mb-6 text-center">
        <div
          className="p-2 rounded-full mb-3"
          style={{ background: "rgba(34, 197, 94, 0.15)" }}
        >
          <Shield className="h-6 w-6" style={{ color: "var(--color-sentinel-green)" }} />
        </div>
        <p className="text-xs tracking-widest mb-3 uppercase" style={{ color: "var(--color-sentinel-text-disabled)" }}>
          BMS Intelligence
        </p>
        <p className="text-sm" style={{ color: "var(--color-sentinel-text-secondary)" }}>
          Set your password to activate your account
        </p>
      </div>

      {/* Password Form */}
      <div
        className="w-full max-w-md p-6 rounded-xl"
        style={{
          background: "var(--color-sentinel-bg-panel)",
          border: "1px solid var(--color-sentinel-border)",
        }}
      >
        <div className="space-y-4">
          <div>
            <label
              htmlFor="password-input"
              className="block text-sm font-medium mb-2"
              style={{ color: "var(--color-sentinel-text-secondary)" }}
            >
              Password
            </label>
            <input
              ref={inputRef}
              id="password-input"
              type="password"
              value={password}
              onChange={(e) => {
                setPassword(e.target.value);
                setError("");
              }}
              onKeyDown={handleKeyDown}
              disabled={isLoading}
              placeholder="Minimum 8 characters"
              autoComplete="new-password"
              className="w-full px-4 py-3 rounded-lg border focus:outline-none focus:ring-2 transition-all"
              style={{
                background: "var(--color-sentinel-bg-secondary)",
                border: error && !confirmPassword ? "1px solid var(--color-sentinel-red)" : "1px solid var(--color-sentinel-border)",
                color: "var(--color-sentinel-text-primary)",
              }}
            />
          </div>

          <div>
            <label
              htmlFor="confirm-password-input"
              className="block text-sm font-medium mb-2"
              style={{ color: "var(--color-sentinel-text-secondary)" }}
            >
              Confirm Password
            </label>
            <input
              id="confirm-password-input"
              type="password"
              value={confirmPassword}
              onChange={(e) => {
                setConfirmPassword(e.target.value);
                setError("");
              }}
              onKeyDown={handleKeyDown}
              disabled={isLoading}
              placeholder="Repeat your password"
              autoComplete="new-password"
              className="w-full px-4 py-3 rounded-lg border focus:outline-none focus:ring-2 transition-all"
              style={{
                background: "var(--color-sentinel-bg-secondary)",
                border: error ? "1px solid var(--color-sentinel-red)" : "1px solid var(--color-sentinel-border)",
                color: "var(--color-sentinel-text-primary)",
              }}
            />
          </div>

          {/* Error Message */}
          {error && (
            <div
              className="flex items-start gap-2 p-3 rounded-lg"
              style={{ background: "rgba(239, 68, 68, 0.1)" }}
            >
              <AlertCircle
                className="w-5 h-5 flex-shrink-0 mt-0.5"
                style={{ color: "var(--color-sentinel-red)" }}
              />
              <p className="text-sm" style={{ color: "var(--color-sentinel-red)" }}>
                {error}
              </p>
            </div>
          )}

          {/* Submit Button */}
          <button
            onClick={() => void handleSubmit()}
            disabled={isLoading || !password || !confirmPassword}
            className="w-full py-3 rounded-lg font-semibold transition-all duration-150 hover:brightness-125 active:scale-[0.98] disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-2"
            style={{
              background: "var(--color-sentinel-green)",
              color: "white",
            }}
          >
            {isLoading ? (
              <>
                <Loader2 className="w-5 h-5 animate-spin" />
                Activating account...
              </>
            ) : (
              "Activate Account"
            )}
          </button>
        </div>
      </div>

      <p className="mt-6 text-xs" style={{ color: "var(--color-sentinel-text-disabled)" }}>
        This link expires in 48 hours. Contact your administrator if it has expired.
      </p>
    </div>
  );
}

export default InviteAcceptPage;
