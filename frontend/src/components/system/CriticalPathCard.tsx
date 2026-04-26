/**
 * Critical Path Card — SLI Tier 3: Critical Path Latency
 *
 * Shows PARASITE decision latency: approval + execution + total.
 * SLO: p99 < 7000ms for supervised-phase operations.
 * Data from /api/system/sites/{site_id}/critical-path and /critical-path/history
 */

import { useState, useEffect } from 'react';
import { authorizedFetch } from '@/lib/api/client';
import { AlertTriangle, Clock, TrendingUp } from 'lucide-react';

interface CriticalPathHourly {
  site_id: string;
  hour_start: string;
  total_actions: number;
  p50_total_ms: number;
  p99_total_ms: number;
  p99_9_total_ms: number;
  max_total_ms: number;
  avg_total_ms: number;
  slo_pass: boolean;
}

interface CriticalPathResponse {
  site_id: string;
  hour_start: string;
  data: CriticalPathHourly | null;
  message?: string;
}

interface HistoryResponse {
  site_id: string;
  days: number;
  data: CriticalPathHourly[];
}

function formatMs(ms: number | null): string {
  if (ms === null || ms === undefined) return '—';
  if (ms < 1000) return `${ms.toFixed(0)}ms`;
  return `${(ms / 1000).toFixed(2)}s`;
}

function formatHour(isoString: string): string {
  const d = new Date(isoString);
  return d.toLocaleTimeString('en-ZA', { hour: '2-digit', minute: '2-digit', hour12: false });
}

function formatDate(isoString: string): string {
  const d = new Date(isoString);
  return d.toLocaleDateString('en-ZA', { month: 'short', day: 'numeric' });
}

