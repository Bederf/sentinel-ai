/**
 * MfaApprovalWaiting — shown after login when MFA approval is pending.
 * Polls /api/auth/login/approval-status until admin approves or rejects.
 */

import { useState, useEffect, useRef } from "react";
import { Clock, X } from "lucide-react";
import { authApi, type AuthUser, setAccessToken } from "@/lib/api";
import { setAccessToken as setClientAccessToken } from "@/lib/api/client";

interface MfaApprovalWaitingProps {
  email: string;
  onCancel: () => void;
  onApproved: (user: AuthUser, token: string) => void;
}

const POLL_INTERVAL_MS = 2000;
const TIMEOUT_MS = 30 * 60 * 1000; // 30 minutes

export function MfaApprovalWaiting({ email, onCancel, onApproved }: MfaApprovalWaitingProps) {
  const [status, setStatus] = useState<"pending" | "approved" | "rejected" | "expired" | "error">("pending");
  const [message, setMessage] = useState("Waiting for admin approval...");
  const startTime = useRef(Date.now());
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    const poll = async () => {
      if (Date.now() - startTime.current > TIMEOUT_MS) {
        setStatus("expired");
        setMessage("Approval request expired. Please log in again.");
        if (intervalRef.current) clearInterval(intervalRef.current);
        return;
      }

      try {
        const res = await fetch(`/api/auth/login/approval-status?email=${encodeURIComponent(email)}`);
        const data = await res.json();

        if (!res.ok) {
            setMessage(data.detail || "Failed to check approval status.");
            setStatus("error");
            if (intervalRef.current) clearInterval(intervalRef.current);
            return;
        }

        if (data.status === "approved") {
          setStatus("approved");
          setMessage("Login approved!");
          if (intervalRef.current) clearInterval(intervalRef.current);
          // Store tokens locally (same as EmailEntry) then call onApproved
          if (data.access_token) {
            const user: AuthUser = {
              id: data.user.id,
              email: data.user.email,
              full_name: data.user.full_name,
              role: data.user.role as AuthUser["role"],
            };
            localStorage.setItem("sentinel_user", JSON.stringify(user));
            setAccessToken(data.access_token);
            setClientAccessToken(data.access_token);
            if (data.refresh_token) {
              localStorage.setItem("sentinel_refresh_token", data.refresh_token);
            } else {
              localStorage.removeItem("sentinel_refresh_token");
            }
            onApproved(user, data.access_token);
          }
          return;
        }

        if (data.status === "rejected") {
          setStatus("rejected");
          setMessage("Login was rejected by an admin.");
          if (intervalRef.current) clearInterval(intervalRef.current);
          return;
        }

        // still pending
        setMessage(data.message || "Waiting for admin approval...");
      } catch {
        // Network error — keep polling
      }
    };

    poll();
    intervalRef.current = setInterval(poll, POLL_INTERVAL_MS);
    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [email]);

  return (
    <div
      className="min-h-screen flex flex-col items-center justify-center p-4"
      style={{ background: "var(--color-sentinel-bg-canvas)" }}
    >
      <div className="mb-6">
        <img
          src="/images/sentinel-logo.png"
          alt="SENTINEL"
          className="h-16 w-auto mx-auto"
          style={{ opacity: 0.85 }}
        />
      </div>

      <div className="flex flex-col items-center mb-8 text-center">
        <h1
          className="text-2xl font-bold tracking-wide mb-1"
          style={{ color: "var(--color-sentinel-text-primary)" }}
        >
          SENTINEL
        </h1>
        <p className="text-xs tracking-wide mb-3" style={{ color: "var(--color-sentinel-text-disabled)" }}>
          BMS Intelligence
        </p>
      </div>

      <div
        className="w-full max-w-md p-6 rounded-md text-center"
        style={{
          background: "var(--color-sentinel-bg-panel)",
          border: "1px solid var(--color-sentinel-border)",
        }}
      >
        {status === "pending" && (
          <div className="flex flex-col items-center gap-4">
            <div
              className="w-12 h-12 rounded-full flex items-center justify-center animate-pulse"
              style={{ background: "rgba(59, 130, 246, 0.15)" }}
            >
              <Clock className="w-6 h-6" style={{ color: "var(--color-sentinel-blue)" }} />
            </div>
            <div>
              <p className="text-base font-medium mb-1" style={{ color: "var(--color-sentinel-text-primary)" }}>
                Waiting for Admin Approval
              </p>
              <p className="text-sm" style={{ color: "var(--color-sentinel-text-secondary)" }}>
                {message}
              </p>
              <p className="text-xs mt-2" style={{ color: "var(--color-sentinel-text-disabled)" }}>
                An admin will receive a Telegram message. Reply YES or NO to approve or reject.
              </p>
            </div>
          </div>
        )}

        {status === "approved" && (
          <div className="flex flex-col items-center gap-4">
            <div
              className="w-12 h-12 rounded-full flex items-center justify-center"
              style={{ background: "rgba(34, 197, 94, 0.15)" }}
            >
              <span className="text-xl">✅</span>
            </div>
            <div>
              <p className="text-base font-medium mb-1" style={{ color: "var(--color-sentinel-text-primary)" }}>
                Login Approved
              </p>
              <p className="text-sm" style={{ color: "var(--color-sentinel-text-secondary)" }}>
                Redirecting to dashboard...
              </p>
            </div>
          </div>
        )}

        {(status === "rejected" || status === "expired" || status === "error") && (
          <div className="flex flex-col items-center gap-4">
            <div
              className="w-12 h-12 rounded-full flex items-center justify-center"
              style={{ background: "rgba(239, 68, 68, 0.15)" }}
            >
              <X className="w-6 h-6" style={{ color: "var(--color-sentinel-red)" }} />
            </div>
            <div>
              <p className="text-base font-medium mb-1" style={{ color: "var(--color-sentinel-text-primary)" }}>
                {status === "rejected" ? "Login Rejected" : status === "expired" ? "Request Expired" : "Error"}
              </p>
              <p className="text-sm" style={{ color: "var(--color-sentinel-text-secondary)" }}>
                {message}
              </p>
            </div>
            <button
              onClick={onCancel}
              className="mt-2 px-4 py-2 rounded-lg text-sm font-medium transition-colors hover:brightness-125"
              style={{
                background: "var(--color-sentinel-bg-secondary)",
                border: "1px solid var(--color-sentinel-border)",
                color: "var(--color-sentinel-text-secondary)",
              }}
            >
              Back to Login
            </button>
          </div>
        )}
      </div>

      <p className="mt-6 text-xs" style={{ color: "var(--color-sentinel-text-disabled)" }}>
        <button onClick={onCancel} className="underline hover:no-underline">
          Cancel
        </button>
      </p>
    </div>
  );
}

export default MfaApprovalWaiting;
