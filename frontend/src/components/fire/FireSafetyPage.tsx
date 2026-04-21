/**
 * Fire Safety Page — Building tab for fire system monitoring
 *
 * Always read-only (no control toggle). Shows fire equipment status,
 * inspection schedules, and NFPA/SABS compliance.
 */

import { useEffect, useState } from 'react';
import { Flame } from 'lucide-react';
import { authorizedFetch } from '@/lib/api/client';
import { FireEquipmentPanel } from '../compliance/FireEquipmentPanel';
import { SentinelValueCard } from '../SentinelValueCard';

interface FireSafetyPageProps {
  siteId?: string;
}

interface BridgeTelemetrySummary {
  status: 'live' | 'unavailable';
  zones_with_readings?: number;
  zone_count?: number;
  power?: {
    hvac_kw?: number;
    lighting_kw?: number;
    total_kw?: number;
  };
}

export function FireSafetyPage({ siteId = 'site-002' }: FireSafetyPageProps) {
  const [bridgeTelemetry, setBridgeTelemetry] = useState<BridgeTelemetrySummary | null>(null);
  const [sentinelGuidance, setSentinelGuidance] = useState<string | null>(null);
  const [sentinelPosture, setSentinelPosture] = useState<string | null>(null);

  useEffect(() => {
    let mounted = true;
    async function loadTelemetrySummary() {
      try {
        const [rawTelemetryResp, stateResp] = await Promise.all([
          authorizedFetch(`/api/sites/${encodeURIComponent(siteId)}/telemetry`).catch(() => null),
          authorizedFetch(`/api/building-state/${encodeURIComponent(siteId)}`).catch(() => null),
        ]);
        if (!mounted) return;

        if (rawTelemetryResp && rawTelemetryResp.ok) {
          const raw = await rawTelemetryResp.json();
          setBridgeTelemetry({
            status: 'live',
            zones_with_readings: raw?.zones_with_readings ?? 0,
            zone_count: raw?.zone_count ?? 0,
            power: raw?.power ?? {},
          });
        } else {
          setBridgeTelemetry({ status: 'unavailable' });
        }

        if (stateResp && stateResp.ok) {
          const state = await stateResp.json();
          setSentinelGuidance(state?.payload?.operator_guidance?.headline || null);
          setSentinelPosture(state?.payload?.building_posture || null);
        } else {
          setSentinelGuidance(null);
          setSentinelPosture(null);
        }
      } catch {
        if (mounted) {
          setBridgeTelemetry({ status: 'unavailable' });
          setSentinelGuidance(null);
          setSentinelPosture(null);
        }
      }
    }
    loadTelemetrySummary();
    return () => {
      mounted = false;
    };
  }, [siteId]);

  return (
    <div className="h-full overflow-y-auto p-4 md:p-6">
      {/* Page Header — matches Lighting tab pattern */}
      <div className="mb-6">
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-3">
            <div className="p-2 rounded" style={{ background: "rgba(239, 68, 68, 0.15)" }}>
              <Flame className="h-6 w-6" style={{ color: "var(--color-sentinel-red)" }} />
            </div>
            <div>
              <h1 className="text-2xl font-bold" style={{ color: "var(--color-sentinel-text-primary)" }}>
                Fire Safety
              </h1>
              <p className="text-sm" style={{ color: "var(--color-sentinel-text-secondary)" }}>
                Equipment Compliance &amp; Readiness
              </p>
            </div>
          </div>
        </div>
      </div>

      <div className="space-y-6">
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <div className="rounded-lg p-4" style={{ background: 'var(--color-sentinel-bg-panel)', border: '1px solid var(--color-sentinel-border)' }}>
          <div className="flex items-center justify-between mb-2">
            <h2 className="text-sm font-semibold" style={{ color: 'var(--color-sentinel-text-primary)' }}>
              Raw Bridge Telemetry
            </h2>
            <span
              className="text-xs px-2 py-1 rounded"
              style={{
                background: bridgeTelemetry?.status === 'live' ? 'rgba(16,185,129,0.15)' : 'rgba(245,158,11,0.15)',
                color: bridgeTelemetry?.status === 'live' ? 'var(--color-sentinel-green)' : 'var(--color-sentinel-amber)',
              }}
            >
              {bridgeTelemetry?.status === 'live' ? 'Live' : 'Unavailable'}
            </span>
          </div>
          <p className="text-xs" style={{ color: 'var(--color-sentinel-text-secondary)' }}>
            Zones: {bridgeTelemetry?.zones_with_readings ?? 0}/{bridgeTelemetry?.zone_count ?? 0}
          </p>
          <p className="text-xs mt-1" style={{ color: 'var(--color-sentinel-text-secondary)' }}>
            Power: HVAC {(bridgeTelemetry?.power?.hvac_kw ?? 0).toFixed(2)} kW · Total {(bridgeTelemetry?.power?.total_kw ?? 0).toFixed(2)} kW
          </p>
        </div>
        <div className="rounded-lg p-4" style={{ background: 'var(--color-sentinel-bg-panel)', border: '1px solid var(--color-sentinel-border)' }}>
          <h2 className="text-sm font-semibold mb-2" style={{ color: 'var(--color-sentinel-text-primary)' }}>
            SENTINEL Fire Interpretation
          </h2>
          <p className="text-xs capitalize" style={{ color: 'var(--color-sentinel-text-secondary)' }}>
            Posture: <span style={{ color: 'var(--color-sentinel-text-primary)' }}>{sentinelPosture || 'unknown'}</span>
          </p>
          <p className="text-xs mt-1" style={{ color: 'var(--color-sentinel-text-secondary)' }}>
            {sentinelGuidance || 'No active guidance yet.'}
          </p>
        </div>
      </div>

      <SentinelValueCard
        title="Fire Safety Intelligence Impact"
        icon={Flame}
        baseline={{ label: "", value: 0, unit: "incidents" }}
        sentinel={{ label: "", value: 0, unit: "incidents" }}
        savingsPercent={0}
        period="Monthly"
        collecting
      />
      <FireEquipmentPanel siteCode="S002" />
      </div>
    </div>
  );
}
