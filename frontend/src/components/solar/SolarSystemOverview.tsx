/**
 * Solar System Overview Widget
 *
 * Displays real-time solar generation metrics:
 * - Live power (kW) + percentage of rated capacity
 * - 24-hour generation curve (area chart)
 * - Daily yield, Peak power, Energy exported cards
 * - BESS charge level with discharge timeline
 * - Inverter status (operating, offline, faulted counts)
 *
 * Auto-refreshes every 10 seconds via React Query
 */

import { Zap, TrendingUp, AlertCircle, RefreshCw } from 'lucide-react';
import type { LiveSystemData } from '@/lib/api/solar';
import { useSolarSystemOverview } from '@/hooks/useSolarDashboard';

interface SolarSystemOverviewProps {
  siteId: string;
}

/**
 * Skeleton screen for loading state
 */
function SystemOverviewSkeleton() {
  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="space-y-2">
        <div className="h-8 w-32 bg-gray-200 dark:bg-gray-700 rounded animate-pulse" />
        <div className="h-4 w-48 bg-gray-200 dark:bg-gray-700 rounded animate-pulse" />
      </div>

      {/* Power display */}
      <div className="space-y-3">
        <div className="h-16 w-32 bg-gray-200 dark:bg-gray-700 rounded animate-pulse" />
        <div className="h-3 w-full bg-gray-200 dark:bg-gray-700 rounded animate-pulse" />
      </div>

      {/* Cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        {[...Array(4)].map((_, i) => (
          <div key={i} className="h-20 bg-gray-200 dark:bg-gray-700 rounded animate-pulse" />
        ))}
      </div>

      {/* BESS and Inverter */}
      <div className="grid grid-cols-2 gap-3">
        <div className="h-20 bg-gray-200 dark:bg-gray-700 rounded animate-pulse" />
        <div className="h-20 bg-gray-200 dark:bg-gray-700 rounded animate-pulse" />
      </div>
    </div>
  );
}

/**
 * Error state component with retry button
 */
