// @ts-nocheck
import { useState, useEffect } from 'react';
import { Zap, ArrowRight } from 'lucide-react';
import api from '@/lib/api';
import type { OptimizationStatusResponse } from '@/lib/api';

interface EnergyIntelligenceCardProps {
  siteId: string;
  onNavigate: () => void;
}

export function EnergyIntelligenceCard({ siteId, onNavigate }: EnergyIntelligenceCardProps) {
  const [status, setStatus] = useState<OptimizationStatusResponse | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      setLoading(true);
      try {
        const s = await api.getOptimizationStatus(siteId);
        if (!cancelled) setStatus(s);
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
        <div className="animate-spin h-6 w-6 border-3 border-green-500 border-t-transparent rounded-full mx-auto mb-2" />
        <p className="text-xs" style={{ color: 'var(--color-sentinel-text-secondary)' }}>Loading Energy data...</p>
      </div>
    );
  }

  const savings = status?.monthly_savings?.monthly_savings_zar ?? 0;
  const mode = status?.optimization_settings?.mode ?? 'supervised';
  const applied = status?.monthly_savings?.applied_recommendations ?? 0;

  const savingsText = savings > 0
    ? `R${savings.toLocaleString()}/month saved`
    : 'Collecting baseline...';

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
          <div className="p-2 rounded" style={{ background: 'rgba(16, 185, 129, 0.15)' }}>
            <Zap className="h-5 w-5" style={{ color: '#10B981' }} />
          </div>
          <div>
            <h3 className="font-medium text-sm" style={{ color: 'var(--color-sentinel-text-primary)' }}>
              Energy Intelligence
            </h3>
            <span className="text-xs" style={{ color: 'var(--color-sentinel-text-secondary)' }}>
              Optimisation &amp; cost management
            </span>
          </div>
        </div>
        <span
          className="text-xs px-2 py-1 rounded font-medium"
          style={{
            background: savings > 0 ? 'rgba(16, 185, 129, 0.15)' : 'rgba(245, 158, 11, 0.15)',
            color: savings > 0 ? 'var(--color-sentinel-green)' : 'var(--color-sentinel-amber)',
          }}
        >
          {savingsText}
        </span>
      </div>

      {/* Metrics */}
      <div className="p-4">
        <div className="grid grid-cols-3 gap-3 mb-4">
          <MetricBox label="Monthly Savings" value={savings > 0 ? `R${savings.toLocaleString()}` : '—'} color="#10B981" />
          <MetricBox label="Mode" value={mode === 'automatic' ? 'Auto' : 'Supervised'} color="#3B82F6" />
          <MetricBox label="Applied" value={`${applied}`} color="#F59E0B" />
        </div>

        {/* AI Value + Navigate */}
        <div className="flex items-center justify-between">
          <p className="text-xs" style={{ color: 'var(--color-sentinel-text-secondary)' }}>
            <span style={{ color: 'var(--color-sentinel-green)' }}>SENTINEL AI:</span>{' '}
            Cross-system energy optimisation with tariff awareness
          </p>
          <button
            onClick={onNavigate}
            className="flex items-center gap-1 text-xs font-medium hover:underline"
            style={{ color: 'var(--color-sentinel-green)', background: 'none', border: 'none', cursor: 'pointer' }}
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