export function CriticalPathCard({ siteId = 'site-002' }: { siteId?: string }) {
  const [current, setCurrent] = useState<CriticalPathHourly | null>(null);
  const [history, setHistory] = useState<CriticalPathHourly[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    async function fetchCriticalPath() {
      try {
        // Fetch current hour + 7-day history in parallel
        const [currentRes, historyRes] = await Promise.all([
          authorizedFetch(`/api/system/sites/${siteId}/critical-path`),
          authorizedFetch(`/api/system/sites/${siteId}/critical-path/history?days=7`),
        ]);

        if (!cancelled) {
          if (currentRes.ok) {
            const currentJson: CriticalPathResponse = await currentRes.json();
            setCurrent(currentJson.data || null);
          }
          if (historyRes.ok) {
            const historyJson: HistoryResponse = await historyRes.json();
            setHistory(historyJson.data || []);
          }
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

    fetchCriticalPath();
    const interval = setInterval(fetchCriticalPath, 300000); // Refresh every 5 min
    return () => {
      cancelled = true;
      clearInterval(interval);
    };
  }, [siteId]);

  if (loading && !current && history.length === 0) {
    return (
      <div
        className="rounded-lg p-6"
        style={{
          background: 'var(--color-sentinel-bg-panel)',
          border: '1px solid var(--color-sentinel-border)',
        }}
      >
        <div className="flex items-center gap-2">
          <Clock className="w-4 h-4 animate-pulse" style={{ color: 'var(--color-sentinel-text-secondary)' }} />
          <span className="text-xs" style={{ color: 'var(--color-sentinel-text-secondary)' }}>
            Loading critical path data…
          </span>
        </div>
      </div>
    );
  }

  if (error && !current) {
    return (
      <div
        className="rounded-lg p-6"
        style={{
          background: 'var(--color-sentinel-bg-panel)',
          border: '1px solid rgba(220, 38, 38, 0.35)',
        }}
      >
        <div className="flex items-center gap-2">
          <AlertTriangle className="w-4 h-4 text-red-500" />
          <span className="text-xs text-red-500">Critical path data unavailable</span>
        </div>
      </div>
    );
  }

  const sloPass = current?.slo_pass ?? null;
  const p99 = current?.p99_total_ms ?? null;

  return (
    <div
      className="rounded-lg p-5"
      style={{
        background: 'var(--color-sentinel-bg-panel)',
        border: `1px solid ${
          sloPass === true
            ? 'rgba(34, 197, 94, 0.35)'
            : sloPass === false
              ? 'rgba(234, 179, 8, 0.35)'
              : 'var(--color-sentinel-border)'
        }`,
      }}
    >
      {/* Header */}
      <div className="pb-3">
        <div className="flex items-center justify-between mb-1">
          <div className="flex items-center gap-2">
            <TrendingUp className="w-4 h-4" style={{ color: 'var(--color-sentinel-blue)' }} />
            <span className="text-base font-semibold" style={{ color: 'var(--color-sentinel-text-primary)' }}>
              Critical Path Latency
            </span>
          </div>
          {sloPass !== null && (
            <span
              className="text-xs font-medium px-2 py-1 rounded"
              style={{
                background: sloPass ? 'rgba(34,197,94,0.12)' : 'rgba(234,179,8,0.12)',
                border: `1px solid ${sloPass ? 'rgba(34,197,94,0.35)' : 'rgba(234,179,8,0.35)'}`,
                color: sloPass ? 'var(--color-sentinel-green)' : 'var(--color-sentinel-amber)',
              }}
            >
              {sloPass ? '✅ SLO PASS' : '⚠️ SLO BREACH'}
            </span>
          )}
        </div>
        <p className="text-xs" style={{ color: 'var(--color-sentinel-text-secondary)' }}>
          Target: p99 &lt; 7000ms · PARASITE supervised decisions
        </p>
      </div>

      {/* Current hour stats */}
      {current ? (
        <div
          className="mb-4 p-4 rounded-lg"
          style={{
            background: sloPass
              ? 'rgba(34, 197, 94, 0.08)'
              : sloPass === false
                ? 'rgba(234, 179, 8, 0.08)'
                : 'var(--color-sentinel-bg-secondary)',
            border: `1px solid ${
              sloPass
                ? 'rgba(34, 197, 94, 0.3)'
                : sloPass === false
                  ? 'rgba(234, 179, 8, 0.3)'
                  : 'var(--color-sentinel-border)'
            }`,
          }}
        >
          <div className="flex items-baseline justify-between mb-3">
            <div>
              <p className="text-xs uppercase tracking-wide" style={{ color: 'var(--color-sentinel-text-secondary)' }}>
                Current Hour · {formatHour(current.hour_start)}
              </p>
              <div className="flex items-baseline gap-1 mt-0.5">
                <span
                  className="text-2xl font-bold font-mono"
                  style={{ color: sloPass === false ? 'var(--color-sentinel-amber)' : 'var(--color-sentinel-text-primary)' }}
                >
                  {formatMs(p99)}
                </span>
                <span className="text-xs" style={{ color: 'var(--color-sentinel-text-secondary)' }}>
                  p99
                </span>
              </div>
            </div>
            <div className="text-right">
              <p className="text-xs" style={{ color: 'var(--color-sentinel-text-secondary)' }}>
                {current.total_actions} action{current.total_actions !== 1 ? 's' : ''}
              </p>
              <p className="text-xs mt-0.5" style={{ color: 'var(--color-sentinel-text-secondary)' }}>
                avg {formatMs(current.avg_total_ms)}
              </p>
            </div>
          </div>

          {/* Percentile breakdown */}
          <div className="grid grid-cols-4 gap-2">
            {[
              { label: 'p50', value: current.p50_total_ms },
              { label: 'p99', value: current.p99_total_ms },
              { label: 'p99.9', value: current.p99_9_total_ms },
              { label: 'max', value: current.max_total_ms },
            ].map(({ label, value }) => (
              <div
                key={label}
                className="rounded p-2 text-center"
                style={{ background: 'var(--color-sentinel-bg-secondary)', border: '1px solid var(--color-sentinel-border)' }}
              >
                <p className="text-[10px] uppercase tracking-wide" style={{ color: 'var(--color-sentinel-text-secondary)' }}>
                  {label}
                </p>
                <p className="text-sm font-bold font-mono mt-0.5" style={{ color: 'var(--color-sentinel-text-primary)' }}>
                  {formatMs(value)}
                </p>
              </div>
            ))}
          </div>
        </div>
      ) : (
        <div className="mb-4 p-4 rounded-lg text-center" style={{ background: 'var(--color-sentinel-bg-secondary)', border: '1px solid var(--color-sentinel-border)' }}>
          <p className="text-sm" style={{ color: 'var(--color-sentinel-text-secondary)' }}>
            No traces recorded this hour yet
          </p>
        </div>
      )}

      {/* 7-day sparkline */}
      {history.length > 0 && (
        <div>
          <p className="text-xs font-medium mb-2" style={{ color: 'var(--color-sentinel-text-secondary)' }}>
            7-Day p99 Trend
          </p>
          <div className="flex items-end gap-1 h-12">
            {history.slice(-14).map((row, i) => {
              const maxVal = Math.max(...history.map((h) => h.p99_total_ms || 0), 7000);
              const barHeight = row.p99_total_ms ? Math.max(4, (row.p99_total_ms / maxVal) * 48) : 4;
              const isBreach = row.p99_total_ms > 7000;
              return (
                <div
                  key={i}
                  className="flex-1 rounded-t transition-all hover:opacity-80"
                  style={{
                    height: `${barHeight}px`,
                    background: isBreach ? 'var(--color-sentinel-amber)' : 'var(--color-sentinel-blue)',
                    minHeight: '4px',
                  }}
                  title={`${formatDate(row.hour_start)} ${formatHour(row.hour_start)}: p99=${formatMs(row.p99_total_ms)}`}
                />
              );
            })}
          </div>
          {/* SLO line legend */}
          <div className="flex items-center justify-between mt-1">
            <p className="text-[10px]" style={{ color: 'var(--color-sentinel-text-disabled)' }}>7 days ago</p>
            <p className="text-[10px] flex items-center gap-1" style={{ color: 'var(--color-sentinel-text-disabled)' }}>
              <span className="w-2 h-0.5 rounded" style={{ background: 'var(--color-sentinel-amber)' }} />
              7000ms SLO
            </p>
            <p className="text-[10px]" style={{ color: 'var(--color-sentinel-text-disabled)' }}>now</p>
          </div>
        </div>
      )}
    </div>
  );
}
