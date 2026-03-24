/**
 * VerificationSection: Verification steps and primary metric
 */

import type { BmsExecutionGuide } from '@/lib/decisionSurface'

interface VerificationSectionProps {
  bmsGuide: BmsExecutionGuide | null
  primaryMetric: string
}

export function VerificationSection({ bmsGuide, primaryMetric }: VerificationSectionProps) {
  return (
    <div className="rounded-lg border border-gray-200 dark:border-gray-700 overflow-hidden">
      <div className="px-4 py-3 bg-gray-50 dark:bg-gray-900 border-b border-gray-200 dark:border-gray-700">
        <p className="text-sm font-semibold text-gray-700 dark:text-gray-300 uppercase tracking-wider">
          Confirm Success
        </p>
      </div>
      <div className="px-4 py-4 space-y-3">
        <div className="text-sm text-gray-700 dark:text-gray-300">
          <p className="font-semibold text-gray-900 dark:text-white mb-1">Verification Steps:</p>
          <p className="leading-relaxed">
            {bmsGuide?.verification || 'Verification steps not available.'}
          </p>
        </div>

        <div className="rounded bg-blue-50 dark:bg-blue-900/20 border border-blue-200 dark:border-blue-800 p-3">
          <p className="text-xs text-blue-800 dark:text-blue-300">
            <span className="font-semibold">Primary Metric:</span> {primaryMetric}
          </p>
          <p className="text-xs text-blue-700 dark:text-blue-400 mt-1">
            Wait for telemetry refresh to confirm the metric improves after your action.
          </p>
        </div>
      </div>
    </div>
  )
}
