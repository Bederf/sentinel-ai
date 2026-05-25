import { useCallback, useEffect, useMemo, useState } from 'react'
import { authorizedFetch } from '@/lib/api'
import type { Equipment } from '@/lib/api/sites'
import type { HVACOverview } from '@/lib/hvacApi'
import { CockpitView } from './CockpitView'
import { CockpitBuildingThree } from './CockpitBuildingThree'
import { mapCockpitState, type BuildingStatePayload, type EnergyCentreTelemetry, type EquipmentWarningInput } from './mapCockpitState'
import type { CockpitTwinZoneSignal, ModelReadiness } from './types'

import type { BuildingTabId } from '@/lib/navigation'

interface OverviewCockpitHostProps {
  siteId: string
  siteName: string
  gpsLat?: number | null
  gpsLon?: number | null
  orientationDegrees?: number | null
  onboardingPhase?: 'shadow' | 'advisory' | 'supervised' | 'auto'
  activeAlerts: number
  predictionsCount: number
  equipmentCount: number
  posture?: string | null
  systemFilter?: string | null
  onModuleDisplayChange?: (moduleDisplay: Record<string, string>) => void
  siteFloors?: string[] // floors from building config (settings page), e.g. ['B1','L0','L1','L2']
  activeMainTab: BuildingTabId
  onMainTabChange: (tab: BuildingTabId) => void
  isModuleActive: (module: string) => boolean
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
  const [equipment, setEquipment] = useState<Equipment[] | null>(null)
  const [lastUpdatedAt, setLastUpdatedAt] = useState<number | null>(null)

