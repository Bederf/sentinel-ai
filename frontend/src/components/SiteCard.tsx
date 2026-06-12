/**
 * SiteCard — Dashboard card for a single site/building.
 *
 * Displays: site name, location, type badge, equipment count, risk count,
 * status badge (Protected/Elevated/Critical), safety summary, and optimization status.
 */

import { type Site } from "@/lib/api";
import { api } from "@/lib/api";
import { useSiteSummary } from "@/hooks/useSiteSummary";
import { Shield, AlertTriangle, TrendingUp, Wifi, WifiOff, AlertOctagon, Siren, ShieldOff } from "lucide-react";
import { useState, useEffect } from "react";

interface SiteCardProps {
  site: Site;
  onClick?: (site: Site) => void;
  showSafetyStatus?: boolean;
  showOptimizationStatus?: boolean;
  onEquipmentControlNavigate?: (equipmentId: string, siteId: string) => void;
}

function StatusBadge({ status }: { status: string }) {
  const config: Record<string, { label: string; color: string; bg: string }> = {
    normal:   { label: "Protected", color: "var(--color-sentinel-green)",  bg: "color-mix(in oklch, var(--color-sentinel-green) 15%, transparent)"  },
    warning:  { label: "Elevated",  color: "var(--color-sentinel-amber)", bg: "color-mix(in oklch, var(--color-sentinel-amber) 15%, transparent)" },
    critical: { label: "Critical",  color: "var(--color-sentinel-red)",    bg: "color-mix(in oklch, var(--color-sentinel-red) 15%, transparent)"    },
    healthy:  { label: "Protected", color: "var(--color-sentinel-green)",  bg: "color-mix(in oklch, var(--color-sentinel-green) 15%, transparent)"  },
    degraded: { label: "Elevated",  color: "var(--color-sentinel-amber)", bg: "color-mix(in oklch, var(--color-sentinel-amber) 15%, transparent)" },
    at_risk:  { label: "Critical",  color: "var(--color-sentinel-red)",    bg: "color-mix(in oklch, var(--color-sentinel-red) 15%, transparent)"    },
  };
  const cfg = config[status] ?? config.normal;
  return (
    <span
      style={{ color: cfg.color, background: cfg.bg }}
      className="px-2 py-0.5 rounded text-xs font-medium"
    >
      {cfg.label}
    </span>
  );
}

interface OptimizationStatusProps {
  siteId: string;
  enabled: boolean;
}

function OptimizationStatus({ siteId, enabled }: OptimizationStatusProps) {
  const [status, setStatus] = useState<{
    state: string;
    last: string | null;
  } | null>(null);

  useEffect(() => {
    if (!enabled) return;
    api.getOptimizationStatus(siteId)
      .then((r) =>
        setStatus({
          state: r.optimization_status ?? "unknown",
          last: r.last_optimization ?? null,
        })
      )
      .catch(() => null);
  }, [siteId, enabled]);

  if (!enabled) return null;

  const color =
    status?.state === "optimized"
      ? "var(--color-sentinel-green)"
      : status?.state === "optimizing"
      ? "var(--color-sentinel-amber)"
      : status?.state === "recommendation_pending"
      ? "var(--color-sentinel-amber)"
      : status?.state === "learning"
      ? "var(--color-sentinel-blue)"
      : status?.state === "error"
      ? "var(--color-sentinel-red)"
      : status?.state === "supervised"
      ? "var(--color-sentinel-amber)"
      : status?.state === "automatic"
      ? "var(--color-sentinel-green)"
      : status?.state === "advisory"
      ? "var(--color-sentinel-blue)"
      : status?.state === "active"
      ? "var(--color-sentinel-green)"
      : "var(--color-sentinel-text-secondary)";
  const label =
    status?.state === "optimized"
      ? "Optimised"
      : status?.state === "optimizing"
      ? "Optimising..."
      : status?.state === "recommendation_pending"
      ? "Action required"
      : status?.state === "learning"
      ? "Learning"
      : status?.state === "disabled"
      ? "Paused"
      : status?.state === "error"
      ? "Attention needed"
      : status?.state === "supervised"
      ? "Supervised"
      : status?.state === "automatic"
      ? "Automatic"
      : status?.state === "advisory"
      ? "Advisory"
      : status?.state === "active"
      ? "Monitoring"
      : "Pending";

  return (
    <div className="flex items-center gap-1 text-xs" style={{ color }}>
      <TrendingUp className="w-3 h-3" />
      <span>{label}</span>
    </div>
  );
}

