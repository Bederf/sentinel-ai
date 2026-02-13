/**
 * Server-Sent Events (SSE) Hook
 *
 * Connects to backend SSE stream and provides real-time event subscription.
 * Automatically invalidates React Query caches on relevant events.
 * Handles connection, reconnection, and graceful disconnection.
 */

import { useEffect, useRef, useCallback } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'

// Event types that can be received
export type ServerEvent =
  | {
      type: 'alert_created'
      data: {
        alert_id: string
        equipment_id: string
        equipment_code: string
        equipment_name: string
        severity: string
        health_score: number
        message: string
      }
    }
  | {
      type: 'health_changed'
      data: {
        equipment_id: string
        equipment_code: string
        equipment_name: string
        old_health_score: number
        new_health_score: number
        reason?: string
      }
    }
  | {
      type: 'work_order_updated'
      data: {
        work_order_id: string
        equipment_id: string
        equipment_code: string
        status: string
        work_order_type?: string
      }
    }
  | {
      type: 'inspection_completed'
      data: {
        work_order_id: string
        equipment_id: string
        equipment_code: string
        findings: string
        recommendation?: string
      }
    }
  | {
      type: 'connected' | 'message'
      data: Record<string, unknown>
    }

interface ServerEventFrame {
  type: string
  data: Record<string, unknown>
  timestamp: string
}

type EventHandler = (event: ServerEvent) => void

/**
 * Hook for subscribing to real-time server events
 *
 * @param onEvent - Optional callback when any event is received
 * @param autoInvalidate - Whether to auto-invalidate React Query caches (default: true)
 *
 * @example
 * const { isConnected } = useServerEvents((event) => {
 *   console.log('Event received:', event)
 * })
 *
 * // Show connection status
 * return <div>{isConnected ? 'Connected' : 'Disconnected'}</div>
 */
