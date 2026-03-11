/**
 * FuelTrendChart - Time-series chart of fuel level % over time.
 *
 * Shows level trend with period toggle (24h/7d/30d), tank selector,
 * and consumption rate overlay. Uses Tremor AreaChart.
 */

import { useState, useEffect, useCallback } from 'react';
import { Card, Title, Text, AreaChart, Flex } from '@tremor/react';
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

  // Transform readings for Tremor AreaChart
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

  const categories = ['Level %'];
  if (readings.some(r => r.temperature_c != null)) {
    categories.push('Temp C');
  }

  return (
    <Card>
      <Flex justifyContent="between" alignItems="center" className="mb-4">
        <Title>Fuel Level Trend</Title>
        <Flex className="gap-2" alignItems="center">
          {/* Tank Selector */}
          {tanks.length > 1 && (
            <select
              value={selectedTankId}
              onChange={e => setSelectedTankId(e.target.value)}
              className="text-sm border border-gray-300 rounded-md px-2 py-1 bg-white"
            >
              {tanks.map(t => (
                <option key={t.tank_id} value={t.tank_id}>
                  {t.name}
                </option>
              ))}
            </select>
          )}

          {/* Period Toggle */}
          <div className="flex rounded-lg border border-gray-200 overflow-hidden">
            {(['24h', '7d', '30d'] as Period[]).map(p => (
              <button
                key={p}
                onClick={() => setPeriod(p)}
                className={`px-3 py-1 text-sm font-medium transition-colors ${
                  period === p
                    ? 'bg-blue-600 text-white'
                    : 'bg-white text-gray-600 hover:bg-gray-50'
                }`}
              >
                {p}
              </button>
            ))}
          </div>
        </Flex>
      </Flex>

      {loading ? (
        <div className="h-64 flex items-center justify-center">
          <Text className="text-gray-400">Loading chart data...</Text>
        </div>
      ) : chartData.length === 0 ? (
        <div className="h-64 flex items-center justify-center">
          <Text className="text-gray-400">No telemetry data for the selected period</Text>
        </div>
      ) : (
        <AreaChart
          className="h-64"
          data={chartData}
          index="time"
          categories={categories}
          colors={['blue', 'orange']}
          showLegend={categories.length > 1}
          showGridLines
          curveType="monotone"
          yAxisWidth={48}
        />
      )}
    </Card>
  );
}
