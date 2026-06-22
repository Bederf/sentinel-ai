/**
 * Adapter Health Card — SLI Tier 1: Adapter Heartbeat
 *
 * Shows per-adapter health: shadow_bridge, BACnet, Niagara, OBIX, DALI.
 * Data from /api/system/sites/{site_id}/adapter-health
 */

import { useState, useEffect } from 'react';
import { authorizedFetch } from '@/lib/api/client';
import { Link as LinkIcon, CheckCircle, AlertTriangle, XCircle, Wifi, WifiOff } from 'lucide-react';

interface AdapterStatus {
  name: string;
  type: string;
  is_healthy: boolean;
  uptime_1h_percent: number | null;
  uptime_24h_percent: number | null;
  last_check: string | null;
  consecutive_failures: number;
  error_message?: string | null;
}

interface AdapterHealthData {
  site_id: string;
  adapters: AdapterStatus[];
}

const ADAPTER_TYPE_LABELS: Record<string, string> = {
  shadow_bridge: 'Shadow Bridge',
  bacnet: 'BACnet/IP',
  niagara: 'Niagara',
  obix: 'OBIX',
  dali: 'DALI',
  concept_mri: 'Concept MRI',
  unknown: 'Unknown',
};

function getAdapterIcon(type: string, healthy: boolean) {
  if (!healthy) return <XCircle className="w-4 h-4 text-red-500" />;
  switch (type) {
    case 'shadow_bridge':
      return <Wifi className="w-4 h-4 text-green-500" />;
    case 'bacnet':
    case 'niagara':
      return <Wifi className="w-4 h-4 text-green-500" />;
    default:
      return <CheckCircle className="w-4 h-4 text-green-500" />;
  }
}

function formatUptime(pct: number | null): string {
  if (pct === null) return '—';
  return `${pct.toFixed(1)}%`;
}

function formatLastCheck(dateStr: string | null): string {
  if (!dateStr) return 'Never';
  const date = new Date(dateStr);
  const diffMs = Date.now() - date.getTime();
  const diffSec = Math.floor(diffMs / 1000);
  if (diffSec < 60) return `${diffSec}s ago`;
  const diffMin = Math.floor(diffSec / 60);
  if (diffMin < 60) return `${diffMin}m ago`;
  const diffHr = Math.floor(diffMin / 60);
  return `${diffHr}h ago`;
}

