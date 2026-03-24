/**
 * Decision Moment: Display pending decision and handle approval
 *
 * Shows a pending decision that requires user approval before control is executed.
 * Integrates ApproveButton for supervised execution workflow.
 *
 * Phase 170-01: Supervised Execution UI
 */

import { useState, useMemo } from 'react'
import { AlertCircle, Clock, Zap } from 'lucide-react'
import type { Decision } from '@/lib/api/decision'
import { Card } from './Card'
import { ApproveButton } from './ApproveButton'

interface DecisionMomentProps {
  decision: Decision
  site_id: string
  onApproved?: () => void
  onRejected?: () => void
  onFailed?: (error: string) => void
  disabled?: boolean
}

export function DecisionMoment({
  decision,
  site_id,
  onApproved,
  onRejected,
  onFailed,
  disabled = false,
}: DecisionMomentProps) {
  const [isRejecting, setIsRejecting] = useState(false)

  /**
   * Get color coding based on tier level
   */
  const getTierColor = () => {
    switch (decision.tier) {
      case 3: // CRITICAL
        return {
          bg: 'bg-red-50 dark:bg-red-950',
          border: 'border-red-200 dark:border-red-800',
          badge: 'bg-red-100 text-red-800 dark:bg-red-900 dark:text-red-100',
          icon: 'text-red-600 dark:text-red-400',
        }
      case 2: // HIGH
        return {
          bg: 'bg-orange-50 dark:bg-orange-950',
          border: 'border-orange-200 dark:border-orange-800',
          badge: 'bg-orange-100 text-orange-800 dark:bg-orange-900 dark:text-orange-100',
          icon: 'text-orange-600 dark:text-orange-400',
        }
      default: // MEDIUM
        return {
          bg: 'bg-yellow-50 dark:bg-yellow-950',
          border: 'border-yellow-200 dark:border-yellow-800',
          badge: 'bg-yellow-100 text-yellow-800 dark:bg-yellow-900 dark:text-yellow-100',
          icon: 'text-yellow-600 dark:text-yellow-400',
        }
    }
  }

  const tierColor = getTierColor()
  const tierLabel = ['', 'MEDIUM', 'HIGH', 'CRITICAL'][decision.tier] || `TIER-${decision.tier}`
  const cause = decision.cause ?? 'Device control action requires operator review before execution.'
  const impact = decision.impact ?? 'Outcome will be confirmed once the command is verified against live telemetry.'
  const tradeoff = decision.tradeoff ?? 'Prioritises safe execution over speed to prevent accidental or unsafe writes.'
  const timeMetricLabel = decision.time_metric_label ?? 'Time to Constraint Breach'
  const timeMetricValue = decision.time_metric_value ?? 'Pending'
  const actionSummary = decision.action_summary ?? `${decision.point} -> ${String(decision.command_value)}`
  const expectedOutcome = decision.expected_outcome ?? 'After approval, SENTINEL dispatches the command and waits for verification feedback.'

  // Calculate age at render time (memoized)
  // eslint-disable react-hooks/purity -- Date.now() is safe inside useMemo
  const ageSeconds = useMemo(
    () => {
      const createdAt = new Date(decision.created_at)
      // eslint-disable-next-line react-hooks/purity
      return Math.floor((Date.now() - createdAt.getTime()) / 1000)
    },
    [decision.created_at]
  )

  return (
    <Card
      className={`
        p-6 rounded-lg border-2
        ${tierColor.bg} ${tierColor.border}
        space-y-4
      `}
    >
      {/* Header: Title and Tier */}
      <div className="flex items-start justify-between">
        <div className="flex items-start gap-3">
          <AlertCircle className={`w-6 h-6 flex-shrink-0 mt-0.5 ${tierColor.icon}`} />
          <div>
            <h3 className="text-lg font-semibold text-gray-900 dark:text-white">
              Pending Approval
            </h3>
            <p className="text-sm text-gray-600 dark:text-gray-300 mt-0.5">
              Device control action requires human authorization
            </p>
          </div>
        </div>
        <span
          className={`
            px-3 py-1 rounded-full text-sm font-semibold whitespace-nowrap
            ${tierColor.badge}
          `}
        >
          {tierLabel}
        </span>
      </div>

      {/* Decision Details */}
      <div className="bg-white dark:bg-gray-900 rounded-lg p-4 space-y-3">
        <div className="grid gap-4 md:grid-cols-2">
          <div>
            <p className="text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase">
              Cause
            </p>
            <p className="text-sm text-gray-900 dark:text-white mt-1">
              {cause}
            </p>
          </div>

          <div>
            <p className="text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase">
              Impact
            </p>
            <p className="text-sm text-gray-900 dark:text-white mt-1">
              {impact}
            </p>
          </div>

          <div>
            <p className="text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase">
              Time
            </p>
            <p className="text-sm text-gray-900 dark:text-white mt-1">
              <span className="font-semibold">{timeMetricLabel}:</span> {timeMetricValue}
            </p>
          </div>

          <div>
            <p className="text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase">
              Action
            </p>
            <div className="flex items-start gap-2 mt-1">
              <Zap className="w-4 h-4 text-blue-600 dark:text-blue-400" />
              <p className="text-sm text-gray-900 dark:text-white">{actionSummary}</p>
            </div>
          </div>
        </div>

        {/* Divider */}
        <div className="border-t border-gray-200 dark:border-gray-700" />

        <div className="space-y-1">
          <p className="text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase">
            Trade-Off
          </p>
          <p className="text-sm text-gray-900 dark:text-white">
            {tradeoff}
          </p>
          <p className="text-sm text-gray-600 dark:text-gray-300">
            {expectedOutcome}
          </p>
        </div>

        <div className="flex items-center justify-between gap-4 text-sm text-gray-900 dark:text-white">
          <div>
            <span className="font-semibold">Age:</span>{' '}
            {ageSeconds < 60 ? `${ageSeconds}s ago` : `${Math.floor(ageSeconds / 60)}m ago`}
          </div>
          <div>
            <span className="font-semibold">Point:</span> <span className="font-mono">{decision.point}</span>
          </div>
          <div>
            <span className="font-semibold">Device:</span> <span className="font-mono">{decision.device_id}</span>
          </div>
        </div>

        {/* Decision ID (for audit) */}
        <div className="text-xs text-gray-500 dark:text-gray-400 space-y-1">
          <p>
            <strong>Decision ID:</strong> <span className="font-mono">{decision.id}</span>
          </p>
          <p>
            <strong>Site:</strong> <span className="font-mono">{decision.site_id}</span>
          </p>
        </div>
      </div>

      {/* Approval Action */}
      <div className="space-y-3">
        <div className="rounded-lg border border-orange-200 bg-orange-50 px-3 py-2 text-sm font-semibold text-orange-800 dark:border-orange-800 dark:bg-orange-950 dark:text-orange-100">
          [HOLD TO APPROVE]
        </div>
        <ApproveButton
          decision_id={decision.id}
          site_id={site_id}
          tier={decision.tier}
          device_id={decision.device_id}
          point={decision.point}
          command_value={decision.command_value}
          disabled={disabled || isRejecting}
          onApproved={() => {
            onApproved?.()
          }}
          onFailed={(error) => {
            onFailed?.(error)
          }}
          onTimeout={() => {
            onFailed?.('Verification timeout')
          }}
        />

        {/* Reject button */}
        <button
          onClick={() => {
            setIsRejecting(true)
            onRejected?.()
          }}
          disabled={disabled || isRejecting}
          className="w-full px-4 py-2 bg-red-100 dark:bg-red-900 text-red-800 dark:text-red-100 rounded-lg font-medium hover:bg-red-200 dark:hover:bg-red-800 transition-colors disabled:opacity-50"
        >
          Reject
        </button>
      </div>

      {/* Info: What happens next */}
      <div className="bg-blue-50 dark:bg-blue-950 border border-blue-200 dark:border-blue-800 rounded-lg p-3 text-xs text-blue-800 dark:text-blue-200 space-y-1">
        <div className="flex items-start gap-2">
          <Clock className="w-4 h-4 flex-shrink-0 mt-0.5" />
          <div>
            <p className="font-semibold">Supervised execution keeps instructions off this card.</p>
            <p className="mt-1">
              Operators see cause, impact, time metric, and trade-off here, then use hold-to-approve to trigger the verified control workflow.
            </p>
          </div>
        </div>
      </div>
    </Card>
  )
}
