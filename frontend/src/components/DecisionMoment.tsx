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
          bg: 'rgba(var(--color-sentinel-red-rgb), 0.08)',
          border: 'rgba(var(--color-sentinel-red-rgb), 0.25)',
          badgeBg: 'rgba(var(--color-sentinel-red-rgb), 0.15)',
          badgeColor: 'var(--color-sentinel-red)',
          iconColor: 'var(--color-sentinel-red)',
          labelColor: 'var(--color-sentinel-red)',
        }
      case 2: // HIGH
        return {
          bg: 'rgba(var(--color-sentinel-amber-rgb), 0.08)',
          border: 'rgba(var(--color-sentinel-amber-rgb), 0.25)',
          badgeBg: 'rgba(var(--color-sentinel-amber-rgb), 0.15)',
          badgeColor: 'var(--color-sentinel-amber)',
          iconColor: 'var(--color-sentinel-amber)',
          labelColor: 'var(--color-sentinel-amber)',
        }
      default: // MEDIUM
        return {
          bg: 'rgba(var(--color-sentinel-amber-rgb), 0.05)',
          border: 'rgba(var(--color-sentinel-amber-rgb), 0.2)',
          badgeBg: 'rgba(var(--color-sentinel-amber-rgb), 0.1)',
          badgeColor: 'var(--color-sentinel-amber)',
          iconColor: 'var(--color-sentinel-amber)',
          labelColor: 'var(--color-sentinel-amber)',
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

  const panelBg = 'var(--color-sentinel-bg-secondary)'
  const labelStyle = { color: 'var(--color-sentinel-text-secondary)' }
  const valueStyle = { color: 'var(--color-sentinel-text-primary)' }

  return (
    <Card
      className="p-6 rounded-lg border-2 space-y-4"
      style={{ background: tierColor.bg, borderColor: tierColor.border }}
    >
      {/* Header: Title and Tier */}
      <div className="flex items-start justify-between">
        <div className="flex items-start gap-3">
          <AlertCircle className="w-6 h-6 flex-shrink-0 mt-0.5" style={{ color: tierColor.iconColor }} />
          <div>
            <h3 className="text-lg font-semibold" style={valueStyle}>
              Pending Approval
            </h3>
            <p className="text-sm mt-0.5" style={labelStyle}>
              Device control action requires human authorization
            </p>
          </div>
        </div>
        <span
          className="px-3 py-1 rounded-full text-sm font-semibold whitespace-nowrap"
          style={{ background: tierColor.badgeBg, color: tierColor.badgeColor }}
        >
          {tierLabel}
        </span>
      </div>

      {/* Decision Details */}
      <div className="rounded-lg p-4 space-y-3" style={{ background: panelBg }}>
        <div className="grid gap-4 md:grid-cols-2">
          <div>
            <p className="text-xs font-semibold uppercase" style={labelStyle}>Cause</p>
            <p className="text-sm mt-1" style={valueStyle}>{cause}</p>
          </div>

          <div>
            <p className="text-xs font-semibold uppercase" style={labelStyle}>Impact</p>
            <p className="text-sm mt-1" style={valueStyle}>{impact}</p>
          </div>

          <div>
            <p className="text-xs font-semibold uppercase" style={labelStyle}>Time</p>
            <p className="text-sm mt-1" style={valueStyle}>
              <span className="font-semibold">{timeMetricLabel}:</span> {timeMetricValue}
            </p>
          </div>

          <div>
            <p className="text-xs font-semibold uppercase" style={labelStyle}>Action</p>
            <div className="flex items-start gap-2 mt-1">
              <Zap className="w-4 h-4 mt-0.5" style={{ color: 'var(--color-sentinel-blue)' }} />
              <p className="text-sm" style={valueStyle}>{actionSummary}</p>
            </div>
          </div>
        </div>

        {/* Divider */}
        <div className="border-t" style={{ borderColor: 'var(--color-sentinel-border)' }} />

        <div className="space-y-1">
          <p className="text-xs font-semibold uppercase" style={labelStyle}>Trade-Off</p>
          <p className="text-sm" style={valueStyle}>{tradeoff}</p>
          <p className="text-sm" style={labelStyle}>{expectedOutcome}</p>
        </div>

        <div className="flex items-center justify-between gap-4 text-sm" style={valueStyle}>
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
        <div className="text-xs space-y-1" style={labelStyle}>
          <p><strong>Decision ID:</strong> <span className="font-mono">{decision.id}</span></p>
          <p><strong>Site:</strong> <span className="font-mono">{decision.site_id}</span></p>
        </div>
      </div>

      {/* Approval Action */}
      <div className="space-y-3">
        <div
          className="rounded-lg border px-3 py-2 text-sm font-semibold"
          style={{
            background: 'rgba(var(--color-sentinel-amber-rgb), 0.08)',
            borderColor: 'rgba(var(--color-sentinel-amber-rgb), 0.25)',
            color: 'var(--color-sentinel-amber)',
          }}
        >
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
          onApproved={() => { onApproved?.() }}
          onFailed={(error) => { onFailed?.(error) }}
          onTimeout={() => { onFailed?.('Verification timeout') }}
        />

        {/* Reject button */}
        <button
          onClick={() => { setIsRejecting(true); onRejected?.() }}
          disabled={disabled || isRejecting}
          className="w-full px-4 py-2 rounded-lg font-medium transition-colors disabled:opacity-50"
          style={{
            background: 'rgba(var(--color-sentinel-red-rgb), 0.1)',
            color: 'var(--color-sentinel-red)',
            border: '1px solid rgba(var(--color-sentinel-red-rgb), 0.25)',
          }}
        >
          Reject
        </button>
      </div>

      {/* Info: What happens next */}
      <div
        className="rounded-lg p-3 text-xs space-y-1"
        style={{
          background: 'rgba(var(--color-sentinel-blue-rgb, 59,130,246), 0.08)',
          border: '1px solid rgba(var(--color-sentinel-blue-rgb, 59,130,246), 0.2)',
          color: 'var(--color-sentinel-blue)',
        }}
      >
        <div className="flex items-start gap-2">
          <Clock className="w-4 h-4 flex-shrink-0 mt-0.5" />
          <div>
            <p className="font-semibold">Supervised execution keeps instructions off this card.</p>
            <p className="mt-1" style={{ color: 'var(--color-sentinel-text-secondary)' }}>
              Operators see cause, impact, time metric, and trade-off here, then use hold-to-approve to trigger the verified control workflow.
            </p>
          </div>
        </div>
      </div>
    </Card>
  )
}
