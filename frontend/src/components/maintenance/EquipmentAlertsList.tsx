/**
 * Equipment Alerts List Component
 *
 * Displays alert/error history for equipment with severity indicators.
 * Follows AlertFeed design pattern with consistent severity color coding.
 */

import { useEquipmentAlerts } from '@/hooks/useEquipmentHistory';
import { RefreshCw, AlertCircle, CheckCircle2, Clock } from 'lucide-react';

interface EquipmentAlertsListProps {
  equipmentId: string;
  limit?: number;
}

/**
 * Get relative time string from timestamp
 */
function getRelativeTime(timestamp: string): string {
  const now = new Date();
  const alertTime = new Date(timestamp);
  const diffMs = now.getTime() - alertTime.getTime();
  const diffMins = Math.floor(diffMs / 60000);
  const diffHours = Math.floor(diffMins / 60);
  const diffDays = Math.floor(diffHours / 24);

  if (diffMins < 1) {
    return 'Just now';
  }
  if (diffMins < 60) {
    return `${diffMins}m ago`;
  }
  if (diffHours < 24) {
    return `${diffHours}h ago`;
  }
  return `${diffDays}d ago`;
}

/**
 * Get severity configuration matching AlertFeed pattern
 */
function getSeverityConfig(severity: string): {
  color: string;
  bg: string;
  label: string;
} {
  switch (severity) {
    case 'critical':
      return {
        color: 'var(--color-status-error)',
        bg: 'rgba(242, 73, 92, 0.1)',
        label: 'CRITICAL',
      };
    case 'high':
      return {
        color: 'var(--color-status-warning)',
        bg: 'rgba(255, 152, 48, 0.1)',
        label: 'HIGH',
      };
    case 'warning':
      return {
        color: 'var(--color-status-warning)',
        bg: 'rgba(255, 152, 48, 0.1)',
        label: 'WARNING',
      };
    case 'medium':
      return {
        color: 'var(--color-grafana-yellow)',
        bg: 'rgba(242, 204, 12, 0.1)',
        label: 'MEDIUM',
      };
    case 'low':
      return {
        color: 'var(--color-grafana-blue)',
        bg: 'rgba(50, 116, 217, 0.1)',
        label: 'LOW',
      };
    default:
      return {
        color: 'var(--color-grafana-text-secondary)',
        bg: 'rgba(142, 142, 142, 0.1)',
        label: 'INFO',
      };
  }
}

/**
 * Get status configuration
 */
function getStatusConfig(status: string): { color: string; label: string } {
  switch (status) {
    case 'resolved':
      return { color: 'var(--color-status-success)', label: 'RESOLVED' };
    case 'acknowledged':
      return { color: 'var(--color-grafana-yellow)', label: 'ACKNOWLEDGED' };
    case 'active':
      return { color: 'var(--color-status-error)', label: 'ACTIVE' };
    default:
      return { color: 'var(--color-grafana-text-secondary)', label: status.toUpperCase() };
  }
}

export function EquipmentAlertsList({ equipmentId, limit = 10 }: EquipmentAlertsListProps) {
  const { data: alerts = [], isLoading, error } = useEquipmentAlerts(equipmentId, limit);

  // Loading state
  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-8">
        <RefreshCw
          className="h-5 w-5 animate-spin"
          style={{ color: 'var(--color-grafana-text-disabled)' }}
        />
        <span
          className="ml-2 text-sm"
          style={{ color: 'var(--color-grafana-text-secondary)' }}
        >
          Loading alerts...
        </span>
      </div>
    );
  }

  // Error state
  if (error) {
    return (
      <div
        className="p-3 rounded text-sm flex items-center gap-2"
        style={{
          background: 'rgba(242, 73, 92, 0.1)',
          border: '1px solid rgba(242, 73, 92, 0.3)',
          color: 'var(--color-status-error)',
        }}
      >
        <AlertCircle className="h-4 w-4 flex-shrink-0" />
        <span>Failed to load alerts</span>
      </div>
    );
  }

  // Empty state
  if (alerts.length === 0) {
    return (
      <div className="text-center py-8">
        <CheckCircle2
          className="h-8 w-8 mx-auto mb-2"
          style={{ color: 'var(--color-status-success)' }}
        />
        <span
          className="text-sm block"
          style={{ color: 'var(--color-grafana-text-secondary)' }}
        >
          No active alerts
        </span>
        <span
          className="text-xs block mt-1"
          style={{ color: 'var(--color-grafana-text-disabled)' }}
        >
          Equipment is operating normally
        </span>
      </div>
    );
  }

  return (
    <div className="space-y-2">
      {alerts.map((alert) => {
        const severityConfig = getSeverityConfig(alert.severity);
        const statusConfig = getStatusConfig(alert.status);

        return (
          <div
            key={alert.id}
            className="rounded overflow-hidden transition-colors hover:brightness-105"
            style={{
              background: severityConfig.bg,
              borderLeft: `3px solid ${severityConfig.color}`,
              border: `1px solid ${severityConfig.color}30`,
            }}
          >
            <div className="p-3">
              {/* Header: Title and Severity Badge */}
              <div className="flex items-start justify-between gap-2 mb-2">
                <div className="flex items-start gap-2 flex-1 min-w-0">
                  <AlertCircle
                    className="h-4 w-4 mt-0.5 flex-shrink-0"
                    style={{ color: severityConfig.color }}
                  />
                  <div className="min-w-0 flex-1">
                    <h4
                      className="text-sm font-medium line-clamp-1"
                      style={{ color: 'var(--color-grafana-text-primary)' }}
                    >
                      {alert.title}
                    </h4>
                    {alert.message && (
                      <p
                        className="text-xs mt-0.5 line-clamp-1"
                        style={{ color: 'var(--color-grafana-text-secondary)' }}
                      >
                        {alert.message}
                      </p>
                    )}
                  </div>
                </div>
                <div className="flex items-center gap-1 flex-shrink-0">
                  <span
                    className="text-xs font-medium px-1.5 py-0.5 rounded"
                    style={{
                      background: `${severityConfig.color}20`,
                      color: severityConfig.color,
                    }}
                  >
                    {severityConfig.label}
                  </span>
                </div>
              </div>

              {/* Status and Timestamp */}
              <div className="flex items-center justify-between gap-2 text-xs">
                <span
                  className="px-1.5 py-0.5 rounded"
                  style={{
                    background: `${statusConfig.color}20`,
                    color: statusConfig.color,
                  }}
                >
                  {statusConfig.label}
                </span>
                <div className="flex items-center gap-1">
                  <Clock
                    className="h-3 w-3"
                    style={{ color: 'var(--color-grafana-text-disabled)' }}
                  />
                  <span style={{ color: 'var(--color-grafana-text-disabled)' }}>
                    {getRelativeTime(alert.created_at)}
                  </span>
                </div>
              </div>
            </div>
          </div>
        );
      })}
    </div>
  );
}
