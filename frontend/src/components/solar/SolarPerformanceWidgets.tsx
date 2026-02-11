/**
 * Solar Performance Widgets
 *
 * Displays performance metrics with peer comparison:
 * - System efficiency % vs peer average (green/red indicator)
 * - String health bar chart (green >90%, yellow 75-90%, red <75%)
 * - Capacity factor trending (24h, 7d, 30d)
 * - Soiling loss % with degradation trend
 *
 * Auto-refreshes every 30 seconds via React Query
 */

import { TrendingUp, TrendingDown, HelpCircle, AlertCircle, RefreshCw } from 'lucide-react';
import type { PerformanceSummary } from '@/lib/api/solar';
import { useSolarPerformance } from '@/hooks/useSolarDashboard';

interface SolarPerformanceWidgetsProps {
  siteId: string;
}

/**
 * Skeleton screen for loading state
 */
function PerformanceSkeleton() {
  return (
    <div className="space-y-4">
      {[...Array(4)].map((_, i) => (
        <div
          key={i}
          className="h-24 bg-gray-200 dark:bg-gray-700 rounded animate-pulse"
        />
      ))}
    </div>
  );
}

/**
 * Error state component
 */
function PerformanceError({
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
        {error?.message || 'Failed to load performance metrics'}
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
 * Trend indicator component
 */
function TrendIndicator({
  trend,
  isImproving = true,
}: {
  trend: 'improving' | 'stable' | 'declining';
  isImproving?: boolean;
}) {
  const icons = {
    improving: <TrendingUp className="h-4 w-4 text-green-500" />,
    stable: <div className="h-4 w-4 text-gray-400">—</div>,
    declining: <TrendingDown className="h-4 w-4 text-red-500" />,
  };

  return (
    <div className="flex items-center gap-1">
      {icons[trend]}
      <span className="text-xs font-semibold text-gray-600 dark:text-gray-400 capitalize">
        {trend}
      </span>
    </div>
  );
}

/**
 * String health bar component
 */
function StringHealthBar({
  stringId,
  health,
}: {
  stringId: string;
  health: number;
}) {
  let bgColor = 'bg-green-500';
  if (health < 75) bgColor = 'bg-red-500';
  else if (health < 90) bgColor = 'bg-yellow-500';

  return (
    <div className="mb-2">
      <div className="flex justify-between items-center mb-1">
        <span className="text-xs font-semibold text-gray-700 dark:text-gray-300">
          {stringId}
        </span>
        <span className="text-xs font-semibold text-gray-600 dark:text-gray-400">
          {health.toFixed(1)}%
        </span>
      </div>
      <div className="w-full bg-gray-200 dark:bg-gray-700 rounded-full h-2">
        <div
          className={`${bgColor} h-2 rounded-full transition-all`}
          style={{ width: `${Math.min(health, 100)}%` }}
        />
      </div>
    </div>
  );
}

/**
 * Help tooltip component
 */
function HelpTooltip({ text }: { text: string }) {
  return (
    <div className="relative group">
      <HelpCircle className="h-4 w-4 text-gray-400 cursor-help" />
      <div className="absolute bottom-full left-1/2 transform -translate-x-1/2 mb-2 w-48 p-2 bg-gray-900 dark:bg-gray-950 text-white text-xs rounded opacity-0 group-hover:opacity-100 pointer-events-none transition whitespace-normal">
        {text}
        <div className="absolute top-full left-1/2 transform -translate-x-1/2 w-2 h-2 bg-gray-900 dark:bg-gray-950" />
      </div>
    </div>
  );
}

export function SolarPerformanceWidgets({ siteId }: SolarPerformanceWidgetsProps) {
  const { data, isLoading, error, refetch } = useSolarPerformance(siteId);

  if (isLoading) {
    return (
      <div className="p-6 bg-white dark:bg-gray-900 rounded-lg border border-gray-200 dark:border-gray-700">
        <PerformanceSkeleton />
      </div>
    );
  }

  if (error || !data) {
    return (
      <div className="p-6 bg-white dark:bg-gray-900 rounded-lg border border-gray-200 dark:border-gray-700">
        <PerformanceError error={error} onRetry={() => refetch()} />
      </div>
    );
  }

  const efficiencyDiff = data.system_efficiency_percent - data.peer_average_efficiency_percent;
  const efficiencyColor =
    efficiencyDiff >= 0
      ? 'bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-200'
      : 'bg-red-100 text-red-800 dark:bg-red-900 dark:text-red-200';

  return (
    <div className="p-6 bg-white dark:bg-gray-900 rounded-lg border border-gray-200 dark:border-gray-700 space-y-6">
      {/* Header */}
      <div className="flex items-center gap-3">
        <TrendingUp className="h-5 w-5 text-blue-500" />
        <div>
          <h3 className="text-lg font-semibold text-gray-900 dark:text-white">
            Performance Metrics
          </h3>
          <p className="text-xs text-gray-500 dark:text-gray-400">
            System health and efficiency analysis
          </p>
        </div>
      </div>

      {/* Efficiency Comparison Card */}
      <div className="p-4 bg-blue-50 dark:bg-gray-800 rounded-lg border border-blue-200 dark:border-gray-700">
        <div className="flex items-center justify-between mb-3">
          <div className="flex items-center gap-2">
            <span className="text-xs font-semibold text-gray-600 dark:text-gray-400">
              System Efficiency
            </span>
            <HelpTooltip text="Percentage of received solar energy converted to usable electricity compared to industry averages" />
          </div>
          <TrendIndicator trend={data.efficiency_trend} />
        </div>

        <div className="grid grid-cols-2 gap-4 mb-3">
          <div>
            <div className="text-2xl font-bold text-gray-900 dark:text-white">
              {data.system_efficiency_percent.toFixed(1)}%
            </div>
            <div className="text-xs text-gray-600 dark:text-gray-400">System</div>
          </div>
          <div>
            <div className="text-2xl font-bold text-gray-600 dark:text-gray-300">
              {data.peer_average_efficiency_percent.toFixed(1)}%
            </div>
            <div className="text-xs text-gray-600 dark:text-gray-400">Peer Avg</div>
          </div>
        </div>

        <div className={`p-2 rounded text-center ${efficiencyColor}`}>
          <span className="text-sm font-semibold">
            {efficiencyDiff > 0 ? '+' : ''}{efficiencyDiff.toFixed(1)}% vs peers
          </span>
        </div>
      </div>

      {/* String Health Card */}
      <div className="p-4 bg-purple-50 dark:bg-gray-800 rounded-lg border border-purple-200 dark:border-gray-700">
        <div className="flex items-center gap-2 mb-3">
          <span className="text-xs font-semibold text-gray-600 dark:text-gray-400">
            String Health
          </span>
          <HelpTooltip text="Health percentage for each MPPT string (green >90%, yellow 75-90%, red <75%)" />
        </div>

        {data.string_health.length > 0 ? (
          <div className="space-y-2">
            {data.string_health.map((string) => (
              <StringHealthBar
                key={string.string_id}
                stringId={string.string_id}
                health={string.health_percent}
              />
            ))}
          </div>
        ) : (
          <div className="text-xs text-gray-500 dark:text-gray-400">No string data available</div>
        )}
      </div>

      {/* Capacity Factor Card */}
      <div className="p-4 bg-indigo-50 dark:bg-gray-800 rounded-lg border border-indigo-200 dark:border-gray-700">
        <div className="flex items-center gap-2 mb-3">
          <span className="text-xs font-semibold text-gray-600 dark:text-gray-400">
            Capacity Factor
          </span>
          <HelpTooltip text="Actual energy produced vs theoretical maximum capacity over time periods" />
        </div>

        <div className="grid grid-cols-3 gap-3">
          <div className="text-center">
            <div className="text-xl font-bold text-gray-900 dark:text-white">
              {data.capacity_factor_24h.toFixed(1)}%
            </div>
            <div className="text-xs text-gray-600 dark:text-gray-400">24h</div>
          </div>
          <div className="text-center">
            <div className="text-xl font-bold text-gray-900 dark:text-white">
              {data.capacity_factor_7d.toFixed(1)}%
            </div>
            <div className="text-xs text-gray-600 dark:text-gray-400">7d</div>
          </div>
          <div className="text-center">
            <div className="text-xl font-bold text-gray-900 dark:text-white">
              {data.capacity_factor_30d.toFixed(1)}%
            </div>
            <div className="text-xs text-gray-600 dark:text-gray-400">30d</div>
          </div>
        </div>
      </div>

      {/* Soiling Loss Card */}
      <div className="p-4 bg-orange-50 dark:bg-gray-800 rounded-lg border border-orange-200 dark:border-gray-700">
        <div className="flex items-center justify-between mb-3">
          <div className="flex items-center gap-2">
            <span className="text-xs font-semibold text-gray-600 dark:text-gray-400">
              Soiling Loss
            </span>
            <HelpTooltip text="Power loss due to dust, dirt, or other surface contamination reducing light transmission" />
          </div>
          <TrendIndicator
            trend={data.soiling_trend}
            isImproving={data.soiling_trend === 'improving'}
          />
        </div>

        <div className="grid grid-cols-2 gap-3">
          <div>
            <div className="text-2xl font-bold text-gray-900 dark:text-white">
              {data.soiling_loss_percent.toFixed(2)}%
            </div>
            <div className="text-xs text-gray-600 dark:text-gray-400">Current</div>
          </div>
          <div>
            <div className="text-2xl font-bold text-gray-900 dark:text-white">
              {data.soiling_annual_percent.toFixed(2)}%
            </div>
            <div className="text-xs text-gray-600 dark:text-gray-400">Annual</div>
          </div>
        </div>
      </div>

      {/* Degradation Card */}
      <div className="p-4 bg-red-50 dark:bg-gray-800 rounded-lg border border-red-200 dark:border-gray-700">
        <div className="flex items-center gap-2 mb-3">
          <span className="text-xs font-semibold text-gray-600 dark:text-gray-400">
            Degradation
          </span>
          <HelpTooltip text="Expected annual power loss due to panel aging and component wear" />
        </div>

        <div className="grid grid-cols-3 gap-3">
          <div className="text-center">
            <div className="text-xl font-bold text-gray-900 dark:text-white">
              {data.degradation_yearly_percent.toFixed(3)}%
            </div>
            <div className="text-xs text-gray-600 dark:text-gray-400">Yearly</div>
          </div>
          <div className="text-center">
            <div className="text-xl font-bold text-gray-900 dark:text-white">
              {data.degradation_annual_percent.toFixed(2)}%
            </div>
            <div className="text-xs text-gray-600 dark:text-gray-400">Annual</div>
          </div>
          <div className="text-center">
            <div
              className={`text-xs font-semibold px-2 py-1 rounded ${
                data.warranty_status === 'active'
                  ? 'bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-200'
                  : 'bg-yellow-100 text-yellow-800 dark:bg-yellow-900 dark:text-yellow-200'
              }`}
            >
              {data.warranty_status}
            </div>
          </div>
        </div>
      </div>

      {/* Auto-refresh indicator */}
      <div className="text-xs text-gray-500 dark:text-gray-400 flex items-center gap-2">
        <div className="h-2 w-2 bg-green-500 rounded-full animate-pulse" />
        Auto-refreshing every 30 seconds
      </div>
    </div>
  );
}

export default SolarPerformanceWidgets;
