// @ts-nocheck
import { useState, useEffect } from 'react';
import { Sun, ArrowRight } from 'lucide-react';
import { fetchLiveSystemData, fetchPerformanceSummary } from '@/lib/api/solar';
import type { LiveSystemData, PerformanceSummary } from '@/lib/api/solar';

interface SolarIntelligenceCardProps {
  siteId: string;
  onNavigate: () => void;
}

export function SolarIntelligenceCard({ siteId, onNavigate }: SolarIntelligenceCardProps) {
  const [live, setLive] = useState<LiveSystemData | null>(null);
  const [perf, setPerf] = useState<PerformanceSummary | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      setLoading(true);
      try {
        const [l, p] = await Promise.allSettled([
          fetchLiveSystemData(siteId),
          fetchPerformanceSummary(siteId),
        ]);
        if (cancelled) return;
        if (l.status === 'fulfilled') setLive(l.value);
        if (p.status === 'fulfilled') setPerf(p.value);
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
        <div className="animate-spin h-6 w-6 border-3 border-amber-500 border-t-transparent rounded-full mx-auto mb-2" />
        <p className="text-xs" style={{ color: 'var(--color-sentinel-text-secondary)' }}>Loading Solar data...</p>
      </div>
    );
  }

  const currentGen = live?.current_generation_kw ?? 0;
  const ratedCapacity = live?.rated_capacity_kwp ?? 297;
  const genPercent = live?.generation_percent ?? 0;
  const selfConsumption = ratedCapacity > 0 ? Math.max(0, 100 - ((live?.energy_exported_kwh ?? 0) / Math.max(1, live?.daily_yield_kwh ?? 1)) * 100) : 0;
  const perfRatio = perf?.system_efficiency_percent ?? 0;

  // Estimate daily savings: daily_yield * R5/kWh (commercial rate)
  const dailySavings = (live?.daily_yield_kwh ?? 0) * 5;
  const savingsText = dailySavings > 0
    ? `~R${dailySavings.toLocaleString(undefined, { maximumFractionDigits: 0 })}/day`
    : 'No generation';

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
          <div className="p-2 rounded" style={{ background: 'rgba(250, 204, 21, 0.15)' }}>
            <Sun className="h-5 w-5" style={{ color: '#FACC15' }} />
          </div>
          <div>
            <h3 className="font-medium text-sm" style={{ color: 'var(--color-sentinel-text-primary)' }}>
              Solar &amp; BESS Intelligence
            </h3>
            <span className="text-xs" style={{ color: 'var(--color-sentinel-text-secondary)' }}>
              Generation, storage &amp; grid offset
            </span>
          </div>
        </div>
        <span
          className="text-xs px-2 py-1 rounded font-medium"
          style={{
            background: dailySavings > 0 ? 'rgba(16, 185, 129, 0.15)' : 'rgba(245, 158, 11, 0.15)',
            color: dailySavings > 0 ? 'var(--color-sentinel-green)' : 'var(--color-sentinel-amber)',
          }}
        >
          {savingsText}
        </span>
      </div>

      {/* Metrics */}
      <div className="p-4">
        <div className="grid grid-cols-3 gap-3 mb-4">
          <MetricBox label="Generation" value={`${currentGen.toFixed(1)} kW`} subtitle={`of ${ratedCapacity} kWp (${genPercent.toFixed(0)}%)`} color="#FACC15" />
          <MetricBox label="Self-Consumption" value={`${selfConsumption.toFixed(0)}%`} color="#10B981" />
          <MetricBox label="Performance Ratio" value={perfRatio > 0 ? `${perfRatio.toFixed(1)}%` : '—'} color="#3B82F6" />
        </div>

        {/* AI Value + Navigate */}
        <div className="flex items-center justify-between">
          <p className="text-xs" style={{ color: 'var(--color-sentinel-text-secondary)' }}>
            <span style={{ color: '#FACC15' }}>SENTINEL AI:</span>{' '}
            Solar yield optimisation with BESS dispatch scheduling
          </p>
          <button
            onClick={onNavigate}
            className="flex items-center gap-1 text-xs font-medium hover:underline"
            style={{ color: '#FACC15', background: 'none', border: 'none', cursor: 'pointer' }}
          >
            View Details <ArrowRight className="h-3 w-3" />
          </button>
        </div>
      </div>
    </div>
  );
}

function MetricBox({ label, value, subtitle, color }: { label: string; value: string; subtitle?: string; color: string }) {
  return (
    <div className="p-3 rounded text-center" style={{
      background: 'var(--color-sentinel-bg-secondary)',
      border: '1px solid var(--color-sentinel-border)',
    }}>
      <div className="text-lg font-semibold" style={{ color }}>{value}</div>
      {subtitle && <div className="text-[10px] mt-0.5" style={{ color: 'var(--color-sentinel-text-secondary)' }}>{subtitle}</div>}
      <div className="text-xs mt-1" style={{ color: 'var(--color-sentinel-text-secondary)' }}>{label}</div>
    </div>
  );
}
