// @ts-nocheck
import { useState, useEffect } from 'react';
import { Thermometer, ArrowRight } from 'lucide-react';
import { hvacApi } from '@/lib/hvacApi';
import type { HVACOverview, ThermalRunway } from '@/lib/hvacApi';

interface HVACIntelligenceCardProps {
  siteId: string;
  onNavigate: () => void;
}

export function HVACIntelligenceCard({ siteId, onNavigate }: HVACIntelligenceCardProps) {
  const [overview, setOverview] = useState<HVACOverview | null>(null);
  const [thermal, setThermal] = useState<ThermalRunway | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      setLoading(true);
      try {
        const [ov, th] = await Promise.allSettled([
          hvacApi.getOverview(siteId),
          hvacApi.getThermalRunway(siteId),
        ]);
        if (cancelled) return;
        if (ov.status === 'fulfilled') setOverview(ov.value);
        if (th.status === 'fulfilled') setThermal(th.value);
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
        <div className="animate-spin h-6 w-6 border-3 border-blue-500 border-t-transparent rounded-full mx-auto mb-2" />
        <p className="text-xs" style={{ color: 'var(--color-sentinel-text-secondary)' }}>Loading HVAC data...</p>
      </div>
    );
  }

  const healthPct = overview?.overall_health ?? 0;
  const zonesRunning = overview ? overview.zones.total - overview.zones.fault - overview.zones.offline : 0;
  const zonesFault = overview?.zones.fault ?? 0;
  const runwayHours = thermal?.metrics?.runway_with ?? 0;
  const improvementPct = thermal?.metrics?.improvement_percent ?? 0;

  const savingsText = improvementPct > 0
    ? `${improvementPct.toFixed(0)}% pre-cooling improvement`
    : 'Analysing thermal patterns...';

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
          <div className="p-2 rounded" style={{ background: 'rgba(59, 130, 246, 0.15)' }}>
            <Thermometer className="h-5 w-5" style={{ color: '#3B82F6' }} />
          </div>
          <div>
            <h3 className="font-medium text-sm" style={{ color: 'var(--color-sentinel-text-primary)' }}>
              HVAC Intelligence
            </h3>
            <span className="text-xs" style={{ color: 'var(--color-sentinel-text-secondary)' }}>
              Climate control &amp; thermal management
            </span>
          </div>
        </div>
        <span
          className="text-xs px-2 py-1 rounded font-medium"
          style={{
            background: improvementPct > 0 ? 'rgba(16, 185, 129, 0.15)' : 'rgba(245, 158, 11, 0.15)',
            color: improvementPct > 0 ? 'var(--color-sentinel-green)' : 'var(--color-sentinel-amber)',
          }}
        >
          {savingsText}
        </span>
      </div>

      {/* Metrics */}
      <div className="p-4">
        <div className="grid grid-cols-3 gap-3 mb-4">
          <MetricBox label="Overall Health" value={`${healthPct.toFixed(0)}%`} color="#3B82F6" />
          <MetricBox label="Zones Running" value={`${zonesRunning}${zonesFault > 0 ? ` / ${zonesFault} fault` : ''}`} color={zonesFault > 0 ? '#EF4444' : '#22C55E'} />
          <MetricBox label="Thermal Runway" value={runwayHours > 0 ? `${runwayHours.toFixed(1)}h` : '—'} color="#F59E0B" />
        </div>

        {/* AI Value + Navigate */}
        <div className="flex items-center justify-between">
          <p className="text-xs" style={{ color: 'var(--color-sentinel-text-secondary)' }}>
            <span style={{ color: 'var(--color-sentinel-blue)' }}>SENTINEL AI:</span>{' '}
            Predictive zone control with pre-cooling optimisation
          </p>
          <button
            onClick={onNavigate}
            className="flex items-center gap-1 text-xs font-medium hover:underline"
            style={{ color: 'var(--color-sentinel-blue)', background: 'none', border: 'none', cursor: 'pointer' }}
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
