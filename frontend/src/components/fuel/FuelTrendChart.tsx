import { useState, useEffect, useCallback } from 'react';
import { fuelApi } from '../../lib/api';
import type { FuelTank, FuelTelemetryReading } from '../../lib/api';

interface FuelTrendChartProps {
  tanks: FuelTank[];
}

type Period = '24h' | '7d' | '30d';

const PERIOD_HOURS: Record<Period, number> = {
  '24h': 24,
  '7d': 168,
  '30d': 720,
};

export function FuelTrendChart({ tanks }: FuelTrendChartProps) {
  const [selectedTankId, setSelectedTankId] = useState(tanks[0]?.tank_id ?? '');
  const [period, setPeriod] = useState<Period>('24h');
  const [readings, setReadings] = useState<FuelTelemetryReading[]>([]);
  const [loading, setLoading] = useState(false);

  const fetchHistory = useCallback(async () => {
    if (!selectedTankId) return;
    setLoading(true);
    try {
      const res = await fuelApi.fetchTankHistory(selectedTankId, PERIOD_HOURS[period]);
      setReadings(res.readings);
    } catch {
      setReadings([]);
    } finally {
      setLoading(false);
    }
  }, [selectedTankId, period]);

  useEffect(() => {
    fetchHistory();
  }, [fetchHistory]);

  const chartData = readings.map(r => ({
    time: new Date(r.ts * 1000).toLocaleString(undefined, {
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    }),
    'Level %': Number(r.level_pct.toFixed(1)),
    ...(r.temperature_c != null ? { 'Temp C': Number(r.temperature_c.toFixed(1)) } : {}),
  }));

  return (
    <div className="rounded-lg p-4" style={{ background: "var(--sentinel-bg-panel)", border: "1px solid var(--sentinel-border)" }}>
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-sm font-medium" style={{ color: "var(--sentinel-text-primary)" }}>Fuel Level Trend</h3>
        <div className="flex items-center gap-2">
          {tanks.length > 1 && (
            <select
              value={selectedTankId}
              onChange={e => setSelectedTankId(e.target.value)}
              className="text-sm border rounded-md px-2 py-1"
              style={{ borderColor: "var(--sentinel-border)", background: "var(--sentinel-bg-secondary)", color: "var(--sentinel-text-primary)" }}
            >
              {tanks.map(t => (
                <option key={t.tank_id} value={t.tank_id}>
                  {t.name}
                </option>
              ))}
            </select>
          )}
          <div className="flex rounded-lg overflow-hidden" style={{ border: "1px solid var(--sentinel-border)" }}>
            {(['24h', '7d', '30d'] as Period[]).map(p => (
              <button
                key={p}
                onClick={() => setPeriod(p)}
                className="px-3 py-1 text-sm font-medium transition-colors"
                style={{
                  background: period === p ? "var(--sentinel-blue)" : "transparent",
                  color: period === p ? "white" : "var(--sentinel-text-secondary)",
                }}
              >
                {p}
              </button>
            ))}
          </div>
        </div>
      </div>

      {loading ? (
        <div className="h-64 flex items-center justify-center">
          <span style={{ color: "var(--sentinel-text-secondary)" }}>Loading chart data...</span>
        </div>
      ) : chartData.length === 0 ? (
        <div className="h-64 flex items-center justify-center">
          <span style={{ color: "var(--sentinel-text-secondary)" }}>No telemetry data for the selected period</span>
        </div>
      ) : (
        <div className="h-64 flex items-end gap-px p-2" style={{ background: "var(--sentinel-bg-secondary)", borderRadius: "0.5rem" }}>
          {chartData.map((d, i) => (
            <div key={i} className="flex-1 flex flex-col items-center justify-end" title={`${d.time}: ${d['Level %']}%`}>
              <div
                className="w-full rounded-t origin-bottom will-change-transform"
                style={{
                  height: '100%',
                  background: "var(--sentinel-blue)",
                  transform: `scaleY(${Math.max(d['Level %'], 0.4) / 100})`,
                  transition: 'transform 0.2s ease',
                }}
              />
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
