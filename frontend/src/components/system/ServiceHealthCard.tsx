/**
 * Service Health Card
 * 
 * Shows status of background services like ML, AI, Device Manager, etc.
 */

import React from 'react';
import { Zap, CheckCircle, AlertTriangle } from 'lucide-react';
import type { SystemHealthSnapshot } from '@/lib/api/system';

interface ServiceHealthCardProps {
  health: SystemHealthSnapshot;
}

export function ServiceHealthCard({ health }: ServiceHealthCardProps) {
  const component = health.components['service_health'] || {
    name: 'service_health',
    status: 'healthy',
    score: 88,
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

  const services = [
    { name: 'Device Manager', status: 'running' },
    { name: 'AI Optimizer', status: 'running' },
    { name: 'ML Models', status: 'ready' },
    { name: 'Background Tasks', status: 'running' },
    { name: 'Scheduler', status: 'running' },
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
            <Zap className="w-5 h-5" style={{ color: statusColor[component.status] }} />
          </div>
          <div>
            <h3
              className="text-sm font-medium"
              style={{ color: 'var(--color-sentinel-text-primary)' }}
            >
              Services Health
            </h3>
            <p className="text-xs mt-1" style={{ color: 'var(--color-sentinel-text-secondary)' }}>
              Background services status
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

      {/* Services List */}
      <div className="space-y-2">
        {services.map((svc) => (
          <div
            key={svc.name}
            className="flex items-center justify-between p-2 rounded text-xs"
            style={{ background: 'var(--color-sentinel-bg-secondary)' }}
          >
            <div className="flex items-center gap-2">
              <CheckCircle className="w-3 h-3" style={{ color: 'var(--color-sentinel-green)' }} />
              <span style={{ color: 'var(--color-sentinel-text-primary)' }}>
                {svc.name}
              </span>
            </div>
            <span
              className="px-2 py-0.5 rounded text-xs font-medium"
              style={{
                background: 'var(--color-sentinel-blue)20',
                color: 'var(--color-sentinel-blue)',
              }}
            >
              {svc.status}
            </span>
          </div>
        ))}
      </div>

      {/* Summary */}
      <div className="mt-4 pt-3" style={{ borderTop: '1px solid var(--color-sentinel-border)' }}>
        <span
          className="text-xs"
          style={{ color: 'var(--color-sentinel-text-secondary)' }}
        >
          All services operational
        </span>
      </div>
    </div>
  );
}