export function useServerEvents(
  onEvent?: EventHandler,
  autoInvalidate: boolean = true
) {
  const queryClient = useQueryClient()
  const eventSourceRef = useRef<EventSource | null>(null)
  const isConnectedRef = useRef(false)
  const reconnectAttemptsRef = useRef(0)
  const maxReconnectAttemptsRef = useRef(5)
  const reconnectDelayRef = useRef(1000)

  // Handle individual event
  const handleEvent = useCallback(
    (event: ServerEvent) => {
      // Fire custom callback if provided
      if (onEvent) {
        onEvent(event)
      }

      // Auto-invalidate relevant caches based on event type
      if (!autoInvalidate) return

      switch (event.type) {
        case 'alert_created': {
          const { equipment_code, health_score, severity } = event.data

          // Show toast notification
          const severityEmoji = {
            critical: '🚨',
            warning: '⚠️',
            info: 'ℹ️'
          }[severity] || '📢'

          toast.warning(
            `${severityEmoji} ${equipment_code} - ${severity.toUpperCase()} (${health_score}% health)`,
            {
              duration: 5000,
              icon: severityEmoji
            }
          )

          // Invalidate alerts and equipment queries
          queryClient.invalidateQueries({ queryKey: ['alerts'] })
          queryClient.invalidateQueries({
            queryKey: ['equipment', 'health']
          })
          break
        }

        case 'health_changed': {
          const { equipment_code, new_health_score, old_health_score } = event.data
          const healthChange = new_health_score - old_health_score

          // Show toast with health change
          if (healthChange > 0) {
            toast.success(
              `✅ ${equipment_code} health improved: ${old_health_score}% → ${new_health_score}%`,
              { duration: 4000 }
            )
          } else if (healthChange < 0) {
            toast.error(
              `❌ ${equipment_code} health declined: ${old_health_score}% → ${new_health_score}%`,
              { duration: 4000 }
            )
          }

          // Invalidate equipment and predictions queries
          queryClient.invalidateQueries({
            queryKey: ['equipment', 'health']
          })
          queryClient.invalidateQueries({
            queryKey: ['predictions']
          })
          break
        }

        case 'work_order_updated': {
          const { work_order_id, status } = event.data

          // Show toast for work order updates
          toast.info(`📋 Work Order ${work_order_id} → ${status}`, {
            duration: 3000
          })

          // Invalidate work order queries
          queryClient.invalidateQueries({ queryKey: ['workOrders'] })
          queryClient.invalidateQueries({
            queryKey: ['workOrder', work_order_id]
          })
          break
        }

        case 'inspection_completed': {
          const { equipment_code, recommendation } = event.data

          // Show toast for inspection completion
          toast.info(
            `🔍 Inspection complete for ${equipment_code} - ${recommendation || 'See details'}`,
            { duration: 5000 }
          )

          // Invalidate inspection and recommendations
          queryClient.invalidateQueries({
            queryKey: ['inspections']
          })
          queryClient.invalidateQueries({
            queryKey: ['recommendations']
          })
          break
        }

        default:
          // Unknown event type, but don't error
          break
      }
    },
    [queryClient, onEvent, autoInvalidate]
  )

  // Connect to SSE stream
  const connect = useCallback(() => {
    if (eventSourceRef.current) {
      // Already connected
      return
    }

    const apiUrl = import.meta.env.VITE_API_URL || 'http://localhost:9095'
    const token = localStorage.getItem('sentinel_token')
    const eventSourceUrl = token
      ? `${apiUrl}/api/events/stream?access_token=${encodeURIComponent(token)}`
      : `${apiUrl}/api/events/stream`

    try {
      const eventSource = new EventSource(eventSourceUrl)

      // Handle incoming messages
      eventSource.addEventListener('message', (e: MessageEvent) => {
        try {
          const frame = JSON.parse(e.data) as ServerEventFrame
          const event: ServerEvent = {
            type: frame.type,
            data: frame.data
          } as ServerEvent

          handleEvent(event)
          reconnectAttemptsRef.current = 0
          reconnectDelayRef.current = 1000
        } catch (error) {
          console.error('Failed to parse SSE message:', error, e.data)
        }
      })

      // Handle connection established
      eventSource.addEventListener('open', () => {
        console.log('✓ SSE connected')
        isConnectedRef.current = true
        reconnectAttemptsRef.current = 0
        reconnectDelayRef.current = 1000
      })

      // Handle errors
      eventSource.addEventListener('error', (error: Event) => {
        console.error('SSE connection error:', error)
        isConnectedRef.current = false

        // Don't retry if explicitly closed
        if (
          eventSource.readyState === EventSource.CLOSED &&
          reconnectAttemptsRef.current >= maxReconnectAttemptsRef.current
        ) {
          console.log('Max reconnection attempts reached, giving up')
          eventSource.close()
          return
        }

        // Schedule reconnection
        if (reconnectAttemptsRef.current < maxReconnectAttemptsRef.current) {
          reconnectAttemptsRef.current += 1
          const delay = reconnectDelayRef.current
          reconnectDelayRef.current = Math.min(
            reconnectDelayRef.current * 2,
            30000
          ) // Max 30s

          console.log(
            `Reconnecting in ${delay}ms (attempt ${reconnectAttemptsRef.current}/${maxReconnectAttemptsRef.current})`
          )

          setTimeout(() => {
            eventSourceRef.current = null
            connect()
          }, delay)
        }
      })

      eventSourceRef.current = eventSource
    } catch (error) {
      console.error('Failed to create EventSource:', error)
      toast.error('Failed to connect to real-time events')
    }
  }, [handleEvent])

  // Disconnect from SSE stream
  const disconnect = useCallback(() => {
    if (eventSourceRef.current) {
      eventSourceRef.current.close()
      eventSourceRef.current = null
      isConnectedRef.current = false
      console.log('SSE disconnected')
    }
  }, [])

  // Setup connection on mount, cleanup on unmount
  useEffect(() => {
    connect()

    return () => {
      disconnect()
    }
  }, [connect, disconnect])

  return {
    isConnected: isConnectedRef.current,
    reconnectAttempts: reconnectAttemptsRef.current
  }
}
