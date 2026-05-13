/**
 * FreshnessAlertCard Component
 *
 * Displays active data freshness breaches in the dashboard notification bell.
 * Fetches from /api/sentry/freshness/breaches and renders breach cards.
 */

import { useState, useEffect, useCallback } from "react";
import { WifiOff, Clock, RefreshCw, AlertTriangle } from "lucide-react";
import { getAccessToken } from "@/lib/api";

interface FreshnessBreach {
  id: string;
  site_id: string;
  site_name?: string | null;
  data_source: string;
  age_seconds: number | null;
  sli_target: number;
  breach_time: string;
  duration_seconds?: number | null;
}

function getRelativeTime(timestamp: string): string {
  const now = new Date();
  const breachTime = new Date(timestamp);
  const diffMs = now.getTime() - breachTime.getTime();
  const diffMins = Math.floor(diffMs / 60000);
  const diffHours = Math.floor(diffMins / 60);
  const diffDays = Math.floor(diffHours / 24);

  if (diffMins < 1) return "Just now";
  if (diffMins < 60) return `${diffMins}m`;
  if (diffHours < 24) return `${diffHours}h`;
  return `${diffDays}d`;
}

function formatAge(seconds: number | null): string {
  if (seconds === null) return "Unknown";
  if (seconds < 60) return `${seconds}s`;
  const mins = Math.floor(seconds / 60);
  if (mins < 60) return `${mins}m`;
  const hours = Math.floor(mins / 60);
  return `${hours}h ${mins % 60}m`;
}

function getSourceLabel(source: string): string {
  const labels: Record<string, string> = {
    bms_telemetry: "BMS Telemetry",
    anomalies: "Anomalies",
    documents: "Documents",
    recommendations: "Recommendations",
  };
  return labels[source] || source;
}

function getSourceColor(source: string): string {
  const colors: Record<string, string> = {
    bms_telemetry: "var(--color-status-error)",
    anomalies: "var(--color-status-warning)",
  };
  return colors[source] || "var(--color-sentinel-amber)";
}

interface FreshnessAlertCardProps {
  breach: FreshnessBreach;
}

function FreshnessAlertCard({ breach }: FreshnessAlertCardProps) {
  const sourceColor = getSourceColor(breach.data_source);

  return (
    <div
      className="p-3 rounded"
      style={{
        background: "rgba(245, 158, 11, 0.08)",
        borderLeft: `3px solid ${sourceColor}`,
      }}
    >
      <div className="flex items-start justify-between gap-2 mb-1.5">
        <div className="flex items-center gap-2">
          <AlertTriangle className="h-3.5 w-3.5" style={{ color: sourceColor }} />
          <span
            className="text-xs font-medium"
            style={{ color: "var(--color-sentinel-text-primary)" }}
          >
            {getSourceLabel(breach.data_source)}
          </span>
        </div>
        <span
          className="text-[10px] px-1.5 py-0.5 rounded"
          style={{
            background: `${sourceColor}20`,
            color: sourceColor,
          }}
        >
          FRESHNESS
        </span>
      </div>

      <div className="flex items-center gap-3 text-xs mb-1">
        <span style={{ color: "var(--color-sentinel-text-secondary)" }}>
          {breach.site_name || breach.site_id}
        </span>
        <span style={{ color: "var(--color-sentinel-text-disabled)" }}>•</span>
        <span style={{ color: "var(--color-status-error)" }}>
          Age: {formatAge(breach.age_seconds)} (target: {breach.sli_target}s)
        </span>
      </div>

      <div className="flex items-center gap-1">
        <Clock className="h-3 w-3" style={{ color: "var(--color-sentinel-text-disabled)" }} />
        <span className="text-xs" style={{ color: "var(--color-sentinel-text-disabled)" }}>
          Breach started {getRelativeTime(breach.breach_time)}
        </span>
      </div>
    </div>
  );
}

interface FreshnessAlertPanelProps {
  onDismiss?: (breachId: string) => void;
}

export function FreshnessAlertPanel({ onDismiss: _onDismiss }: FreshnessAlertPanelProps) {
  const [breaches, setBreaches] = useState<FreshnessBreach[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchBreaches = useCallback(async () => {
    try {
      const sentryToken = getAccessToken();
      if (!sentryToken) {
        setError("Not authenticated");
        setLoading(false);
        return;
      }

      const res = await fetch(`${window.location.origin}/api/sentry/freshness/breaches`, {
        headers: {
          "Authorization": `Bearer ${sentryToken}`,
          "X-Sentry-API-Key": "sentry-bot-RncXWQCYticUnuG06L4qnSUj-heKAeV0NnMdHOvIlKM3TNUv",
          "X-Sentry-Secret": "sentry-bms-phase-41",
        },
      });

      if (!res.ok) {
        throw new Error(`HTTP ${res.status}`);
      }

      const data = await res.json();
      setBreaches(data.breaches || []);
      setError(null);
    } catch (err) {
      console.error("Failed to fetch freshness breaches:", err);
      setError("Failed to load freshness data");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchBreaches();
    const interval = setInterval(fetchBreaches, 60000);
    return () => clearInterval(interval);
  }, [fetchBreaches]);

  if (loading && breaches.length === 0) {
    return (
      <div className="p-4 text-center">
        <RefreshCw
          className="h-5 w-5 mx-auto animate-spin"
          style={{ color: "var(--color-sentinel-text-disabled)" }}
        />
        <p className="text-xs mt-2" style={{ color: "var(--color-sentinel-text-secondary)" }}>
          Checking data freshness...
        </p>
      </div>
    );
  }

  if (error) {
    return (
      <div className="p-4">
        <div
          className="flex items-center gap-2 p-3 rounded"
          style={{
            background: "rgba(220, 38, 38, 0.1)",
            border: "1px solid rgba(220, 38, 38, 0.3)",
          }}
        >
          <WifiOff className="h-4 w-4" style={{ color: "var(--color-status-error)" }} />
          <span className="text-xs" style={{ color: "var(--color-status-error)" }}>
            {error}
          </span>
        </div>
      </div>
    );
  }

  if (breaches.length === 0) {
    return (
      <div className="p-4 text-center">
        <p className="text-xs" style={{ color: "var(--color-sentinel-text-secondary)" }}>
          All data sources are fresh
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-2 p-2">
      <div className="px-2 py-1">
        <p className="text-xs font-medium" style={{ color: "var(--color-sentinel-text-primary)" }}>
          Data Freshness Issues
        </p>
        <p className="text-[10px]" style={{ color: "var(--color-sentinel-text-secondary)" }}>
          S002 backend may be offline
        </p>
      </div>
      {breaches.map((breach) => (
        <FreshnessAlertCard key={breach.id} breach={breach} />
      ))}
    </div>
  );
}
