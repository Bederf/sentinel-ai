/**
 * Generator Synoptic Panel - Bolt-on Module
 *
 * SCADA-style visualization of generator fleet with:
 * - Real-time status indicators
 * - Engine/electrical telemetry
 * - Fuel monitoring
 * - Predictive health indicators
 */

import { useState, useEffect, useCallback } from 'react';
import { generatorApi } from '../../lib/energyCentreApi';
import type { Generator, GeneratorGroupStatus, GeneratorHealth, FuelStatus } from '../../lib/energyCentreApi';

interface GeneratorSynopticProps {
  siteId: string;
  groupId?: string;
  onHealthAlert?: (generator: Generator, health: GeneratorHealth) => void;
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

const statusColors: Record<string, string> = {
  standby: 'gray',
  running: 'blue',
  on_load: 'green',
  cooling: 'cyan',
  maintenance: 'yellow',
  fault: 'red',
  offline: 'slate',
};

const trendColors: Record<string, string> = {
  improving: 'green',
  stable: 'blue',
  degrading: 'yellow',
  critical: 'red',
};

export function GeneratorSynoptic({ siteId, groupId, onHealthAlert }: GeneratorSynopticProps) {
  const [groupStatus, setGroupStatus] = useState<GeneratorGroupStatus | null>(null);
  const [fuelStatus, setFuelStatus] = useState<FuelStatus | null>(null);
  const [healthData, setHealthData] = useState<Record<string, GeneratorHealth>>({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const loadData = useCallback(async () => {
    try {
      // Get groups first if no specific groupId
      let targetGroupId = groupId;
      if (!targetGroupId) {
        const groups = await generatorApi.getGroups(siteId);
        if (groups.length > 0) {
          targetGroupId = groups[0].group_id;
        }
      }

      if (targetGroupId) {
        const [status, fuel] = await Promise.all([
          generatorApi.getGroupStatus(targetGroupId),
          generatorApi.getFuelStatus(targetGroupId).catch(() => null),
        ]);
        setGroupStatus(status);
        setFuelStatus(fuel);

        // Load health data for each generator
        const healthPromises = status.generator_details.map(async (gen) => {
          try {
            const health = await generatorApi.getHealth(gen.generator_id);
            // Trigger alert callback for critical health
            if (onHealthAlert && health.status === 'critical') {
              const fullGen = await generatorApi.getGenerator(gen.generator_id);
              onHealthAlert(fullGen, health);
            }
            return { id: gen.generator_id, health };
          } catch {
            return null;
          }
        });

        const healthResults = await Promise.all(healthPromises);
        const healthMap: Record<string, GeneratorHealth> = {};
        healthResults.forEach((result) => {
          if (result) healthMap[result.id] = result.health;
        });
        setHealthData(healthMap);
      }

      setLoading(false);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load generator data');
      setLoading(false);
    }
  }, [siteId, groupId, onHealthAlert]);

  useEffect(() => {
    loadData();
    const interval = setInterval(loadData, 5000); // Poll every 5 seconds
    return () => clearInterval(interval);
  }, [loadData]);

  if (loading) {
    return (
      <div className="rounded-lg p-4" style={{ background: "var(--sentinel-bg-panel)", border: "1px solid var(--sentinel-border)" }}>
        <h3 className="text-sm font-medium" style={{ color: "var(--sentinel-text-primary)" }}>Generator Plant</h3>
        <div className="animate-pulse h-64 bg-gray-100 rounded mt-4" />
      </div>
    );
  }

  if (error || !groupStatus) {
    return (
      <div className="rounded-lg p-4" style={{ background: "var(--sentinel-bg-panel)", border: "1px solid var(--sentinel-border)" }}>
        <h3 className="text-sm font-medium" style={{ color: "var(--sentinel-text-primary)" }}>Generator Plant</h3>
        <span className="text-red-500">{error || 'No generator data available'}</span>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {/* Group Overview */}
      <div className="rounded-lg p-4" style={{ background: "var(--sentinel-bg-panel)", border: "1px solid var(--sentinel-border)" }}>
        <div className="flex items-start justify-between">
          <div>
            <h3 className="text-sm font-medium" style={{ color: "var(--sentinel-text-primary)" }}>{groupStatus.name}</h3>
            <span style={{ color: "var(--sentinel-text-secondary)" }}>N+1 Redundancy: {groupStatus.generators.required}/{groupStatus.generators.total} required</span>
          </div>
          <span className="text-xs px-2 py-0.5 rounded font-medium" style={{ background: sentinelColors[groupStatus.ats.mains_healthy ? 'green' : 'red'], color: "white" }}>
            {groupStatus.ats.position.toUpperCase()}
          </span>
        </div>

        <div className="grid grid-cols-4 gap-4 mt-4">
          <div className="rounded-lg p-4" style={{ background: "var(--sentinel-bg-panel)", border: "1px solid var(--sentinel-border)", borderTop: "3px solid var(--sentinel-green)" }}>
            <span style={{ color: "var(--sentinel-text-secondary)" }}>Running</span>
            <span className="text-2xl font-bold tabular-nums block" style={{ color: "var(--sentinel-text-primary)" }}>{groupStatus.generators.running}</span>
          </div>
          <div className="rounded-lg p-4" style={{ background: "var(--sentinel-bg-panel)", border: "1px solid var(--sentinel-border)", borderTop: "3px solid var(--sentinel-blue)" }}>
            <span style={{ color: "var(--sentinel-text-secondary)" }}>On Load</span>
            <span className="text-2xl font-bold tabular-nums block" style={{ color: "var(--sentinel-text-primary)" }}>{groupStatus.generators.on_load}</span>
          </div>
          <div className="rounded-lg p-4" style={{ background: "var(--sentinel-bg-panel)", border: "1px solid var(--sentinel-border)", borderTop: "3px solid var(--sentinel-amber)" }}>
            <span style={{ color: "var(--sentinel-text-secondary)" }}>Load</span>
            <span className="text-2xl font-bold tabular-nums block" style={{ color: "var(--sentinel-text-primary)" }}>{groupStatus.load.percent.toFixed(0)}%</span>
          </div>
          <div className="rounded-lg p-4" style={{ background: "var(--sentinel-bg-panel)", border: "1px solid var(--sentinel-border)", borderTop: `3px solid ${sentinelColors[groupStatus.ats.mains_healthy ? 'green' : 'red']}` }}>
            <span style={{ color: "var(--sentinel-text-secondary)" }}>Mains</span>
            <span className="text-2xl font-bold tabular-nums block" style={{ color: "var(--sentinel-text-primary)" }}>{groupStatus.ats.mains_healthy ? 'OK' : 'FAIL'}</span>
          </div>
        </div>

        {/* Load bar */}
        <div className="mt-4">
          <div className="flex items-center justify-between mb-1">
            <span style={{ color: "var(--sentinel-text-secondary)" }}>Total Load: {groupStatus.load.current_kw.toFixed(0)} kW</span>
            <span style={{ color: "var(--sentinel-text-secondary)" }}>Capacity: {groupStatus.load.capacity_kw} kW</span>
          </div>
          <div className="w-full h-2 rounded-full overflow-hidden" style={{ background: "var(--sentinel-border)" }}>
            <div className="h-full rounded-full" style={{ width: `${groupStatus.load.percent}%`, background: "var(--sentinel-green)" }} />
          </div>
        </div>
      </div>

      {/* Generator Cards */}
      <div className="grid grid-cols-2 gap-4">
        {groupStatus.generator_details.map((gen) => {
          const health = healthData[gen.generator_id];
          const genAccent = sentinelColors[statusColors[gen.status]] || sentinelColors.gray;
          return (
            <div key={gen.generator_id} className="rounded-lg p-4" style={{ background: "var(--sentinel-bg-panel)", border: "1px solid var(--sentinel-border)", borderLeft: `3px solid ${genAccent}` }}>
              <div className="flex items-start justify-between">
                <div>
                  <h3 className="text-sm font-medium" style={{ color: "var(--sentinel-text-primary)" }}>{gen.name}</h3>
                  <span className="text-xs" style={{ color: "var(--sentinel-text-secondary)" }}>Priority {gen.priority}</span>
                </div>
                <div className="text-right">
                  <span className="text-xs px-2 py-0.5 rounded font-medium" style={{ background: sentinelColors[statusColors[gen.status]] || sentinelColors.gray, color: "white" }}>
                    {gen.status.toUpperCase().replace('_', ' ')}
                  </span>
                  {health && (
                    <span className="text-xs px-2 py-0.5 rounded font-medium ml-1" style={{ background: sentinelColors[trendColors[health.status]] || sentinelColors.gray, color: "white" }}>
                      {health.overall_score.toFixed(0)}%
                    </span>
                  )}
                </div>
              </div>

              <div className="grid grid-cols-3 gap-2 mt-3">
                <div>
                  <span className="text-xs" style={{ color: "var(--sentinel-text-secondary)" }}>Battery</span>
                  <span className={gen.battery_voltage < 25.5 ? 'text-red-500 font-bold block' : 'block'} style={{ color: "var(--sentinel-text-primary)" }}>
                    {gen.battery_voltage.toFixed(1)}V
                  </span>
                </div>
                <div>
                  <span className="text-xs" style={{ color: "var(--sentinel-text-secondary)" }}>Fuel</span>
                  <span className={gen.fuel_level_pct < 20 ? 'text-red-500 font-bold block' : 'block'} style={{ color: "var(--sentinel-text-primary)" }}>
                    {gen.fuel_level_pct}%
                  </span>
                </div>
                <div>
                  <span className="text-xs" style={{ color: "var(--sentinel-text-secondary)" }}>Load</span>
                  <span style={{ color: "var(--sentinel-text-primary)" }}>{gen.load_kw.toFixed(0)} kW</span>
                </div>
              </div>

              {/* Health indicators */}
              {health && health.indicators.some(i => i.recommendation) && (
                <div className="mt-2 pt-2 border-t border-gray-200">
                  {health.indicators
                    .filter(i => i.recommendation)
                    .slice(0, 2)
                    .map((ind, idx) => (
                      <span key={idx} className="text-xs text-amber-600 block">
                        {ind.parameter}: {ind.recommendation}
                      </span>
                    ))}
                </div>
              )}
            </div>
          );
        })}
      </div>

      {/* Fuel Tank */}
      {fuelStatus && (
        <div className="rounded-lg p-4" style={{ background: "var(--sentinel-bg-panel)", border: "1px solid var(--sentinel-border)" }}>
          <div className="flex items-start justify-between">
            <div>
              <h3 className="text-sm font-medium" style={{ color: "var(--sentinel-text-primary)" }}>{fuelStatus.name}</h3>
              <span className="text-xs" style={{ color: "var(--sentinel-text-secondary)" }}>
                {fuelStatus.current_liters.toLocaleString()}L / {fuelStatus.capacity_liters.toLocaleString()}L
              </span>
            </div>
            {fuelStatus.hours_remaining && (
              <span className="text-xs px-2 py-0.5 rounded font-medium" style={{ background: sentinelColors[fuelStatus.current_pct < 20 ? 'red' : fuelStatus.current_pct < 30 ? 'yellow' : 'green'], color: fuelStatus.current_pct < 30 && fuelStatus.current_pct >= 20 ? 'black' : 'white' }}>
                {fuelStatus.hours_remaining.toFixed(0)}h remaining
              </span>
            )}
          </div>
          <div className="w-full h-2 rounded-full overflow-hidden mt-2" style={{ background: "var(--sentinel-border)" }}>
            <div className="h-full rounded-full" style={{ width: `${fuelStatus.current_pct}%`, background: sentinelColors[fuelStatus.current_pct < 20 ? 'red' : fuelStatus.current_pct < 30 ? 'yellow' : 'green'] }} />
          </div>
          {fuelStatus.alerts.length > 0 && (
            <div className="mt-2">
              {fuelStatus.alerts.map((alert, idx) => (
                <span key={idx} className={`text-xs block ${alert.severity === 'alarm' ? 'text-red-500' : 'text-amber-500'}`}>
                  {alert.message} - {alert.action}
                </span>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

export default GeneratorSynoptic;
