/**
 * SiteCard Component - SENTINEL site panel
 *
 * Displays:
 * - Site name with protection status indicator
 * - Location and type information
 * - Equipment count metric
 * - Risk alerts with severity coloring
 * - Safety status indicators
 * - Status-based left border accent
 *
 * Follows SENTINEL dark theme design.
 */

import { Building2, Cpu, AlertTriangle, MapPin, Shield } from "lucide-react";
import { useState, useEffect } from "react";
import api, { type Site } from "../lib/api";

interface SiteCardProps {
  site: Site;
  onClick?: (site: Site) => void;
  showSafetyStatus?: boolean;
}

type SafetyStatus = 'safe' | 'warning' | 'blocked' | 'alarm' | 'unknown';

interface DeviceSafetySummary {
  total: number;
  safe: number;
  warning: number;
  blocked: number;
  alarm: number;
  overallStatus: SafetyStatus;
}

/**
 * Get status colors for SENTINEL theme
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
        color: "var(--color-sentinel-green)",
        bg: "rgba(16, 185, 129, 0.15)",
        border: "rgba(16, 185, 129, 0.5)",
        label: "Protected",
      };
    case "warning":
      return {
        color: "var(--color-sentinel-amber)",
        bg: "rgba(245, 158, 11, 0.15)",
        border: "rgba(245, 158, 11, 0.5)",
        label: "Elevated",
      };
    case "critical":
      return {
        color: "var(--color-sentinel-red)",
        bg: "rgba(220, 38, 38, 0.15)",
        border: "rgba(220, 38, 38, 0.5)",
        label: "Critical",
      };
    default:
      return {
        color: "var(--color-sentinel-text-secondary)",
        bg: "rgba(142, 142, 142, 0.15)",
        border: "rgba(142, 142, 142, 0.5)",
        label: "Unknown",
      };
  }
}

export function SiteCard({ site, onClick, showSafetyStatus = true }: SiteCardProps) {
  const statusConfig = getStatusConfig(site.status);
  const hasAlerts = site.alert_count > 0;
  const [safetySummary, setSafetySummary] = useState<DeviceSafetySummary | null>(null);
  const [loadingSafety, setLoadingSafety] = useState(false);

  const handleClick = () => {
    if (onClick) {
      onClick(site);
    }
  };

  // Fetch safety status for devices at this site
  useEffect(() => {
    if (!showSafetyStatus) return;

    const fetchSafetyStatus = async () => {
      setLoadingSafety(true);
      try {
        // Get devices for this site
        const devices = await api.getSiteDevices(site.id);

        if (devices.length === 0) {
          setSafetySummary({
            total: 0,
            safe: 0,
            warning: 0,
            blocked: 0,
            alarm: 0,
            overallStatus: 'unknown',
          });
          return;
        }

        // Fetch safety status for a sample of devices (limit to 5 for performance)
        const sampleDevices = devices.slice(0, 5);
        const statusPromises = sampleDevices.map(async (device) => {
          try {
            const status = await api.getDeviceSafetyStatus(device.id);
            return status.overall_status;
          } catch {
            return 'unknown' as SafetyStatus;
          }
        });

        const statuses = await Promise.all(statusPromises);

        const summary: DeviceSafetySummary = {
          total: devices.length,
          safe: statuses.filter((s) => s === 'safe').length,
          warning: statuses.filter((s) => s === 'warning').length,
          blocked: statuses.filter((s) => s === 'blocked').length,
          alarm: statuses.filter((s) => s === 'alarm').length,
          overallStatus: 'unknown',
        };

        // Determine overall status
        if (summary.blocked > 0) {
          summary.overallStatus = 'blocked';
        } else if (summary.alarm > 0) {
          summary.overallStatus = 'alarm';
        } else if (summary.warning > 0) {
          summary.overallStatus = 'warning';
        } else if (summary.safe > 0) {
          summary.overallStatus = 'safe';
        }

        setSafetySummary(summary);
      } catch (error) {
        console.error('Failed to fetch safety status:', error);
        setSafetySummary(null);
      } finally {
        setLoadingSafety(false);
      }
    };

    fetchSafetyStatus();
  }, [site.id, showSafetyStatus]);

  return (
    <div
      className={`relative rounded-md overflow-hidden transition-all duration-150 ${onClick ? "cursor-pointer hover:brightness-110" : ""}`}
      style={{
        background: "var(--color-sentinel-bg-panel)",
        border: "1px solid var(--color-sentinel-border)",
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
              style={{ color: "var(--color-sentinel-blue)" }}
            />
            <span
              className="font-medium text-sm"
              style={{ color: "var(--color-sentinel-text-primary)" }}
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
            style={{ color: "var(--color-sentinel-text-disabled)" }}
          />
          <span
            className="text-xs"
            style={{ color: "var(--color-sentinel-text-secondary)" }}
          >
            {site.location}
          </span>
        </div>

        {/* Type badge */}
        <div
          className="inline-block px-2 py-0.5 rounded text-xs mb-3"
          style={{
            background: "var(--color-sentinel-bg-secondary)",
            color: "var(--color-sentinel-text-secondary)",
            border: "1px solid var(--color-sentinel-border)",
          }}
        >
          {site.type}
        </div>

        {/* Stats Row */}
        <div
          className="flex items-center justify-between pt-3"
          style={{ borderTop: "1px solid var(--color-sentinel-border)" }}
        >
          {/* Equipment Count */}
          <div className="flex items-center gap-2">
            <Cpu
              className="h-4 w-4"
              style={{ color: "var(--color-sentinel-blue)" }}
            />
            <div>
              <div
                className="text-lg font-medium"
                style={{
                  color: "var(--color-sentinel-text-primary)",
                  fontVariantNumeric: "tabular-nums",
                }}
              >
                {site.equipment_count}
              </div>
              <div
                className="text-xs"
                style={{ color: "var(--color-sentinel-text-disabled)" }}
              >
                Assets
              </div>
            </div>
          </div>

          {/* Safety Status */}
          {showSafetyStatus && (
            <div className="flex items-center gap-2">
              <Shield
                className="h-4 w-4"
                style={{
                  color: safetySummary?.overallStatus === 'safe'
                    ? "var(--color-sentinel-green)"
                    : safetySummary?.overallStatus === 'warning'
                    ? "var(--color-sentinel-amber)"
                    : safetySummary?.overallStatus === 'blocked' || safetySummary?.overallStatus === 'alarm'
                    ? "var(--color-sentinel-red)"
                    : "var(--color-sentinel-text-disabled)",
                }}
              />
              <div className="text-right">
                {loadingSafety ? (
                  <div
                    className="text-lg font-medium"
                    style={{
                      color: "var(--color-sentinel-text-disabled)",
                      fontVariantNumeric: "tabular-nums",
                    }}
                  >
                    ...
                  </div>
                ) : safetySummary ? (
                  <>
                    <div
                      className="text-lg font-medium"
                      style={{
                        color: safetySummary.overallStatus === 'safe'
                          ? "var(--color-sentinel-green)"
                          : safetySummary.overallStatus === 'warning'
                          ? "var(--color-sentinel-amber)"
                          : safetySummary.overallStatus === 'blocked' || safetySummary.overallStatus === 'alarm'
                          ? "var(--color-sentinel-red)"
                          : "var(--color-sentinel-text-primary)",
                        fontVariantNumeric: "tabular-nums",
                      }}
                    >
                      {safetySummary.safe}/{safetySummary.total}
                    </div>
                    <div
                      className="text-xs"
                      style={{ color: "var(--color-sentinel-text-disabled)" }}
                    >
                      Safe
                    </div>
                  </>
                ) : (
                  <div
                    className="text-xs"
                    style={{ color: "var(--color-sentinel-text-disabled)" }}
                  >
                    No data
                  </div>
                )}
              </div>
            </div>
          )}

          {/* Risk Alert Count */}
          <div className="flex items-center gap-2">
            <AlertTriangle
              className="h-4 w-4"
              style={{
                color: hasAlerts
                  ? "var(--color-sentinel-amber)"
                  : "var(--color-sentinel-text-disabled)",
              }}
            />
            <div className="text-right">
              <div
                className="text-lg font-medium"
                style={{
                  color: hasAlerts
                    ? "var(--color-sentinel-amber)"
                    : "var(--color-sentinel-text-primary)",
                  fontVariantNumeric: "tabular-nums",
                }}
              >
                {site.alert_count}
              </div>
              <div
                className="text-xs"
                style={{ color: "var(--color-sentinel-text-disabled)" }}
              >
                Risks
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

export default SiteCard;
