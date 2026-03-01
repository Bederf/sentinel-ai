// @ts-nocheck
import { useState, useEffect } from 'react';
import { Flame, ArrowRight } from 'lucide-react';
import { authorizedFetch } from '@/lib/api';

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

  useEffect(() => {
    let cancelled = false;
    async function load() {
      setLoading(true);
      try {
        const res = await authorizedFetch(`/api/compliance/fire/health?site_code=${encodeURIComponent(siteId)}`);
        if (cancelled) return;
        if (res.ok) {
          const data = await res.json();
          setHealth(data);
        }
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
        <div className="animate-spin h-6 w-6 border-3 border-red-500 border-t-transparent rounded-full mx-auto mb-2" />
        <p className="text-xs" style={{ color: 'var(--color-sentinel-text-secondary)' }}>Loading Fire data...</p>
      </div>
    );
  }

  const coveragePct = health?.equipment_count
    ? ((health.inspected_count ?? 0) / health.equipment_count * 100)
    : 0;
  const systemStatus = health?.system_status ?? 'Unknown';
  const overdue = health?.overdue_count ?? 0;

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
          <div className="p-2 rounded" style={{ background: 'rgba(239, 68, 68, 0.15)' }}>
            <Flame className="h-5 w-5" style={{ color: '#EF4444' }} />
          </div>
          <div>
            <h3 className="font-medium text-sm" style={{ color: 'var(--color-sentinel-text-primary)' }}>
              Fire Safety Intelligence
            </h3>
            <span className="text-xs" style={{ color: 'var(--color-sentinel-text-secondary)' }}>
              Equipment compliance &amp; readiness
            </span>
          </div>
        </div>
        <span
          className="text-xs px-2 py-1 rounded font-medium animate-pulse"
          style={{
            background: 'rgba(245, 158, 11, 0.15)',
            color: 'var(--color-sentinel-amber)',
          }}
        >
          Collecting baseline...
        </span>
      </div>

      {/* Metrics */}
      <div className="p-4">
        <div className="grid grid-cols-3 gap-3 mb-4">
          <MetricBox
            label="Equipment Coverage"
            value={coveragePct > 0 ? `${coveragePct.toFixed(0)}%` : '—'}
            color="#EF4444"
          />
          <MetricBox
            label="System Status"
            value={systemStatus}
            color={systemStatus === 'Compliant' ? '#22C55E' : '#F59E0B'}
          />
          <MetricBox
            label="Overdue Items"
            value={`${overdue}`}
            color={overdue > 0 ? '#EF4444' : '#22C55E'}
          />
        </div>

        {/* AI Value + Navigate */}
        <div className="flex items-center justify-between">
          <p className="text-xs" style={{ color: 'var(--color-sentinel-text-secondary)' }}>
            <span style={{ color: '#EF4444' }}>SENTINEL AI:</span>{' '}
            Compliance tracking with automated inspection scheduling
          </p>
          <button
            onClick={onNavigate}
            className="flex items-center gap-1 text-xs font-medium hover:underline"
            style={{ color: '#EF4444', background: 'none', border: 'none', cursor: 'pointer' }}
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
