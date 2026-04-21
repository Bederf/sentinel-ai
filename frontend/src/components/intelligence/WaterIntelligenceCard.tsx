/* eslint-disable @typescript-eslint/ban-ts-comment */
// @ts-nocheck
import { useState, useEffect } from 'react';
import { Droplets } from 'lucide-react';
import { waterApi } from '@/lib/waterApi';
import type { WaterTrending, WaterAlert } from '@/lib/waterApi';
import {
  IntelligenceCard, ValueMetricBox, ValueBadge, LearningBadge, AwaitingDataBadge,
  BaselineComparisonBar, type CardState,
} from './shared';

interface WaterIntelligenceCardProps {
  siteId: string;
  onNavigate?: () => void;
}

export function WaterIntelligenceCard({ siteId, onNavigate }: WaterIntelligenceCardProps) {
  const [trending, setTrending] = useState<WaterTrending | null>(null);
  const [alerts, setAlerts] = useState<WaterAlert[]>([]);
  const [loading, setLoading] = useState(true);
  const [apiError, setApiError] = useState(false);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      setLoading(true);
      setApiError(false);
      try {
        const [t, a] = await Promise.allSettled([
          waterApi.getTrending(siteId, 'week'),
          waterApi.getActiveAlerts(siteId),
        ]);
        if (cancelled) return;
        const trendOk = t.status === 'fulfilled';
        const alertOk = a.status === 'fulfilled';
        if (!trendOk && !alertOk) { setApiError(true); return; }
        if (trendOk) setTrending(t.value);
        if (alertOk) setAlerts(Array.isArray(a.value) ? a.value : (a.value as any)?.alerts ?? []);
      } catch {
        if (!cancelled) setApiError(true);
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
  const trendDirection = trending?.trend_direction ?? 'stable';

  // Determine state
  let state: CardState;
  if (apiError || (!trending && activeAlerts === 0)) {
    state = 'no-data';
  } else if (trending && baselineComparison === 0 && activeAlerts === 0) {
    state = 'learning';
  } else {
    state = 'active';
  }

  // Badge
  const badge = state === 'no-data'
    ? <AwaitingDataBadge />
    : state === 'learning'
      ? <LearningBadge text="Collecting baseline" />
      : activeAlerts > 0
        ? <ValueBadge text={`${activeAlerts} anomal${activeAlerts === 1 ? 'y' : 'ies'} detected`} positive={false} />
        : <ValueBadge text={`${Math.abs(baselineComparison).toFixed(0)}% below baseline`} />;

  // Footer
  const footer = state === 'no-data'
    ? 'Connected and ready. Start data source to begin analysis.'
    : state === 'learning'
      ? 'Building consumption baseline from historical patterns. Full comparison available soon.'
      : activeAlerts > 0 && baselineComparison < 0
        ? `Detected ${activeAlerts} anomal${activeAlerts === 1 ? 'y' : 'ies'}, maintained ${Math.abs(baselineComparison).toFixed(0)}% below baseline through pattern analysis`
        : activeAlerts > 0
          ? `Detected ${activeAlerts} consumption anomal${activeAlerts === 1 ? 'y' : 'ies'} through pattern analysis`
          : `Maintained ${Math.abs(baselineComparison).toFixed(0)}% below baseline — no anomalies detected`;

  const trendLabel = trendDirection === 'rising' ? 'Rising' : trendDirection === 'falling' ? 'Falling' : 'Stable';
  const trendColor = trendDirection === 'falling' ? 'var(--color-sentinel-green)' : trendDirection === 'rising' ? 'var(--color-sentinel-amber)' : 'var(--color-sentinel-blue)';

  return (
    <IntelligenceCard
      title="Water Intelligence"
      subtitle="Consumption monitoring &amp; leak detection"
      icon={<Droplets className="h-5 w-5" style={{ color: 'var(--color-sentinel-cyan)' }} />}
      iconBg="rgba(6, 182, 212, 0.15)"
      accentColor="var(--color-sentinel-cyan)"
      badge={badge}
      state={state}
      footer={footer}
      onNavigate={onNavigate}
      metrics={
        <>
          <ValueMetricBox label="Below baseline" value={baselineComparison < 0 ? `${Math.abs(baselineComparison).toFixed(0)}%` : '—'} color={baselineComparison <= 0 ? 'var(--color-sentinel-green)' : 'var(--color-sentinel-amber)'} />
          <ValueMetricBox label="Alerts caught" value={`${activeAlerts}`} color={activeAlerts > 0 ? 'var(--color-sentinel-red)' : 'var(--color-sentinel-green)'} />
          <ValueMetricBox label="Trend" value={trendLabel} color={trendColor} />
        </>
      }
      comparison={baselineComparison < 0 ? (
        <BaselineComparisonBar
          baselineValue={100}
          optimizedValue={100 + baselineComparison}
          unit="%"
          baselineLabel="Baseline consumption"
          optimizedLabel="With SENTINEL monitoring"
          accentColor="var(--color-sentinel-cyan)"
        />
      ) : undefined}
    />
  );
}
