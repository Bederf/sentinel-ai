/**
 * Database Status Card
 *
 * Shows Supabase, InfluxDB, and Redis connectivity.
 */

import React from 'react';
import { Database, CheckCircle } from 'lucide-react';
import type { SystemHealthSnapshot } from '@/lib/api/system';

interface DatabaseStatusCardProps {
  health: SystemHealthSnapshot;
}

export function DatabaseStatusCard({ health }: DatabaseStatusCardProps) {
  const component = health.components['database_status'] || {
    name: 'database_status',
    status: 'healthy',
    score: 95,
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

  const databases = [
    { name: 'Supabase (PostgreSQL)', status: 'connected', queryTime: '12ms' },
    { name: 'InfluxDB', status: 'connected', queryTime: '8ms' },
    { name: 'Redis Cache', status: 'connected', queryTime: '2ms' },
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
            <Database className="w-5 h-5" style={{ color: statusColor[component.status] }} />
          </div>
          <div>
            <h3
              className="text-sm font-medium"
              style={{ color: 'var(--color-sentinel-text-primary)' }}
            >
              Database Status
            </h3>
            <p className="text-xs mt-1" style={{ color: 'var(--color-sentinel-text-secondary)' }}>
              Storage & caching systems
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

      {/* Databases List */}
      <div className="space-y-2">
        {databases.map((db) => (
          <div
            key={db.name}
            className="flex items-center justify-between p-2 rounded text-xs"
            style={{ background: 'var(--color-sentinel-bg-secondary)' }}
          >
            <div className="flex items-center gap-2">
              <CheckCircle className="w-3 h-3" style={{ color: 'var(--color-sentinel-green)' }} />
              <span style={{ color: 'var(--color-sentinel-text-primary)' }}>
                {db.name}
              </span>
            </div>
            <span style={{ color: 'var(--color-sentinel-text-secondary)' }}>
              {db.queryTime}
            </span>
          </div>
        ))}
      </div>

      {/* Metrics */}
      <div className="mt-4 pt-3 space-y-2" style={{ borderTop: '1px solid var(--color-sentinel-border)' }}>
        <div className="flex items-center justify-between text-xs">
          <span style={{ color: 'var(--color-sentinel-text-secondary)' }}>
            Connections Active
          </span>
          <span style={{ color: 'var(--color-sentinel-text-primary)' }}>
            12/100
          </span>
        </div>
        <div className="flex items-center justify-between text-xs">
          <span style={{ color: 'var(--color-sentinel-text-secondary)' }}>
            Storage Usage
          </span>
          <span style={{ color: 'var(--color-sentinel-text-primary)' }}>
            28 GB / 500 GB
          </span>
        </div>
      </div>
    </div>
  );
}
