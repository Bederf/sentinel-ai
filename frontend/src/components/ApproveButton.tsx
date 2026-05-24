/**
 * Hold-to-Approve Button for Supervised Control Execution
 *
 * User must hold the button for 3 seconds to confirm approval.
 * Shows progress indicator during hold time.
 * Prevents accidental execution through haptic feedback (if available).
 *
 * Phase 170-01: Supervised Execution UI
 */

import { useState, useRef, useCallback } from 'react'
import { Check, X, Clock } from 'lucide-react'
import { useDecisionExecution } from '@/hooks/useDecisionExecution'

interface ApproveButtonProps {
  decision_id: string
  site_id: string
  tier: number
  device_id: string
  point: string
  command_value: number | boolean | string
  disabled?: boolean
  onApproved?: () => void
  onFailed?: (error: string) => void
  onTimeout?: () => void
}

const HOLD_DURATION_MS = 3000

export function ApproveButton({
  decision_id,
  site_id,
  tier,
  device_id,
  point,
  command_value,
  disabled = false,
  onApproved,
  onFailed,
  onTimeout,
}: ApproveButtonProps) {
  const [isHolding, setIsHolding] = useState(false)
  const [holdProgress, setHoldProgress] = useState(0) // 0-100
  const holdTimerRef = useRef<NodeJS.Timeout | null>(null)
  const progressIntervalRef = useRef<NodeJS.Timeout | null>(null)

  const { execute, isExecuting, isVerified, isTimeout, isError, error } =
    useDecisionExecution({
      siteId: site_id,
      decisionId: decision_id,
      onVerified: () => {
        onApproved?.()
      },
      onTimeout: () => {
        onTimeout?.()
      },
      onError: (err) => {
        onFailed?.(err)
      },
    })

  const tierColor = (() => {
    switch (tier) {
      case 3: // CRITICAL
        return 'var(--color-sentinel-red)'
      case 2: // HIGH
        return 'var(--color-sentinel-amber)'
      default: // MEDIUM or LOW
        return 'var(--color-sentinel-green)'
    }
  })()

  const tierBg = (() => {
    switch (tier) {
      case 3:
        return 'rgba(var(--color-sentinel-red-rgb), 0.15)'
      case 2:
        return 'rgba(var(--color-sentinel-amber-rgb), 0.15)'
      default:
        return 'rgba(var(--color-sentinel-green-rgb), 0.15)'
    }
  })()

  /**
   * Start hold timer when mouse down
   */
  const handleMouseDown = useCallback(() => {
    if (disabled || isExecuting || isVerified) return

    setIsHolding(true)
    setHoldProgress(0)

    // Update progress bar
    progressIntervalRef.current = setInterval(() => {
      setHoldProgress((p) => {
        const next = p + (100 / (HOLD_DURATION_MS / 50))
        return Math.min(next, 100)
      })
    }, 50)

    // Execute after hold duration
    holdTimerRef.current = setTimeout(async () => {
      setHoldProgress(100)

      // Haptic feedback on desktop (if available)
      if (navigator.vibrate) {
        navigator.vibrate(20)
      }

      // Dispatch execution
      await execute()

      setIsHolding(false)
    }, HOLD_DURATION_MS)
  }, [disabled, isExecuting, isVerified, execute])

  /**
   * Cancel hold if user releases too early
   */
  const handleMouseUp = useCallback(() => {
    if (holdTimerRef.current) {
      clearTimeout(holdTimerRef.current)
      holdTimerRef.current = null
    }
    if (progressIntervalRef.current) {
      clearInterval(progressIntervalRef.current)
      progressIntervalRef.current = null
    }

    if (holdProgress < 100) {
      setIsHolding(false)
      setHoldProgress(0)
    }
  }, [holdProgress])

  /**
   * Show loading state while executing
   */
  if (isExecuting) {
    return (
      <button
        disabled
        className="px-4 py-2 rounded-lg font-medium flex items-center justify-center gap-2 opacity-75"
        style={{ background: 'var(--color-sentinel-blue)', color: 'white' }}
      >
        <Clock className="w-4 h-4 animate-spin" />
        Dispatching...
      </button>
    )
  }

  /**
   * Show verified state
   */
  if (isVerified) {
    return (
      <button
        disabled
        className="px-4 py-2 rounded-lg font-medium flex items-center justify-center gap-2"
        style={{ background: 'var(--color-sentinel-green)', color: 'white' }}
      >
        <Check className="w-4 h-4" />
        Verified
      </button>
    )
  }

  /**
   * Show error state
   */
  if (isError || isTimeout) {
    return (
      <div className="space-y-1">
        <button
          disabled
          className="w-full px-4 py-2 rounded-lg font-medium flex items-center justify-center gap-2"
          style={{ background: 'var(--color-sentinel-red)', color: 'white' }}
        >
          <X className="w-4 h-4" />
          {isTimeout ? 'Timeout' : 'Failed'}
        </button>
        {error && <p className="text-xs text-center" style={{ color: 'var(--color-sentinel-red)' }}>{error}</p>}
      </div>
    )
  }

  /**
   * Main hold-to-approve button
   */
  return (
    <div className="space-y-2">
      <button
        onMouseDown={handleMouseDown}
        onMouseUp={handleMouseUp}
        onMouseLeave={handleMouseUp}
        onTouchStart={handleMouseDown}
        onTouchEnd={handleMouseUp}
        disabled={disabled}
        className="w-full px-4 py-3 rounded-lg font-semibold flex items-center justify-center gap-2 transition-all select-none active:scale-95 disabled:opacity-50"
        style={{
          background: tierColor,
          color: 'white',
          opacity: isHolding ? 0.75 : 1,
        }}
      >
        <Check className="w-5 h-5" />
        {isHolding ? `Hold (${Math.round(holdProgress)}%)` : 'Hold to Approve'}
      </button>

      {/* Progress bar under button */}
      {isHolding && (
        <div className="w-full h-1 rounded-full overflow-hidden" style={{ background: 'var(--color-sentinel-border)' }}>
          <div
            className="h-full transition-all duration-50"
            style={{ width: `${holdProgress}%`, background: tierColor }}
          />
        </div>
      )}

      {/* Tier and device info */}
      <div className="text-xs text-center space-y-1" style={{ color: 'var(--color-sentinel-text-secondary)' }}>
        <p>
          <strong style={{ color: 'var(--color-sentinel-text-primary)' }}>Tier {tier}:</strong>{' '}
          <span style={{ fontFamily: 'monospace' }}>{device_id} / {point}</span>
        </p>
        <p>
          <strong style={{ color: 'var(--color-sentinel-text-primary)' }}>Command:</strong>{' '}
          {typeof command_value === 'boolean' ? (command_value ? 'ON' : 'OFF') : command_value}
        </p>
      </div>
    </div>
  )
}
