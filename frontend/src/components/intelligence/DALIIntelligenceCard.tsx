/**
 * DALIIntelligenceCard
 *
 * Renders DALI Zone Intelligence from /api/lighting/zone-intelligence.
 * Shows health badges, remaining lamp life progress bars, and action lists
 * per zone (A/B/C). Graceful degradation when endpoint is unavailable.
 */

import { useState, useEffect } from 'react';
import { Activity, AlertTriangle, CheckCircle2, Clock, Zap } from 'lucide-react';
import { authorizedFetch } from '@/lib/api/client';

interface ZoneIntelligence {
  zone: string;
  equipment_code: string;
  health_status: 'critical' | 'warning' | 'healthy' | 'unknown';
  headline: string;
  remaining_life_pct: number;
  estimated_remaining_hours: number;
  rated_lifetime_hours: number;
  gear_operating_hours: number | null;
  lamp_operating_hours: number | null;
  efficiency_pct: number | null;
  cost_today_zar: number | null;
  lamp_failures: number;
  control_gear_status: 'ok' | 'fault';
  power_watts: number | null;
  brightness_pct: number | null;
  actions: string[];
}

interface ZoneIntelligenceResponse {
  site_id: string;
  tariff_zar_per_kwh: number;
  zones: ZoneIntelligence[];
}

const STATUS_CONFIG = {
  critical: {
    bg: "rgba(239, 68, 68, 0.12)",
    border: "rgba(239, 68, 68, 0.35)",
    text: "var(--color-sentinel-red)",
    icon: AlertTriangle,
    label: "Critical",
    lifeBar: "bg-red-500",
  },
  warning: {
    bg: "rgba(245, 158, 11, 0.12)",
    border: "rgba(245, 158, 11, 0.35)",
    text: "var(--color-sentinel-amber)",
    icon: Clock,
    label: "Warning",
    lifeBar: "bg-amber-500",
  },
  healthy: {
    bg: "rgba(16, 185, 129, 0.12)",
    border: "rgba(16, 185, 129, 0.35)",
    text: "var(--color-sentinel-green)",
    icon: CheckCircle2,
    label: "Healthy",
    lifeBar: "bg-emerald-500",
  },
  unknown: {
    bg: "rgba(156, 163, 175, 0.12)",
    border: "rgba(156, 163, 175, 0.35)",
    text: "var(--color-sentinel-text-secondary)",
    icon: Activity,
    label: "Unknown",
    lifeBar: "bg-gray-400",
  },
};

function LifeProgressBar({ pct }: { pct: number }) {
  return (
    <div className="w-full">
      <div className="flex justify-between text-xs mb-1">
        <span style={{ color: "var(--color-sentinel-text-secondary)" }}>Lamp life remaining</span>
        <span className="font-medium" style={{ color: pct < 20 ? "var(--color-sentinel-red)" : "var(--color-sentinel-text-primary)" }}>
          {pct.toFixed(1)}%
        </span>
      </div>
      <div className="w-full h-2 rounded-full" style={{ background: "var(--color-sentinel-border)" }}>
        <div
          className="h-2 rounded-full transition-all duration-500"
          style={{
            width: `${Math.max(0, Math.min(100, pct))}%`,
            background: pct < 20 ? "var(--color-sentinel-red)" : pct < 40 ? "var(--color-sentinel-amber)" : "var(--color-sentinel-green)",
          }}
        />
      </div>
    </div>
  );
}