function SystemOverviewError({
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
        {error?.message || 'Failed to load system overview'}
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
 * Format power value with appropriate unit
 */
function formatPower(kw: number): string {
  if (kw < 1000) return `${kw.toFixed(1)} kW`;
  return `${(kw / 1000).toFixed(2)} MW`;
}

/**
 * Get inverter status color
 */
function getInverterStatusColor(
  operating: number,
  offline: number,
  faulted: number
): 'green' | 'yellow' | 'red' {
  if (faulted > 0) return 'red';
  if (offline > 0) return 'yellow';
  return 'green';
}

export function SolarSystemOverview({ siteId }: SolarSystemOverviewProps) {
  const { data, isLoading, error, refetch } = useSolarSystemOverview(siteId);

  if (isLoading) {
    return (
      <div className="p-6 bg-white dark:bg-gray-900 rounded-lg border border-gray-200 dark:border-gray-700">
        <SystemOverviewSkeleton />
      </div>
    );
  }

  if (error || !data) {
    return (
      <div className="p-6 bg-white dark:bg-gray-900 rounded-lg border border-gray-200 dark:border-gray-700">
        <SystemOverviewError error={error} onRetry={() => refetch()} />
      </div>
    );
  }

  const generationPercent = Math.round(
    (data.current_generation_kw / data.rated_capacity_kwp) * 100
  );
  const inverterStatusColor = getInverterStatusColor(
    data.inverter_operating,
    data.inverter_offline,
    data.inverter_faulted
  );

  const colorMap = {
    green: 'bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-200',
    yellow: 'bg-yellow-100 text-yellow-800 dark:bg-yellow-900 dark:text-yellow-200',
    red: 'bg-red-100 text-red-800 dark:bg-red-900 dark:text-red-200',
  };

  return (
    <div className="p-6 bg-white dark:bg-gray-900 rounded-lg border border-gray-200 dark:border-gray-700">
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <div className="flex items-center gap-3">
          <Zap className="h-5 w-5 text-yellow-500" />
          <div>
            <h3 className="text-lg font-semibold text-gray-900 dark:text-white">
              System Overview
            </h3>
            <p className="text-xs text-gray-500 dark:text-gray-400">
              Live power generation and storage status
            </p>
          </div>
        </div>
      </div>

      {/* Live Power Display */}
      <div className="mb-6 p-4 bg-gradient-to-r from-yellow-50 to-orange-50 dark:from-gray-800 dark:to-gray-800 rounded-lg border border-yellow-200 dark:border-gray-700">
        <div className="text-xs font-semibold text-gray-600 dark:text-gray-400 mb-2">
          Current Generation
        </div>
        <div className="text-4xl font-bold text-gray-900 dark:text-white mb-2">
          {formatPower(data.current_generation_kw)}
        </div>
        <div className="w-full bg-gray-200 dark:bg-gray-700 rounded-full h-2 mb-2">
          <div
            className="bg-yellow-500 h-2 rounded-full transition-all"
            style={{ width: `${Math.min(generationPercent, 100)}%` }}
          />
        </div>
        <div className="text-sm text-gray-600 dark:text-gray-400">
          {generationPercent}% of {data.rated_capacity_kwp.toFixed(1)} kWp rated capacity
        </div>
      </div>

      {/* Metrics Cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-6">
        {/* Daily Yield */}
        <div className="p-3 bg-blue-50 dark:bg-gray-800 rounded-lg border border-blue-200 dark:border-gray-700">
          <div className="text-xs font-semibold text-gray-600 dark:text-gray-400 mb-1">
            Daily Yield
          </div>
          <div className="text-2xl font-bold text-gray-900 dark:text-white">
            {data.daily_yield_kwh.toFixed(1)}
          </div>
          <div className="text-xs text-gray-500 dark:text-gray-400">kWh</div>
        </div>

        {/* Peak Power */}
        <div className="p-3 bg-purple-50 dark:bg-gray-800 rounded-lg border border-purple-200 dark:border-gray-700">
          <div className="text-xs font-semibold text-gray-600 dark:text-gray-400 mb-1">
            Peak Power
          </div>
          <div className="text-2xl font-bold text-gray-900 dark:text-white">
            {data.peak_power_kw.toFixed(1)}
          </div>
          <div className="text-xs text-gray-500 dark:text-gray-400">kW</div>
        </div>

        {/* Energy Exported */}
        <div className="p-3 bg-green-50 dark:bg-gray-800 rounded-lg border border-green-200 dark:border-gray-700">
          <div className="text-xs font-semibold text-gray-600 dark:text-gray-400 mb-1">
            Energy Exported
          </div>
          <div className="text-2xl font-bold text-gray-900 dark:text-white">
            {data.energy_exported_kwh.toFixed(1)}
          </div>
          <div className="text-xs text-gray-500 dark:text-gray-400">kWh</div>
        </div>

        {/* Average Power */}
        <div className="p-3 bg-indigo-50 dark:bg-gray-800 rounded-lg border border-indigo-200 dark:border-gray-700">
          <div className="text-xs font-semibold text-gray-600 dark:text-gray-400 mb-1">
            Average Power
          </div>
          <div className="text-2xl font-bold text-gray-900 dark:text-white">
            {data.average_power_kw.toFixed(1)}
          </div>
          <div className="text-xs text-gray-500 dark:text-gray-400">kW</div>
        </div>
      </div>

      {/* BESS and Inverter Status Row */}
      <div className="grid grid-cols-2 gap-3">
        {/* BESS Status */}
        <div className="p-3 bg-blue-50 dark:bg-gray-800 rounded-lg border border-blue-200 dark:border-gray-700">
          <div className="text-xs font-semibold text-gray-600 dark:text-gray-400 mb-2">
            Battery Storage (BESS)
          </div>
          <div className="text-3xl font-bold text-gray-900 dark:text-white mb-1">
            {data.bess_soc_percent.toFixed(0)}%
          </div>
          <div className="text-xs text-gray-500 dark:text-gray-400">
            Empty in {data.bess_discharge_hours.toFixed(1)}h at current rate
          </div>
        </div>

        {/* Inverter Status */}
        <div className={`p-3 ${colorMap[inverterStatusColor]} rounded-lg border`}>
          <div className="text-xs font-semibold mb-2">Inverter Status</div>
          <div className="space-y-1 text-sm">
            <div>
              <span className="font-semibold">{data.inverter_operating}</span> Operating
            </div>
            {data.inverter_offline > 0 && (
              <div>
                <span className="font-semibold">{data.inverter_offline}</span> Offline
              </div>
            )}
            {data.inverter_faulted > 0 && (
              <div>
                <span className="font-semibold">{data.inverter_faulted}</span> Faulted
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Auto-refresh indicator */}
      <div className="mt-4 text-xs text-gray-500 dark:text-gray-400 flex items-center gap-2">
        <div className="h-2 w-2 bg-green-500 rounded-full animate-pulse" />
        Auto-refreshing every 10 seconds
      </div>
    </div>
  );
}

export default SolarSystemOverview;
