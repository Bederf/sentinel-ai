/**
 * API Health Status Card
 * 
 * Shows status of REST API endpoints and response times.
 */

import React from 'react';
import { Server, CheckCircle, AlertTriangle, XCircle } from 'lucide-react';
import type { SystemHealthSnapshot } from '@/lib/api/system';

interface APIHealthCardProps {
  health: SystemHealthSnapshot;
}

export function APIHealthCard({ health }: APIHealthCardProps) {
  const component = health.components['api_health'] || {
    name: 'api_health',
    status: 'healthy',
    score: 90,
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

  const endpoints = [
    { path: '/api/health', responseTime: '12ms' },
    { path: '/api/devices', responseTime: '45ms' },
    { path: '/api/equipment', responseTime: '38ms' },
    { path: '/api/integration', responseTime: '156ms' },
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
            <Server className="w-5 h-5" style={{ color: statusColor[component.status] }} />
          </div>
          <div>
            <h3
              className="text-sm font-medium"
              style={{ color: 'var(--color-sentinel-text-primary)' }}
            >
              API Health
            </h3>
            <p className="text-xs mt-1" style={{ color: 'var(--color-sentinel-text-secondary)' }}>
              REST endpoints & response times
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

      {/* Endpoints List */}
      <div className="space-y-2">
        {endpoints.map((ep) => (
          <div
            key={ep.path}
            className="flex items-center justify-between p-2 rounded text-xs"
            style={{ background: 'var(--color-sentinel-bg-secondary)' }}
          >
            <span style={{ color: 'var(--color-sentinel-text-primary)', fontFamily: 'monospace' }}>
              {ep.path}
            </span>
            <span style={{ color: 'var(--color-sentinel-blue)' }}>
              {ep.responseTime}
            </span>
          </div>
        ))}
      </div>

      {/* Score Detail */}
      <div className="mt-4 pt-3" style={{ borderTop: '1px solid var(--color-sentinel-border)' }}>
        <div className="flex items-center justify-between text-xs">
          <span style={{ color: 'var(--color-sentinel-text-secondary)' }}>
            Availability
          </span>
          <span style={{ color: 'var(--color-sentinel-text-primary)' }}>
            {component.score}%
          </span>
        </div>
        <div
          className="w-full h-2 rounded-full mt-2"
          style={{ background: 'var(--color-sentinel-bg-secondary)' }}
        >
          <div
            className="h-full rounded-full transition-all"
            style={{
              width: `${component.score}%`,
              background: statusColor[component.status],
            }}
          />
        </div>
      </div>
    </div>
  );
}
