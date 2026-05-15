/**
 * Anomaly Detection Dashboard
 *
 * Shows anomaly status for all monitored equipment with
 * severity indicators and score visualization.
 */

import { useEffect, useState } from "react";

import {
  AlertTriangle,
  CheckCircle,
  RefreshCw,
} from "lucide-react";
import type { AnomalyResult, MLHealth } from "../../lib/mlApi";
import {
  getAllAnomalies,
  getAnomalyAlerts,
  getMLHealth,
  getSeverityColor,
  getSeverityBadge,
} from "../../lib/mlApi";

interface AnomalyDashboardProps {
  refreshInterval?: number;
}

const severityBgColor = (severity: string): string => {
  const tremorColor = getSeverityColor(severity as AnomalyResult["severity"]);
  const map: Record<string, string> = {
    red: 'rgba(220,38,38,0.15)',
    orange: 'rgba(245,158,11,0.15)',
    yellow: 'rgba(245,158,11,0.15)',
    green: 'rgba(16,185,129,0.15)',
    gray: 'rgba(139,148,158,0.15)',
  };
  return map[tremorColor] || 'rgba(139,148,158,0.15)';
};

const severityTextColor = (severity: string): string => {
  const tremorColor = getSeverityColor(severity as AnomalyResult["severity"]);
  const map: Record<string, string> = {
    red: 'var(--color-sentinel-red)',
    orange: 'var(--color-sentinel-amber)',
    yellow: 'var(--color-sentinel-amber)',
    green: 'var(--color-sentinel-green)',
    gray: 'var(--color-sentinel-text-secondary)',
  };
  return map[tremorColor] || 'var(--color-sentinel-text-secondary)';
};

