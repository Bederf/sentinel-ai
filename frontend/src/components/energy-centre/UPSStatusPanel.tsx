/**
 * UPS Status Panel - Bolt-on Module
 *
 * UPS fleet monitoring with:
 * - Mode indicators
 * - Battery status
 * - Runtime remaining
 * - Load percentage
 */

import { useState, useEffect, useCallback } from 'react';
import { energyCentreApi } from '../../lib/energyCentreApi';
import type { UPSSummary } from '../../lib/energyCentreApi';

interface UPSStatusPanelProps {
  siteId: string;
  compact?: boolean;
  onBatteryAlert?: (ups: any) => void;
}

const sentinelColors: Record<string, string> = {
  blue: 'var(--sentinel-blue)',
  amber: 'var(--sentinel-amber)',
  gray: 'var(--sentinel-text-disabled)',
  green: 'var(--sentinel-green)',
  red: 'var(--sentinel-red)',
  cyan: 'var(--sentinel-cyan)',
  purple: '#7c3aed',
  yellow: '#eab308',
  slate: '#64748b',
};

const modeColors: Record<string, string> = {
  online: 'green',
  battery: 'red',
  bypass: 'amber',
  standby: 'gray',
  fault: 'red',
};

export function UPSStatusPanel({ siteId, compact = false, onBatteryAlert }: UPSStatusPanelProps) {
  const [summary, setSummary] = useState<UPSSummary | null>(null);
  const [loading, setLoading] = useState(true);

  const loadData = useCallback(async () => {
    try {
      const data = await energyCentreApi.getUPSSummary(siteId);
      setSummary(data);

      // Trigger alerts for UPS on battery
      if (onBatteryAlert && data.systems.some(s => s.on_battery)) {
        data.systems.filter(s => s.on_battery).forEach(ups => {
          onBatteryAlert(ups);
        });
      }

      setLoading(false);
    } catch (_err) {
      setLoading(false);
    }
  }, [siteId, onBatteryAlert]);

  useEffect(() => {
    loadData();
    const interval = setInterval(loadData, 5000);
    return () => clearInterval(interval);
  }, [loadData]);

  if (loading) {
    return (
      <div className="rounded-lg p-4" style={{ background: "var(--sentinel-bg-panel)", border: "1px solid var(--sentinel-border)" }}>
        <h3 className="text-sm font-medium" style={{ color: "var(--sentinel-text-primary)" }}>UPS Systems</h3>
        <div className="animate-pulse h-32 bg-gray-100 rounded mt-4" />
      </div>
    );
  }

  if (!summary) {
    return (
      <div className="rounded-lg p-4" style={{ background: "var(--sentinel-bg-panel)", border: "1px solid var(--sentinel-border)" }}>
        <h3 className="text-sm font-medium" style={{ color: "var(--sentinel-text-primary)" }}>UPS Systems</h3>
        <p style={{ color: "var(--sentinel-text-secondary)" }}>No UPS data available</p>
      </div>
    );
  }

  if (compact) {
    const compactAccent = summary.any_on_battery ? 'var(--sentinel-red)' : summary.all_healthy ? 'var(--sentinel-green)' : 'var(--sentinel-amber)';
    return (
      <div className="rounded-lg p-4" style={{ background: "var(--sentinel-bg-panel)", border: "1px solid var(--sentinel-border)", borderTop: `3px solid ${compactAccent}` }}>
        <div className="flex items-start justify-between">
          <div>
            <span style={{ color: "var(--sentinel-text-secondary)" }}>UPS Fleet</span>
            <span className="text-2xl font-bold tabular-nums block" style={{ color: "var(--sentinel-text-primary)" }}>{summary.systems.length}</span>
          </div>
          <div className="text-right">
            {summary.any_on_battery ? (
              <span className="text-sm px-3 py-1 rounded font-medium" style={{ background: "var(--sentinel-red)", color: "white" }}>ON BATTERY</span>
            ) : (
              <span className="text-sm px-3 py-1 rounded font-medium" style={{ background: "var(--sentinel-green)", color: "white" }}>ONLINE</span>
            )}
          </div>
        </div>
        <span className="text-xs mt-2 block" style={{ color: "var(--sentinel-text-secondary)" }}>
          Load: {summary.total_load_kw.toFixed(0)} kW / {summary.total_capacity_kva.toFixed(0)} kVA
        </span>
      </div>
    );
  }

  return (
    <div className="rounded-lg p-4" style={{ background: "var(--sentinel-bg-panel)", border: "1px solid var(--sentinel-border)" }}>
      <div className="flex items-start justify-between">
        <h3 className="text-sm font-medium" style={{ color: "var(--sentinel-text-primary)" }}>UPS Systems</h3>
        <div className="flex gap-2">
          {summary.any_on_battery && (
            <span className="text-sm px-3 py-1 rounded font-medium" style={{ background: "var(--sentinel-red)", color: "white" }}>ON BATTERY</span>
          )}
          <span className="text-xs px-2 py-0.5 rounded font-medium" style={{ background: sentinelColors[summary.all_healthy ? 'green' : 'amber'], color: "white" }}>
            {summary.all_healthy ? 'All Healthy' : 'Attention Required'}
          </span>
        </div>
      </div>

      <div className="mt-4 space-y-4">
        {summary.systems.map((ups) => {
          const upsAccent = sentinelColors[modeColors[ups.mode]] || sentinelColors.gray;
          return (
            <div
              key={ups.ups_id}
              className="rounded-lg p-4"
              style={{
                background: "var(--sentinel-bg-panel)",
                border: ups.on_battery ? "2px solid var(--sentinel-red)" : "1px solid var(--sentinel-border)",
                borderLeft: `3px solid ${upsAccent}`,
              }}
            >
              <div className="flex items-start justify-between">
                <div>
                  <span className="font-bold" style={{ color: "var(--sentinel-text-primary)" }}>{ups.name}</span>
                  <span className="text-xs px-2 py-0.5 rounded font-medium ml-2" style={{ background: sentinelColors[modeColors[ups.mode]] || sentinelColors.gray, color: "white" }}>
                    {ups.mode.toUpperCase()}
                  </span>
                </div>
                {ups.on_battery && (
                  <div className="text-right">
                    <span className="text-red-500 font-bold text-xl block">
                      {ups.runtime_min.toFixed(0)} min
                    </span>
                    <span className="text-xs text-red-500">runtime</span>
                  </div>
                )}
              </div>

              <div className="grid grid-cols-3 gap-4 mt-3">
                <div>
                  <span className="text-xs" style={{ color: "var(--sentinel-text-secondary)" }}>Load</span>
                  <span className={ups.load_percent > 80 ? 'text-amber-500 font-bold block' : 'block'} style={{ color: "var(--sentinel-text-primary)" }}>
                    {ups.load_percent}%
                  </span>
                  <div className="w-full h-2 rounded-full overflow-hidden mt-1" style={{ background: "var(--sentinel-border)" }}>
                    <div className="h-full rounded-full" style={{ width: `${ups.load_percent}%`, background: ups.load_percent > 80 ? 'var(--sentinel-amber)' : 'var(--sentinel-blue)' }} />
                  </div>
                </div>
                <div>
                  <span className="text-xs" style={{ color: "var(--sentinel-text-secondary)" }}>Battery</span>
                  <span className={ups.battery_charge_pct < 50 ? 'text-amber-500 font-bold block' : 'block'} style={{ color: "var(--sentinel-text-primary)" }}>
                    {ups.battery_charge_pct}%
                  </span>
                  <div className="w-full h-2 rounded-full overflow-hidden mt-1" style={{ background: "var(--sentinel-border)" }}>
                    <div className="h-full rounded-full" style={{ width: `${ups.battery_charge_pct}%`, background: ups.battery_charge_pct < 50 ? 'var(--sentinel-amber)' : 'var(--sentinel-green)' }} />
                  </div>
                </div>
                <div>
                  <span className="text-xs" style={{ color: "var(--sentinel-text-secondary)" }}>Runtime</span>
                  <span style={{ color: "var(--sentinel-text-primary)" }}>{ups.runtime_min.toFixed(0)} min</span>
                </div>
              </div>

              {ups.alarms.length > 0 && (
                <div className="mt-2 pt-2 border-t border-gray-200">
                  {ups.alarms.map((alarm, idx) => (
                    <span key={idx} className="text-xs px-2 py-0.5 rounded font-medium mr-1" style={{ background: "var(--sentinel-red)", color: "white" }}>
                      {alarm}
                    </span>
                  ))}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}

export default UPSStatusPanel;
