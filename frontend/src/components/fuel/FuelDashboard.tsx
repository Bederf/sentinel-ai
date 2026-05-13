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

interface FuelDashboardProps {
  siteId?: string;
}

const POLL_INTERVAL_MS = 30_000;

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
        <Title>Fuel Monitoring</Title>
        <LoadingSkeleton />
      </div>
    );
  }

  if (error) {
    return (
      <Card>
        <Title>Fuel Monitoring</Title>
        <Text className="text-red-600 mt-2">{error}</Text>
      </Card>
    );
  }

  if (tanks.length === 0) {
    return (
      <Card>
        <Title>Fuel Monitoring</Title>
        <Text className="text-gray-500 mt-2">
          No fuel tanks configured. Configure tanks via the fuel monitoring module settings.
        </Text>
      </Card>
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
      <Flex justifyContent="between" alignItems="center">
        <Title>Fuel Monitoring</Title>
        <Text className="text-xs text-gray-400">Auto-refresh every 30s</Text>
      </Flex>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <Card>
          <div className="flex items-center justify-between mb-2">
            <Text className="text-sm font-semibold">Raw Bridge Telemetry</Text>
            <Badge color={bridgeTelemetry?.status === 'live' ? 'green' : 'amber'} size="sm">
              {bridgeTelemetry?.status === 'live' ? 'Live' : 'Unavailable'}
            </Badge>
          </div>
          <Text className="text-xs text-gray-500">Zones: {bridgeTelemetry?.zones_with_readings ?? 0}/{bridgeTelemetry?.zone_count ?? 0}</Text>
        </Card>
        <Card>
          <Text className="text-sm font-semibold mb-2">SENTINEL Fuel Interpretation</Text>
          <Text className="text-xs text-gray-500">Posture: {sentinelPosture || 'unknown'}</Text>
          <Text className="text-xs text-gray-500 mt-1">{sentinelGuidance || 'No active guidance yet.'}</Text>
        </Card>
      </div>

      {/* Summary Stats Row */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <Card className="p-3 text-center">
          <Text className="text-sm text-gray-500">Total Tanks</Text>
          <Text className="text-2xl font-bold">{tanks.length}</Text>
        </Card>
        <Card className="p-3 text-center">
          <Text className="text-sm text-gray-500">Warning</Text>
          <Text className="text-2xl font-bold text-amber-600">{tanksWarning}</Text>
        </Card>
        <Card className="p-3 text-center">
          <Text className="text-sm text-gray-500">Critical</Text>
          <Text className="text-2xl font-bold text-red-600">{tanksCritical}</Text>
        </Card>
        <Card className="p-3 text-center">
          <Text className="text-sm text-gray-500">Avg Days to Empty</Text>
          <Text className="text-2xl font-bold">{avgDaysToEmpty > 0 ? avgDaysToEmpty.toFixed(0) : '--'}</Text>
        </Card>
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
      <Card>
        <Title className="mb-3">Recent Fuel Events</Title>
        {events.length === 0 ? (
          <Text className="text-gray-500">No recent fuel events</Text>
        ) : (
          <div className="space-y-2">
            {events.map(evt => (
              <Flex key={evt.event_id} justifyContent="between" alignItems="center"
                className="py-2 border-b border-gray-100 last:border-0">
                <Flex alignItems="center" className="gap-2">
                  <Badge color={eventTypeBadgeColor(evt.event_type)} size="sm">
                    {formatEventType(evt.event_type)}
                  </Badge>
                  <Text className="text-sm text-gray-600">{evt.tank_id}</Text>
                </Flex>
                <Text className="text-xs text-gray-400">{formatTimestamp(evt.ts)}</Text>
              </Flex>
            ))}
          </div>
        )}
      </Card>

      {/* Refill Log Table */}
      <Card>
        <Title className="mb-3">Refill Log</Title>
        {refills.length === 0 ? (
          <Text className="text-gray-500">No refill events recorded</Text>
        ) : (
          <Table>
            <TableHead>
              <TableRow>
                <TableHeaderCell>Date</TableHeaderCell>
                <TableHeaderCell>Tank</TableHeaderCell>
                <TableHeaderCell>Litres Added</TableHeaderCell>
                <TableHeaderCell>Previous Level</TableHeaderCell>
                <TableHeaderCell>New Level</TableHeaderCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {refills.map(r => {
                const details = r.details || {};
                return (
                  <TableRow key={r.event_id}>
                    <TableCell>{formatTimestamp(r.ts)}</TableCell>
                    <TableCell>{r.tank_id}</TableCell>
                    <TableCell>{typeof details.litres_added === 'number' ? `${(details.litres_added as number).toFixed(0)} L` : '--'}</TableCell>
                    <TableCell>{typeof details.previous_pct === 'number' ? `${(details.previous_pct as number).toFixed(1)}%` : '--'}</TableCell>
                    <TableCell>{typeof details.new_pct === 'number' ? `${(details.new_pct as number).toFixed(1)}%` : '--'}</TableCell>
                  </TableRow>
                );
              })}
            </TableBody>
          </Table>
        )}
      </Card>

      {/* Generator Runtime History */}
      <Card>
        <Title className="mb-3">Generator Runtime History</Title>
        {runtimeSessions.length === 0 ? (
          <Text className="text-gray-500">No generator runtime sessions recorded</Text>
        ) : (
          <Table>
            <TableHead>
              <TableRow>
                <TableHeaderCell>Date</TableHeaderCell>
                <TableHeaderCell>Tank</TableHeaderCell>
                <TableHeaderCell>Duration</TableHeaderCell>
                <TableHeaderCell>Fuel Consumed</TableHeaderCell>
                <TableHeaderCell>Anomaly</TableHeaderCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {runtimeSessions.map(s => {
                const details = s.details || {};
                const duration = typeof details.duration_seconds === 'number' ? details.duration_seconds as number : null;
                const consumed = typeof details.fuel_consumed_litres === 'number' ? details.fuel_consumed_litres as number : null;
                const anomaly = Boolean(details.anomaly);
                return (
                  <TableRow key={s.event_id}>
                    <TableCell>{formatTimestamp(s.ts)}</TableCell>
                    <TableCell>{s.tank_id}</TableCell>
                    <TableCell>{duration != null ? formatDuration(duration) : '--'}</TableCell>
                    <TableCell>{consumed != null ? `${consumed.toFixed(1)} L` : '--'}</TableCell>
                    <TableCell>
                      {anomaly ? (
                        <Badge color="red" size="sm">Anomaly</Badge>
                      ) : (
                        <Badge color="green" size="sm">Normal</Badge>
                      )}
                    </TableCell>
                  </TableRow>
                );
              })}
            </TableBody>
          </Table>
        )}
      </Card>
    </div>
  );
}

export default FuelDashboard;
