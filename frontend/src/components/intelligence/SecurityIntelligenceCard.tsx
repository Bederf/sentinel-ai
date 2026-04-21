/* eslint-disable @typescript-eslint/ban-ts-comment */
// @ts-nocheck
import { useState, useEffect } from 'react';
import { Shield } from 'lucide-react';
import { securityApi } from '@/lib/api';
import {
  IntelligenceCard, ValueMetricBox, ValueBadge, LearningBadge, AwaitingDataBadge,
  BaselineComparisonBar, type CardState,
} from './shared';

interface SecurityIntelligenceCardProps {
  siteId: string;
  onNavigate?: () => void;
}

export function SecurityIntelligenceCard({ siteId, onNavigate }: SecurityIntelligenceCardProps) {
  const [status, setStatus] = useState<any>(null);
  const [occupancy, setOccupancy] = useState<any>(null);
  const [afterHours, setAfterHours] = useState<{ events: any[]; count: number }>({ events: [], count: 0 });
  const [anomalies, setAnomalies] = useState<{ anomalies: any[]; anomaly_count: number }>({ anomalies: [], anomaly_count: 0 });
  const [loading, setLoading] = useState(true);
  const [apiError, setApiError] = useState(false);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      setLoading(true);
      setApiError(false);
      try {
        const [s, o, ah, an] = await Promise.allSettled([
          securityApi.getStatus(siteId),
          securityApi.getOccupancy(siteId),
          securityApi.getAfterHoursEvents(siteId),
          securityApi.getAnomalies(siteId),
        ]);
        if (cancelled) return;
        const anyOk = s.status === 'fulfilled' || o.status === 'fulfilled';
        if (!anyOk) { setApiError(true); return; }
        if (s.status === 'fulfilled') setStatus(s.value);
        if (o.status === 'fulfilled') setOccupancy(o.value);
        if (ah.status === 'fulfilled') setAfterHours(ah.value);
        if (an.status === 'fulfilled') setAnomalies(an.value);
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
        <div className="animate-spin h-6 w-6 border-3 border-purple-500 border-t-transparent rounded-full mx-auto mb-2" />
        <p className="text-xs" style={{ color: 'var(--color-sentinel-text-secondary)' }}>Loading Security data...</p>
      </div>
    );
  }

  const totalOccupancy = occupancy?.total_occupancy ?? status?.occupancy_total ?? 0;
  const afterHoursCount = afterHours?.count ?? afterHours?.events?.length ?? 0;
  const anomalyCount = anomalies?.anomaly_count ?? anomalies?.anomalies?.length ?? 0;
  const hasOccupancyData = totalOccupancy > 0;

  // Determine state
  let state: CardState;
  if (apiError || (!status && !occupancy)) {
    state = 'no-data';
  } else if (!hasOccupancyData && anomalyCount === 0 && afterHoursCount === 0) {
    state = 'learning';
  } else {
    state = 'active';
  }

  // Badge
  const badge = state === 'no-data'
    ? <AwaitingDataBadge />
    : state === 'learning'
      ? <LearningBadge text="Collecting baseline" />
      : anomalyCount > 0
        ? <ValueBadge text={`${anomalyCount} anomal${anomalyCount === 1 ? 'y' : 'ies'} detected`} positive={false} />
        : hasOccupancyData
          ? <ValueBadge text={`${totalOccupancy} people — occupancy-HVAC correlation active`} />
          : <ValueBadge text="Monitoring active" />;

  // Footer
  const footer = state === 'no-data'
    ? 'Connected and ready. Start data source to begin analysis.'
    : state === 'learning'
      ? 'Building occupancy baseline for cross-system correlation. Anomaly detection will activate once patterns are established.'
      : hasOccupancyData && afterHoursCount > 0
        ? `Tracked ${totalOccupancy} occupants, flagged ${afterHoursCount} after-hours entr${afterHoursCount === 1 ? 'y' : 'ies'}, correlated with HVAC scheduling`
        : hasOccupancyData
          ? `Tracking ${totalOccupancy} occupants with cross-system HVAC correlation active`
          : 'Monitoring access events for anomaly detection';

  return (
    <IntelligenceCard
      title="Security Intelligence"
      subtitle="Access control &amp; occupancy monitoring"
      icon={<Shield className="h-5 w-5" style={{ color: 'var(--color-sentinel-purple)' }} />}
      iconBg="rgba(168, 85, 247, 0.15)"
      accentColor="var(--color-sentinel-purple)"
      badge={badge}
      state={state}
      footer={footer}
      onNavigate={onNavigate}
      metrics={
        <>
          <ValueMetricBox label="Occupants tracked" value={hasOccupancyData ? `${totalOccupancy}` : '—'} color="var(--color-sentinel-purple)" />
          <ValueMetricBox label="After-hours flagged" value={`${afterHoursCount}`} color={afterHoursCount > 0 ? 'var(--color-sentinel-amber)' : 'var(--color-sentinel-green)'} />
          <ValueMetricBox label="Cross-system correlation" value={hasOccupancyData ? 'Active' : 'Monitoring'} color={hasOccupancyData ? 'var(--color-sentinel-green)' : 'var(--color-sentinel-text-secondary)'} />
        </>
      }
      comparison={afterHoursCount > 0 || anomalyCount > 0 ? (
        <BaselineComparisonBar
          baselineValue={afterHoursCount + anomalyCount}
          optimizedValue={0}
          unit=""
          baselineLabel="Undetected events (no AI)"
          optimizedLabel="Caught by SENTINEL"
          accentColor="var(--color-sentinel-purple)"
        />
      ) : undefined}
    />
  );
}
