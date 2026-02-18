/**
 * Server-Sent Events (SSE) Hook
 *
 * Connects to backend SSE stream and provides real-time event subscription.
 * Automatically invalidates React Query caches on relevant events.
 * Handles connection, reconnection, and graceful disconnection.
 *
 * Security: Uses ticket-based auth to avoid exposing JWTs in EventSource URLs.
 * 1. POST /api/events/ticket with Bearer token in Authorization header
 * 2. Get back a random UUID ticket (short-lived, single-use)
 * 3. Open EventSource with ?ticket=UUID (safe to appear in logs/console)
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
 * Obtain a short-lived SSE ticket from the backend.
 * The JWT is sent in the Authorization header (not in the URL).
 * Returns a random UUID ticket or null on failure.
 */
async function obtainSseTicket(apiUrl: string, token: string): Promise<string | null> {
  try {
    const res = await fetch(`${apiUrl}/api/events/ticket`, {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${token}`,
        'Content-Type': 'application/json',
      },
    })
    if (!res.ok) return null
    const data = await res.json()
    return data.ticket || null
  } catch {
    return null
  }
}

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
  const connectingRef = useRef(false)

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

  // Connect to SSE stream (async: obtains ticket first)
  const connect = useCallback(() => {
    if (eventSourceRef.current || connectingRef.current) {
      return
    }

    connectingRef.current = true

    const apiUrl = import.meta.env.VITE_API_URL || 'http://localhost:9095'
    const token = localStorage.getItem('sentinel_token')

    // Async ticket acquisition then EventSource connection
    const doConnect = async () => {
      try {
        let eventSourceUrl = `${apiUrl}/api/events/stream`

        if (token) {
          // Get a short-lived ticket (JWT stays in Authorization header, not in URL)
          const ticket = await obtainSseTicket(apiUrl, token)
          if (ticket) {
            eventSourceUrl = `${apiUrl}/api/events/stream?ticket=${encodeURIComponent(ticket)}`
          }
          // If ticket acquisition fails, still try connecting (demo mode may allow it)
        }

        // Guard against race condition if disconnected while awaiting ticket
        if (eventSourceRef.current) {
          connectingRef.current = false
          return
        }

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
            console.error('Failed to parse SSE message:', error)
          }
        })

        // Handle connection established
        eventSource.addEventListener('open', () => {
          isConnectedRef.current = true
          reconnectAttemptsRef.current = 0
          reconnectDelayRef.current = 1000
        })

        // Handle errors
        eventSource.addEventListener('error', () => {
          isConnectedRef.current = false

          // Don't retry if explicitly closed
          if (
            eventSource.readyState === EventSource.CLOSED &&
            reconnectAttemptsRef.current >= maxReconnectAttemptsRef.current
          ) {
            eventSource.close()
            connectingRef.current = false
            return
          }

          // Close current connection before reconnecting
          eventSource.close()
          eventSourceRef.current = null

          // Schedule reconnection with new ticket
          if (reconnectAttemptsRef.current < maxReconnectAttemptsRef.current) {
            reconnectAttemptsRef.current += 1
            const delay = reconnectDelayRef.current
            reconnectDelayRef.current = Math.min(
              reconnectDelayRef.current * 2,
              30000
            )

            setTimeout(() => {
              connectingRef.current = false
              connect()
            }, delay)
          } else {
            connectingRef.current = false
          }
        })

        eventSourceRef.current = eventSource
        connectingRef.current = false
      } catch {
        connectingRef.current = false
        toast.error('Failed to connect to real-time events')
      }
    }

    doConnect()
  }, [handleEvent])

  // Disconnect from SSE stream
  const disconnect = useCallback(() => {
    if (eventSourceRef.current) {
      eventSourceRef.current.close()
      eventSourceRef.current = null
      isConnectedRef.current = false
    }
    connectingRef.current = false
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
