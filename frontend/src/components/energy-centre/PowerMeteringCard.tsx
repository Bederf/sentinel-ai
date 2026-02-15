/**
 * Power Metering Card - Bolt-on Module
 *
 * Real-time power metrics with:
 * - kW/kVA/PF readings
 * - TOU tariff indicator
 * - Demand tracking
 * - Power quality (THD)
 */

import { useState, useEffect, useCallback } from 'react';
import { Card, Title, Text, Metric, Grid, Badge, Flex } from '@tremor/react';
import { energyCentreApi } from '../../lib/energyCentreApi';
import type { PowerMeter } from '../../lib/energyCentreApi';

interface PowerMeteringCardProps {
  siteId: string;
  compact?: boolean;
}

const touColors: Record<string, string> = {
  peak: 'red',
  standard: 'yellow',
  'off-peak': 'green',
};

export function PowerMeteringCard({ siteId, compact = false }: PowerMeteringCardProps) {
  const [meter, setMeter] = useState<PowerMeter | null>(null);
  const [loading, setLoading] = useState(true);

  const loadData = useCallback(async () => {
    try {
      const meters = await energyCentreApi.getMeters(siteId, 'main');
      if (meters.length > 0) {
        setMeter(meters[0]);
      }
      setLoading(false);
    } catch (_err) {
      setLoading(false);
    }
  }, [siteId]);

  useEffect(() => {
    loadData();
    const interval = setInterval(loadData, 5000);
    return () => clearInterval(interval);
  }, [loadData]);

  if (loading) {
    return (
      <Card>
        <Title>Power Metering</Title>
        <div className="animate-pulse h-32 bg-gray-100 rounded mt-4" />
      </Card>
    );
  }

  if (!meter) {
    return (
      <Card>
        <Title>Power Metering</Title>
        <Text className="text-gray-500">No meter data available</Text>
      </Card>
    );
  }

  if (compact) {
    return (
      <Card decoration="top" decorationColor={touColors[meter.tou_period || 'standard'] || 'gray'}>
        <Flex justifyContent="between" alignItems="start">
          <div>
            <Text>Power</Text>
            <Metric>{meter.active_power_kw.toFixed(0)} kW</Metric>
          </div>
          <div className="text-right">
            <Text>PF</Text>
            <Metric className={meter.power_factor < 0.9 ? 'text-amber-500' : ''}>
              {meter.power_factor.toFixed(2)}
            </Metric>
          </div>
        </Flex>
        {meter.tou_period && (
          <Badge color={touColors[meter.tou_period] || 'gray'} className="mt-2">
            {meter.tariff_type} - {meter.tou_period.toUpperCase()}
          </Badge>
        )}
      </Card>
    );
  }

  return (
    <Card>
      <Flex justifyContent="between" alignItems="start">
        <div>
          <Title>Main Incomer</Title>
          <Text className="text-xs">{meter.manufacturer} {meter.model}</Text>
        </div>
        {meter.tou_period && (
          <Badge color={touColors[meter.tou_period] || 'gray'} size="lg">
            {meter.tariff_type} - {meter.tou_period.toUpperCase()}
          </Badge>
        )}
      </Flex>

      <Grid className="grid grid-cols-4 gap-4 mt-4">
        <Card decoration="top" decorationColor="blue">
          <Text>Active Power</Text>
          <Metric>{meter.active_power_kw.toFixed(0)}</Metric>
          <Text className="text-xs">kW</Text>
        </Card>
        <Card decoration="top" decorationColor="purple">
          <Text>Apparent Power</Text>
          <Metric>{meter.apparent_power_kva.toFixed(0)}</Metric>
          <Text className="text-xs">kVA</Text>
        </Card>
        <Card decoration="top" decorationColor={meter.power_factor < 0.9 ? 'amber' : 'green'}>
          <Text>Power Factor</Text>
          <Metric>{meter.power_factor.toFixed(2)}</Metric>
          <Text className="text-xs">target 0.95</Text>
        </Card>
        <Card decoration="top" decorationColor="cyan">
          <Text>Frequency</Text>
          <Metric>{meter.frequency_hz.toFixed(1)}</Metric>
          <Text className="text-xs">Hz</Text>
        </Card>
      </Grid>

      {/* Voltage & Current */}
      <div className="mt-4 grid grid-cols-3 gap-2 text-center">
        <div>
          <Text className="text-xs text-gray-500">L1</Text>
          <Text>{meter.voltage_l1_n.toFixed(0)}V / {meter.current_l1.toFixed(0)}A</Text>
        </div>
        <div>
          <Text className="text-xs text-gray-500">L2</Text>
          <Text>{meter.voltage_l2_n.toFixed(0)}V / {meter.current_l2.toFixed(0)}A</Text>
        </div>
        <div>
          <Text className="text-xs text-gray-500">L3</Text>
          <Text>{meter.voltage_l3_n.toFixed(0)}V / {meter.current_l3.toFixed(0)}A</Text>
        </div>
      </div>

      {/* Energy totals */}
      <div className="mt-4 pt-4 border-t border-gray-200">
        <Flex justifyContent="between">
          <div>
            <Text className="text-xs text-gray-500">Total Import</Text>
            <Text className="font-bold">{(meter.kwh_import / 1000).toFixed(1)} MWh</Text>
          </div>
          <div className="text-right">
            <Text className="text-xs text-gray-500">Max Demand</Text>
            <Text className="font-bold">{meter.max_demand_kw.toFixed(0)} kW</Text>
          </div>
        </Flex>
      </div>

      {/* Power Quality */}
      {(meter.thd_voltage_pct || meter.thd_current_pct) && (
        <div className="mt-4 pt-4 border-t border-gray-200">
          <Text className="text-xs text-gray-500 mb-2">Power Quality</Text>
          <Grid className="grid grid-cols-3 gap-2">
            {meter.thd_voltage_pct !== undefined && (
              <div>
                <Text className="text-xs">THD-V</Text>
                <Text className={meter.thd_voltage_pct > 5 ? 'text-amber-500' : ''}>
                  {meter.thd_voltage_pct.toFixed(1)}%
                </Text>
              </div>
            )}
            {meter.thd_current_pct !== undefined && (
              <div>
                <Text className="text-xs">THD-I</Text>
                <Text className={meter.thd_current_pct > 15 ? 'text-amber-500' : ''}>
                  {meter.thd_current_pct.toFixed(1)}%
                </Text>
              </div>
            )}
            {meter.voltage_unbalance_pct !== undefined && (
              <div>
                <Text className="text-xs">Unbalance</Text>
                <Text className={meter.voltage_unbalance_pct > 2 ? 'text-amber-500' : ''}>
                  {meter.voltage_unbalance_pct.toFixed(1)}%
                </Text>
              </div>
            )}
          </Grid>
        </div>
      )}
    </Card>
  );
}

export default PowerMeteringCard;
