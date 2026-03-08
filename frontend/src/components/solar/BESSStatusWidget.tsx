/**
 * BESS Status Widget
 *
 * Displays battery energy storage system metrics:
 * - Power meter (kW) with charging/discharging indicator
 * - Battery charge curve (24-hour area chart)
 * - Temperature with thermal alert (red zone > 45°C)
 * - State of Health (SOH) % with degradation trend
 * - Cycle count and estimated remaining life
 * - Round-trip efficiency vs rated
 * - Energy reserve (kWh) and discharge hours
 *
 * Auto-refreshes every 15 seconds
 */

import { Battery, TrendingDown, AlertTriangle, AlertCircle, RefreshCw } from 'lucide-react';
import { useBESSStatus } from '@/hooks/useSolarDashboard';

interface BESSStatusWidgetProps {
  siteId: string;
}

/**
 * Skeleton screen for loading state
 */
function BESSStatusSkeleton() {
  return (
    <div className="space-y-4">
      {[...Array(5)].map((_, i) => (
        <div
          key={i}
          className="h-20 bg-gray-200 dark:bg-gray-700 rounded animate-pulse"
        />
      ))}
    </div>
  );
}

/**
 * Error state component
 */
function BESSStatusError({
  error,
  onRetry,
}: {
  error: Error | null;
  onRetry: () => void;
}) {
  return (
    <div className="flex flex-col items-center justify-center p-8 text-center">
      <AlertCircle className="h-8 w-8 text-red-500 mb-3" />
      <p className="text-sm text-gray-600 dark:text-gray-400 mb-4">
        {error?.message || 'Failed to load BESS status'}
      </p>
      <button
        onClick={onRetry}
        className="flex items-center gap-2 px-3 py-2 text-sm bg-blue-500 hover:bg-blue-600 text-white rounded transition"
      >
        <RefreshCw className="h-4 w-4" />
        Retry
      </button>
    </div>
  );
}

/**
 * Get power direction arrow
 */
function getPowerDirection(direction: 'charging' | 'discharging' | 'idle'): string {
  const arrows = {
    charging: '⬆️ Charging',
    discharging: '⬇️ Discharging',
    idle: '⏸️ Idle',
  };
  return arrows[direction];
}

/**
 * Simple area chart for battery curve
 */
function BatteryCurveChart({ data }: { data: Array<{ timestamp: string; charge_percent: number }> }) {
  if (data.length === 0) return null;

  const min = Math.min(...data.map((d) => d.charge_percent));
  const max = Math.max(...data.map((d) => d.charge_percent));
  const range = max - min || 1;
  const height = 60;

  const points = data.map((item, index) => {
    const x = (index / (data.length - 1)) * 100;
    const y = height - ((item.charge_percent - min) / range) * height;
    return `${x},${y}`;
  });

  return (
    <svg viewBox={`0 0 100 ${height}`} className="w-full h-16">
      <defs>
        <linearGradient id="batteryGradient" x1="0%" y1="0%" x2="0%" y2="100%">
          <stop offset="0%" stopColor="rgb(59, 130, 246)" stopOpacity="0.5" />
          <stop offset="100%" stopColor="rgb(59, 130, 246)" stopOpacity="0.1" />
        </linearGradient>
      </defs>
      {/* Area fill */}
      <polyline
        points={`0,${height} ${points.join(' ')} 100,${height}`}
        fill="url(#batteryGradient)"
      />
      {/* Line */}
      <polyline
        points={points.join(' ')}
        fill="none"
        stroke="rgb(59, 130, 246)"
        strokeWidth="2"
      />
    </svg>
  );
}

