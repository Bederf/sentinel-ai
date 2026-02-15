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
import { Card, Title, Text, Badge, Grid, Metric, ProgressBar, Flex } from '@tremor/react';
import { generatorApi } from '../../lib/energyCentreApi';
import type { Generator, GeneratorGroupStatus, GeneratorHealth, FuelStatus } from '../../lib/energyCentreApi';

interface GeneratorSynopticProps {
  siteId: string;
  groupId?: string;
  onHealthAlert?: (generator: Generator, health: GeneratorHealth) => void;
}

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
      <Card>
        <Title>Generator Plant</Title>
        <div className="animate-pulse h-64 bg-gray-100 rounded mt-4" />
      </Card>
    );
  }

  if (error || !groupStatus) {
    return (
      <Card>
        <Title>Generator Plant</Title>
        <Text className="text-red-500">{error || 'No generator data available'}</Text>
      </Card>
    );
  }

  return (
    <div className="space-y-4">
      {/* Group Overview */}
      <Card>
        <Flex justifyContent="between" alignItems="start">
          <div>
            <Title>{groupStatus.name}</Title>
            <Text>N+1 Redundancy: {groupStatus.generators.required}/{groupStatus.generators.total} required</Text>
          </div>
          <Badge color={groupStatus.ats.mains_healthy ? 'green' : 'red'} size="lg">
            {groupStatus.ats.position.toUpperCase()}
          </Badge>
        </Flex>

        <Grid className="grid grid-cols-4 gap-4 mt-4">
          <Card decoration="top" decorationColor="green">
            <Text>Running</Text>
            <Metric>{groupStatus.generators.running}</Metric>
          </Card>
          <Card decoration="top" decorationColor="blue">
            <Text>On Load</Text>
            <Metric>{groupStatus.generators.on_load}</Metric>
          </Card>
          <Card decoration="top" decorationColor="yellow">
            <Text>Load</Text>
            <Metric>{groupStatus.load.percent.toFixed(0)}%</Metric>
          </Card>
          <Card decoration="top" decorationColor={groupStatus.ats.mains_healthy ? 'green' : 'red'}>
            <Text>Mains</Text>
            <Metric>{groupStatus.ats.mains_healthy ? 'OK' : 'FAIL'}</Metric>
          </Card>
        </Grid>

        {/* Load bar */}
        <div className="mt-4">
          <Flex justifyContent="between" className="mb-1">
            <Text>Total Load: {groupStatus.load.current_kw.toFixed(0)} kW</Text>
            <Text>Capacity: {groupStatus.load.capacity_kw} kW</Text>
          </Flex>
          <ProgressBar value={groupStatus.load.percent} color="green" />
        </div>
      </Card>

      {/* Generator Cards */}
      <Grid className="grid grid-cols-2 gap-4">
        {groupStatus.generator_details.map((gen) => {
          const health = healthData[gen.generator_id];
          return (
            <Card key={gen.generator_id} decoration="left" decorationColor={statusColors[gen.status] || 'gray'}>
              <Flex justifyContent="between" alignItems="start">
                <div>
                  <Title className="text-sm">{gen.name}</Title>
                  <Text className="text-xs">Priority {gen.priority}</Text>
                </div>
                <div className="text-right">
                  <Badge color={statusColors[gen.status] || 'gray'}>
                    {gen.status.toUpperCase().replace('_', ' ')}
                  </Badge>
                  {health && (
                    <Badge color={trendColors[health.status] || 'gray'} className="ml-1">
                      {health.overall_score.toFixed(0)}%
                    </Badge>
                  )}
                </div>
              </Flex>

              <Grid className="grid grid-cols-3 gap-2 mt-3">
                <div>
                  <Text className="text-xs text-gray-500">Battery</Text>
                  <Text className={gen.battery_voltage < 25.5 ? 'text-red-500 font-bold' : ''}>
                    {gen.battery_voltage.toFixed(1)}V
                  </Text>
                </div>
                <div>
                  <Text className="text-xs text-gray-500">Fuel</Text>
                  <Text className={gen.fuel_level_pct < 20 ? 'text-red-500 font-bold' : ''}>
                    {gen.fuel_level_pct}%
                  </Text>
                </div>
                <div>
                  <Text className="text-xs text-gray-500">Load</Text>
                  <Text>{gen.load_kw.toFixed(0)} kW</Text>
                </div>
              </Grid>

              {/* Health indicators */}
              {health && health.indicators.some(i => i.recommendation) && (
                <div className="mt-2 pt-2 border-t border-gray-200">
                  {health.indicators
                    .filter(i => i.recommendation)
                    .slice(0, 2)
                    .map((ind, idx) => (
                      <Text key={idx} className="text-xs text-amber-600">
                        {ind.parameter}: {ind.recommendation}
                      </Text>
                    ))}
                </div>
              )}
            </Card>
          );
        })}
      </Grid>

      {/* Fuel Tank */}
      {fuelStatus && (
        <Card>
          <Flex justifyContent="between" alignItems="start">
            <div>
              <Title className="text-sm">{fuelStatus.name}</Title>
              <Text className="text-xs">
                {fuelStatus.current_liters.toLocaleString()}L / {fuelStatus.capacity_liters.toLocaleString()}L
              </Text>
            </div>
            {fuelStatus.hours_remaining && (
              <Badge color={fuelStatus.current_pct < 20 ? 'red' : fuelStatus.current_pct < 30 ? 'yellow' : 'green'}>
                {fuelStatus.hours_remaining.toFixed(0)}h remaining
              </Badge>
            )}
          </Flex>
          <ProgressBar
            value={fuelStatus.current_pct}
            color={fuelStatus.current_pct < 20 ? 'red' : fuelStatus.current_pct < 30 ? 'yellow' : 'green'}
            className="mt-2"
          />
          {fuelStatus.alerts.length > 0 && (
            <div className="mt-2">
              {fuelStatus.alerts.map((alert, idx) => (
                <Text key={idx} className={`text-xs ${alert.severity === 'alarm' ? 'text-red-500' : 'text-amber-500'}`}>
                  {alert.message} - {alert.action}
                </Text>
              ))}
            </div>
          )}
        </Card>
      )}
    </div>
  );
}

export default GeneratorSynoptic;
