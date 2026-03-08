/**
 * Grid Compliance Widget
 *
 * Displays grid integration metrics:
 * - Grid frequency with safe band overlay (Hz, green/yellow/red)
 * - Frequency trend chart (last 1 hour)
 * - Load shedding stage indicator (1-8)
 * - Compliance violations (count, expandable list)
 * - Auto-response status (curtailment %, standby, droop)
 * - Compliance badge (green/red)
 *
 * Auto-refreshes every 5 seconds (grid parameters critical)
 */

import { Zap, AlertTriangle, CheckCircle, AlertCircle, RefreshCw, ChevronDown } from 'lucide-react';
import { useState } from 'react';
// GridComplianceStatus type available from '@/lib/api/solar' if needed
import { useGridCompliance } from '@/hooks/useSolarDashboard';

interface GridComplianceWidgetProps {
  siteId: string;
}

/**
 * Skeleton screen for loading state
 */
function GridComplianceSkeleton() {
  return (
    <div className="space-y-4">
      {[...Array(5)].map((_, i) => (
        <div
          key={i}
          className="h-16 bg-gray-200 dark:bg-gray-700 rounded animate-pulse"
        />
      ))}
    </div>
  );
}

/**
 * Error state component
 */
function GridComplianceError({
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
        {error?.message || 'Failed to load grid compliance status'}
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
 * Get frequency band status color
 */
function getFrequencyColor(status: 'green' | 'yellow' | 'red'): string {
  const colorMap = {
    green: 'bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-200',
    yellow: 'bg-yellow-100 text-yellow-800 dark:bg-yellow-900 dark:text-yellow-200',
    red: 'bg-red-100 text-red-800 dark:bg-red-900 dark:text-red-200',
  };
  return colorMap[status];
}

/**
 * Get load shedding color based on stage
 */
function getLoadSheddingColor(stage: number): string {
  if (stage <= 2) return 'bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-200';
  if (stage <= 5) return 'bg-yellow-100 text-yellow-800 dark:bg-yellow-900 dark:text-yellow-200';
  return 'bg-red-100 text-red-800 dark:bg-red-900 dark:text-red-200';
}

/**
 * Frequency trend sparkline
 */
function FrequencyTrendChart({ data }: { data: number[] }) {
  if (data.length === 0) return null;

  const min = Math.min(...data);
  const max = Math.max(...data);
  const range = max - min || 1;
  const height = 40;

  const points = data.map((value, index) => {
    const x = (index / (data.length - 1)) * 100;
    const y = height - ((value - min) / range) * height;
    return `${x},${y}`;
  });

  return (
    <svg viewBox={`0 0 100 ${height}`} className="w-full h-12">
      <polyline
        points={points.join(' ')}
        fill="none"
        stroke="currentColor"
        strokeWidth="1"
        className="text-blue-500"
      />
      <polyline
        points={points.join(' ')}
        fill="url(#gradient)"
        className="opacity-20"
      />
      <defs>
        <linearGradient id="gradient" x1="0%" y1="0%" x2="0%" y2="100%">
          <stop offset="0%" stopColor="currentColor" className="text-blue-500" />
          <stop offset="100%" stopColor="currentColor" className="text-blue-500" />
        </linearGradient>
      </defs>
    </svg>
  );
}

export function GridComplianceWidget({ siteId }: GridComplianceWidgetProps) {
  const { data, isLoading, error, refetch } = useGridCompliance(siteId);
  const [showViolations, setShowViolations] = useState(false);

  if (isLoading) {
    return (
      <div className="p-6 bg-white dark:bg-gray-900 rounded-lg border border-gray-200 dark:border-gray-700">
        <GridComplianceSkeleton />
      </div>
    );
  }

  if (error || !data) {
    return (
      <div className="p-6 bg-white dark:bg-gray-900 rounded-lg border border-gray-200 dark:border-gray-700">
        <GridComplianceError error={error} onRetry={() => refetch()} />
      </div>
    );
  }

  const frequencyInBand = data.frequency_safe;

  return (
    <div className="p-6 bg-white dark:bg-gray-900 rounded-lg border border-gray-200 dark:border-gray-700 space-y-6">
      {/* Header */}
      <div className="flex items-center gap-3">
        <Zap className="h-5 w-5 text-blue-500" />
        <div>
          <h3 className="text-lg font-semibold text-gray-900 dark:text-white">
            Grid Compliance
          </h3>
          <p className="text-xs text-gray-500 dark:text-gray-400">
            Real-time grid parameters and compliance status
          </p>
        </div>
      </div>

      {/* Frequency Display Card */}
      <div className={`p-4 rounded-lg border ${getFrequencyColor(data.frequency_band_status)}`}>
        <div className="flex items-center justify-between mb-2">
          <span className="text-xs font-semibold">Grid Frequency</span>
          {frequencyInBand ? (
            <CheckCircle className="h-4 w-4" />
          ) : (
            <AlertTriangle className="h-4 w-4" />
          )}
        </div>

        <div className="text-3xl font-bold mb-2">{data.grid_frequency_hz.toFixed(2)} Hz</div>

        {/* Safe band indicator */}
        <div className="text-xs font-semibold mb-3">
          {data.frequency_band_status === 'green' && 'Safe band: 49.5 - 50.5 Hz'}
          {data.frequency_band_status === 'yellow' && 'Warning band: 48 - 51 Hz'}
          {data.frequency_band_status === 'red' && 'Critical: Outside 48 - 51 Hz'}
        </div>

        {/* Frequency trend chart */}
        {data.frequency_trend_1h.length > 0 && (
          <div className="mt-3">
            <div className="text-xs font-semibold mb-1">1-hour trend</div>
            <FrequencyTrendChart data={data.frequency_trend_1h} />
          </div>
        )}
      </div>

      {/* Load Shedding Stage Card */}
      <div
        className={`p-4 rounded-lg border ${getLoadSheddingColor(data.load_shedding_stage)}`}
      >
        <div className="flex items-center justify-between">
          <span className="text-xs font-semibold">Load Shedding Stage</span>
          {data.load_shedding_active && <AlertTriangle className="h-4 w-4" />}
        </div>

        <div className="text-4xl font-bold mt-2">{data.load_shedding_stage}/8</div>

        <div className="text-xs mt-2">
          {data.load_shedding_stage === 0
            ? 'No load shedding'
            : `Stage ${data.load_shedding_stage} active - ${data.load_shedding_active ? 'Currently shedding' : 'Standby'}`}
        </div>

        {/* Stage progression bar */}
        <div className="mt-3">
          <div className="flex gap-1">
            {[...Array(8)].map((_, i) => (
              <div
                key={i}
                className={`flex-1 h-2 rounded ${
                  i < data.load_shedding_stage
                    ? 'bg-red-500'
                    : 'bg-gray-300 dark:bg-gray-700'
                }`}
              />
            ))}
          </div>
        </div>
      </div>

      {/* Auto-Response Status Card */}
      <div className="p-4 bg-purple-50 dark:bg-gray-800 rounded-lg border border-purple-200 dark:border-gray-700">
        <div className="text-xs font-semibold text-gray-600 dark:text-gray-400 mb-3">
          Auto-Response Status
        </div>

        <div className="grid grid-cols-3 gap-2 text-sm">
          <div>
            <div className="font-semibold text-gray-900 dark:text-white">
              {data.auto_response_curtailment_percent.toFixed(0)}%
            </div>
            <div className="text-xs text-gray-600 dark:text-gray-400">Curtailment</div>
          </div>
          <div>
            <div className="font-semibold text-gray-900 dark:text-white">
              {data.auto_response_standby ? 'ON' : 'OFF'}
            </div>
            <div className="text-xs text-gray-600 dark:text-gray-400">Standby Mode</div>
          </div>
          <div>
            <div className="font-semibold text-gray-900 dark:text-white">
              {data.auto_response_droop.toFixed(2)}
            </div>
            <div className="text-xs text-gray-600 dark:text-gray-400">Droop</div>
          </div>
        </div>
      </div>

      {/* Violations Section */}
      <div className="p-4 bg-red-50 dark:bg-gray-800 rounded-lg border border-red-200 dark:border-gray-700">
        <button
          onClick={() => setShowViolations(!showViolations)}
          className="w-full flex items-center justify-between text-left"
        >
          <div className="flex items-center gap-2">
            <AlertTriangle className="h-4 w-4" />
            <span className="text-xs font-semibold text-gray-600 dark:text-gray-400">
              Violations
            </span>
            <span className="ml-1 text-sm font-bold text-gray-900 dark:text-white">
              {data.violations_count}
            </span>
          </div>
          <ChevronDown
            className={`h-4 w-4 transition-transform ${showViolations ? 'rotate-180' : ''}`}
          />
        </button>

        {showViolations && data.violations_count > 0 && (
          <div className="mt-3 space-y-2 max-h-48 overflow-y-auto">
            {data.violations.map((violation, i) => (
              <div
                key={i}
                className="p-2 bg-white dark:bg-gray-900 rounded border border-red-200 dark:border-gray-700 text-xs"
              >
                <div className="font-semibold text-gray-900 dark:text-white">
                  {violation.parameter}
                </div>
                <div className="text-gray-600 dark:text-gray-400">{violation.status}</div>
                <div className="text-gray-500 dark:text-gray-500 text-xs mt-1">
                  {new Date(violation.timestamp).toLocaleTimeString()}
                </div>
              </div>
            ))}
          </div>
        )}

        {data.violations_count === 0 && (
          <div className="mt-2 text-xs text-gray-600 dark:text-gray-400">No violations</div>
        )}
      </div>

      {/* Compliance Badge */}
      <div className="flex items-center justify-between p-4 bg-gray-50 dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700">
        <div>
          <div className="text-xs font-semibold text-gray-600 dark:text-gray-400 mb-1">
            Compliance Status
          </div>
          <div className="text-sm text-gray-600 dark:text-gray-400">
            Last check: {new Date(data.last_check_time).toLocaleTimeString()}
          </div>
        </div>
        <div
          className={`px-3 py-2 rounded font-semibold flex items-center gap-2 ${
            data.compliance_badge === 'compliant'
              ? 'bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-200'
              : 'bg-red-100 text-red-800 dark:bg-red-900 dark:text-red-200'
          }`}
        >
          {data.compliance_badge === 'compliant' ? (
            <CheckCircle className="h-4 w-4" />
          ) : (
            <AlertTriangle className="h-4 w-4" />
          )}
          <span className="text-sm font-semibold capitalize">{data.compliance_badge}</span>
        </div>
      </div>

      {/* Auto-refresh indicator */}
      <div className="text-xs text-gray-500 dark:text-gray-400 flex items-center gap-2">
        <div className="h-2 w-2 bg-green-500 rounded-full animate-pulse" />
        Auto-refreshing every 5 seconds
      </div>
    </div>
  );
}

export default GridComplianceWidget;