export function BESSStatusWidget({ siteId }: BESSStatusWidgetProps) {
  const { data, isLoading, error, refetch } = useBESSStatus(siteId);

  if (isLoading) {
    return (
      <div className="p-6 bg-white dark:bg-gray-900 rounded-lg border border-gray-200 dark:border-gray-700">
        <BESSStatusSkeleton />
      </div>
    );
  }

  if (error || !data) {
    return (
      <div className="p-6 bg-white dark:bg-gray-900 rounded-lg border border-gray-200 dark:border-gray-700">
        <BESSStatusError error={error} onRetry={() => refetch()} />
      </div>
    );
  }

  const isThermalAlert = data.temperature_c > data.thermal_limit_c;

  return (
    <div className="p-6 bg-white dark:bg-gray-900 rounded-lg border border-gray-200 dark:border-gray-700 space-y-6">
      {/* Header */}
      <div className="flex items-center gap-3">
        <Battery className="h-5 w-5 text-blue-500" />
        <div>
          <h3 className="text-lg font-semibold text-gray-900 dark:text-white">
            BESS Status
          </h3>
          <p className="text-xs text-gray-500 dark:text-gray-400">
            Battery energy storage system health and performance
          </p>
        </div>
      </div>

      {/* Power Meter Card */}
      <div className="p-4 bg-gradient-to-r from-blue-50 to-cyan-50 dark:from-gray-800 dark:to-gray-800 rounded-lg border border-blue-200 dark:border-gray-700">
        <div className="text-xs font-semibold text-gray-600 dark:text-gray-400 mb-2">
          Current Power
        </div>

        <div className="flex items-end justify-between mb-3">
          <div>
            <div className="text-4xl font-bold text-gray-900 dark:text-white">
              {Math.abs(data.current_power_kw).toFixed(1)}
            </div>
            <div className="text-xs text-gray-600 dark:text-gray-400">kW</div>
          </div>
          <div
            className={`px-3 py-2 rounded font-semibold text-sm ${
              data.power_direction === 'charging'
                ? 'bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-200'
                : data.power_direction === 'discharging'
                  ? 'bg-orange-100 text-orange-800 dark:bg-orange-900 dark:text-orange-200'
                  : 'bg-gray-100 text-gray-800 dark:bg-gray-700 dark:text-gray-200'
            }`}
          >
            {getPowerDirection(data.power_direction)}
          </div>
        </div>

        {/* Detailed power breakdown */}
        <div className="grid grid-cols-2 gap-2 text-sm">
          <div>
            <div className="text-gray-600 dark:text-gray-400 text-xs">Charge Power</div>
            <div className="font-semibold text-gray-900 dark:text-white">
              {data.charge_power_kw.toFixed(1)} kW
            </div>
          </div>
          <div>
            <div className="text-gray-600 dark:text-gray-400 text-xs">Discharge Power</div>
            <div className="font-semibold text-gray-900 dark:text-white">
              {data.discharge_power_kw.toFixed(1)} kW
            </div>
          </div>
        </div>
      </div>

      {/* Battery Charge Curve */}
      <div className="p-4 bg-purple-50 dark:bg-gray-800 rounded-lg border border-purple-200 dark:border-gray-700">
        <div className="flex items-center justify-between mb-3">
          <div className="text-xs font-semibold text-gray-600 dark:text-gray-400">
            24-Hour Charge Curve
          </div>
          <div className="text-2xl font-bold text-gray-900 dark:text-white">
            {data.battery_charge_percent.toFixed(0)}%
          </div>
        </div>

        {/* Charge bar */}
        <div className="w-full bg-gray-200 dark:bg-gray-700 rounded-full h-3 mb-3">
          <div
            className="bg-blue-500 h-3 rounded-full transition-all"
            style={{ width: `${Math.min(data.battery_charge_percent, 100)}%` }}
          />
        </div>

        {/* Chart */}
        {data.battery_curve_24h.length > 0 && (
          <BatteryCurveChart data={data.battery_curve_24h} />
        )}
      </div>

      {/* Temperature Card */}
      <div
        className={`p-4 rounded-lg border ${
          isThermalAlert
            ? 'bg-red-50 border-red-200 dark:bg-red-900/20 dark:border-red-700'
            : 'bg-green-50 border-green-200 dark:bg-green-900/20 dark:border-green-700'
        }`}
      >
        <div className="flex items-center justify-between mb-2">
          <span className="text-xs font-semibold text-gray-600 dark:text-gray-400">
            Temperature
          </span>
          {isThermalAlert && <AlertTriangle className="h-4 w-4 text-red-500" />}
        </div>

        <div className="text-3xl font-bold text-gray-900 dark:text-white mb-2">
          {data.temperature_c.toFixed(1)}°C
        </div>

        {/* Thermal limit indicator */}
        <div className="text-xs text-gray-600 dark:text-gray-400">
          Thermal limit: {data.thermal_limit_c}°C
        </div>

        {/* Temperature bar with limit zone */}
        <div className="mt-2">
          <div className="w-full bg-gray-200 dark:bg-gray-700 rounded-full h-2">
            <div
              className={`h-2 rounded-full transition-all ${
                isThermalAlert ? 'bg-red-500' : 'bg-green-500'
              }`}
              style={{
                width: `${Math.min((data.temperature_c / (data.thermal_limit_c + 10)) * 100, 100)}%`,
              }}
            />
          </div>
        </div>
      </div>

      {/* State of Health Card */}
      <div className="p-4 bg-indigo-50 dark:bg-gray-800 rounded-lg border border-indigo-200 dark:border-gray-700">
        <div className="flex items-center justify-between mb-2">
          <span className="text-xs font-semibold text-gray-600 dark:text-gray-400">
            State of Health (SOH)
          </span>
          {data.soh_trend === 'declining' && (
            <TrendingDown className="h-4 w-4 text-red-500" />
          )}
        </div>

        <div className="text-3xl font-bold text-gray-900 dark:text-white mb-2">
          {data.state_of_health_percent.toFixed(1)}%
        </div>

        {/* SOH bar */}
        <div className="w-full bg-gray-200 dark:bg-gray-700 rounded-full h-2 mb-2">
          <div
            className="bg-indigo-500 h-2 rounded-full transition-all"
            style={{ width: `${Math.min(data.state_of_health_percent, 100)}%` }}
          />
        </div>

        <div className="text-xs text-gray-600 dark:text-gray-400">
          Trend: {data.soh_trend.charAt(0).toUpperCase() + data.soh_trend.slice(1)}
        </div>
      </div>

      {/* Cycle Count & Life Remaining Card */}
      <div className="p-4 bg-yellow-50 dark:bg-gray-800 rounded-lg border border-yellow-200 dark:border-gray-700">
        <div className="text-xs font-semibold text-gray-600 dark:text-gray-400 mb-3">
          Usage & Life
        </div>

        <div className="grid grid-cols-3 gap-3">
          <div>
            <div className="text-2xl font-bold text-gray-900 dark:text-white">
              {data.cycle_count.toLocaleString()}
            </div>
            <div className="text-xs text-gray-600 dark:text-gray-400">Cycles</div>
          </div>
          <div>
            <div className="text-2xl font-bold text-gray-900 dark:text-white">
              {data.estimated_remaining_years.toFixed(1)}
            </div>
            <div className="text-xs text-gray-600 dark:text-gray-400">Years</div>
          </div>
          <div>
            <div className="text-2xl font-bold text-gray-900 dark:text-white">
              {data.suitable_for_hours.toFixed(0)}h
            </div>
            <div className="text-xs text-gray-600 dark:text-gray-400">Discharge</div>
          </div>
        </div>
      </div>

      {/* Efficiency Card */}
      <div className="p-4 bg-teal-50 dark:bg-gray-800 rounded-lg border border-teal-200 dark:border-gray-700">
        <div className="text-xs font-semibold text-gray-600 dark:text-gray-400 mb-3">
          Round-Trip Efficiency
        </div>

        <div className="grid grid-cols-2 gap-4">
          <div>
            <div className="text-2xl font-bold text-gray-900 dark:text-white">
              {data.efficiency_roundtrip_percent.toFixed(1)}%
            </div>
            <div className="text-xs text-gray-600 dark:text-gray-400">Actual</div>
          </div>
          <div>
            <div className="text-2xl font-bold text-gray-900 dark:text-white">
              {data.efficiency_rated_percent.toFixed(1)}%
            </div>
            <div className="text-xs text-gray-600 dark:text-gray-400">Rated</div>
          </div>
        </div>

        {/* Efficiency bar */}
        <div className="mt-3 w-full bg-gray-200 dark:bg-gray-700 rounded-full h-2">
          <div
            className="bg-teal-500 h-2 rounded-full transition-all"
            style={{
              width: `${Math.min(
                (data.efficiency_roundtrip_percent / data.efficiency_rated_percent) * 100,
                100
              )}%`,
            }}
          />
        </div>
      </div>

      {/* Energy Reserve Card */}
      <div className="p-4 bg-orange-50 dark:bg-gray-800 rounded-lg border border-orange-200 dark:border-gray-700">
        <div className="text-xs font-semibold text-gray-600 dark:text-gray-400 mb-2">
          Available Energy Reserve
        </div>

        <div className="grid grid-cols-2 gap-4">
          <div>
            <div className="text-2xl font-bold text-gray-900 dark:text-white">
              {data.energy_reserve_kwh.toFixed(1)}
            </div>
            <div className="text-xs text-gray-600 dark:text-gray-400">kWh</div>
          </div>
          <div>
            <div className="text-2xl font-bold text-gray-900 dark:text-white">
              {data.suitable_for_hours.toFixed(1)}
            </div>
            <div className="text-xs text-gray-600 dark:text-gray-400">
              hours @ rated load
            </div>
          </div>
        </div>
      </div>

      {/* Auto-refresh indicator */}
      <div className="text-xs text-gray-500 dark:text-gray-400 flex items-center gap-2">
        <div className="h-2 w-2 bg-green-500 rounded-full animate-pulse" />
        Auto-refreshing every 15 seconds
      </div>
    </div>
  );
}

export default BESSStatusWidget;
