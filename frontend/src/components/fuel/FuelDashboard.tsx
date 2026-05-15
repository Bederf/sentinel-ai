/**
 * FuelDashboard - Fuel monitoring dashboard page.
 *
 * Shows tank level cards, summary stats, recent events feed,
 * refill log table, and generator runtime history.
 * Polls every 30 seconds for live data updates.
 * Gated behind fuel module activation.
 */

import { useState, useEffect, useCallback } from 'react';

import { FuelTankCard } from './FuelTankCard';
import { FuelTrendChart } from './FuelTrendChart';
import { fuelApi } from '../../lib/api';
import { authorizedFetch } from '@/lib/api/client';
import type { FuelTank, FuelEvent, GeneratorRuntimeSession, RefillRecord } from '../../lib/api';
import { Badge } from '../Badge';

interface FuelDashboardProps {
  siteId?: string;
}

const POLL_INTERVAL_MS = 30_000;

const badgeEventColor: Record<string, string> = {
  red: 'bg-red-500/15 text-[var(--color-sentinel-red)]',
  amber: 'bg-amber-500/15 text-[var(--color-sentinel-amber)]',
  green: 'bg-green-500/15 text-[var(--color-sentinel-green)]',
  blue: 'bg-blue-500/15 text-[var(--color-sentinel-blue)]',
  gray: 'bg-gray-500/15 text-[var(--color-sentinel-text-secondary)]',
};

function eventTypeBadgeColor(eventType: string): string {
  switch (eventType) {
    case 'theft_suspected': return 'red';
    case 'leak_detected': return 'red';
    case 'low_fuel': return 'amber';
    case 'temperature_anomaly': return 'amber';
    case 'sensor_fault': return 'amber';
    case 'refill_detected': return 'green';
    case 'runtime_complete': return 'blue';
    default: return 'gray';
  }
}

function formatEventType(eventType: string): string {
  return eventType.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
}

function formatTimestamp(ts: number): string {
  return new Date(ts * 1000).toLocaleString();
}

function formatDuration(seconds: number): string {
  const hrs = Math.floor(seconds / 3600);
  const mins = Math.floor((seconds % 3600) / 60);
  if (hrs > 0) return `${hrs}h ${mins}m`;
  return `${mins}m`;
}

// Loading skeleton component
function LoadingSkeleton() {
  return (
    <div className="space-y-4 animate-pulse">
      <div className="grid grid-cols-1 md:grid-cols-4 gap-3">
        {[1, 2, 3, 4].map(i => (
          <div key={i} className="h-8 bg-gray-200 rounded" />
        ))}
      </div>
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {[1, 2, 3].map(i => (
          <div key={i} className="h-48 bg-gray-100 rounded" />
        ))}
      </div>
      <div className="h-64 bg-gray-100 rounded" />
    </div>
  );
}