export function AnomalyDashboard({ refreshInterval = 30000 }: AnomalyDashboardProps) {
  const [anomalies, setAnomalies] = useState<AnomalyResult[]>([]);
  const [alerts, setAlerts] = useState<AnomalyResult[]>([]);
  const [health, setHealth] = useState<MLHealth | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [lastRefresh, setLastRefresh] = useState<Date>(new Date());

  const fetchData = async () => {
    try {
      setError(null);
      // Stagger requests to avoid rate limiting
      const anomalyData = await getAllAnomalies(20);
      await new Promise((resolve) => setTimeout(resolve, 400));
      const alertData = await getAnomalyAlerts();
      await new Promise((resolve) => setTimeout(resolve, 400));
      const healthData = await getMLHealth();
      setAnomalies(anomalyData);
      setAlerts(alertData);
      setHealth(healthData);
      setLastRefresh(new Date());
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load data");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchData();

    if (refreshInterval > 0) {
      const interval = setInterval(fetchData, refreshInterval);
      return () => clearInterval(interval);
    }
  }, [refreshInterval]);

  const normalCount = anomalies.filter((a) => !a.is_anomaly).length;
  const anomalyCount = anomalies.filter((a) => a.is_anomaly).length;

  if (loading) {
    return (
      <div style={{background:'var(--color-sentinel-bg-panel)', border:'1px solid var(--color-sentinel-border)', borderRadius:8}}>
        <h2 className="text-sm font-semibold" style={{color:'var(--color-sentinel-text-primary)'}}>Anomaly Detection Dashboard</h2>
        <div className="h-96 flex items-center justify-center">
          <p className="text-sm" style={{color:'var(--color-sentinel-text-secondary)'}}>Loading anomaly data...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Summary Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <div style={{background:'var(--color-sentinel-bg-panel)', border:'1px solid var(--color-sentinel-border)', borderRadius:8, borderTop:'3px solid var(--color-sentinel-green)'}}>
          <div className="flex items-start space-x-4">
            <CheckCircle className="h-6 w-6" style={{color:'var(--color-sentinel-green)'}} />
            <div>
              <p className="text-sm" style={{color:'var(--color-sentinel-text-secondary)'}}>Normal Equipment</p>
              <div className="text-3xl font-semibold tabular-nums">{normalCount}</div>
            </div>
          </div>
        </div>

        <div style={{background:'var(--color-sentinel-bg-panel)', border:'1px solid var(--color-sentinel-border)', borderRadius:8, borderTop:'3px solid var(--color-sentinel-red)'}}>
          <div className="flex items-start space-x-4">
            <AlertTriangle className="h-6 w-6" style={{color:'var(--color-sentinel-red)'}} />
            <div>
              <p className="text-sm" style={{color:'var(--color-sentinel-text-secondary)'}}>Active Anomalies</p>
              <div className="text-3xl font-semibold tabular-nums">{anomalyCount}</div>
            </div>
          </div>
        </div>

        <div style={{background:'var(--color-sentinel-bg-panel)', border:'1px solid var(--color-sentinel-border)', borderRadius:8, borderTop:'3px solid var(--color-sentinel-blue)'}}>
          <p className="text-sm" style={{color:'var(--color-sentinel-text-secondary)'}}>Active Models</p>
          <div className="text-3xl font-semibold tabular-nums">{health?.active_models || 0}</div>
          <p className="text-sm" style={{color:'var(--color-sentinel-text-secondary)'}}>
            {health?.equipment_types_covered?.join(", ") || "None"}
          </p>
        </div>

        <div style={{background:'var(--color-sentinel-bg-panel)', border:'1px solid var(--color-sentinel-border)', borderRadius:8, borderTop:'3px solid var(--color-sentinel-text-secondary)'}}>
          <p className="text-sm" style={{color:'var(--color-sentinel-text-secondary)'}}>Last Updated</p>
          <div className="text-lg font-semibold tabular-nums">
            {lastRefresh.toLocaleTimeString()}
          </div>
          <button
            onClick={fetchData}
            className="mt-2 inline-flex items-center gap-1 px-2 py-1 text-xs font-medium rounded"
            style={{background:'var(--color-sentinel-bg-secondary)', color:'var(--color-sentinel-text-primary)', border:'1px solid var(--color-sentinel-border)'}}
          >
            <RefreshCw className="h-3 w-3" /> Refresh
          </button>
        </div>
      </div>

      {/* Active Alerts */}
      {alerts.length > 0 && (
        <div style={{background:'var(--color-sentinel-bg-panel)', border:'1px solid var(--color-sentinel-border)', borderRadius:8}}>
          <div className="flex items-center gap-2">
            <h3 className="text-sm font-semibold" style={{color:'var(--color-sentinel-text-primary)'}}>Active Anomaly Alerts</h3>
            <span className="inline-flex items-center px-1.5 py-0.5 text-xs font-medium rounded-full" style={{background:'rgba(59,130,246,0.15)', color:'var(--color-sentinel-blue)'}}>AI</span>
          </div>
          <p className="text-xs italic -mt-2 mb-2" style={{color:'var(--color-sentinel-text-disabled)'}}>
            AI-generated anomaly detection &middot; Review before acting
          </p>
          <table className="w-full text-sm mt-4">
            <thead>
              <tr className="border-b" style={{borderColor:'var(--color-sentinel-border)'}}>
                <th className="text-left py-2 px-1 font-medium" style={{color:'var(--color-sentinel-text-secondary)'}}>Equipment</th>
                <th className="text-left py-2 px-1 font-medium" style={{color:'var(--color-sentinel-text-secondary)'}}>Type</th>
                <th className="text-left py-2 px-1 font-medium" style={{color:'var(--color-sentinel-text-secondary)'}}>Severity</th>
                <th className="text-left py-2 px-1 font-medium" style={{color:'var(--color-sentinel-text-secondary)'}}>Score</th>
                <th className="text-left py-2 px-1 font-medium" style={{color:'var(--color-sentinel-text-secondary)'}}>Threshold</th>
              </tr>
            </thead>
            <tbody>
              {alerts.map((alert) => (
                <tr key={alert.equipment_id} className="border-b" style={{borderColor:'var(--color-sentinel-border)'}}>
                  <td className="py-2 px-1">
                    <p className="font-medium" style={{color:'var(--color-sentinel-text-primary)'}}>{alert.equipment_id}</p>
                  </td>
                  <td className="py-2 px-1" style={{color:'var(--color-sentinel-text-primary)'}}>{alert.equipment_type}</td>
                  <td className="py-2 px-1">
                    <span className="inline-flex items-center px-2 py-1 text-xs font-medium rounded-full" style={{background: severityBgColor(alert.severity ?? ''), color: severityTextColor(alert.severity ?? '')}}>
                      {getSeverityBadge(alert.severity)}
                    </span>
                  </td>
                  <td className="py-2 px-1">
                    <span className="text-sm" style={{color:'var(--color-sentinel-text-primary)'}}>{alert.anomaly_score?.toFixed(6) || "N/A"}</span>
                  </td>
                  <td className="py-2 px-1">
                    <span className="text-sm" style={{color:'var(--color-sentinel-text-primary)'}}>{alert.threshold?.toFixed(6) || "N/A"}</span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* All Equipment Status */}
      <div style={{background:'var(--color-sentinel-bg-panel)', border:'1px solid var(--color-sentinel-border)', borderRadius:8}}>
        <h3 className="text-sm font-semibold" style={{color:'var(--color-sentinel-text-primary)'}}>All Equipment Anomaly Status</h3>
        {error ? (
          <p className="mt-4" style={{color:'var(--color-sentinel-red)'}}>
            {error}
          </p>
        ) : (
          <table className="w-full text-sm mt-4">
            <thead>
              <tr className="border-b" style={{borderColor:'var(--color-sentinel-border)'}}>
                <th className="text-left py-2 px-1 font-medium" style={{color:'var(--color-sentinel-text-secondary)'}}>Equipment</th>
                <th className="text-left py-2 px-1 font-medium" style={{color:'var(--color-sentinel-text-secondary)'}}>Type</th>
                <th className="text-left py-2 px-1 font-medium" style={{color:'var(--color-sentinel-text-secondary)'}}>Status</th>
                <th className="text-left py-2 px-1 font-medium" style={{color:'var(--color-sentinel-text-secondary)'}}>Score vs Threshold</th>
                <th className="text-left py-2 px-1 font-medium" style={{color:'var(--color-sentinel-text-secondary)'}}>Severity</th>
              </tr>
            </thead>
            <tbody>
              {anomalies.map((item) => (
                <tr key={item.equipment_id} className="border-b" style={{borderColor:'var(--color-sentinel-border)'}}>
                  <td className="py-2 px-1">
                    <p className="font-medium" style={{color:'var(--color-sentinel-text-primary)'}}>{item.equipment_id}</p>
                  </td>
                  <td className="py-2 px-1" style={{color:'var(--color-sentinel-text-primary)'}}>{item.equipment_type || "N/A"}</td>
                  <td className="py-2 px-1">
                    {item.is_anomaly ? (
                      <span className="inline-flex items-center px-2 py-1 text-xs font-medium rounded-full" style={{background:'rgba(220,38,38,0.15)', color:'var(--color-sentinel-red)'}}>Anomaly</span>
                    ) : (
                      <span className="inline-flex items-center px-2 py-1 text-xs font-medium rounded-full" style={{background:'rgba(16,185,129,0.15)', color:'var(--color-sentinel-green)'}}>Normal</span>
                    )}
                  </td>
                  <td className="py-2 px-1">
                    <div className="flex space-x-2">
                      <div className="w-24 h-1.5 rounded" style={{background:'var(--color-sentinel-border)'}}>
                        <div style={{
                          width: `${Math.min(item.score_pct || 0, 100)}%`,
                          background: (item.score_pct || 0) > 100
                            ? 'var(--color-sentinel-red)'
                            : (item.score_pct || 0) > 70
                            ? 'var(--color-sentinel-amber)'
                            : 'var(--color-sentinel-green)',
                        }} className="h-full rounded" />
                      </div>
                      <span className="text-sm" style={{color:'var(--color-sentinel-text-primary)'}}>
                        {item.score_pct?.toFixed(0) || 0}%
                      </span>
                    </div>
                  </td>
                  <td className="py-2 px-1">
                    <span className="inline-flex items-center px-2 py-1 text-xs font-medium rounded-full" style={{background: severityBgColor(item.severity ?? ''), color: severityTextColor(item.severity ?? '')}}>
                      {getSeverityBadge(item.severity)}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}

export default AnomalyDashboard;
