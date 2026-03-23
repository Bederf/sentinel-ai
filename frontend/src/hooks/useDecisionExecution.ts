/**
 * Hook for managing decision execution state
 *
 * Handles:
 * - Dispatching execution request to backend
 * - Tracking immediate ACCEPTED response
 * - Listening for async verification events (SSE)
 * - Transitioning state from ACCEPTED → VERIFIED/TIMEOUT/ERROR
 *
 * Phase 170-01: Supervised Execution UI
 */

import { useState, useCallback, useEffect, useRef } from 'react'
import { decisionApi } from '@/lib/api/decision'
import type { ExecutionState, ExecutionProgress, ExecutionEvent } from '@/lib/api/decision'

interface UseDecisionExecutionOptions {
  siteId: string
  decisionId: string
  onVerified?: (details: ExecutionEvent['details']) => void
  onTimeout?: () => void
  onError?: (error: string) => void
}

export function useDecisionExecution({
  siteId,
  decisionId,
  onVerified,
  onTimeout,
  onError,
}: UseDecisionExecutionOptions) {
  const [progress, setProgress] = useState<ExecutionProgress>({
    state: 'pending',
    decision_id: decisionId,
    timestamp: Date.now(),
  })

  const [isExecuting, setIsExecuting] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const eventSourceRef = useRef<EventSource | null>(null)
  const timeoutTimerRef = useRef<NodeJS.Timeout | null>(null)

  /**
   * Listen for verification events from SSE stream
   * Events come from /api/events endpoint with subscription to correlation_id
   */
  const setupEventListener = useCallback((correlationId: string) => {
    // Create EventSource for SSE stream with correlation ID filter
    // In production, this would use a subscription mechanism or polling fallback
    try {
      const eventUrl = new URL('/api/events', window.location.origin)
      eventUrl.searchParams.set('type', 'decision_execution')
      eventUrl.searchParams.set('correlation_id', correlationId)

      const es = new EventSource(eventUrl.toString())

      es.addEventListener('COMMAND_ACCEPTED', (event: Event) => {
        const customEvent = event as MessageEvent<string>
        const _data = JSON.parse(customEvent.data) as ExecutionEvent
        setProgress((p) => ({
          ...p,
          state: 'accepted' as ExecutionState,
          correlation_id: _data.correlation_id,
          message: 'Command dispatched. Awaiting verification...',
          timestamp: Date.now(),
        }))
      })

      es.addEventListener('COMMAND_VERIFIED', (event: Event) => {
        const customEvent = event as MessageEvent<string>
        const verifyData = JSON.parse(customEvent.data) as ExecutionEvent
        setProgress((p) => ({
          ...p,
          state: 'verified' as ExecutionState,
          message: 'Command verified by telemetry',
          timestamp: Date.now(),
        }))
        if (timeoutTimerRef.current) {
          clearTimeout(timeoutTimerRef.current)
        }
        es.close()
        onVerified?.(verifyData.details)
      })

      es.addEventListener('COMMAND_TIMEOUT', (event: Event) => {
        const customEvent = event as MessageEvent<string>
        JSON.parse(customEvent.data) as ExecutionEvent
        setProgress((p) => ({
          ...p,
          state: 'timeout' as ExecutionState,
          error: 'Verification timeout: device did not report change within 30 seconds',
          timestamp: Date.now(),
        }))
        es.close()
        setIsExecuting(false)
        onTimeout?.()
      })

      es.addEventListener('COMMAND_FAILED', (event: Event) => {
        const customEvent = event as MessageEvent<string>
        const data = JSON.parse(customEvent.data) as ExecutionEvent
        setProgress((p) => ({
          ...p,
          state: 'error' as ExecutionState,
          error: data.details?.error_message || 'Command execution failed',
          timestamp: Date.now(),
        }))
        es.close()
        setIsExecuting(false)
        onError?.(data.details?.error_message || 'Command execution failed')
      })

      es.onerror = () => {
        es.close()
        // On SSE error, set timeout fallback
        // In production, implement polling fallback here
      }

      eventSourceRef.current = es

      // Set 35-second timeout for verification (backend estimates 30s)
      timeoutTimerRef.current = setTimeout(() => {
        if (progress.state === 'accepted') {
          setProgress((p) => ({
            ...p,
            state: 'timeout' as ExecutionState,
            error: 'Verification timeout: no response after 35 seconds',
          }))
          es.close()
          setIsExecuting(false)
          onTimeout?.()
        }
      }, 35000)
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to setup event listener'
      setError(message)
      setIsExecuting(false)
      onError?.(message)
    }
  }, [onVerified, onTimeout, onError, progress.state])

  /**
   * Execute the decision: POST to /api/v1/approval/execute/{site_id}
   * Returns ACCEPTED immediately; SSE listener above handles async outcome
   */
  const execute = useCallback(async () => {
    setIsExecuting(true)
    setError(null)

    try {
      setProgress((p) => ({
        ...p,
        state: 'pending' as ExecutionState,
        message: 'Dispatching command...',
        timestamp: Date.now(),
      }))

      const response = await decisionApi.executeDecision(siteId, decisionId, 'approved')

      if (!response) {
        throw new Error('No response from server')
      }

      // Response comes back ACCEPTED immediately (step 11 of 14-step flow)
      setProgress((p) => ({
        ...p,
        state: 'accepted' as ExecutionState,
        correlation_id: response.correlation_id,
        message: response.message,
        timestamp: Date.now(),
      }))

      // Now listen for async verification (steps 12-14 happen in background)
      setupEventListener(response.correlation_id)
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Execution failed'
      setError(message)
      setProgress((p) => ({
        ...p,
        state: 'error' as ExecutionState,
        error: message,
        timestamp: Date.now(),
      }))
      setIsExecuting(false)
      onError?.(message)
    }
  }, [siteId, decisionId, setupEventListener, onError])

  /**
   * Cancel execution and cleanup
   */
  const cancel = useCallback(() => {
    if (eventSourceRef.current) {
      eventSourceRef.current.close()
      eventSourceRef.current = null
    }
    if (timeoutTimerRef.current) {
      clearTimeout(timeoutTimerRef.current)
      timeoutTimerRef.current = null
    }
    setIsExecuting(false)
    setProgress((p) => ({
      ...p,
      state: 'error' as ExecutionState,
      error: 'Execution cancelled',
      timestamp: Date.now(),
    }))
  }, [])

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      if (eventSourceRef.current) {
        eventSourceRef.current.close()
      }
      if (timeoutTimerRef.current) {
        clearTimeout(timeoutTimerRef.current)
      }
    }
  }, [])

  return {
    // State
    progress,
    state: progress.state,
    isExecuting,
    error,
    message: progress.message,
    correlationId: progress.correlation_id,

    // Actions
    execute,
    cancel,

    // Helpers
    isAccepted: progress.state === 'accepted',
    isVerified: progress.state === 'verified',
    isTimeout: progress.state === 'timeout',
    isError: progress.state === 'error',
  }
}
