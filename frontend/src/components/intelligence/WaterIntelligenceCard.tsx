// @ts-nocheck
import { useState, useEffect } from 'react';
import { Droplets, ArrowRight } from 'lucide-react';
import { waterApi } from '@/lib/waterApi';
import type { WaterTrending, WaterAlert } from '@/lib/waterApi';

interface WaterIntelligenceCardProps {
  siteId: string;
  onNavigate: () => void;
}

export function WaterIntelligenceCard({ siteId, onNavigate }: WaterIntelligenceCardProps) {
  const [trending, setTrending] = useState<WaterTrending | null>(null);
  const [alerts, setAlerts] = useState<WaterAlert[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      setLoading(true);
      try {
        const [t, a] = await Promise.allSettled([
          waterApi.getTrending(siteId, 'weekly'),
          waterApi.getActiveAlerts(siteId),
        ]);
        if (cancelled) return;
        if (t.status === 'fulfilled') setTrending(t.value);
        if (a.status === 'fulfilled') setAlerts(Array.isArray(a.value) ? a.value : (a.value as any)?.alerts ?? []);
      } catch {
        // graceful degradation
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    load();
    return () => { cancelled = true; };
  }, [siteId]);

  if (loading) {
    return (
      <div className="p-6 text-center rounded-lg" style={{ background: 'var(--color-sentinel-bg-panel)' }}>
        <div className="animate-spin h-6 w-6 border-3 border-cyan-500 border-t-transparent rounded-full mx-auto mb-2" />
        <p className="text-xs" style={{ color: 'var(--color-sentinel-text-secondary)' }}>Loading Water data...</p>
      </div>
    );
  }

  const baselineComparison = trending?.baseline_comparison_percent ?? 0;
  const activeAlerts = alerts.length;
  const peakFlow = trending?.peak_flow_rate_lpm ?? 0;
  const trendDirection = trending?.trend_direction ?? 'stable';

  const savingsText = baselineComparison < 0
    ? `${Math.abs(baselineComparison).toFixed(0)}% below baseline`
    : baselineComparison > 0
      ? `${baselineComparison.toFixed(0)}% above baseline`
      : 'Collecting baseline...';

  return (
    <div
      className="rounded-lg overflow-hidden"
      style={{
        background: 'var(--color-sentinel-bg-panel)',
        border: '1px solid var(--color-sentinel-border)',
      }}
    >
      {/* Header */}
      <div className="p-4 flex items-center justify-between" style={{ borderBottom: '1px solid var(--color-sentinel-border)' }}>
        <div className="flex items-center gap-3">
          <div className="p-2 rounded" style={{ background: 'rgba(6, 182, 212, 0.15)' }}>
            <Droplets className="h-5 w-5" style={{ color: '#06B6D4' }} />
          </div>
          <div>
            <h3 className="font-medium text-sm" style={{ color: 'var(--color-sentinel-text-primary)' }}>
              Water Intelligence
            </h3>
            <span className="text-xs" style={{ color: 'var(--color-sentinel-text-secondary)' }}>
              Consumption monitoring &amp; leak detection
            </span>
          </div>
        </div>
        <span
          className="text-xs px-2 py-1 rounded font-medium"
          style={{
            background: baselineComparison <= 0 ? 'rgba(16, 185, 129, 0.15)' : 'rgba(245, 158, 11, 0.15)',
            color: baselineComparison <= 0 ? 'var(--color-sentinel-green)' : 'var(--color-sentinel-amber)',
          }}
        >
          {savingsText}
        </span>
      </div>

      {/* Metrics */}
      <div className="p-4">
        <div className="grid grid-cols-3 gap-3 mb-4">
          <MetricBox
            label="vs Baseline"
            value={baselineComparison !== 0 ? `${baselineComparison > 0 ? '+' : ''}${baselineComparison.toFixed(0)}%` : '—'}
            color={baselineComparison <= 0 ? '#10B981' : '#F59E0B'}
          />
          <MetricBox
            label="Active Alerts"
            value={`${activeAlerts}`}
            color={activeAlerts > 0 ? '#EF4444' : '#22C55E'}
          />
          <MetricBox
            label="Peak Flow"
            value={peakFlow > 0 ? `${peakFlow.toFixed(1)} L/m` : '—'}
            color="#06B6D4"
          />
        </div>

        {/* AI Value + Navigate */}
        <div className="flex items-center justify-between">
          <p className="text-xs" style={{ color: 'var(--color-sentinel-text-secondary)' }}>
            <span style={{ color: '#06B6D4' }}>SENTINEL AI:</span>{' '}
            Leak detection with pattern analysis &amp; baseline tracking
          </p>
          <button
            onClick={onNavigate}
            className="flex items-center gap-1 text-xs font-medium hover:underline"
            style={{ color: '#06B6D4', background: 'none', border: 'none', cursor: 'pointer' }}
          >
            View Details <ArrowRight className="h-3 w-3" />
          </button>
        </div>
      </div>
    </div>
  );
}

function MetricBox({ label, value, color }: { label: string; value: string; color: string }) {
  return (
    <div className="p-3 rounded text-center" style={{
      background: 'var(--color-sentinel-bg-secondary)',
      border: '1px solid var(--color-sentinel-border)',
    }}>
      <div className="text-lg font-semibold" style={{ color }}>{value}</div>
      <div className="text-xs mt-1" style={{ color: 'var(--color-sentinel-text-secondary)' }}>{label}</div>
    </div>
  );
}
