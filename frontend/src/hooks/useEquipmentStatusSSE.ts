/**
 * SSE Hook for real-time equipment status in the Digital Twin.
 *
 * Connects to /api/digital-twin/status/stream and provides real-time
 * equipment status updates and predictive fault overlays.
 * Follows useServerEvents.ts pattern: ticket-based auth, auto-reconnect.
 */

import { useEffect, useRef, useCallback, useState } from 'react'
import type { EquipmentStatusUpdate, PredictiveFault, EquipmentStatusFrame } from '@/lib/api'

const DT_TICKET_RETRY_COOLDOWN_MS = 30000
let dtTicketRequestInFlight: Promise<string | null> | null = null
let dtTicketCooldownUntil = 0

/**
 * Obtain a short-lived SSE ticket for the digital twin stream.
 */
async function obtainDtSseTicket(apiUrl: string, token: string | null): Promise<string | null> {
  if (Date.now() < dtTicketCooldownUntil) {
    return null
  }
  if (dtTicketRequestInFlight) {
    return dtTicketRequestInFlight
  }

  dtTicketRequestInFlight = (async () => {
  try {
    const headers: Record<string, string> = { 'Content-Type': 'application/json' }
    if (token) {
      headers['Authorization'] = `Bearer ${token}`
    }
    const res = await fetch(`${apiUrl}/api/digital-twin/status/ticket`, {
      method: 'POST',
      headers,
    })
    if (res.status === 429) {
      dtTicketCooldownUntil = Date.now() + DT_TICKET_RETRY_COOLDOWN_MS
      return null
    }
    if (!res.ok) return null
    const data = await res.json()
    return data.ticket || null
  } catch {
    return null
  } finally {
    dtTicketRequestInFlight = null
  }
  })()

  return dtTicketRequestInFlight
}

interface UseEquipmentStatusSSEResult {
  equipmentUpdates: Map<string, EquipmentStatusUpdate>
  predictions: PredictiveFault[]
  isConnected: boolean
}

/**
 * Hook for subscribing to real-time equipment status via SSE.
 *
 * @param siteId - Site UUID to stream status for
 * @returns Equipment updates map (keyed by equipment_id), predictions, and connection status
 *
 * @example
 * const { equipmentUpdates, predictions, isConnected } = useEquipmentStatusSSE(siteId)
 */
export function useEquipmentStatusSSE(siteId: string): UseEquipmentStatusSSEResult {
  const eventSourceRef = useRef<EventSource | null>(null)
  const [isConnected, setIsConnected] = useState(false)
  const [equipmentUpdates, setEquipmentUpdates] = useState<Map<string, EquipmentStatusUpdate>>(new Map())
  const [predictions, setPredictions] = useState<PredictiveFault[]>([])
  const reconnectAttemptsRef = useRef(0)
  const maxReconnectAttempts = 5
  const reconnectDelayRef = useRef(1000)
  const connectingRef = useRef(false)

  const connect = useCallback(() => {
    if (!siteId || eventSourceRef.current || connectingRef.current) {
      return
    }

    connectingRef.current = true

    const apiUrl = import.meta.env.VITE_API_URL || 'http://localhost:9095'
    const token = localStorage.getItem('sentinel_token')

    const doConnect = async () => {
      const scheduleReconnect = () => {
        if (reconnectAttemptsRef.current < maxReconnectAttempts) {
          reconnectAttemptsRef.current += 1
          const delay = reconnectDelayRef.current
          reconnectDelayRef.current = Math.min(reconnectDelayRef.current * 2, 30000)
          setTimeout(() => {
            connectingRef.current = false
            // eslint-disable-next-line react-hooks/immutability
            connect()
          }, delay)
        } else {
          connectingRef.current = false
        }
      }

      try {
        // Get a short-lived ticket
        const ticket = await obtainDtSseTicket(apiUrl, token)
        if (!ticket) {
          setIsConnected(false)
          scheduleReconnect()
          return
        }
        const url = `${apiUrl}/api/digital-twin/status/stream?site_id=${encodeURIComponent(siteId)}&ticket=${encodeURIComponent(ticket)}`

        // Guard against race condition
        if (eventSourceRef.current) {
          connectingRef.current = false
          return
        }

        const eventSource = new EventSource(url)

        eventSource.addEventListener('message', (e: MessageEvent) => {
          try {
            const frame = JSON.parse(e.data) as EquipmentStatusFrame

            // Skip "connected" type messages
            if ((frame as any).type === 'connected') {
              return
            }

            // Update equipment map
            if (frame.equipment_updates && frame.equipment_updates.length > 0) {
              setEquipmentUpdates(prev => {
                const next = new Map(prev)
                for (const update of frame.equipment_updates) {
                  next.set(update.equipment_id, update)
                }
                return next
              })
            }

            // Update predictions
            if (frame.predictions) {
              setPredictions(frame.predictions)
            }

            // Reset reconnect on successful data
            reconnectAttemptsRef.current = 0
            reconnectDelayRef.current = 1000
          } catch {
            // Ignore parse errors for heartbeat/control messages
          }
        })

        eventSource.addEventListener('open', () => {
          setIsConnected(true)
          reconnectAttemptsRef.current = 0
          reconnectDelayRef.current = 1000
        })

        eventSource.addEventListener('error', () => {
          setIsConnected(false)

          if (
            eventSource.readyState === EventSource.CLOSED &&
            reconnectAttemptsRef.current >= maxReconnectAttempts
          ) {
            eventSource.close()
            connectingRef.current = false
            return
          }

          eventSource.close()
          eventSourceRef.current = null

          // Schedule reconnection with exponential backoff
          scheduleReconnect()
        })

        eventSourceRef.current = eventSource
        connectingRef.current = false
      } catch {
        scheduleReconnect()
      }
    }

    doConnect()
  }, [siteId])

  const disconnect = useCallback(() => {
    if (eventSourceRef.current) {
      eventSourceRef.current.close()
      eventSourceRef.current = null
      setIsConnected(false)
    }
    connectingRef.current = false
  }, [])

  // Connect on mount / siteId change, cleanup on unmount
  useEffect(() => {
    connect()

    return () => {
      disconnect()
    }
  }, [connect, disconnect])

  return { equipmentUpdates, predictions, isConnected }
}
