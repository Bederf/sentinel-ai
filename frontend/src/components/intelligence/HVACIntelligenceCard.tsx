// @ts-nocheck
import { useState, useEffect } from 'react';
import { Thermometer } from 'lucide-react';
import { hvacApi } from '@/lib/hvacApi';
import api from '@/lib/api';
import type { HVACOverview, ThermalRunway } from '@/lib/hvacApi';
import type { PredictionsResponse } from '@/lib/api';
import {
  IntelligenceCard, ValueMetricBox, ValueBadge, LearningBadge, AwaitingDataBadge,
  hasValue, formatCurrencyZAR, type CardState,
} from './shared';

const HVAC_TYPES = ['chiller', 'ahu', 'fcu', 'vav', 'split', 'ct', 'crac'];

interface HVACIntelligenceCardProps {
  siteId: string;
  onNavigate: () => void;
}

export function HVACIntelligenceCard({ siteId, onNavigate }: HVACIntelligenceCardProps) {
  const [overview, setOverview] = useState<HVACOverview | null>(null);
  const [thermal, setThermal] = useState<ThermalRunway | null>(null);
  const [predictions, setPredictions] = useState<PredictionsResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [apiError, setApiError] = useState(false);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      setLoading(true);
      setApiError(false);
      try {
        const [ov, th, pred] = await Promise.allSettled([
          hvacApi.getOverview(siteId),
          hvacApi.getThermalRunway(siteId),
          api.getPredictions(siteId),
        ]);
        if (cancelled) return;
        const anyOk = ov.status === 'fulfilled' || th.status === 'fulfilled' || pred.status === 'fulfilled';
        if (!anyOk) { setApiError(true); return; }
        if (ov.status === 'fulfilled') setOverview(ov.value);
        if (th.status === 'fulfilled') setThermal(th.value);
        if (pred.status === 'fulfilled') setPredictions(pred.value);
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
        <div className="animate-spin h-6 w-6 border-3 border-blue-500 border-t-transparent rounded-full mx-auto mb-2" />
        <p className="text-xs" style={{ color: 'var(--color-sentinel-text-secondary)' }}>Loading HVAC data...</p>
      </div>
    );
  }

  // Filter predictions to HVAC types
  const hvacPredictions = predictions?.predictions?.filter(p =>
    HVAC_TYPES.includes((p.equipment_type || '').toLowerCase())
  ) ?? [];
  const faultsPredicted = hvacPredictions.length;
  const riskAvoided = hvacPredictions.reduce((sum, p) => sum + (p.financial_impact?.potential_loss_zar ?? 0), 0);

  const runwayHours = thermal?.metrics?.runway_with ?? 0;
  const improvementPct = thermal?.metrics?.improvement_percent ?? 0;

  const zonesTotal = overview?.zones?.total ?? 0;
  const zonesFault = overview?.zones?.fault ?? 0;
  const zonesOffline = overview?.zones?.offline ?? 0;
  const zonesComfort = zonesTotal > 0
    ? Math.round(((zonesTotal - zonesFault - zonesOffline) / zonesTotal) * 100)
    : 0;

  // Determine state
  let state: CardState;
  if (apiError || (!overview && !thermal && !predictions)) {
    state = 'no-data';
  } else if (zonesTotal === 0 && faultsPredicted === 0 && runwayHours === 0) {
    state = 'learning';
  } else {
    state = 'active';
  }

  // Badge
  let badge;
  if (state === 'no-data') {
    badge = <AwaitingDataBadge />;
  } else if (state === 'learning') {
    badge = <LearningBadge text="Analysing thermal patterns" />;
  } else if (faultsPredicted > 0) {
    badge = <ValueBadge text={`${faultsPredicted} fault${faultsPredicted !== 1 ? 's' : ''} predicted — ${formatCurrencyZAR(riskAvoided)} risk avoided`} />;
  } else if (improvementPct > 0) {
    badge = <ValueBadge text={`${improvementPct.toFixed(0)}% pre-cooling improvement`} />;
  } else {
    badge = <ValueBadge text={`${zonesComfort}% zone comfort`} />;
  }

  // Footer
  const footer = state === 'no-data'
    ? 'Connected and ready. Start data source to begin analysis.'
    : state === 'learning'
      ? 'Building thermal models from zone data. Predictive analysis will activate once patterns are established.'
      : faultsPredicted > 0 && runwayHours > 0
        ? `Predicted ${faultsPredicted} fault${faultsPredicted !== 1 ? 's' : ''}, extended thermal runway by ${runwayHours.toFixed(1)}h through pre-cooling`
        : faultsPredicted > 0
          ? `Predicted ${faultsPredicted} fault${faultsPredicted !== 1 ? 's' : ''} across HVAC fleet — ${formatCurrencyZAR(riskAvoided)} risk avoided`
          : improvementPct > 0
            ? `Pre-cooling optimisation delivering ${improvementPct.toFixed(0)}% improvement with ${zonesComfort}% zone comfort`
            : `Monitoring ${zonesTotal} zones — ${zonesComfort}% comfort maintained`;

  return (
    <IntelligenceCard
      title="HVAC Intelligence"
      subtitle="Climate control &amp; thermal management"
      icon={<Thermometer className="h-5 w-5" style={{ color: '#3B82F6' }} />}
      iconBg="rgba(59, 130, 246, 0.15)"
      accentColor="var(--color-sentinel-blue)"
      badge={badge}
      state={state}
      footer={footer}
      onNavigate={onNavigate}
      metrics={
        <>
          <ValueMetricBox label="Pre-cooling runway" value={runwayHours > 0 ? `${runwayHours.toFixed(1)}h` : '—'} color="#3B82F6" />
          <ValueMetricBox label="Zone comfort maintained" value={zonesTotal > 0 ? `${zonesComfort}%` : '—'} color={zonesComfort >= 90 ? '#22C55E' : '#F59E0B'} />
          <ValueMetricBox label="Anomalies detected" value={`${zonesFault}`} color={zonesFault > 0 ? '#EF4444' : '#22C55E'} />
        </>
      }
    />
  );
}