  useEffect(() => {
    let mounted = true
    let timer: ReturnType<typeof setInterval> | null = null
    let controller: AbortController | null = null

    async function load() {
      try {
        controller?.abort()
        controller = new AbortController()

        const [buildingStateRes, hvacRes, energyRes, equipmentRes] = await Promise.all([
          authorizedFetch(`/api/building-state/${encodeURIComponent(siteId)}`, {
            signal: controller.signal,
          }),
          authorizedFetch(`/api/hvac/overview/${encodeURIComponent(siteId)}`, {
            signal: controller.signal,
          }),
          authorizedFetch(`/api/energy-centre/power-summary/${encodeURIComponent(siteId)}`, {
            signal: controller.signal,
          }),
          authorizedFetch(`/api/buildings/${encodeURIComponent(siteId)}/equipment`, {
            signal: controller.signal,
          }),
        ])

        if (!buildingStateRes.ok) {
          if (mounted) {
            setPayload(null)
            setHvacOverview(null)
            setEnergyTelemetry(null)
            setEquipment(null)
            setLastUpdatedAt(Date.now())
          }
          return
        }

        const json = await buildingStateRes.json()
        const hvacJson = hvacRes.ok ? await hvacRes.json() : null
        const energyJson = energyRes.ok ? await energyRes.json() : null
        const equipmentJson = equipmentRes.ok ? await equipmentRes.json() : null
        if (mounted) {
          setPayload(json.payload as BuildingStatePayload | null)
          setHvacOverview((hvacJson as HVACOverview | null) ?? null)
          const hvacPower = hvacJson?.raw_telemetry?.power
          const totalKw = hvacPower?.total_kw ?? Number(energyJson?.total_power_kw ?? 0)
          const hvacKw = hvacPower?.hvac_kw ?? 0
          const lightingKw = hvacPower?.lighting_kw ?? 0
          const powerPercent = totalKw > 0 && hvacKw > 0 ? (hvacKw / totalKw) * 100 : 0
          setEnergyTelemetry(
            energyJson || hvacPower
              ? {
                  totalKw,
                  hvacKw,
                  lightingKw,
                  powerKw: totalKw,
                  powerPercent,
                  timestamp: typeof energyJson?.timestamp === 'string' ? energyJson.timestamp : undefined,
                }
              : null,
          )
          setEquipment(equipmentJson?.equipment ?? null)
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

  return { payload, hvacOverview, energyTelemetry, equipment, lastUpdatedAt }
}

function buildCockpitSummary(
  props: OverviewCockpitHostProps,
  lastUpdatedAt: number | null,
) {
  return {
    siteId: props.siteId,
    siteName: props.siteName,
    gpsLat: props.gpsLat ?? null,
    gpsLon: props.gpsLon ?? null,
    orientationDegrees: props.orientationDegrees ?? null,
    onboardingPhase: props.onboardingPhase,
    posture: props.posture,
    activeAlerts: props.activeAlerts,
    predictionsCount: props.predictionsCount,
    equipmentCount: props.equipmentCount,
    dataFreshnessLabel: formatFreshness(lastUpdatedAt),
    siteFloors: props.siteFloors ?? null,
  }
}

export function OverviewCockpitHost({
  siteId,
  siteName,
  gpsLat,
  gpsLon,
  orientationDegrees,
  onboardingPhase,
  activeAlerts,
  predictionsCount,
  equipmentCount,
  posture,
  systemFilter,
  onModuleDisplayChange: _onModuleDisplayChange,
  siteFloors,
  activeMainTab,
  onMainTabChange,
  isModuleActive,
}: OverviewCockpitHostProps) {
  const { payload, hvacOverview, energyTelemetry, equipment, lastUpdatedAt } = useBuildingStatePayload(siteId)
  const [selectedZone, setSelectedZone] = useState<CockpitTwinZoneSignal | null>(null)
  const [modelReadiness, setModelReadiness] = useState<ModelReadiness | null>(null)

  // Poll ML model readiness for shadow training progress
  useEffect(() => {
    let mounted = true
    let timer: ReturnType<typeof setInterval> | null = null

    async function loadReadiness() {
      try {
        const res = await authorizedFetch(`/api/ml/model-readiness/${encodeURIComponent(siteId)}`)
        if (res.ok && mounted) {
          const data = await res.json()
          setModelReadiness({
            siteId: data.site_id,
            trainingEnabled: data.training_enabled,
            ready: data.ready,
            activeModelCount: data.active_model_count,
            equipmentTypesCovered: data.equipment_types_covered,
            lastTrainingAt: data.last_training_at,
            message: data.message,
          })
        }
      } catch {
        // Readiness failures are silent — cockpit continues showing telemetry
      }
    }

    loadReadiness()
    timer = setInterval(loadReadiness, POLL_INTERVAL_MS)

    return () => {
      mounted = false
      if (timer) clearInterval(timer)
    }
  }, [siteId])

  const handleApprove = useCallback(async () => {
    try {
      await authorizedFetch(`/api/cockpit/decision/approve/${encodeURIComponent(siteId)}`, {
        method: 'POST',
      })
    } catch {
      // Approval failure is silent — operator sees no state change; backend logs it
    }
  }, [siteId])

  const handleAdvancePhase = useCallback(async () => {
    const nextPhase = onboardingPhase === 'shadow' ? 'advisory' : onboardingPhase === 'advisory' ? 'supervised' : 'auto'
    try {
      await authorizedFetch(`/api/sites/${encodeURIComponent(siteId)}/phase`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ phase: nextPhase }),
      })
    } catch {
      // Phase advance failures are silent
    }
  }, [siteId, onboardingPhase])

  const state = useMemo(() => {
    const summary = buildCockpitSummary(
      { siteId, siteName, gpsLat, gpsLon, orientationDegrees, onboardingPhase, posture, activeAlerts, predictionsCount, equipmentCount, siteFloors },
      lastUpdatedAt,
    )
    // Extract floor_id from zone_key (e.g. Zone-L1-1 → L1, Zone-L3-ICU → L3)
    const equipmentWarnings: EquipmentWarningInput[] = (equipment ?? [])
      .filter((eq) => eq.health_score < 85)
      .map((eq) => {
        let floorId = ''
        const zoneKey = eq.zone_key ?? ''
        const match = zoneKey.match(/^Zone-(L\d+|B\d+|R|G)/i)
        if (match) {
          floorId = match[1].toUpperCase()
        }
        return {
          id: eq.id,
          equipment_id: eq.id,
          code: eq.code,
          equipment_type: eq.equipment_type,
          floor_id: floorId,
          health_score: eq.health_score,
          health_state: eq.health_score >= 70 ? 'degraded' : 'critical',
          zone_id: zoneKey,
        }
      })
    return mapCockpitState(summary, payload, hvacOverview, energyTelemetry, undefined, systemFilter, equipmentWarnings)
  }, [siteId, siteName, gpsLat, gpsLon, orientationDegrees, onboardingPhase, posture, activeAlerts, predictionsCount, equipmentCount, lastUpdatedAt, payload, hvacOverview, energyTelemetry, systemFilter, siteFloors, equipment])

  return (
    <CockpitView
      state={state}
      renderMode="embedded"
      spatialCanvas={<CockpitBuildingThree state={state} onZoneSelect={setSelectedZone} />}
      onApprove={handleApprove}
      selectedZone={selectedZone}
      onZoneClose={() => setSelectedZone(null)}
      modelReadiness={modelReadiness}
      onAdvancePhase={handleAdvancePhase}
      activeMainTab={activeMainTab}
      onMainTabChange={onMainTabChange}
      isModuleActive={isModuleActive}
    />
  )
}
