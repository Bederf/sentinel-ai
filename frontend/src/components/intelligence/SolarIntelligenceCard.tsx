// @ts-nocheck
import { useState, useEffect } from 'react';
import { Sun } from 'lucide-react';
import { fetchLiveSystemData, fetchPerformanceSummary } from '@/lib/api/solar';
import { authorizedFetch } from '@/lib/api';
import type { LiveSystemData, PerformanceSummary } from '@/lib/api/solar';
import {
  IntelligenceCard, ValueMetricBox, ValueBadge, LearningBadge, AwaitingDataBadge,
  BaselineComparisonBar, hasValue, formatCurrencyZAR, type CardState,
} from './shared';

interface SolarIntelligenceCardProps {
  siteId: string;
  onNavigate?: () => void;
}

interface FinancialSummary {
  total_savings_zar?: number;
  monthly_avg_zar?: number;
  daily_avg_zar?: number;
  ytd_roi_percent?: number;
  self_consumption_percent?: number;
  period?: string;
}

export function SolarIntelligenceCard({ siteId, onNavigate }: SolarIntelligenceCardProps) {
  const [live, setLive] = useState<LiveSystemData | null>(null);
  const [perf, setPerf] = useState<PerformanceSummary | null>(null);
  const [financial, setFinancial] = useState<FinancialSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [apiError, setApiError] = useState(false);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      setLoading(true);
      setApiError(false);
      try {
        const [l, p, f] = await Promise.allSettled([
          fetchLiveSystemData(siteId),
          fetchPerformanceSummary(siteId),
          authorizedFetch(`/api/solar/sites/${siteId}/financial/summary?period=ytd`).then(r => r.ok ? r.json() : null),
        ]);
        if (cancelled) return;
        const anyOk = l.status === 'fulfilled' || p.status === 'fulfilled' || (f.status === 'fulfilled' && f.value);
        if (!anyOk) { setApiError(true); return; }
        if (l.status === 'fulfilled') setLive(l.value);
        if (p.status === 'fulfilled') setPerf(p.value);
        if (f.status === 'fulfilled' && f.value) setFinancial(f.value);
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
        <div className="animate-spin h-6 w-6 border-3 border-amber-500 border-t-transparent rounded-full mx-auto mb-2" />
        <p className="text-xs" style={{ color: 'var(--color-sentinel-text-secondary)' }}>Loading Solar data...</p>
      </div>
    );
  }

  const ratedCapacity = live?.rated_capacity_kwp ?? 297;
  const monthlyValue = financial?.monthly_avg_zar ?? 0;
  const dailyValue = financial?.daily_avg_zar ?? ((live?.daily_yield_kwh ?? 0) * 5);
  const ytdRoi = financial?.ytd_roi_percent ?? 0;
  const totalSavingsYtd = financial?.total_savings_zar ?? 0;
  const selfConsumption = financial?.self_consumption_percent ??
    (ratedCapacity > 0 ? Math.max(0, 100 - ((live?.energy_exported_kwh ?? 0) / Math.max(1, live?.daily_yield_kwh ?? 1)) * 100) : 0);

  // Determine state
  let state: CardState;
  if (apiError || (!live && !financial)) {
    state = 'no-data';
  } else if (!hasValue(monthlyValue) && !hasValue(dailyValue)) {
    state = 'learning';
  } else {
    state = 'active';
  }

  // Badge
  const badge = state === 'no-data'
    ? <AwaitingDataBadge />
    : state === 'learning'
      ? <LearningBadge text="Awaiting generation" />
      : hasValue(monthlyValue)
        ? <ValueBadge text={`${formatCurrencyZAR(monthlyValue)}/month solar value captured`} />
        : <ValueBadge text={`~${formatCurrencyZAR(dailyValue)}/day`} />;

  // Footer
  const footer = state === 'no-data'
    ? 'Connected and ready. Start data source to begin analysis.'
    : state === 'learning'
      ? `Monitoring ${ratedCapacity} kWp plant. Value tracking will activate once generation data flows.`
      : hasValue(totalSavingsYtd)
        ? `Optimised ${formatCurrencyZAR(totalSavingsYtd)} YTD through BESS dispatch and self-consumption maximisation`
        : `Capturing ~${formatCurrencyZAR(dailyValue)}/day from ${ratedCapacity} kWp plant with BESS dispatch optimisation`;

  // Baseline vs SENTINEL: grid cost without solar vs with solar+BESS optimisation
  // Without SENTINEL dispatch, self-consumption would be ~60% (no BESS scheduling)
  const baselineSelfConsumption = 60;
  const gridCostBaseline = monthlyValue > 0 ? monthlyValue / (selfConsumption / 100) : 0;
  const gridCostOptimized = gridCostBaseline - monthlyValue;

  return (
    <IntelligenceCard
      title="Solar &amp; BESS Intelligence"
      subtitle="Generation, storage &amp; grid offset"
      icon={<Sun className="h-5 w-5" style={{ color: '#FACC15' }} />}
      iconBg="rgba(250, 204, 21, 0.15)"
      accentColor="#FACC15"
      badge={badge}
      state={state}
      footer={footer}
      onNavigate={onNavigate}
      metrics={
        <>
          <ValueMetricBox label="Self-consumption optimised" value={selfConsumption > 0 ? `${selfConsumption.toFixed(0)}%` : '—'} color="#10B981" />
          <ValueMetricBox label="Daily generation value" value={hasValue(dailyValue) ? formatCurrencyZAR(dailyValue) : '—'} color="#FACC15" />
          <ValueMetricBox label="YTD ROI" value={ytdRoi > 0 ? `${ytdRoi.toFixed(1)}%` : '—'} color="#3B82F6" />
        </>
      }
      comparison={gridCostBaseline > 0 ? (
        <BaselineComparisonBar
          baselineValue={gridCostBaseline}
          optimizedValue={gridCostOptimized}
          unit="ZAR"
          baselineLabel="Monthly grid cost (no solar)"
          optimizedLabel="With SENTINEL dispatch"
          accentColor="#FACC15"
        />
      ) : undefined}
    />
  );
}