function ZoneCard({ zone }: { zone: ZoneIntelligence }) {
  const cfg = STATUS_CONFIG[zone.health_status] ?? STATUS_CONFIG.unknown;
  const StatusIcon = cfg.icon;

  return (
    <div
      className="rounded-lg p-4 flex flex-col gap-3"
      style={{ background: cfg.bg, border: `1px solid ${cfg.border}` }}
    >
      {/* Zone header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <StatusIcon className="w-4 h-4" style={{ color: cfg.text }} />
          <span className="text-sm font-semibold" style={{ color: cfg.text }}>
            Zone {zone.zone}
          </span>
        </div>
        <span
          className="text-xs px-2 py-0.5 rounded capitalize font-medium"
          style={{ background: cfg.bg, color: cfg.text, border: `1px solid ${cfg.border}` }}
        >
          {cfg.label}
        </span>
      </div>

      {/* Headline */}
      <p className="text-xs leading-relaxed" style={{ color: "var(--color-sentinel-text-primary)" }}>
        {zone.headline}
      </p>

      {/* Life progress */}
      <LifeProgressBar pct={zone.remaining_life_pct} />

      {/* Secondary metrics */}
      <div className="grid grid-cols-2 gap-x-4 gap-y-1">
        {zone.gear_operating_hours != null && (
          <MetricRow
            label="Gear hours"
            value={`${zone.gear_operating_hours.toLocaleString()} h`}
          />
        )}
        {zone.estimated_remaining_hours > 0 && (
          <MetricRow
            label="Est. remaining"
            value={`${zone.estimated_remaining_hours.toLocaleString()} h`}
          />
        )}
        {zone.lamp_failures > 0 && (
          <MetricRow
            label="Lamp failures"
            value={String(zone.lamp_failures)}
            highlight={zone.lamp_failures > 0}
          />
        )}
        {zone.control_gear_status === 'fault' && (
          <MetricRow
            label="Gear status"
            value="FAULT"
            highlight={true}
          />
        )}
        {zone.efficiency_pct != null && (
          <MetricRow label="Efficiency" value={`${zone.efficiency_pct.toFixed(1)}%`} />
        )}
        {zone.power_watts != null && (
          <MetricRow label="Power" value={`${zone.power_watts.toFixed(1)} W`} />
        )}
        {zone.brightness_pct != null && (
          <MetricRow label="Brightness" value={`${zone.brightness_pct.toFixed(0)}%`} />
        )}
        {zone.cost_today_zar != null && (
          <MetricRow label="Cost today" value={`R${zone.cost_today_zar.toFixed(2)}`} />
        )}
      </div>

      {/* Actions */}
      {zone.actions.length > 0 && (
        <div className="mt-1">
          <p className="text-xs font-medium mb-1" style={{ color: "var(--color-sentinel-text-secondary)" }}>
            Actions
          </p>
          <ul className="space-y-0.5">
            {zone.actions.map((action, i) => (
              <li key={i} className="text-xs flex items-start gap-1.5" style={{ color: "var(--color-sentinel-text-secondary)" }}>
                <span style={{ color: cfg.text }}>•</span>
                <span>{action}</span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

function MetricRow({ label, value, highlight = false }: { label: string; value: string; highlight?: boolean }) {
  return (
    <div className="flex justify-between items-center">
      <span className="text-xs" style={{ color: "var(--color-sentinel-text-secondary)" }}>{label}</span>
      <span
        className="text-xs font-medium"
        style={{ color: highlight ? "var(--color-sentinel-red)" : "var(--color-sentinel-text-primary)" }}
      >
        {value}
      </span>
    </div>
  );
}

interface DALIIntelligenceCardProps {
  siteId: string;
}

export function DALIIntelligenceCard({ siteId }: DALIIntelligenceCardProps) {
  const [data, setData] = useState<ZoneIntelligenceResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!siteId) return;
    let cancelled = false;
    setLoading(true);
    setError(null);

    authorizedFetch(`/api/lighting/zone-intelligence?site_id=${encodeURIComponent(siteId)}`)
      .then((resp) => {
        if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
        return resp.json();
      })
      .then((body: ZoneIntelligenceResponse) => {
        if (!cancelled) {
          setData(body);
          setLoading(false);
        }
      })
      .catch((err) => {
        if (!cancelled) {
          setError(String(err));
          setLoading(false);
        }
      });

    return () => { cancelled = true; };
  }, [siteId]);

  return (
    <div
      className="rounded-lg p-4"
      style={{ background: "var(--color-sentinel-bg-panel)", border: "1px solid var(--color-sentinel-border)" }}
    >
      <div className="flex items-center gap-2 mb-4">
        <Zap className="w-4 h-4" style={{ color: "var(--color-sentinel-amber)" }} />
        <h2 className="text-sm font-semibold" style={{ color: "var(--color-sentinel-text-primary)" }}>
          DALI Zone Intelligence
        </h2>
      </div>

      {loading && (
        <p className="text-xs" style={{ color: "var(--color-sentinel-text-secondary)" }}>Loading…</p>
      )}

      {error && (
        <p className="text-xs" style={{ color: "var(--color-sentinel-red)" }}>
          DALI intelligence unavailable — {error}
        </p>
      )}

      {data && (
        <div className="space-y-3">
          {data.zones.map((zone) => (
            <ZoneCard key={zone.zone} zone={zone} />
          ))}
        </div>
      )}
    </div>
  );
}
