import { useEffect, useMemo, useState } from 'react'
import api, { authorizedFetch } from '@/lib/api'
import { CockpitView } from './CockpitView'
import { CockpitNervousSystemTwin } from './CockpitNervousSystemTwin'
import { mapCockpitState, type CockpitDecisionPayload } from './mapCockpitState'
import { DEFAULT_COCKPIT_THRESHOLD_POLICY, type CockpitThresholdPolicy } from './thresholdPolicy'

interface OverviewCockpitHostProps {
  siteId: string
  siteName: string
  activeAlerts: number
  predictionsCount: number
  equipmentCount: number
  posture?: string | null
  onModuleDisplayChange?: (moduleDisplay: Record<string, string>) => void
}

const POLL_INTERVAL_MS = 30_000

function formatFreshness(lastUpdatedAt: number | null): string {
  if (!lastUpdatedAt) return 'Freshness unavailable'
  const ageSeconds = Math.max(0, Math.floor((Date.now() - lastUpdatedAt) / 1000))
  if (ageSeconds < 60) return `Updated ${ageSeconds}s ago`
  return `Updated ${Math.floor(ageSeconds / 60)}m ago`
}

export function OverviewCockpitHost({
  siteId,
  siteName,
  activeAlerts,
  predictionsCount,
  equipmentCount,
  posture,
  onModuleDisplayChange: _onModuleDisplayChange,
}: OverviewCockpitHostProps) {
  const [payload, setPayload] = useState<CockpitDecisionPayload | null>(null)
  const [lastUpdatedAt, setLastUpdatedAt] = useState<number | null>(null)
  const [thresholdPolicy, setThresholdPolicy] = useState<CockpitThresholdPolicy>(DEFAULT_COCKPIT_THRESHOLD_POLICY)

  useEffect(() => {
    let mounted = true

    async function loadThresholdPolicy() {
      try {
        const [health, risk] = await Promise.all([
          api.getHealthThresholds(),
          api.getRiskThresholds(),
        ])

        if (mounted) {
          setThresholdPolicy({
            health,
            risk,
            source: 'settings',
          })
        }
      } catch {
        if (mounted) {
          setThresholdPolicy(DEFAULT_COCKPIT_THRESHOLD_POLICY)
        }
      }
    }

    loadThresholdPolicy()

    return () => {
      mounted = false
    }
  }, [])

  useEffect(() => {
    let mounted = true
    let timer: ReturnType<typeof setInterval> | null = null
    let controller: AbortController | null = null

    async function load() {
      try {
        if (controller) controller.abort()
        controller = new AbortController()

        const response = await authorizedFetch(`/api/cockpit/decision/${encodeURIComponent(siteId)}`, {
          signal: controller.signal,
        })

        if (!response.ok) {
          if (mounted) {
            setPayload(null)
            setLastUpdatedAt(Date.now())
          }
          return
        }

        const json = await response.json()
        if (mounted) {
          // Cockpit endpoint returns {payload: null | CockpitDecisionPayload, site_id, fetched_at}
          setPayload(json.payload as CockpitDecisionPayload | null)
          setLastUpdatedAt(Date.now())
        }
      } catch (error) {
        if (error instanceof Error && error.name === 'AbortError') {
          return
        }
        // On network error, leave payload unchanged; let freshness indicator show age
      }
    }

    load()
    timer = setInterval(load, POLL_INTERVAL_MS)

    return () => {
      mounted = false
      if (controller) controller.abort()
      if (timer) clearInterval(timer)
    }
  }, [siteId])

  const state = useMemo(
    () =>
      mapCockpitState(
        {
          siteId,
          siteName,
          posture,
          activeAlerts,
          predictionsCount,
          equipmentCount,
          dataFreshnessLabel: formatFreshness(lastUpdatedAt),
        },
        payload,
        thresholdPolicy,
      ),
    [siteId, siteName, posture, activeAlerts, predictionsCount, equipmentCount, lastUpdatedAt, payload, thresholdPolicy],
  )

  return (
    <CockpitView
      state={state}
      renderMode="embedded"
      spatialCanvas={<CockpitNervousSystemTwin state={state} />}
    />
  )
}
