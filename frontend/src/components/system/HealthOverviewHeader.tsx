/**
 * System Health Overview Header
 * 
 * Displays overall health status badge with score, timestamp, and auto-refresh indicator.
 */

import React from 'react';
import { Activity, RefreshCw } from 'lucide-react';
import type { SystemHealthSnapshot } from '@/lib/api';

interface HealthOverviewHeaderProps {
  health: SystemHealthSnapshot;
}

export function HealthOverviewHeader({ health }: HealthOverviewHeaderProps) {
  // Status color mapping
  const statusColors = {
    healthy: {
      bg: 'rgba(16, 185, 129, 0.15)',
      border: 'rgba(16, 185, 129, 0.3)',
      color: 'var(--color-sentinel-green)',
      label: 'Healthy',
    },
    degraded: {
      bg: 'rgba(245, 158, 11, 0.15)',
      border: 'rgba(245, 158, 11, 0.3)',
      color: 'var(--color-sentinel-amber)',
      label: 'Degraded',
    },
    critical: {
      bg: 'rgba(220, 38, 38, 0.15)',
      border: 'rgba(220, 38, 38, 0.3)',
      color: 'var(--color-sentinel-red)',
      label: 'Critical',
    },
  };

  const config = statusColors[health.overall_status] || statusColors.healthy;

  // Format timestamp
  const timestamp = new Date(health.timestamp).toLocaleString('en-US', {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  });

  return (
    <div
      className="rounded-lg p-6 mb-6"
      style={{
        background: 'var(--color-sentinel-bg-panel)',
        border: '1px solid var(--color-sentinel-border)',
      }}
    >
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        {/* Status Badge */}
        <div className="flex items-center gap-4">
          <div
            className="p-3 rounded-lg"
            style={{ background: config.bg, border: `1px solid ${config.border}` }}
          >
            <Activity
              className="w-6 h-6"
              style={{ color: config.color }}
            />
          </div>

          <div>
            <div
              className="text-xs font-medium uppercase tracking-wider"
              style={{ color: 'var(--color-sentinel-text-secondary)' }}
            >
              System Status
            </div>
            <div className="flex items-center gap-3 mt-2">
              <span
                className="text-2xl font-bold"
                style={{ color: config.color }}
              >
                {config.label}
              </span>
              <span
                className="text-lg font-semibold"
                style={{ color: 'var(--color-sentinel-text-primary)' }}
              >
                {health.overall_score}%
              </span>
            </div>
          </div>
        </div>

        {/* Status Details */}
        <div className="flex flex-col items-start sm:items-end gap-2">
          <div className="flex items-center gap-2">
            <RefreshCw className="w-3 h-3 animate-spin" style={{ color: 'var(--color-sentinel-text-secondary)' }} />
            <span
              className="text-xs"
              style={{ color: 'var(--color-sentinel-text-secondary)' }}
            >
              Last updated: {timestamp}
            </span>
          </div>

          {/* Component Status Summary */}
          <div
            className="text-xs"
            style={{ color: 'var(--color-sentinel-text-disabled)' }}
          >
            <span className="block">
              {Object.values(health.components).filter((c) => c.status === 'healthy').length} healthy
              {' '}/ {Object.values(health.components).filter((c) => c.status === 'degraded').length} degraded
              {' '}/ {Object.values(health.components).filter((c) => c.status === 'critical').length} critical
            </span>
          </div>
        </div>
      </div>

      {/* Recommendations */}
      {health.recommendations.length > 0 && (
        <div className="mt-4 pt-4" style={{ borderTop: '1px solid var(--color-sentinel-border)' }}>
          <div
            className="text-xs font-medium mb-2"
            style={{ color: 'var(--color-sentinel-text-secondary)' }}
          >
            Recommendations
          </div>
          <ul className="space-y-1">
            {health.recommendations.slice(0, 3).map((rec, i) => (
              <li key={i} className="text-xs flex gap-2" style={{ color: 'var(--color-sentinel-text-primary)' }}>
                <span style={{ color: 'var(--color-sentinel-blue)' }}>→</span>
                <span>{rec}</span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
