/**
 * BMS Connectivity Status Card
 * 
 * Shows connectivity status of Niagara, BACnet, ObiX, and DALI systems.
 */

import React from 'react';
import { Link as LinkIcon, CheckCircle, AlertTriangle, XCircle } from 'lucide-react';
import type { SystemHealthSnapshot } from '@/lib/api/system';

interface BMSConnectivityCardProps {
  health: SystemHealthSnapshot;
}

export function BMSConnectivityCard({ health }: BMSConnectivityCardProps) {
  const component = health.components['bms_connectivity'] || {
    name: 'bms_connectivity',
    status: 'critical',
    score: 0,
  };

  const statusIcons: Record<string, React.ReactNode> = {
    healthy: <CheckCircle className="w-4 h-4" style={{ color: 'var(--color-sentinel-green)' }} />,
    degraded: <AlertTriangle className="w-4 h-4" style={{ color: 'var(--color-sentinel-amber)' }} />,
    critical: <XCircle className="w-4 h-4" style={{ color: 'var(--color-sentinel-red)' }} />,
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

  // Mock subsystem data for demo
  const subsystems = [
    { name: 'Niagara', status: component.score >= 80 ? 'online' : 'offline' },
    { name: 'BACnet', status: component.score >= 60 ? 'online' : 'degraded' },
    { name: 'ObiX', status: component.score >= 60 ? 'connected' : 'disconnected' },
    { name: 'DALI', status: component.score >= 60 ? 'online' : 'offline' },
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
            <LinkIcon className="w-5 h-5" style={{ color: statusColor[component.status] }} />
          </div>
          <div>
            <h3
              className="text-sm font-medium"
              style={{ color: 'var(--color-sentinel-text-primary)' }}
            >
              BMS Connectivity
            </h3>
            <p className="text-xs mt-1" style={{ color: 'var(--color-sentinel-text-secondary)' }}>
              Protocol connections & gateways
            </p>
          </div>
        </div>

        <div className="flex items-center gap-2">
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
      </div>

      {/* Subsystems List */}
      <div className="space-y-2">
        {subsystems.map((sys) => (
          <div
            key={sys.name}
            className="flex items-center justify-between p-2 rounded text-xs"
            style={{
              background: 'var(--color-sentinel-bg-secondary)',
            }}
          >
            <span style={{ color: 'var(--color-sentinel-text-primary)' }}>
              {sys.name}
            </span>
            <span
              style={{
                color:
                  sys.status === 'online' || sys.status === 'connected'
                    ? 'var(--color-sentinel-green)'
                    : sys.status === 'degraded'
                    ? 'var(--color-sentinel-amber)'
                    : 'var(--color-sentinel-red)',
              }}
            >
              {sys.status}
            </span>
          </div>
        ))}
      </div>

      {/* Score Detail */}
      <div className="mt-4 pt-3" style={{ borderTop: '1px solid var(--color-sentinel-border)' }}>
        <div className="flex items-center justify-between text-xs">
          <span style={{ color: 'var(--color-sentinel-text-secondary)' }}>
            Score
          </span>
          <span style={{ color: 'var(--color-sentinel-text-primary)' }}>
            {component.score} / 100
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
