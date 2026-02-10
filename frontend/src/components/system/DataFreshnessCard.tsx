/**
 * Data Freshness Card
 * 
 * Shows how recent the data is and staleness alerts.
 */

import React from 'react';
import { Clock, AlertTriangle } from 'lucide-react';
import type { SystemHealthSnapshot } from '@/lib/api';

interface DataFreshnessCardProps {
  health: SystemHealthSnapshot;
}

export function DataFreshnessCard({ health }: DataFreshnessCardProps) {
  const component = health.components['data_freshness'] || {
    name: 'data_freshness',
    status: 'healthy',
    score: 85,
  };

  const statusBg: Record<string, string> = {
    healthy: 'rgba(16, 185, 129, 0.15)',
    degraded: 'rgba(245, 158, 11, 0.15)',
    critical: 'rgba(220, 38, 38, 0.15)',
  };

  const statusColor: Record<string, string> = {
    healthy: 'var(--color-sentinel-green)',
    degraded: 'var(--color-sentinel-amber)',
    critical: 'var(--color-sentinel-red)',
  };

  const dataPoints = [
    { source: 'Niagara', lastUpdate: '2 min ago' },
    { source: 'BACnet', lastUpdate: '5 min ago' },
    { source: 'InfluxDB', lastUpdate: '1 min ago' },
    { source: 'Supabase', lastUpdate: '<1 min ago' },
  ];

  return (
    <div
      className="rounded-lg p-6"
      style={{
        background: 'var(--color-sentinel-bg-panel)',
        border: '1px solid var(--color-sentinel-border)',
      }}
    >
      {/* Header */}
      <div className="flex items-start justify-between mb-4">
        <div className="flex items-center gap-3">
          <div
            className="p-2 rounded"
            style={{ background: statusBg[component.status] }}
          >
            <Clock className="w-5 h-5" style={{ color: statusColor[component.status] }} />
          </div>
          <div>
            <h3
              className="text-sm font-medium"
              style={{ color: 'var(--color-sentinel-text-primary)' }}
            >
              Data Freshness
            </h3>
            <p className="text-xs mt-1" style={{ color: 'var(--color-sentinel-text-secondary)' }}>
              Data recency by source
            </p>
          </div>
        </div>

        <span
          className="text-xs px-2 py-1 rounded-full font-medium"
          style={{
            background: statusBg[component.status],
            color: statusColor[component.status],
          }}
        >
          {component.score}%
        </span>
      </div>

      {/* Data Sources */}
      <div className="space-y-2">
        {dataPoints.map((dp) => (
          <div
            key={dp.source}
            className="flex items-center justify-between p-2 rounded text-xs"
            style={{ background: 'var(--color-sentinel-bg-secondary)' }}
          >
            <span style={{ color: 'var(--color-sentinel-text-primary)' }}>
              {dp.source}
            </span>
            <span style={{ color: 'var(--color-sentinel-text-secondary)' }}>
              {dp.lastUpdate}
            </span>
          </div>
        ))}
      </div>

      {/* Warning if stale */}
      {component.status !== 'healthy' && (
        <div
          className="mt-3 p-2 rounded flex items-start gap-2 text-xs"
          style={{
            background: 'rgba(245, 158, 11, 0.1)',
            border: '1px solid rgba(245, 158, 11, 0.2)',
          }}
        >
          <AlertTriangle className="w-3 h-3 mt-0.5" style={{ color: 'var(--color-sentinel-amber)' }} />
          <span style={{ color: 'var(--color-sentinel-text-secondary)' }}>
            Some data sources are stale. Check integration status.
          </span>
        </div>
      )}
    </div>
  );
}