export function AdapterHealthCard({ siteId = 'site-002' }: { siteId?: string }) {
  const [data, setData] = useState<AdapterHealthData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    async function fetchAdapterHealth() {
      try {
        const res = await authorizedFetch(`/api/system/sites/${siteId}/adapter-health`);
        if (!res.ok) throw new Error('Failed to fetch');
        const json = await res.json();
        if (!cancelled) {
          setData(json);
          setError(null);
        }
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : 'Unknown error');
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    fetchAdapterHealth();
    // Refresh every 60 seconds (aligns with health monitor cadence)
    const interval = setInterval(fetchAdapterHealth, 60000);
    return () => {
      cancelled = true;
      clearInterval(interval);
    };
  }, [siteId]);

  if (loading && !data) {
    return (
      <div
        className="rounded-lg p-6"
        style={{
          background: 'var(--color-sentinel-bg-panel)',
          border: '1px solid var(--color-sentinel-border)',
        }}
      >
        <div className="flex items-center gap-2">
          <Wifi className="w-4 h-4 animate-pulse" style={{ color: 'var(--color-sentinel-text-secondary)' }} />
          <span className="text-xs" style={{ color: 'var(--color-sentinel-text-secondary)' }}>
            Loading adapter health…
          </span>
        </div>
      </div>
    );
  }

  if (error && !data) {
    return (
      <div
        className="rounded-lg p-6"
        style={{
          background: 'var(--color-sentinel-bg-panel)',
          border: '1px solid rgba(220, 38, 38, 0.35)',
        }}
      >
        <div className="flex items-center gap-2">
          <XCircle className="w-4 h-4 text-red-500" />
          <span className="text-xs text-red-500">Adapter health unavailable</span>
        </div>
      </div>
    );
  }

  const adapters = data?.adapters || [];
  const healthyCount = adapters.filter((a) => a.is_healthy).length;
  const overallStatus = healthyCount === adapters.length ? 'healthy' : healthyCount > 0 ? 'degraded' : 'critical';

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
            style={{ background: statusBg[overallStatus] }}
          >
            <LinkIcon className="w-5 h-5" style={{ color: statusColor[overallStatus] }} />
          </div>
          <div>
            <h3
              className="text-sm font-medium"
              style={{ color: 'var(--color-sentinel-text-primary)' }}
            >
              Adapter Health
            </h3>
            <p className="text-xs mt-1" style={{ color: 'var(--color-sentinel-text-secondary)' }}>
              BMS protocol adapters • SLI Tier 1
            </p>
          </div>
        </div>
        <span
          className="text-xs px-2 py-1 rounded-full font-medium"
          style={{
            background: statusBg[overallStatus],
            color: statusColor[overallStatus],
          }}
        >
          {healthyCount}/{adapters.length} healthy
        </span>
      </div>

      {/* Adapters list */}
      {adapters.length === 0 ? (
        <div className="flex items-center gap-2 py-3">
          <WifiOff className="w-4 h-4" style={{ color: 'var(--color-sentinel-text-disabled)' }} />
          <span className="text-xs" style={{ color: 'var(--color-sentinel-text-disabled)' }}>
            No adapters registered yet
          </span>
        </div>
      ) : (
        <div className="space-y-2">
          {adapters.map((adapter) => {
            const label = ADAPTER_TYPE_LABELS[adapter.type] || adapter.type;
            const itemStatus = adapter.is_healthy ? 'healthy' : adapter.consecutive_failures >= 3 ? 'critical' : 'degraded';
            return (
              <div
                key={adapter.name}
                className="flex items-start justify-between gap-3 p-2 rounded text-xs"
                style={{ background: 'var(--color-sentinel-bg-secondary)' }}
              >
                <div className="flex min-w-0 items-start gap-2">
                  {getAdapterIcon(adapter.type, adapter.is_healthy)}
                  <div className="min-w-0">
                    <div className="flex min-w-0 flex-wrap items-baseline gap-x-2 gap-y-1">
                      <span style={{ color: 'var(--color-sentinel-text-primary)' }}>
                        {label}
                      </span>
                      <span
                        className="truncate"
                        style={{ color: 'var(--color-sentinel-text-disabled)', fontSize: '10px' }}
                      >
                        {adapter.name}
                      </span>
                    </div>
                    {!adapter.is_healthy && adapter.error_message && (
                      <div
                        className="mt-1 break-words"
                        style={{ color: 'var(--color-sentinel-red)', fontSize: '10px', lineHeight: 1.35 }}
                      >
                        {adapter.error_message}
                      </div>
                    )}
                  </div>
                </div>
                <div className="flex items-center gap-3">
                  <div className="text-right">
                    <div
                      style={{
                        color:
                          itemStatus === 'healthy'
                            ? 'var(--color-sentinel-green)'
                            : itemStatus === 'degraded'
                            ? 'var(--color-sentinel-amber)'
                            : 'var(--color-sentinel-red)',
                        fontWeight: 600,
                        fontSize: '11px',
                      }}
                    >
                      {adapter.is_healthy ? 'UP' : 'DOWN'}
                    </div>
                    <div style={{ color: 'var(--color-sentinel-text-disabled)', fontSize: '9px' }}>
                      {formatLastCheck(adapter.last_check)}
                    </div>
                  </div>
                  <div className="text-right hidden sm:block">
                    <div style={{ color: 'var(--color-sentinel-text-secondary)', fontSize: '9px' }}>24h</div>
                    <div style={{ color: 'var(--color-sentinel-text-primary)', fontSize: '11px', fontVariantNumeric: 'tabular-nums' }}>
                      {formatUptime(adapter.uptime_24h_percent)}
                    </div>
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      )}

      {/* Footer: consecutive failure warning */}
      {adapters.some((a) => a.consecutive_failures >= 3 && !a.is_healthy) && (
        <div
          className="mt-3 pt-3 flex items-center gap-2 text-xs rounded px-3 py-2"
          style={{
            background: 'rgba(220, 38, 38, 0.1)',
            border: '1px solid rgba(220, 38, 38, 0.3)',
          }}
        >
          <AlertTriangle className="w-3 h-3 text-red-500 shrink-0" />
          <span style={{ color: 'var(--color-sentinel-red)' }}>
            {adapters.filter((a) => a.consecutive_failures >= 3 && !a.is_healthy).length} adapter(s) failing — alert fired
          </span>
        </div>
      )}
    </div>
  );
}
