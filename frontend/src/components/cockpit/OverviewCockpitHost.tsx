import { useCallback, useEffect, useMemo, useState } from 'react'
import { authorizedFetch } from '@/lib/api'
import type { Equipment } from '@/lib/api/sites'
import type { HVACOverview } from '@/lib/hvacApi'
import { CockpitView } from './CockpitView'
import { CockpitBuildingThree } from './CockpitBuildingThree'
import { getModuleScope } from './moduleScopes'
import { mapCockpitState, type BuildingStatePayload, type EnergyCentreTelemetry, type EquipmentWarningInput } from './mapCockpitState'
import type { CockpitIssueActionType, CockpitIssuesPayload, CockpitTwinZoneSignal, ModelReadiness, WaterTelemetry } from './types'

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

function formatFreshness(lastUpdatedAt: number | null, loading: boolean): string {
  if (!lastUpdatedAt) return loading ? 'Fetching data…' : 'No data received yet'
  const ageSeconds = Math.max(0, Math.floor((Date.now() - lastUpdatedAt) / 1000))
  if (ageSeconds < 60) return `Updated ${ageSeconds}s ago`
  if (ageSeconds < 3600) return `Updated ${Math.floor(ageSeconds / 60)}m ago`
  return `Updated ${Math.floor(ageSeconds / 3600)}h ago`
}

