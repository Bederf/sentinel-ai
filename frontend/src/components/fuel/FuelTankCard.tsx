/**
 * FuelTankCard - Visual fuel tank level gauge with status indicators.
 *
 * Shows level gauge (color-coded), temperature, days-to-empty countdown,
 * and last reading timestamp for a single fuel tank.
 */

import { Card, Text, Badge, Flex } from '@tremor/react';
import type { FuelTank } from '../../lib/api';

interface FuelTankCardProps {
  tank: FuelTank;
}

function getLevelColor(pct: number): string {
  if (pct > 30) return 'bg-emerald-500';
  if (pct > 15) return 'bg-amber-500';
  return 'bg-red-500';
}

function getLevelBadgeColor(pct: number): string {
  if (pct > 30) return 'green';
  if (pct > 15) return 'amber';
  return 'red';
}

function getStatusBadge(tank: FuelTank): { label: string; color: string } {
  const telemetry = tank.latest_telemetry;
  if (!telemetry) return { label: 'No Data', color: 'gray' };
  const pct = telemetry.level_pct;
  if (pct <= tank.low_fuel_pct_2) return { label: 'Critical', color: 'red' };
  if (pct <= tank.low_fuel_pct_1) return { label: 'Warning', color: 'amber' };
  return { label: 'Normal', color: 'green' };
}

export function FuelTankCard({ tank }: FuelTankCardProps) {
  const telemetry = tank.latest_telemetry;
  const levelPct = telemetry?.level_pct ?? 0;
  const levelLitres = telemetry?.level_litres ?? 0;
  const tempC = telemetry?.temperature_c;
  const daysToEmpty = telemetry?.days_to_empty;
  const receivedAt = telemetry?.received_at;
  const status = getStatusBadge(tank);

  return (
    <Card className="p-4">
      <Flex justifyContent="between" alignItems="start" className="mb-3">
        <div>
          <Text className="font-bold text-lg">{tank.name}</Text>
          <Text className="text-xs text-gray-500">{tank.tank_id}</Text>
        </div>
        <Badge color={status.color}>{status.label}</Badge>
      </Flex>

      {/* Level Gauge */}
      <div className="mb-4">
        <Flex justifyContent="between" className="mb-1">
          <Text className="text-sm text-gray-600">Level</Text>
          <Text className="text-sm font-semibold">
            <Badge color={getLevelBadgeColor(levelPct)} size="sm">
              {levelPct.toFixed(1)}%
            </Badge>
          </Text>
        </Flex>
        <div className="w-full bg-gray-200 rounded-full h-4 overflow-hidden">
          <div
            className={`h-full rounded-full transition-all duration-500 ${getLevelColor(levelPct)}`}
            style={{ width: `${Math.min(100, Math.max(0, levelPct))}%` }}
          />
        </div>
        <Text className="text-xs text-gray-500 mt-1">
          {levelLitres.toFixed(0)} / {tank.capacity_litres.toFixed(0)} litres
        </Text>
      </div>

      {/* Stats Grid */}
      <div className="grid grid-cols-2 gap-3">
        {/* Days to Empty */}
        <div className="bg-gray-50 rounded-lg p-2 text-center">
          <Text className="text-2xl font-bold text-gray-800">
            {daysToEmpty != null ? daysToEmpty.toFixed(0) : '--'}
          </Text>
          <Text className="text-xs text-gray-500">days remaining</Text>
        </div>

        {/* Temperature */}
        <div className="bg-gray-50 rounded-lg p-2 text-center">
          <Text className="text-2xl font-bold text-gray-800">
            {tempC != null ? `${tempC.toFixed(1)}` : '--'}
          </Text>
          <Text className="text-xs text-gray-500">
            {tempC != null ? 'temp C' : 'no temp data'}
          </Text>
        </div>
      </div>

      {/* Fuel Type + Last Reading */}
      <Flex justifyContent="between" className="mt-3 pt-2 border-t border-gray-100">
        <Text className="text-xs text-gray-400">{tank.fuel_type}</Text>
        <Text className="text-xs text-gray-400">
          {receivedAt ? new Date(receivedAt).toLocaleString() : 'No readings'}
        </Text>
      </Flex>
    </Card>
  );
}