export function SiteCard({
  site,
  onClick,
  showSafetyStatus = false,
  showOptimizationStatus = false,
}: SiteCardProps) {
  const { data: summary, isLoading } = useSiteSummary(site.id, {
    enabled: showSafetyStatus,
  });

  const safeCount = summary?.safety?.safe ?? site.equipment_count - site.alert_count;
  const totalCount = summary?.equipment_count ?? site.equipment_count;

  const safeFraction =
    totalCount > 0 ? `${safeCount}/${totalCount}` : `${site.equipment_count}`;

  const isBridgeDegraded =
    site.bridge_connected === false &&
    site.bridge_data_source !== undefined &&
    site.bridge_data_source !== "none";

  const effectiveStatus = isBridgeDegraded ? "degraded" : (site.status ?? "normal");

  const statusBorderColor: Record<string, string> = {
    normal:  "var(--color-sentinel-green)",
    warning: "var(--color-sentinel-amber)",
    critical:"var(--color-sentinel-red)",
    healthy: "var(--color-sentinel-green)",
    degraded:"var(--color-sentinel-amber)",
    at_risk: "var(--color-sentinel-red)",
  };
  const borderColor = statusBorderColor[effectiveStatus] ?? "var(--color-sentinel-border)";

  return (
    <div
      role={onClick ? "button" : undefined}
      tabIndex={onClick ? 0 : undefined}
      onClick={onClick ? () => onClick(site) : undefined}
      onKeyDown={onClick ? (e) => e.key === "Enter" && onClick(site) : undefined}
      className={`relative overflow-hidden${onClick ? " cursor-pointer hover:brightness-110 transition-all" : ""}`}
      aria-label={`${site.name}${onClick ? ', click to view details' : ''}`}
      style={{
        background: "var(--color-sentinel-bg-panel)",
        border: `1px solid ${borderColor}`,
        borderRadius: "8px",
        padding: "16px",
        paddingTop: "20px",
        display: "flex",
        flexDirection: "column",
        gap: "8px",
      }}
    >
      {/* Status accent bar — thicker to match KPI card styling */}
      <div
        className="absolute top-0 left-0 right-0 h-1.5"
        style={{ background: borderColor }}
      />
      {/* Header */}
      <div className="flex items-start justify-between gap-2">
        <div className="flex-1 min-w-0">
          <h4
            className="font-medium text-sm truncate"
            style={{ color: "var(--color-sentinel-text-primary)" }}
          >
            {site.name}
          </h4>
          {site.location && (
            <p
              className="text-xs truncate"
              style={{ color: "var(--color-sentinel-text-secondary)" }}
            >
              {site.location}
            </p>
          )}
        </div>
        <StatusBadge status={effectiveStatus} />
      </div>

      {/* Type badge */}
      {site.type && (
        <span
          className="self-start px-2 py-0.5 rounded text-xs"
          style={{
            background: "var(--color-sentinel-bg-secondary)",
            border: "1px solid var(--color-sentinel-border)",
            color: "var(--color-sentinel-text-secondary)",
          }}
        >
          {site.type}
        </span>
      )}

      {/* Stats */}
      <div className="flex gap-4">
        <div className="flex items-center gap-1.5">
          <Shield className="w-3.5 h-3.5" style={{ color: "var(--color-sentinel-text-secondary)" }} />
          <span className="text-sm font-medium" style={{ color: "var(--color-sentinel-text-primary)" }}>
            {site.equipment_count}
          </span>
          <span className="text-xs" style={{ color: "var(--color-sentinel-text-secondary)" }}>
            Equipment
          </span>
        </div>
        <div className="flex items-center gap-1.5">
          <AlertTriangle
            className="w-3.5 h-3.5"
            style={{ color: site.alert_count > 0 ? "var(--color-sentinel-amber)" : "var(--color-sentinel-text-secondary)" }}
          />
          <span
            className="text-sm font-medium"
            style={{
              color: site.alert_count > 0 ? "var(--color-sentinel-amber)" : "var(--color-sentinel-text-primary)",
            }}
          >
            {site.alert_count}
          </span>
          <span className="text-xs" style={{ color: "var(--color-sentinel-text-secondary)" }}>
            Risks
          </span>
        </div>
      </div>

      {/* Safety status */}
      {showSafetyStatus && (
        <div className="flex items-center gap-2">
          {isLoading ? (
            <span className="text-xs" style={{ color: "var(--color-sentinel-text-disabled)" }}>
              Loading...
            </span>
          ) : (
            <>
              <span
                className="text-xs font-medium"
                style={{ color: "var(--color-sentinel-text-primary)" }}
              >
                {safeFraction}
              </span>
              <span className="text-xs" style={{ color: "var(--color-sentinel-text-secondary)" }}>
                Safe
              </span>
              {summary?.safety && (
                <div className="flex gap-1.5 ml-auto">
                  {summary.safety.warning > 0 && (
                    <span className="inline-flex items-center gap-0.5 text-xs" style={{ color: "var(--color-sentinel-amber)" }} aria-label={`${summary.safety.warning} warning`}>
                      {summary.safety.warning}<AlertOctagon className="w-3 h-3" aria-hidden="true" />
                    </span>
                  )}
                  {summary.safety.alarm > 0 && (
                    <span className="inline-flex items-center gap-0.5 text-xs" style={{ color: "var(--color-sentinel-red)" }} aria-label={`${summary.safety.alarm} alarm`}>
                      {summary.safety.alarm}<Siren className="w-3 h-3" aria-hidden="true" />
                    </span>
                  )}
                  {summary.safety.blocked > 0 && (
                    <span className="inline-flex items-center gap-0.5 text-xs" style={{ color: "var(--color-sentinel-purple)" }} aria-label={`${summary.safety.blocked} blocked`}>
                      {summary.safety.blocked}<ShieldOff className="w-3 h-3" aria-hidden="true" />
                    </span>
                  )}
                </div>
              )}
            </>
          )}
        </div>
      )}

      {/* Optimization status */}
      <OptimizationStatus
        siteId={site.id}
        enabled={showOptimizationStatus ?? site.optimization_enabled ?? false}
      />

      {/* Bridge connection indicator */}
      {site.bridge_connected !== undefined && (
        <div
          className="flex items-center gap-1.5"
          title={
            site.bridge_connected
              ? "Live telemetry flowing from BMS protocol adapters"
              : "No live telemetry from BMS bridge — alerts reflect last known state only. Site monitoring is degraded."
          }
        >
          {site.bridge_connected ? (
            <Wifi className="w-3.5 h-3.5" style={{ color: "var(--color-sentinel-green)" }} />
          ) : (
            <WifiOff className="w-3.5 h-3.5" style={{ color: "var(--color-sentinel-red)" }} />
          )}
          <span
            className="text-xs"
            style={{
              color: site.bridge_connected ? "var(--color-sentinel-green)" : "var(--color-sentinel-red)",
            }}
          >
            {site.bridge_connected ? "Bridge connected" : "Bridge offline"}
          </span>
          {site.bridge_last_sync && (
            <span className="text-xs" style={{ color: "var(--color-sentinel-text-disabled)" }}>
              · {new Date(site.bridge_last_sync).toLocaleTimeString()}
            </span>
          )}
          {!site.bridge_connected && site.bridge_sync_error && (
            <span
              className="text-xs truncate max-w-[120px]"
              style={{ color: "var(--color-sentinel-red)" }}
              title={site.bridge_sync_error}
            >
              · {site.bridge_sync_error}
            </span>
          )}
        </div>
      )}
    </div>
  );
}

export default SiteCard;