function useBuildingStatePayload(siteId: string) {
  const [payload, setPayload] = useState<BuildingStatePayload | null>(null)
  const [hvacOverview, setHvacOverview] = useState<HVACOverview | null>(null)
  const [energyTelemetry, setEnergyTelemetry] = useState<EnergyCentreTelemetry | null>(null)
  const [equipment, setEquipment] = useState<Equipment[] | null>(null)
  const [lastUpdatedAt, setLastUpdatedAt] = useState<number | null>(null)
  const [loading, setLoading] = useState<boolean>(true)

  useEffect(() => {
    let mounted = true
    let timer: ReturnType<typeof setInterval> | null = null
    let controller: AbortController | null = null

    async function load() {
      setLoading(true)
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
          setLoading(false)
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

  return { payload, hvacOverview, energyTelemetry, equipment, lastUpdatedAt, loading }
}

function useWaterTelemetry(siteId: string, onboardingPhase?: string) {
  const [waterTelemetry, setWaterTelemetry] = useState<WaterTelemetry | null>(null)

  useEffect(() => {
    if (onboardingPhase === 'shadow') {
      setWaterTelemetry(null)
      return
    }

    let mounted = true
    let timer: ReturnType<typeof setInterval> | null = null

    async function load() {
      try {
        const [currentRes, alertsRes] = await Promise.all([
          authorizedFetch(`/api/water/sites/${encodeURIComponent(siteId)}/current`),
          authorizedFetch(`/api/water/sites/${encodeURIComponent(siteId)}/alerts/active`),
        ])

        if (!mounted) return

        if (!currentRes.ok) {
          setWaterTelemetry({ flowLpm: null, pressureBar: null, totalM3: null, dailyM3: null, leakDetected: null, lastUpdated: null, sourceHealthy: false })
          return
        }

        const current = await currentRes.json() as {
          flow_rate_lpm: number
          volume_liters: number
          pressure: number | null
          timestamp: string
        }
        const alertsData = alertsRes.ok ? await alertsRes.json() as { alerts?: Array<{ severity: string }> } : null
        const hasLeak = alertsData !== null && (alertsData.alerts?.length ?? 0) > 0

        setWaterTelemetry({
          flowLpm: current.flow_rate_lpm ?? null,
          pressureBar: current.pressure ?? null,
          totalM3: current.volume_liters != null ? current.volume_liters / 1000 : null,
          dailyM3: null,
          leakDetected: hasLeak,
          lastUpdated: current.timestamp ?? null,
          sourceHealthy: true,
        })
      } catch {
        if (mounted) {
          setWaterTelemetry({ flowLpm: null, pressureBar: null, totalM3: null, dailyM3: null, leakDetected: null, lastUpdated: null, sourceHealthy: false })
        }
      }
    }

    load()
    timer = setInterval(load, POLL_INTERVAL_MS)

    return () => {
      mounted = false
      if (timer) clearInterval(timer)
    }
  }, [siteId, onboardingPhase])

  return waterTelemetry
}

// ─── Phase 209 — issue-based decision hook ────────────────────────────────────

interface RawIssueItem {
  id: string
  title: string
  summary: string
  severity: string
  source: string
  status: string
  owner: string | null
  owner_team: string | null
  opened_at?: string
  updated_at?: string
  sla_due_at: string | null
  stale?: boolean
  impact_summary: string | null
  recommended_action: string | null
  confidence: number | null
  confidence_label: string | null
  subsystem: string | null
  location: { zone_ids: string[]; asset_ids: string[]; floor_id: string | null }
  is_group?: boolean
  member_count?: number
  member_ids?: string[]
  group_type?: string
}

interface RawSourceHealth {
  source: string
  label: string
  state: string
  badge_tone: string
  message: string
}

interface RawDecisionResponse {
  payload: {
    building_id: string
    issues: RawIssueItem[]
    overflow_issues?: RawIssueItem[]
    overflow_count?: number
    selected_issue_id: string | null
    source_health: RawSourceHealth[]
    active_posture: string | null
  } | null
  site_id: string
  fetched_at: string
}

function mapRawIssue(i: RawIssueItem): CockpitIssuesPayload['issues'][number] {
  return {
    id: i.id,
    title: i.title,
    summary: i.summary,
    severity: i.severity as CockpitIssuesPayload['issues'][number]['severity'],
    source: i.source as CockpitIssuesPayload['issues'][number]['source'],
    status: i.status as CockpitIssuesPayload['issues'][number]['status'],
    owner: i.owner,
    owner_team: i.owner_team,
    opened_at: i.opened_at ?? new Date().toISOString(),
    updated_at: i.updated_at ?? new Date().toISOString(),
    sla_due_at: i.sla_due_at,
    stale: i.stale ?? false,
    impact_summary: i.impact_summary,
    recommended_action: i.recommended_action,
    confidence: i.confidence,
    confidence_label: i.confidence_label,
    subsystem: i.subsystem,
    location: {
      zone_ids: i.location?.zone_ids ?? [],
      asset_ids: i.location?.asset_ids ?? [],
      floor_id: i.location?.floor_id ?? null,
    },
    is_group: i.is_group,
    member_count: i.member_count,
    member_ids: i.member_ids,
    group_type: i.group_type,
  }
}

function mapIssuesPayload(raw: RawDecisionResponse): CockpitIssuesPayload | null {
  if (!raw.payload) return null
  return {
    issues: raw.payload.issues.map(mapRawIssue),
    overflow_issues: raw.payload.overflow_issues?.map(mapRawIssue) ?? [],
    overflow_count: raw.payload.overflow_count ?? 0,
    selectedIssueId: raw.payload.selected_issue_id,
    sourceHealth: raw.payload.source_health.map((s) => ({
      source: s.source as CockpitIssuesPayload['sourceHealth'][number]['source'],
      label: s.label,
      state: s.state as CockpitIssuesPayload['sourceHealth'][number]['state'],
      badge_tone: s.badge_tone as CockpitIssuesPayload['sourceHealth'][number]['badge_tone'],
      message: s.message,
    })),
    posture: raw.payload.active_posture,
  }
}

function useCockpitIssues(siteId: string) {
  const [issuesPayload, setIssuesPayload] = useState<CockpitIssuesPayload | null>(null)

  useEffect(() => {
    let mounted = true
    let timer: ReturnType<typeof setInterval> | null = null

    async function load() {
      try {
        const res = await authorizedFetch(`/api/cockpit/decision/${encodeURIComponent(siteId)}`)
        if (res.ok && mounted) {
          const data = await res.json() as RawDecisionResponse
          setIssuesPayload(mapIssuesPayload(data))
        }
      } catch {
        // Issues failures are silent — cockpit continues with existing state
      }
    }

    load()
    timer = setInterval(load, POLL_INTERVAL_MS)

    return () => {
      mounted = false
      if (timer) clearInterval(timer)
    }
  }, [siteId])

  return issuesPayload
}

function buildCockpitSummary(
  props: OverviewCockpitHostProps & { healthThreshold: number; warningThreshold: number; criticalThreshold: number },
  lastUpdatedAt: number | null,
  loading: boolean,
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
    dataFreshnessLabel: formatFreshness(lastUpdatedAt, loading),
    siteFloors: props.siteFloors ?? null,
    healthThreshold: props.healthThreshold,
    warningThreshold: props.warningThreshold,
    criticalThreshold: props.criticalThreshold,
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
  const { payload, hvacOverview, energyTelemetry, equipment, lastUpdatedAt, loading } = useBuildingStatePayload(siteId)
  const issuesPayload = useCockpitIssues(siteId)
  const waterTelemetry = useWaterTelemetry(siteId, onboardingPhase)
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

  const handleIssueAction = useCallback(async (issueId: string, action: CockpitIssueActionType) => {
    try {
      await authorizedFetch(
        `/api/cockpit/issues/${encodeURIComponent(siteId)}/${encodeURIComponent(issueId)}/action`,
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            action,
            actor_id: 'operator',
            actor_label: 'Operator',
            evidence_refs: [],
          }),
        },
      )
    } catch {
      // Action failures are silent — operator sees no state change; backend logs it
    }
  }, [siteId])

  // Load thresholds from canonical API
  const [siteThresholds, setSiteThresholds] = useState<{ health: { healthy: number; warning: number; critical: number }; risk: { medium: number; high: number; critical: number } } | null>(null)
  useEffect(() => {
    let mounted = true
    authorizedFetch(`/api/settings/site-thresholds?site_id=${encodeURIComponent(siteId)}`)
      .then((res) => res.ok ? res.json() : null)
      .then((data) => { if (mounted && data) setSiteThresholds(data) })
      .catch(() => {})
    return () => { mounted = false }
  }, [siteId])

  const state = useMemo(() => {
    const { healthy: ht, warning: wt, critical: ct } = siteThresholds?.health ?? { healthy: 85, warning: 65, critical: 40 }
    const thresholds = siteThresholds ?? { health: { healthy: ht, warning: wt, critical: ct }, risk: { medium: 31, high: 61, critical: 81 } }

    const summary = buildCockpitSummary(
      { siteId, siteName, gpsLat, gpsLon, orientationDegrees, onboardingPhase, posture, activeAlerts, predictionsCount, equipmentCount, siteFloors, healthThreshold: ht, warningThreshold: wt, criticalThreshold: ct },
      lastUpdatedAt,
      loading,
    )
    // Collect all known equipment types from module scopes
    const KNOWN_EQUIPMENT_TYPES = new Set(
      ['overview', 'hvac', 'energy', 'lighting', 'water', 'fire', 'security', 'solar_bess', 'occupancy']
        .flatMap((mid) => getModuleScope(mid).equipmentTypes),
    )
    // When a module scope is active, only equipment types from that scope pass through.
    // In overview mode, all known equipment types pass through.
    const scopeTypes = systemFilter ? getModuleScope(systemFilter).equipmentTypes : [...KNOWN_EQUIPMENT_TYPES]
    const activeTypeSet = new Set(scopeTypes)

    const equipmentWarnings: EquipmentWarningInput[] = (equipment ?? [])
      .filter((eq) => {
        const type = (eq.equipment_type || eq.type || '').toLowerCase()
        return (eq.health_score ?? 100) < ht && activeTypeSet.has(type)
      })
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
          health_state: (eq.health_score ?? 100) >= ct ? 'degraded' : 'critical',
          zone_id: zoneKey,
        }
      })
      return mapCockpitState(summary, payload, hvacOverview, energyTelemetry, undefined, systemFilter, equipmentWarnings, thresholds, waterTelemetry)
  }, [siteId, siteName, gpsLat, gpsLon, orientationDegrees, onboardingPhase, posture, activeAlerts, predictionsCount, equipmentCount, lastUpdatedAt, payload, hvacOverview, energyTelemetry, systemFilter, siteFloors, equipment, siteThresholds, waterTelemetry, loading])

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
      issuesPayload={issuesPayload}
      onIssueAction={handleIssueAction}
    />
  )
}
