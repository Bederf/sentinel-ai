/**
 * SiteCard Component - Grafana-inspired site panel
 *
 * Displays:
 * - Site name with status indicator dot
 * - Location and type information
 * - Equipment count metric
 * - Alert count with severity coloring
 * - Status-based left border accent
 *
 * Follows Grafana panel design with dark theme.
 */

import { Building2, Cpu, AlertTriangle, MapPin } from "lucide-react";
import type { Site } from "../lib/api";

interface SiteCardProps {
  site: Site;
  onClick?: (site: Site) => void;
}

/**
 * Get status colors for Grafana theme
 */
function getStatusConfig(status: Site["status"]): {
  color: string;
  bg: string;
  border: string;
  label: string;
} {
  switch (status) {
    case "normal":
      return {
        color: "var(--color-status-success)",
        bg: "rgba(115, 191, 105, 0.15)",
        border: "rgba(115, 191, 105, 0.5)",
        label: "Healthy",
      };
    case "warning":
      return {
        color: "var(--color-status-warning)",
        bg: "rgba(255, 152, 48, 0.15)",
        border: "rgba(255, 152, 48, 0.5)",
        label: "Warning",
      };
    case "critical":
      return {
        color: "var(--color-status-error)",
        bg: "rgba(242, 73, 92, 0.15)",
        border: "rgba(242, 73, 92, 0.5)",
        label: "Critical",
      };
    default:
      return {
        color: "var(--color-grafana-text-secondary)",
        bg: "rgba(142, 142, 142, 0.15)",
        border: "rgba(142, 142, 142, 0.5)",
        label: "Unknown",
      };
  }
}

export function SiteCard({ site, onClick }: SiteCardProps) {
  const statusConfig = getStatusConfig(site.status);
  const hasAlerts = site.alert_count > 0;

  const handleClick = () => {
    if (onClick) {
      onClick(site);
    }
  };

  return (
    <div
      className={`relative rounded overflow-hidden transition-all duration-150 ${onClick ? "cursor-pointer hover:brightness-110" : ""}`}
      style={{
        background: "var(--color-grafana-bg-panel)",
        border: "1px solid var(--color-grafana-border)",
      }}
      onClick={handleClick}
    >
      {/* Left status accent bar */}
      <div
        className="absolute left-0 top-0 bottom-0 w-1"
        style={{ background: statusConfig.color }}
      />

      <div className="p-4 pl-5">
        {/* Header: Name and Status */}
        <div className="flex items-start justify-between mb-2">
          <div className="flex items-center gap-2">
            <Building2
              className="h-4 w-4"
              style={{ color: "var(--color-grafana-blue)" }}
            />
            <span
              className="font-medium text-sm"
              style={{ color: "var(--color-grafana-text-primary)" }}
            >
              {site.name}
            </span>
          </div>
          {/* Status badge */}
          <div
            className="flex items-center gap-1.5 px-2 py-0.5 rounded text-xs font-medium"
            style={{
              background: statusConfig.bg,
              color: statusConfig.color,
            }}
          >
            <div
              className="w-1.5 h-1.5 rounded-full"
              style={{ background: statusConfig.color }}
            />
            {statusConfig.label}
          </div>
        </div>

        {/* Location */}
        <div className="flex items-center gap-1.5 mb-3">
          <MapPin
            className="h-3 w-3"
            style={{ color: "var(--color-grafana-text-disabled)" }}
          />
          <span
            className="text-xs"
            style={{ color: "var(--color-grafana-text-secondary)" }}
          >
            {site.location}
          </span>
        </div>

        {/* Type badge */}
        <div
          className="inline-block px-2 py-0.5 rounded text-xs mb-3"
          style={{
            background: "var(--color-grafana-bg-secondary)",
            color: "var(--color-grafana-text-secondary)",
            border: "1px solid var(--color-grafana-border)",
          }}
        >
          {site.type}
        </div>

        {/* Stats Row */}
        <div
          className="flex items-center justify-between pt-3"
          style={{ borderTop: "1px solid var(--color-grafana-border)" }}
        >
          {/* Equipment Count */}
          <div className="flex items-center gap-2">
            <Cpu
              className="h-4 w-4"
              style={{ color: "var(--color-grafana-cyan)" }}
            />
            <div>
              <div
                className="text-lg font-medium"
                style={{
                  color: "var(--color-grafana-text-primary)",
                  fontVariantNumeric: "tabular-nums",
                }}
              >
                {site.equipment_count}
              </div>
              <div
                className="text-xs"
                style={{ color: "var(--color-grafana-text-disabled)" }}
              >
                Equipment
              </div>
            </div>
          </div>

          {/* Alert Count */}
          <div className="flex items-center gap-2">
            <AlertTriangle
              className="h-4 w-4"
              style={{
                color: hasAlerts
                  ? "var(--color-status-warning)"
                  : "var(--color-grafana-text-disabled)",
              }}
            />
            <div className="text-right">
              <div
                className={`text-lg font-medium ${hasAlerts ? "" : ""}`}
                style={{
                  color: hasAlerts
                    ? "var(--color-status-warning)"
                    : "var(--color-grafana-text-primary)",
                  fontVariantNumeric: "tabular-nums",
                }}
              >
                {site.alert_count}
              </div>
              <div
                className="text-xs"
                style={{ color: "var(--color-grafana-text-disabled)" }}
              >
                Alerts
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

export default SiteCard;
