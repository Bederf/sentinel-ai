// @ts-nocheck
import { useState, useEffect } from 'react';
import { Zap } from 'lucide-react';
import api from '@/lib/api';
import type { OptimizationStatusResponse } from '@/lib/api';
import {
  IntelligenceCard, ValueMetricBox, ValueBadge, LearningBadge, AwaitingDataBadge,
  hasValue, formatCurrencyZAR,
  type CardState,
} from './shared';

interface EnergyIntelligenceCardProps {
  siteId: string;
  onNavigate: () => void;
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

  // Determine state
  let state: CardState;
  if (apiError || !status) {
    state = 'no-data';
  } else if (status.optimization_status === 'unknown' || (!hasValue(savings) && applied === 0)) {
    state = 'learning';
  } else {
    state = 'active';
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

  return (
    <IntelligenceCard
      title="Energy Intelligence"
      subtitle="Optimisation &amp; cost management"
      icon={<Zap className="h-5 w-5" style={{ color: '#10B981' }} />}
      iconBg="rgba(16, 185, 129, 0.15)"
      accentColor="var(--color-sentinel-green)"
      badge={badge}
      state={state}
      footer={footer}
      onNavigate={onNavigate}
      metrics={
        <>
          <ValueMetricBox label="Optimisations applied" value={`${applied}`} color={applied > 0 ? '#10B981' : '#6B7280'} />
          <ValueMetricBox label="Mode" value={mode === 'automatic' ? 'Auto' : 'Supervised'} color="#3B82F6" />
          <ValueMetricBox label="Savings rate" value={hasValue(savingsPerHour) ? `${formatCurrencyZAR(savingsPerHour)}/hr` : '—'} color="#F59E0B" />
        </>
      }
    />
  );
}
