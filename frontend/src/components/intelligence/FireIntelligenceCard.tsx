// @ts-nocheck
import { useState, useEffect } from 'react';
import { Flame } from 'lucide-react';
import { authorizedFetch } from '@/lib/api';
import {
  IntelligenceCard, ValueMetricBox, ValueBadge, LearningBadge, AwaitingDataBadge,
  type CardState,
} from './shared';

interface FireIntelligenceCardProps {
  siteId: string;
  onNavigate: () => void;
}

interface FireHealthData {
  overall_health_percent?: number;
  equipment_count?: number;
  inspected_count?: number;
  overdue_count?: number;
  system_status?: string;
}

export function FireIntelligenceCard({ siteId, onNavigate }: FireIntelligenceCardProps) {
  const [health, setHealth] = useState<FireHealthData | null>(null);
  const [loading, setLoading] = useState(true);
  const [apiError, setApiError] = useState(false);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      setLoading(true);
      setApiError(false);
      try {
        const res = await authorizedFetch(`/api/compliance/fire/health?site_code=${encodeURIComponent(siteId)}`);
        if (cancelled) return;
        if (res.ok) {
          setHealth(await res.json());
        } else {
          setApiError(true);
        }
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
        <div className="animate-spin h-6 w-6 border-3 border-red-500 border-t-transparent rounded-full mx-auto mb-2" />
        <p className="text-xs" style={{ color: 'var(--color-sentinel-text-secondary)' }}>Loading Fire data...</p>
      </div>
    );
  }

  const equipCount = health?.equipment_count ?? 0;
  const inspectedCount = health?.inspected_count ?? 0;
  const overdue = health?.overdue_count ?? 0;

  // Determine state
  let state: CardState;
  if (apiError || !health) {
    state = 'no-data';
  } else if (equipCount === 0) {
    state = 'learning';
  } else {
    state = 'active';
  }

  // Badge
  const badge = state === 'no-data'
    ? <AwaitingDataBadge />
    : state === 'learning'
      ? <LearningBadge text="Discovering assets" />
      : overdue > 0
        ? <ValueBadge text={`${overdue} overdue item${overdue !== 1 ? 's' : ''} flagged`} positive={false} />
        : <ValueBadge text={`${inspectedCount} assets — all current`} />;

  // Footer
  const footer = state === 'no-data'
    ? 'Connected and ready. Start data source to begin analysis.'
    : state === 'learning'
      ? 'Discovering fire safety assets. Compliance tracking will activate once equipment is registered.'
      : overdue > 0
        ? `Flagged ${overdue} overdue inspection${overdue !== 1 ? 's' : ''} — tracking ${equipCount} fire assets`
        : `Tracking ${equipCount} fire assets — all inspections current`;

  return (
    <IntelligenceCard
      title="Fire Safety Intelligence"
      subtitle="Equipment compliance &amp; readiness"
      icon={<Flame className="h-5 w-5" style={{ color: '#EF4444' }} />}
      iconBg="rgba(239, 68, 68, 0.15)"
      accentColor="#EF4444"
      badge={badge}
      state={state}
      footer={footer}
      onNavigate={onNavigate}
      metrics={
        <>
          <ValueMetricBox label="Equipment tracked" value={equipCount > 0 ? `${equipCount}` : '—'} color="#EF4444" />
          <ValueMetricBox label="Inspected" value={inspectedCount > 0 ? `${inspectedCount}` : '—'} color="#22C55E" />
          <ValueMetricBox label="Overdue" value={overdue > 0 ? `${overdue}` : 'All current'} color={overdue > 0 ? '#EF4444' : '#22C55E'} />
        </>
      }
    />
  );
}
