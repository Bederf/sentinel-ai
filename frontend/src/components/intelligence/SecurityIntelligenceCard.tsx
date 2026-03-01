// @ts-nocheck
import { useState, useEffect } from 'react';
import { Shield, ArrowRight } from 'lucide-react';
import { securityApi } from '@/lib/api';

interface SecurityIntelligenceCardProps {
  siteId: string;
  onNavigate: () => void;
}

export function SecurityIntelligenceCard({ siteId, onNavigate }: SecurityIntelligenceCardProps) {
  const [status, setStatus] = useState<any>(null);
  const [occupancy, setOccupancy] = useState<any>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      setLoading(true);
      try {
        const [s, o] = await Promise.allSettled([
          securityApi.getStatus(siteId),
          securityApi.getOccupancy(siteId),
        ]);
        if (cancelled) return;
        if (s.status === 'fulfilled') setStatus(s.value);
        if (o.status === 'fulfilled') setOccupancy(o.value);
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
        <div className="animate-spin h-6 w-6 border-3 border-purple-500 border-t-transparent rounded-full mx-auto mb-2" />
        <p className="text-xs" style={{ color: 'var(--color-sentinel-text-secondary)' }}>Loading Security data...</p>
      </div>
    );
  }

  const alarmZones = status?.alarm_zones_total ?? 0;
  const camerasOnline = status?.cameras_online ?? 0;
  const totalOccupancy = occupancy?.total_occupancy ?? status?.occupancy_total ?? 0;

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
          <div className="p-2 rounded" style={{ background: 'rgba(168, 85, 247, 0.15)' }}>
            <Shield className="h-5 w-5" style={{ color: '#A855F7' }} />
          </div>
          <div>
            <h3 className="font-medium text-sm" style={{ color: 'var(--color-sentinel-text-primary)' }}>
              Security Intelligence
            </h3>
            <span className="text-xs" style={{ color: 'var(--color-sentinel-text-secondary)' }}>
              Access control &amp; occupancy monitoring
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
          <MetricBox label="Alarm Zones" value={alarmZones > 0 ? `${alarmZones}` : '—'} color="#A855F7" />
          <MetricBox label="Cameras Online" value={camerasOnline > 0 ? `${camerasOnline}` : '—'} color="#3B82F6" />
          <MetricBox label="Occupancy" value={`${totalOccupancy}`} color="#10B981" />
        </div>

        {/* AI Value + Navigate */}
        <div className="flex items-center justify-between">
          <p className="text-xs" style={{ color: 'var(--color-sentinel-text-secondary)' }}>
            <span style={{ color: '#A855F7' }}>SENTINEL AI:</span>{' '}
            Anomaly detection with cross-system occupancy correlation
          </p>
          <button
            onClick={onNavigate}
            className="flex items-center gap-1 text-xs font-medium hover:underline"
            style={{ color: '#A855F7', background: 'none', border: 'none', cursor: 'pointer' }}
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
