import { useCallback, useEffect, useMemo, useState } from 'react'
import { authorizedFetch } from '@/lib/api'
import type { HVACOverview } from '@/lib/hvacApi'
import { CockpitView } from './CockpitView'
import { CockpitBuildingThree } from './CockpitBuildingThree'
import { mapCockpitState, type BuildingStatePayload, type EnergyCentreTelemetry } from './mapCockpitState'

interface OverviewCockpitHostProps {
  siteId: string
  siteName: string
  onboardingPhase?: 'shadow' | 'advisory' | 'supervised' | 'auto'
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

function useBuildingStatePayload(siteId: string) {
  const [payload, setPayload] = useState<BuildingStatePayload | null>(null)
  const [hvacOverview, setHvacOverview] = useState<HVACOverview | null>(null)
  const [energyTelemetry, setEnergyTelemetry] = useState<EnergyCentreTelemetry | null>(null)
  const [lastUpdatedAt, setLastUpdatedAt] = useState<number | null>(null)

  useEffect(() => {
    let mounted = true
    let timer: ReturnType<typeof setInterval> | null = null
    let controller: AbortController | null = null

    async function load() {
      try {
        controller?.abort()
        controller = new AbortController()

        const [buildingStateRes, hvacRes, energyRes] = await Promise.all([
          authorizedFetch(`/api/building-state/${encodeURIComponent(siteId)}`, {
            signal: controller.signal,
          }),
          authorizedFetch(`/api/hvac/overview/${encodeURIComponent(siteId)}`, {
            signal: controller.signal,
          }),
          authorizedFetch(`/api/energy-centre/power-summary/${encodeURIComponent(siteId)}`, {
            signal: controller.signal,
          }),
        ])

        if (!buildingStateRes.ok) {
          if (mounted) {
            setPayload(null)
            setHvacOverview(null)
            setEnergyTelemetry(null)
            setLastUpdatedAt(Date.now())
          }
          return
        }

        const json = await buildingStateRes.json()
        const hvacJson = hvacRes.ok ? await hvacRes.json() : null
        const energyJson = energyRes.ok ? await energyRes.json() : null
        if (mounted) {
          setPayload(json.payload as BuildingStatePayload | null)
          setHvacOverview((hvacJson as HVACOverview | null) ?? null)
          setEnergyTelemetry(
            energyJson
              ? {
                  totalKw: Number(energyJson.total_power_kw ?? 0),
                  hvacKw: 0,
                  lightingKw: 0,
                  powerKw: Number(energyJson.total_power_kw ?? 0),
                  powerPercent: 0,
                  timestamp: typeof energyJson.timestamp === 'string' ? energyJson.timestamp : undefined,
                }
              : null,
          )
          setLastUpdatedAt(Date.now())
        }
      } catch (error) {
        if (error instanceof Error && error.name === 'AbortError') {
          return
        }
      }
    }

    load()
    timer = setInterval(load, POLL_INTERVAL_MS)

    return () => {
      mounted = false
      controller?.abort()
      if (timer) clearInterval(timer)
    }
  }, [siteId])

  return { payload, hvacOverview, energyTelemetry, lastUpdatedAt }
}

function buildCockpitSummary(
  props: OverviewCockpitHostProps,
  lastUpdatedAt: number | null,
) {
  return {
    siteId: props.siteId,
    siteName: props.siteName,
    onboardingPhase: props.onboardingPhase,
    posture: props.posture,
    activeAlerts: props.activeAlerts,
    predictionsCount: props.predictionsCount,
    equipmentCount: props.equipmentCount,
    dataFreshnessLabel: formatFreshness(lastUpdatedAt),
  }
}

export function OverviewCockpitHost({
  siteId,
  siteName,
  onboardingPhase,
  activeAlerts,
  predictionsCount,
  equipmentCount,
  posture,
  onModuleDisplayChange: _onModuleDisplayChange,
}: OverviewCockpitHostProps) {
  const { payload, hvacOverview, energyTelemetry, lastUpdatedAt } = useBuildingStatePayload(siteId)

  const handleApprove = useCallback(async () => {
    try {
      await authorizedFetch(`/api/cockpit/decision/approve/${encodeURIComponent(siteId)}`, {
        method: 'POST',
      })
    } catch {
      // Approval failure is silent — operator sees no state change; backend logs it
    }
  }, [siteId])

  const state = useMemo(() => {
    const summary = buildCockpitSummary(
      { siteId, siteName, onboardingPhase, posture, activeAlerts, predictionsCount, equipmentCount },
      lastUpdatedAt,
    )
    return mapCockpitState(summary, payload, hvacOverview, energyTelemetry)
  }, [siteId, siteName, onboardingPhase, posture, activeAlerts, predictionsCount, equipmentCount, lastUpdatedAt, payload, hvacOverview, energyTelemetry])

  return (
    <CockpitView
      state={state}
      renderMode="embedded"
      spatialCanvas={<CockpitBuildingThree state={state} />}
      onApprove={handleApprove}
    />
  )
}
