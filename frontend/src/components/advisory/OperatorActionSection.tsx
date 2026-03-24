/**
 * OperatorActionSection: Command display
 */

import type { BmsExecutionGuide } from '@/lib/decisionSurface'

interface OperatorActionSectionProps {
  bmsGuide: BmsExecutionGuide | null
}

export function OperatorActionSection({ bmsGuide }: OperatorActionSectionProps) {
  return (
    <div className="rounded-lg border border-gray-200 dark:border-gray-700 overflow-hidden">
      <div className="px-4 py-3 bg-gray-50 dark:bg-gray-900 border-b border-gray-200 dark:border-gray-700">
        <p className="text-sm font-semibold text-gray-700 dark:text-gray-300 uppercase tracking-wider">
          Operator Action
        </p>
      </div>
      <div className="px-4 py-4">
        <div className="rounded bg-gray-100 dark:bg-gray-800 p-3 border border-gray-300 dark:border-gray-600">
          <p className="text-sm font-mono text-gray-900 dark:text-white leading-relaxed">
            {bmsGuide?.command || 'No command text available.'}
          </p>
        </div>
        {bmsGuide?.assetId && (
          <div className="mt-2 text-xs text-gray-600 dark:text-gray-400">
            <span className="font-semibold">Equipment:</span>{' '}
            <span className="font-mono text-blue-600 dark:text-blue-400">{bmsGuide.assetId}</span>
          </div>
        )}
      </div>
    </div>
  )
}
