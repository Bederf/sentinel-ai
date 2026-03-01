import { useState, useEffect } from "react";
import { AlertTriangle, Clock, Activity } from "lucide-react";
import { securityApi } from "../lib/api";

export interface SecurityAnomaly {
  type: string;
  severity: "critical" | "warning" | "info";
  badge_event?: {
    person_name: string;
    department?: string;
    timestamp: string;
  };
  recommendation: string;
  energy_impact?: string;
  detected_at: string;
}

export interface SecurityAnomaliesPanelProps {
  siteId?: string;
  refreshKey?: number;
}

export function SecurityAnomaliesPanel({
  siteId = "",
  refreshKey = 0,
}: SecurityAnomaliesPanelProps) {
  const [anomalies, setAnomalies] = useState<SecurityAnomaly[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetchAnomalies();
  }, [refreshKey, siteId]);

  const fetchAnomalies = async () => {
    try {
      const data = await securityApi.getAnomalies(siteId, 1);
      setAnomalies(data.anomalies || []);
    } catch (error) {
      console.error("Failed to fetch security anomalies:", error);
    } finally {
      setLoading(false);
    }
  };

  const getSeverityColor = (severity: string) => {
    switch (severity) {
      case "critical":
        return "var(--color-sentinel-red)";
      case "warning":
        return "var(--color-sentinel-amber)";
      default:
        return "var(--color-sentinel-blue)";
    }
  };

  const getAnomalyIcon = (type: string) => {
    switch (type) {
      case "after_hours_access":
        return <Clock className="h-4 w-4" />;
      case "controller_offline":
        return <Activity className="h-4 w-4" />;
      default:
        return <AlertTriangle className="h-4 w-4" />;
    }
  };

  const formatTime = (isoString: string) => {
    try {
      return new Date(isoString).toLocaleString();
    } catch {
      return isoString;
    }
  };

  return (
    <div
      className="rounded-md"
      style={{
        background: "var(--color-sentinel-bg-panel)",
        border: "1px solid var(--color-sentinel-border)",
      }}
    >
      <div
        className="p-4 border-b"
        style={{
          borderColor: "var(--color-sentinel-border)",
        }}
      >
        <div className="flex items-center justify-between">
          <h3
            className="font-semibold"
            style={{
              color: "var(--color-sentinel-text-primary)",
            }}
          >
            Security Anomalies (24h)
          </h3>
          <span
            className="text-xs px-2 py-1 rounded"
            style={{
              background:
                anomalies.length > 0
                  ? "rgba(239, 68, 68, 0.15)"
                  : "rgba(34, 197, 94, 0.15)",
              color:
                anomalies.length > 0
                  ? "var(--color-sentinel-red)"
                  : "var(--color-sentinel-green)",
            }}
          >
            {anomalies.length} detected
          </span>
        </div>
      </div>

      <div
        className="divide-y"
        style={{
          borderColor: "var(--color-sentinel-border)",
        }}
      >
        {loading ? (
          <div
            className="px-4 py-8 text-center text-sm"
            style={{
              color: "var(--color-sentinel-text-disabled)",
            }}
          >
            Loading anomalies...
          </div>
        ) : anomalies.length === 0 ? (
          <div
            className="px-4 py-8 text-center text-sm"
            style={{
              color: "var(--color-sentinel-text-disabled)",
            }}
          >
            No security anomalies detected in the last 24 hours
          </div>
        ) : (
          anomalies.map((anomaly, idx) => (
            <div key={idx} className="px-4 py-3 hover:bg-opacity-50 transition-colors">
              <div className="flex items-start justify-between gap-3">
                <div className="flex items-start gap-3 flex-1">
                  <div style={{ color: getSeverityColor(anomaly.severity) }}>
                    {getAnomalyIcon(anomaly.type)}
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 mb-1">
                      <span
                        className="font-medium text-sm"
                        style={{
                          color: "var(--color-sentinel-text-primary)",
                        }}
                      >
                        {anomaly.type === "after_hours_access"
                          ? "After-Hours Access"
                          : "Controller Offline"}
                      </span>
                      <span
                        className="text-xs px-2 py-0.5 rounded"
                        style={{
                          background: `${getSeverityColor(anomaly.severity)}20`,
                          color: getSeverityColor(anomaly.severity),
                          border: `1px solid ${getSeverityColor(anomaly.severity)}40`,
                        }}
                      >
                        {anomaly.severity}
                      </span>
                    </div>

                    {anomaly.badge_event && (
                      <div
                        className="text-xs mb-2"
                        style={{
                          color: "var(--color-sentinel-text-secondary)",
                        }}
                      >
                        {anomaly.badge_event.person_name} •{" "}
                        {anomaly.badge_event.department} •
                        {formatTime(anomaly.badge_event.timestamp)}
                      </div>
                    )}

                    <div
                      className="text-sm mb-2"
                      style={{
                        color: "var(--color-sentinel-text-primary)",
                      }}
                    >
                      {anomaly.recommendation}
                    </div>

                    {anomaly.energy_impact && (
                      <div
                        className="text-xs"
                        style={{
                          color: "var(--color-sentinel-text-disabled)",
                        }}
                      >
                        ⚡ {anomaly.energy_impact}
                      </div>
                    )}
                  </div>
                </div>
              </div>
            </div>
          ))
        )}
      </div>
    </div>
  );
}
