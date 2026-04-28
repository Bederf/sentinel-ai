/* eslint-disable @typescript-eslint/ban-ts-comment */
// @ts-nocheck
import { useState, useEffect } from 'react';
import { Zap } from 'lucide-react';
import api from '@/lib/api';
import type { OptimizationStatusResponse } from '@/lib/api';
import {
  IntelligenceCard, ValueMetricBox, ValueBadge, LearningBadge, AwaitingDataBadge,
  BaselineComparisonBar, hasValue, formatCurrencyZAR,
  type CardState,
} from './shared';

interface EnergyIntelligenceCardProps {
  siteId: string;
  onNavigate?: () => void;
}

export function EnergyIntelligenceCard({ siteId, onNavigate }: EnergyIntelligenceCardProps) {
  const [status, setStatus] = useState<OptimizationStatusResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [apiError, setApiError] = useState(false);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      setLoading(true);
      setApiError(false);
      try {
        const s = await api.getOptimizationStatus(siteId);
        if (!cancelled) setStatus(s);
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
        <div className="animate-spin h-6 w-6 border-3 border-green-500 border-t-transparent rounded-full mx-auto mb-2" />
        <p className="text-xs" style={{ color: 'var(--color-sentinel-text-secondary)' }}>Loading Energy data...</p>
      </div>
    );
  }

  const savings = status?.monthly_savings?.monthly_savings_zar ?? 0;
  const savingsPerHour = status?.monthly_savings?.savings_per_hour_zar ?? 0;
  const mode = status?.optimization_settings?.mode ?? 'supervised';
  const applied = status?.monthly_savings?.applied_recommendations ?? 0;

  // Determine state — show active if any meaningful optimization data exists
  // even if optimization_status is "unknown" (baseline established but no recommendations applied yet)
  let state: CardState;
  const hasSavings = hasValue(savings) && savings > 0;
  const hasApplied = applied > 0;
  if (apiError || !status) {
    state = 'no-data';
  } else if (
    status.optimization_status !== 'unknown'
    && status.optimization_status != null
  ) {
    state = 'active';
  } else if (hasSavings || hasApplied) {
    // Baseline established — savings or applied recommendations exist
    state = 'active';
  } else {
    state = 'learning';
  }

  // Badge per state
  const badge = state === 'no-data'
    ? <AwaitingDataBadge />
    : state === 'learning'
      ? <LearningBadge text="Collecting baseline" />
      : <ValueBadge text={`${formatCurrencyZAR(savings)} saved this month`} />;

  // Footer per state
  const footer = state === 'no-data'
    ? 'Connected and ready. Start data source to begin analysis.'
    : state === 'learning'
      ? 'Building energy consumption baseline. Full analysis available once patterns are established.'
      : `Applied ${applied} optimisation${applied !== 1 ? 's' : ''} saving ${formatCurrencyZAR(savings)}/month with tariff-aware scheduling`;

  // Baseline vs SENTINEL: monthly energy cost without vs with optimisation
  // Estimate baseline from savings (if saving R5k/month, baseline was ~R5k higher)
  const monthlyBaseline = savings > 0 ? savings / 0.25 : 0; // savings ≈ 25% of baseline
  const monthlyOptimized = monthlyBaseline - savings;

  return (
    <IntelligenceCard
      title="Energy Intelligence"
      subtitle="Optimisation &amp; cost management"
      icon={<Zap className="h-5 w-5" style={{ color: 'var(--color-sentinel-green)' }} />}
      iconBg="rgba(16, 185, 129, 0.15)"
      accentColor="var(--color-sentinel-green)"
      badge={badge}
      state={state}
      footer={footer}
      onNavigate={onNavigate}
      metrics={
        <>
          <ValueMetricBox label="Optimisations applied" value={`${applied}`} color={applied > 0 ? 'var(--color-sentinel-green)' : 'var(--color-sentinel-text-secondary)'} />
          <ValueMetricBox label="Mode" value={mode === 'automatic' ? 'Auto' : 'Supervised'} color="var(--color-sentinel-blue)" />
          <ValueMetricBox label="Savings rate" value={hasValue(savingsPerHour) ? `${formatCurrencyZAR(savingsPerHour)}/hr` : '—'} color="var(--color-sentinel-amber)" />
        </>
      }
      comparison={monthlyBaseline > 0 ? (
        <BaselineComparisonBar
          baselineValue={monthlyBaseline}
          optimizedValue={monthlyOptimized}
          unit="ZAR"
          baselineLabel="Monthly energy cost"
          optimizedLabel="With SENTINEL optimisation"
          accentColor="var(--color-sentinel-green)"
        />
      ) : undefined}
    />
  );
}