export function FuelDashboard({ siteId }: FuelDashboardProps) {
  const [tanks, setTanks] = useState<FuelTank[]>([]);
  const [events, setEvents] = useState<FuelEvent[]>([]);
  const [runtimeSessions, setRuntimeSessions] = useState<GeneratorRuntimeSession[]>([]);
  const [refills, setRefills] = useState<RefillRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [bridgeTelemetry, setBridgeTelemetry] = useState<{
    status: 'live' | 'unavailable';
    zones_with_readings?: number;
    zone_count?: number;
    power?: { hvac_kw?: number; lighting_kw?: number; total_kw?: number };
  } | null>(null);
  const [sentinelGuidance, setSentinelGuidance] = useState<string | null>(null);
  const [sentinelPosture, setSentinelPosture] = useState<string | null>(null);

  const fetchData = useCallback(async () => {
    try {
      const [tanksRes, eventsRes, runtimeRes, refillsRes] = await Promise.all([
        fuelApi.fetchTanks(siteId),
        fuelApi.fetchEvents(siteId, 10),
        fuelApi.fetchGeneratorRuntime(siteId, 20),
        fuelApi.fetchRefillLog(siteId, 20),
      ]);
      setTanks(tanksRes.tanks);
      setEvents(eventsRes.events);
      setRuntimeSessions(runtimeRes.sessions);
      setRefills(refillsRes.refills);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load fuel data');
    } finally {
      setLoading(false);
    }
  }, [siteId]);

  useEffect(() => {
    fetchData();
    const interval = setInterval(fetchData, POLL_INTERVAL_MS);
    return () => clearInterval(interval);
  }, [fetchData]);

  useEffect(() => {
    if (!siteId) return;
    const siteIdForTelemetry = siteId;
    let mounted = true;
    async function loadTelemetrySummary() {
      try {
        const [rawTelemetryResp, stateResp] = await Promise.all([
          authorizedFetch(`/api/sites/${encodeURIComponent(siteIdForTelemetry)}/telemetry`).catch(() => null),
          authorizedFetch(`/api/building-state/${encodeURIComponent(siteIdForTelemetry)}`).catch(() => null),
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

  if (loading) {
    return (
      <div className="space-y-4">
        <h2 className="text-lg font-semibold" style={{ color: 'var(--color-sentinel-text-primary)' }}>Fuel Monitoring</h2>
        <LoadingSkeleton />
      </div>
    );
  }

  if (error) {
    return (
      <div
        className="rounded-lg p-4"
        style={{
          background: 'var(--color-sentinel-bg-panel)',
          border: '1px solid var(--color-sentinel-border)',
        }}
      >
        <h2 className="text-lg font-semibold" style={{ color: 'var(--color-sentinel-text-primary)' }}>Fuel Monitoring</h2>
        <p className="mt-2" style={{ color: 'var(--color-sentinel-red)' }}>{error}</p>
      </div>
    );
  }

  if (tanks.length === 0) {
    return (
      <div
        className="rounded-lg p-4"
        style={{
          background: 'var(--color-sentinel-bg-panel)',
          border: '1px solid var(--color-sentinel-border)',
        }}
      >
        <h2 className="text-lg font-semibold" style={{ color: 'var(--color-sentinel-text-primary)' }}>Fuel Monitoring</h2>
        <p className="mt-2 text-gray-500">
          No fuel tanks configured. Configure tanks via the fuel monitoring module settings.
        </p>
      </div>
    );
  }

  // Summary stats
  const tanksWarning = tanks.filter(t => {
    const pct = t.latest_telemetry?.level_pct ?? 100;
    return pct <= t.low_fuel_pct_1 && pct > t.low_fuel_pct_2;
  }).length;
  const tanksCritical = tanks.filter(t => {
    const pct = t.latest_telemetry?.level_pct ?? 100;
    return pct <= t.low_fuel_pct_2;
  }).length;
  const avgDaysToEmpty = tanks.reduce((sum, t) => sum + (t.latest_telemetry?.days_to_empty ?? 0), 0) / tanks.length;

  return (
    <div className="space-y-6">
      <div className="flex justify-between items-center">
        <h2 className="text-lg font-semibold" style={{ color: 'var(--color-sentinel-text-primary)' }}>Fuel Monitoring</h2>
        <p className="text-xs text-gray-400">Auto-refresh every 30s</p>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <div
          className="rounded-lg p-4"
          style={{
            background: 'var(--color-sentinel-bg-panel)',
            border: '1px solid var(--color-sentinel-border)',
          }}
        >
          <div className="flex items-center justify-between mb-2">
            <p className="text-sm font-semibold" style={{ color: 'var(--color-sentinel-text-primary)' }}>Raw Bridge Telemetry</p>
            <Badge className={bridgeTelemetry?.status === 'live' ? badgeEventColor.green : badgeEventColor.amber}>
              {bridgeTelemetry?.status === 'live' ? 'Live' : 'Unavailable'}
            </Badge>
          </div>
          <p className="text-xs text-gray-500">Zones: {bridgeTelemetry?.zones_with_readings ?? 0}/{bridgeTelemetry?.zone_count ?? 0}</p>
        </div>
        <div
          className="rounded-lg p-4"
          style={{
            background: 'var(--color-sentinel-bg-panel)',
            border: '1px solid var(--color-sentinel-border)',
          }}
        >
          <p className="text-sm font-semibold mb-2" style={{ color: 'var(--color-sentinel-text-primary)' }}>SENTINEL Fuel Interpretation</p>
          <p className="text-xs text-gray-500">Posture: {sentinelPosture || 'unknown'}</p>
          <p className="text-xs text-gray-500 mt-1">{sentinelGuidance || 'No active guidance yet.'}</p>
        </div>
      </div>

      {/* Summary Stats Row */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        {[
          { label: 'Total Tanks', value: tanks.length, color: undefined },
          { label: 'Warning', value: tanksWarning, color: 'var(--color-sentinel-amber)' },
          { label: 'Critical', value: tanksCritical, color: 'var(--color-sentinel-red)' },
          { label: 'Avg Days to Empty', value: avgDaysToEmpty > 0 ? avgDaysToEmpty.toFixed(0) : '--', color: undefined },
        ].map((stat, i) => (
          <div
            key={i}
            className="p-3 text-center rounded-lg"
            style={{
              background: 'var(--color-sentinel-bg-panel)',
              border: '1px solid var(--color-sentinel-border)',
            }}
          >
            <p className="text-sm" style={{ color: 'var(--color-sentinel-text-secondary)' }}>{stat.label}</p>
            <p
              className="text-2xl font-bold mt-1"
              style={{ color: stat.color || 'var(--color-sentinel-text-primary)' }}
            >
              {stat.value}
            </p>
          </div>
        ))}
      </div>

      {/* Tank Cards Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {tanks.map(tank => (
          <FuelTankCard key={tank.tank_id} tank={tank} />
        ))}
      </div>

      {/* Trend Chart */}
      {tanks.length > 0 && (
        <FuelTrendChart tanks={tanks} />
      )}

      {/* Recent Events Feed */}
      <div
        className="rounded-lg p-4"
        style={{
          background: 'var(--color-sentinel-bg-panel)',
          border: '1px solid var(--color-sentinel-border)',
        }}
      >
        <h3 className="text-base font-semibold mb-3" style={{ color: 'var(--color-sentinel-text-primary)' }}>Recent Fuel Events</h3>
        {events.length === 0 ? (
          <p className="text-gray-500">No recent fuel events</p>
        ) : (
          <div className="space-y-2">
            {events.map(evt => (
              <div
                key={evt.event_id}
                className="flex justify-between items-center py-2 border-b last:border-0"
                style={{ borderColor: 'var(--color-sentinel-border)' }}
              >
                <div className="flex items-center gap-2">
                  <Badge className={badgeEventColor[eventTypeBadgeColor(evt.event_type)]}>
                    {formatEventType(evt.event_type)}
                  </Badge>
                  <p className="text-sm text-gray-600">{evt.tank_id}</p>
                </div>
                <p className="text-xs text-gray-400">{formatTimestamp(evt.ts)}</p>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Refill Log Table */}
      <div
        className="rounded-lg p-4"
        style={{
          background: 'var(--color-sentinel-bg-panel)',
          border: '1px solid var(--color-sentinel-border)',
        }}
      >
        <h3 className="text-base font-semibold mb-3" style={{ color: 'var(--color-sentinel-text-primary)' }}>Refill Log</h3>
        {refills.length === 0 ? (
          <p className="text-gray-500">No refill events recorded</p>
        ) : (
          <table className="w-full">
            <thead>
              <tr
                className="text-left text-xs font-medium uppercase tracking-wider"
                style={{ color: 'var(--color-sentinel-text-secondary)' }}
              >
                <th className="pb-2">Date</th>
                <th className="pb-2">Tank</th>
                <th className="pb-2">Litres Added</th>
                <th className="pb-2">Previous Level</th>
                <th className="pb-2">New Level</th>
              </tr>
            </thead>
            <tbody>
              {refills.map(r => {
                const details = r.details || {};
                return (
                  <tr
                    key={r.event_id}
                    className="border-b last:border-0"
                    style={{ borderColor: 'var(--color-sentinel-border)' }}
                  >
                    <td className="py-2 pr-4 text-sm" style={{ color: 'var(--color-sentinel-text-primary)' }}>{formatTimestamp(r.ts)}</td>
                    <td className="py-2 pr-4 text-sm" style={{ color: 'var(--color-sentinel-text-primary)' }}>{r.tank_id}</td>
                    <td className="py-2 pr-4 text-sm" style={{ color: 'var(--color-sentinel-text-primary)' }}>{typeof details.litres_added === 'number' ? `${(details.litres_added as number).toFixed(0)} L` : '--'}</td>
                    <td className="py-2 pr-4 text-sm" style={{ color: 'var(--color-sentinel-text-primary)' }}>{typeof details.previous_pct === 'number' ? `${(details.previous_pct as number).toFixed(1)}%` : '--'}</td>
                    <td className="py-2 text-sm" style={{ color: 'var(--color-sentinel-text-primary)' }}>{typeof details.new_pct === 'number' ? `${(details.new_pct as number).toFixed(1)}%` : '--'}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
      </div>

      {/* Generator Runtime History */}
      <div
        className="rounded-lg p-4"
        style={{
          background: 'var(--color-sentinel-bg-panel)',
          border: '1px solid var(--color-sentinel-border)',
        }}
      >
        <h3 className="text-base font-semibold mb-3" style={{ color: 'var(--color-sentinel-text-primary)' }}>Generator Runtime History</h3>
        {runtimeSessions.length === 0 ? (
          <p className="text-gray-500">No generator runtime sessions recorded</p>
        ) : (
          <table className="w-full">
            <thead>
              <tr
                className="text-left text-xs font-medium uppercase tracking-wider"
                style={{ color: 'var(--color-sentinel-text-secondary)' }}
              >
                <th className="pb-2">Date</th>
                <th className="pb-2">Tank</th>
                <th className="pb-2">Duration</th>
                <th className="pb-2">Fuel Consumed</th>
                <th className="pb-2">Anomaly</th>
              </tr>
            </thead>
            <tbody>
              {runtimeSessions.map(s => {
                const details = s.details || {};
                const duration = typeof details.duration_seconds === 'number' ? details.duration_seconds as number : null;
                const consumed = typeof details.fuel_consumed_litres === 'number' ? details.fuel_consumed_litres as number : null;
                const anomaly = Boolean(details.anomaly);
                return (
                  <tr
                    key={s.event_id}
                    className="border-b last:border-0"
                    style={{ borderColor: 'var(--color-sentinel-border)' }}
                  >
                    <td className="py-2 pr-4 text-sm" style={{ color: 'var(--color-sentinel-text-primary)' }}>{formatTimestamp(s.ts)}</td>
                    <td className="py-2 pr-4 text-sm" style={{ color: 'var(--color-sentinel-text-primary)' }}>{s.tank_id}</td>
                    <td className="py-2 pr-4 text-sm" style={{ color: 'var(--color-sentinel-text-primary)' }}>{duration != null ? formatDuration(duration) : '--'}</td>
                    <td className="py-2 pr-4 text-sm" style={{ color: 'var(--color-sentinel-text-primary)' }}>{consumed != null ? `${consumed.toFixed(1)} L` : '--'}</td>
                    <td className="py-2 text-sm">
                      {anomaly ? (
                        <Badge className={badgeEventColor.red}>Anomaly</Badge>
                      ) : (
                        <Badge className={badgeEventColor.green}>Normal</Badge>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}

export default FuelDashboard;
