/**
 * FuelTankCard - Visual fuel tank level gauge with status indicators.
 *
 * Shows level gauge (color-coded), temperature, days-to-empty countdown,
 * and last reading timestamp for a single fuel tank.
 */

import type { FuelTank } from '../../lib/api';
import { Badge } from '../Badge';

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

const badgeColorClass: Record<string, string> = {
  green: 'bg-green-500/15 text-[var(--color-sentinel-green)]',
  amber: 'bg-amber-500/15 text-[var(--color-sentinel-amber)]',
  red: 'bg-red-500/15 text-[var(--color-sentinel-red)]',
  gray: 'bg-gray-500/15 text-[var(--color-sentinel-text-secondary)]',
  blue: 'bg-blue-500/15 text-[var(--color-sentinel-blue)]',
};

export function FuelTankCard({ tank }: FuelTankCardProps) {
  const telemetry = tank.latest_telemetry;
  const levelPct = telemetry?.level_pct ?? 0;
  const levelLitres = telemetry?.level_litres ?? 0;
  const tempC = telemetry?.temperature_c;
  const daysToEmpty = telemetry?.days_to_empty;
  const receivedAt = telemetry?.received_at;
  const status = getStatusBadge(tank);

  return (
    <div
      className="p-4 rounded-lg"
      style={{
        background: 'var(--color-sentinel-bg-panel)',
        border: '1px solid var(--color-sentinel-border)',
      }}
    >
      <div className="flex justify-between items-start mb-3">
        <div>
          <p className="font-bold text-lg" style={{ color: 'var(--color-sentinel-text-primary)' }}>{tank.name}</p>
          <p className="text-xs" style={{ color: 'var(--color-sentinel-text-secondary)' }}>{tank.tank_id}</p>
        </div>
        <Badge className={badgeColorClass[status.color]}>{status.label}</Badge>
      </div>

      {/* Level Gauge */}
      <div className="mb-4">
        <div className="flex justify-between mb-1">
          <p className="text-sm" style={{ color: 'var(--color-sentinel-text-secondary)' }}>Level</p>
          <p className="text-sm font-semibold">
            <Badge className={badgeColorClass[getLevelBadgeColor(levelPct)]}>
              {levelPct.toFixed(1)}%
            </Badge>
          </p>
        </div>
        <div className="w-full bg-gray-200 rounded-full h-4 overflow-hidden">
          <div
            className={`h-full rounded-full transition-all duration-500 ${getLevelColor(levelPct)}`}
            style={{ width: `${Math.min(100, Math.max(0, levelPct))}%` }}
          />
        </div>
        <p className="text-xs mt-1" style={{ color: 'var(--color-sentinel-text-secondary)' }}>
          {levelLitres.toFixed(0)} / {tank.capacity_litres.toFixed(0)} litres
        </p>
      </div>

      {/* Stats Grid */}
      <div className="grid grid-cols-2 gap-3">
        <div
          className="rounded-lg p-2 text-center"
          style={{ background: 'var(--color-sentinel-bg-secondary)' }}
        >
          <p className="text-2xl font-bold" style={{ color: 'var(--color-sentinel-text-primary)' }}>
            {daysToEmpty != null ? daysToEmpty.toFixed(0) : '--'}
          </p>
          <p className="text-xs" style={{ color: 'var(--color-sentinel-text-secondary)' }}>
            days remaining
          </p>
        </div>

        <div
          className="rounded-lg p-2 text-center"
          style={{ background: 'var(--color-sentinel-bg-secondary)' }}
        >
          <p className="text-2xl font-bold" style={{ color: 'var(--color-sentinel-text-primary)' }}>
            {tempC != null ? `${tempC.toFixed(1)}` : '--'}
          </p>
          <p className="text-xs" style={{ color: 'var(--color-sentinel-text-secondary)' }}>
            {tempC != null ? 'temp C' : 'no temp data'}
          </p>
        </div>
      </div>

      {/* Footer */}
      <div
        className="flex justify-between mt-3 pt-2 border-t"
        style={{ borderColor: 'var(--color-sentinel-border)' }}
      >
        <p className="text-xs" style={{ color: 'var(--color-sentinel-text-disabled)' }}>
          {tank.fuel_type}
        </p>
        <p className="text-xs" style={{ color: 'var(--color-sentinel-text-disabled)' }}>
          {receivedAt ? new Date(receivedAt).toLocaleString() : 'No readings'}
        </p>
      </div>
    </div>
  );
}
