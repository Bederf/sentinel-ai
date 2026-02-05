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
import { Card, Title, Text, Badge, Grid, Metric, ProgressBar, Flex } from '@tremor/react';
import { energyCentreApi } from '../../lib/energyCentreApi';
import type { UPSSummary } from '../../lib/energyCentreApi';

interface UPSStatusPanelProps {
  siteId: string;
  compact?: boolean;
  onBatteryAlert?: (ups: any) => void;
}

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
      <Card>
        <Title>UPS Systems</Title>
        <div className="animate-pulse h-32 bg-gray-100 rounded mt-4" />
      </Card>
    );
  }

  if (!summary) {
    return (
      <Card>
        <Title>UPS Systems</Title>
        <Text className="text-gray-500">No UPS data available</Text>
      </Card>
    );
  }

  if (compact) {
    return (
      <Card decoration="top" decorationColor={summary.any_on_battery ? 'red' : summary.all_healthy ? 'green' : 'amber'}>
        <Flex justifyContent="between" alignItems="start">
          <div>
            <Text>UPS Fleet</Text>
            <Metric>{summary.systems.length}</Metric>
          </div>
          <div className="text-right">
            {summary.any_on_battery ? (
              <Badge color="red" size="lg">ON BATTERY</Badge>
            ) : (
              <Badge color="green" size="lg">ONLINE</Badge>
            )}
          </div>
        </Flex>
        <Text className="text-xs mt-2">
          Load: {summary.total_load_kw.toFixed(0)} kW / {summary.total_capacity_kva.toFixed(0)} kVA
        </Text>
      </Card>
    );
  }

  return (
    <Card>
      <Flex justifyContent="between" alignItems="start">
        <Title>UPS Systems</Title>
        <div className="flex gap-2">
          {summary.any_on_battery && (
            <Badge color="red" size="lg">ON BATTERY</Badge>
          )}
          <Badge color={summary.all_healthy ? 'green' : 'amber'}>
            {summary.all_healthy ? 'All Healthy' : 'Attention Required'}
          </Badge>
        </div>
      </Flex>

      <div className="mt-4 space-y-4">
        {summary.systems.map((ups) => (
          <Card
            key={ups.ups_id}
            decoration="left"
            decorationColor={modeColors[ups.mode] || 'gray'}
            className={ups.on_battery ? 'border-red-500 border-2' : ''}
          >
            <Flex justifyContent="between" alignItems="start">
              <div>
                <Text className="font-bold">{ups.name}</Text>
                <Badge color={modeColors[ups.mode] || 'gray'}>
                  {ups.mode.toUpperCase()}
                </Badge>
              </div>
              {ups.on_battery && (
                <div className="text-right">
                  <Text className="text-red-500 font-bold text-xl">
                    {ups.runtime_min.toFixed(0)} min
                  </Text>
                  <Text className="text-xs text-red-500">runtime</Text>
                </div>
              )}
            </Flex>

            <Grid numItems={3} className="gap-4 mt-3">
              <div>
                <Text className="text-xs text-gray-500">Load</Text>
                <Text className={ups.load_percent > 80 ? 'text-amber-500 font-bold' : ''}>
                  {ups.load_percent}%
                </Text>
                <ProgressBar
                  value={ups.load_percent}
                  color={ups.load_percent > 80 ? 'amber' : 'blue'}
                  className="mt-1"
                />
              </div>
              <div>
                <Text className="text-xs text-gray-500">Battery</Text>
                <Text className={ups.battery_charge_pct < 50 ? 'text-amber-500 font-bold' : ''}>
                  {ups.battery_charge_pct}%
                </Text>
                <ProgressBar
                  value={ups.battery_charge_pct}
                  color={ups.battery_charge_pct < 50 ? 'amber' : 'green'}
                  className="mt-1"
                />
              </div>
              <div>
                <Text className="text-xs text-gray-500">Runtime</Text>
                <Text>{ups.runtime_min.toFixed(0)} min</Text>
              </div>
            </Grid>

            {ups.alarms.length > 0 && (
              <div className="mt-2 pt-2 border-t border-gray-200">
                {ups.alarms.map((alarm, idx) => (
                  <Badge key={idx} color="red" className="mr-1">
                    {alarm}
                  </Badge>
                ))}
              </div>
            )}
          </Card>
        ))}
      </div>
    </Card>
  );
}

export default UPSStatusPanel;
