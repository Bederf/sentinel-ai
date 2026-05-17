/**
 * SiteCard — Dashboard card for a single site/building.
 *
 * Displays: site name, location, type badge, equipment count, risk count,
 * status badge (Protected/Elevated/Critical), safety summary, and optimization status.
 */

import { type Site } from "@/lib/api";
import { api } from "@/lib/api";
import { useSiteSummary } from "@/hooks/useSiteSummary";
import { Shield, AlertTriangle, TrendingUp, Wifi, WifiOff } from "lucide-react";
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
    normal: { label: "Protected", color: "var(--color-sentinel-green)", bg: "rgba(34,197,94,0.15)" },
    warning: { label: "Elevated", color: "var(--color-sentinel-amber)", bg: "rgba(245,158,11,0.15)" },
    critical: { label: "Critical", color: "var(--color-sentinel-red)", bg: "rgba(239,68,68,0.15)" },
    healthy: { label: "Protected", color: "var(--color-sentinel-green)", bg: "rgba(34,197,94,0.15)" },
    degraded: { label: "Elevated", color: "var(--color-sentinel-amber)", bg: "rgba(245,158,11,0.15)" },
    at_risk: { label: "Critical", color: "var(--color-sentinel-red)", bg: "rgba(239,68,68,0.15)" },
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

  return (
    <div
      role={onClick ? "button" : undefined}
      tabIndex={onClick ? 0 : undefined}
      onClick={onClick ? () => onClick(site) : undefined}
      onKeyDown={onClick ? (e) => e.key === "Enter" && onClick(site) : undefined}
      className={onClick ? "cursor-pointer hover:brightness-110 transition-all" : ""}
      style={{
        background: "var(--color-grafana-bg-panel)",
        border: "1px solid var(--color-grafana-border)",
        borderRadius: "8px",
        padding: "16px",
        display: "flex",
        flexDirection: "column",
        gap: "8px",
      }}
    >
      {/* Header */}
      <div className="flex items-start justify-between gap-2">
        <div className="flex-1 min-w-0">
          <h4
            className="font-medium text-sm truncate"
            style={{ color: "var(--color-grafana-text-primary)" }}
          >
            {site.name}
          </h4>
          {site.location && (
            <p
              className="text-xs truncate"
              style={{ color: "var(--color-grafana-text-secondary)" }}
            >
              {site.location}
            </p>
          )}
        </div>
        <StatusBadge status={site.status ?? "normal"} />
      </div>

      {/* Type badge */}
      {site.type && (
        <span
          className="self-start px-2 py-0.5 rounded text-xs"
          style={{
            background: "var(--color-grafana-bg-secondary)",
            border: "1px solid var(--color-grafana-border)",
            color: "var(--color-grafana-text-secondary)",
          }}
        >
          {site.type}
        </span>
      )}

      {/* Stats */}
      <div className="flex gap-4">
        <div className="flex items-center gap-1.5">
          <Shield className="w-3.5 h-3.5" style={{ color: "var(--color-grafana-text-secondary)" }} />
          <span className="text-sm font-medium" style={{ color: "var(--color-grafana-text-primary)" }}>
            {site.equipment_count}
          </span>
          <span className="text-xs" style={{ color: "var(--color-grafana-text-secondary)" }}>
            Equipment
          </span>
        </div>
        <div className="flex items-center gap-1.5">
          <AlertTriangle
            className="w-3.5 h-3.5"
            style={{ color: site.alert_count > 0 ? "var(--color-sentinel-amber)" : "var(--color-grafana-text-secondary)" }}
          />
          <span
            className="text-sm font-medium"
            style={{
              color: site.alert_count > 0 ? "var(--color-sentinel-amber)" : "var(--color-grafana-text-primary)",
            }}
          >
            {site.alert_count}
          </span>
          <span className="text-xs" style={{ color: "var(--color-grafana-text-secondary)" }}>
            Risks
          </span>
        </div>
      </div>

      {/* Safety status */}
      {showSafetyStatus && (
        <div className="flex items-center gap-2">
          {isLoading ? (
            <span className="text-xs" style={{ color: "var(--color-grafana-text-disabled)" }}>
              Loading...
            </span>
          ) : (
            <>
              <span
                className="text-xs font-medium"
                style={{ color: "var(--color-grafana-text-primary)" }}
              >
                {safeFraction}
              </span>
              <span className="text-xs" style={{ color: "var(--color-grafana-text-secondary)" }}>
                Safe
              </span>
              {summary?.safety && (
                <div className="flex gap-1.5 ml-auto">
                  {summary.safety.warning > 0 && (
                    <span className="text-xs" style={{ color: "var(--color-sentinel-amber)" }}>
                      {summary.safety.warning}⚠
                    </span>
                  )}
                  {summary.safety.alarm > 0 && (
                    <span className="text-xs" style={{ color: "var(--color-sentinel-red)" }}>
                      {summary.safety.alarm}🔴
                    </span>
                  )}
                  {summary.safety.blocked > 0 && (
                    <span className="text-xs" style={{ color: "var(--color-sentinel-purple)" }}>
                      {summary.safety.blocked}🚫
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
        <div className="flex items-center gap-1.5">
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
            <span className="text-xs" style={{ color: "var(--color-grafana-text-disabled)" }}>
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
