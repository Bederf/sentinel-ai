/**
 * SafetyNoticeSection: Equipment-specific safety and escalation guidance
 */

import { AlertTriangle } from 'lucide-react'

interface SafetyNoticeSectionProps {
  message: string
}

export function SafetyNoticeSection({ message }: SafetyNoticeSectionProps) {
  return (
    <div className="rounded-lg border border-amber-200 dark:border-amber-800 bg-amber-50 dark:bg-amber-900/20 overflow-hidden">
      <div className="px-4 py-3 bg-amber-100 dark:bg-amber-900/40 border-b border-amber-200 dark:border-amber-800">
        <div className="flex items-center gap-2">
          <AlertTriangle className="w-4 h-4 text-amber-700 dark:text-amber-400" />
          <p className="text-sm font-semibold text-amber-800 dark:text-amber-300 uppercase tracking-wider">
            Safety Notice
          </p>
        </div>
      </div>
      <div className="px-4 py-3">
        <p className="text-sm text-amber-900 dark:text-amber-200">{message}</p>
      </div>
    </div>
  )
}
