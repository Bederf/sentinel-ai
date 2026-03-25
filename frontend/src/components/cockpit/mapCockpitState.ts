import { buildDecisionSurface } from '@/lib/decisionSurface'
import type { CockpitState, CockpitTwinRiskLevel } from './types'
import { DEFAULT_COCKPIT_THRESHOLD_POLICY, type CockpitThresholdPolicy } from './thresholdPolicy'

export interface CockpitDecisionPayload {
  building_id: string
  alert_text?: string | null
  reasoning_summary?: string | null
  active_posture?: string | null
  time_to_discomfort?: number | null
  time_confidence?: string | number | null
  estimated_impact?: unknown
  recommended_action?: string | null
  urgency_score?: number | null
  urgency_components?: Record<string, number> | null
  affected_zone_ids?: string[] | null
  primary_asset_id?: string | null
  building_metadata?: {
    deployment_mode?: 'ghost' | 'advisory' | 'supervised' | 'autonomous'
    floor_labels?: Record<string, string>
    floor_stack_order?: string[]
  } | null
}

export interface CockpitSiteSummary {
  siteId: string
  siteName: string
  posture?: string | null
  activeAlerts: number
  predictionsCount: number
  equipmentCount: number
  dataFreshnessLabel: string
}

function getTone(riskBand: CockpitState['severity']['riskBand']): CockpitState['primaryMetric']['tone'] {
  if (riskBand === 'critical') return 'critical'
  if (riskBand === 'high') return 'elevated'
  if (riskBand === 'medium') return 'warning'
  return 'normal'
}

function getEvidenceStrength(score: number): 'strong' | 'moderate' | 'limited' {
  if (score >= 0.75) return 'strong'
  if (score >= 0.45) return 'moderate'
  return 'limited'
}

function formatPostureLabel(posture: string | null | undefined): string {
  if (!posture) return 'Watch mode'

  const normalized = posture.trim().toLowerCase()
  if (normalized === 'comfort_priority') return 'Comfort first'
  if (normalized === 'energy_priority') return 'Energy first'
  if (normalized === 'asset_priority') return 'Asset protection'
  if (normalized === 'adaptive_intelligence') return 'Watch mode'

  return posture.replace(/_/g, ' ')
}

const DEFAULT_FLOOR_ORDER = ['R', 'L2', 'L1', 'L0', 'G', 'B1']

function clamp01(value: number): number {
  return Math.max(0, Math.min(1, value))
}

function extractFloorCode(value: string | null | undefined): string | null {
  if (!value) return null
  const match = value.match(/(?:^|-)(R|L\d+|G|B\d+)(?:-|$)/i)
  return match?.[1]?.toUpperCase() ?? null
}

function formatFloorLabel(floorId: string, customLabels?: Record<string, string> | null): string {
  if (customLabels?.[floorId]) return customLabels[floorId]
  if (floorId === 'R') return 'Roof'
  if (floorId === 'G') return 'Ground'
  if (floorId === 'B1') return 'Basement B1'
  if (floorId.startsWith('B')) return `Basement ${floorId.slice(1)}`
  if (floorId.startsWith('L')) return `Level ${floorId.slice(1)}`
  return floorId
}

function toPercent(score: number): number {
  return Math.round(clamp01(score) * 100)
}

function riskBandFromScore(
  score: number,
  thresholds: CockpitThresholdPolicy['risk'],
): CockpitState['severity']['riskBand'] {
  const riskScore = toPercent(score)

  if (riskScore >= thresholds.critical) return 'critical'
  if (riskScore >= thresholds.high) return 'high'
  if (riskScore >= thresholds.medium) return 'medium'
  return 'low'
}

function riskLevelFromBand(riskBand: CockpitState['severity']['riskBand']): CockpitTwinRiskLevel {
  if (riskBand === 'critical') return 'critical'
  if (riskBand === 'high') return 'approaching'
  if (riskBand === 'medium') return 'drift'
  return 'stable'
}

function buildThresholdReason(
  score: number,
  riskBand: CockpitState['severity']['riskBand'],
  thresholds: CockpitThresholdPolicy['risk'],
): string {
  const riskScore = toPercent(score)

  if (riskBand === 'critical') {
    return `Risk ${riskScore} is at or above the critical threshold of ${thresholds.critical}`
  }

  if (riskBand === 'high') {
    return `Risk ${riskScore} is at or above the high threshold of ${thresholds.high}`
  }

  if (riskBand === 'medium') {
    return `Risk ${riskScore} is at or above the medium threshold of ${thresholds.medium}`
  }

  return `Risk ${riskScore} is below the medium threshold of ${thresholds.medium}`
}

function motionProfileFromRiskBand(riskBand: CockpitState['severity']['riskBand']): CockpitState['visualTwin']['motionProfile'] {
  if (riskBand === 'critical') return 'alert'
  if (riskBand === 'high' || riskBand === 'medium') return 'watch'
  return 'calm'
}

function buildVisualTwin(
  resolvedPayload: CockpitDecisionPayload,
  surface: ReturnType<typeof buildDecisionSurface>,
  urgencyScore: number,
  policy: CockpitThresholdPolicy,
): CockpitState['visualTwin'] {
  const floorLabels = resolvedPayload.building_metadata?.floor_labels ?? null
  const configuredOrder = resolvedPayload.building_metadata?.floor_stack_order ?? []
  const focusFloorId =
    extractFloorCode(resolvedPayload.affected_zone_ids?.[0] ?? null)
    ?? extractFloorCode(resolvedPayload.primary_asset_id ?? null)
    ?? null

  const floorOrder = [...configuredOrder]
  for (const fallback of DEFAULT_FLOOR_ORDER) {
    if (!floorOrder.includes(fallback)) {
      floorOrder.push(fallback)
    }
  }
  if (focusFloorId && !floorOrder.includes(focusFloorId)) {
    floorOrder.unshift(focusFloorId)
  }

  const anchorIndex = focusFloorId ? floorOrder.indexOf(focusFloorId) : -1
  const floors = floorOrder.map((floorId, index) => {
    const distance = anchorIndex >= 0 ? Math.abs(index - anchorIndex) : Number.POSITIVE_INFINITY
    const spread = anchorIndex >= 0 ? clamp01(urgencyScore - distance * 0.22) : 0
    const intensity = anchorIndex >= 0
      ? clamp01(0.18 + spread * 0.82)
      : 0.16
    const level = anchorIndex >= 0
      ? riskLevelFromBand(riskBandFromScore(index === anchorIndex ? urgencyScore : spread * 0.9, policy.risk))
      : 'stable'

    return {
      id: floorId,
      label: formatFloorLabel(floorId, floorLabels),
      meshId: `floor:${floorId}`,
      level,
      intensity,
      spread,
      elevation: (floorOrder.length - index - 1) * 2.25,
    }
  })

  const sourceSignals = (resolvedPayload.affected_zone_ids ?? []).length > 0
    ? (resolvedPayload.affected_zone_ids ?? [])
    : resolvedPayload.primary_asset_id
      ? [resolvedPayload.primary_asset_id]
      : []

  const floorSlots = new Map<string, number>()
  const zoneSignals = sourceSignals.map((sourceId, index) => {
    const floorId = extractFloorCode(sourceId) ?? focusFloorId ?? floorOrder[Math.min(index, floorOrder.length - 1)] ?? 'L0'
    const slot = floorSlots.get(floorId) ?? 0
    floorSlots.set(floorId, slot + 1)
    const weight = clamp01(urgencyScore - index * 0.12)

    return {
      zoneId: sourceId,
      label: sourceId.replace(/^Zone-/, '').replace(/-/g, ' '),
      floorId,
      meshId: `mesh:${sourceId.toLowerCase().replace(/[^a-z0-9]+/g, '-')}`,
      level: riskLevelFromBand(riskBandFromScore(weight, policy.risk)),
      weight,
      slot,
      isPrimary: index === 0,
      actionLabel: surface.action.summary,
    }
  })

  return {
    headline: surface.time.value === 'Unknown'
      ? 'No comfort risk right now'
      : `${zoneSignals[0]?.label ?? 'This area'} will breach in ${surface.time.value}`,
    activeLabel: zoneSignals[0]?.label ?? surface.cause,
    modeLabel: surface.presentation.statusLabel,
    motionProfile: motionProfileFromRiskBand(riskBandFromScore(urgencyScore, policy.risk)),
    focusFloorId,
    floors,
    zoneSignals,
  }
}

function buildFallbackPayload(summary: CockpitSiteSummary): CockpitDecisionPayload {
  return {
    building_id: summary.siteId,
    alert_text: 'No comfort risk for the next 30 minutes.',
    reasoning_summary: 'Live signals are steady. Keep watching for the next drift or breach window.',
    active_posture: summary.posture ?? 'adaptive_intelligence',
    time_to_discomfort: null,
    time_confidence: 'steady',
    estimated_impact: 'No immediate comfort, uptime, or compliance impact.',
    recommended_action: 'No action needed. Keep watching the site.',
    urgency_score: 0.18,
    urgency_components: { comfort: 0.06, asset_risk: 0.06, cost: 0.06 },
    affected_zone_ids: [],
    primary_asset_id: null,
    building_metadata: {
      deployment_mode: 'advisory',
    },
  }
}

export function mapCockpitState(
  summary: CockpitSiteSummary,
  payload?: CockpitDecisionPayload | null,
  policy: CockpitThresholdPolicy = DEFAULT_COCKPIT_THRESHOLD_POLICY,
): CockpitState {
  const resolvedPayload = payload ?? buildFallbackPayload(summary)
  const surface = buildDecisionSurface(resolvedPayload)
  const urgencyScore = resolvedPayload.urgency_score ?? 0
  const riskBand = riskBandFromScore(urgencyScore, policy.risk)
  const tone = getTone(riskBand)
  const evidenceStrength = getEvidenceStrength(urgencyScore)
  const primaryMetricValue = surface.time.value === 'Unknown' ? 'Stable' : surface.time.value
  const confidenceLabel = surface.time.detail
  const visualTwin = buildVisualTwin(resolvedPayload, surface, urgencyScore, policy)
  const primaryMetricLabel = 'Time to Comfort Breach'

  return {
    site: {
      id: summary.siteId,
      name: summary.siteName,
      posture: formatPostureLabel(resolvedPayload.active_posture ?? summary.posture),
      mode: surface.mode,
      dataFreshnessLabel: summary.dataFreshnessLabel,
    },
    sitePulse: {
      tone,
      attentionScore: urgencyScore,
      activeConditionCount: Math.max(summary.activeAlerts, payload ? 1 : 0),
      emergingRiskCount: Math.max(summary.predictionsCount, 0),
      evidenceStrength,
    },
    primaryMetric: {
      tone,
      label: primaryMetricLabel,
      value: primaryMetricValue,
      detail: confidenceLabel,
    },
    activeCondition: {
      summary: surface.cause,
      rationale: resolvedPayload.reasoning_summary?.trim()
        || 'Live signals are steady. Keep watching for the next drift window.',
      confidenceLabel,
    },
    decision: {
      mode: surface.mode,
      impact: surface.impact,
      summary: surface.action.summary,
      command: surface.action.bmsGuide?.command ?? surface.action.operatorPrompt,
      operatorPrompt: surface.action.operatorPrompt,
      expectedOutcome: surface.action.expectedOutcome,
      tradeoff: surface.action.tradeoff,
      confidence: confidenceLabel,
      verification: surface.action.bmsGuide?.verification ?? surface.action.expectedOutcome,
      navigationPath: surface.action.bmsGuide?.navigationPath ?? [],
    },
    visualTwin,
    evidence: {
      strength: evidenceStrength,
      summary: payload
        ? `Built from live site signals and ${summary.dataFreshnessLabel.toLowerCase()}.`
        : 'Built from live site signals and current watch rules.',
      refs: [
        ...(resolvedPayload.primary_asset_id ? [`asset:${resolvedPayload.primary_asset_id}`] : []),
        ...(resolvedPayload.affected_zone_ids ?? []).slice(0, 2).map((zoneId) => `zone:${zoneId}`),
        ...Object.keys(resolvedPayload.urgency_components ?? {}).slice(0, 3).map((key) => `signal:${key}`),
      ],
    },
    severity: {
      riskScore: toPercent(urgencyScore),
      riskBand,
      thresholdReason: buildThresholdReason(urgencyScore, riskBand, policy.risk),
      policySource: policy.source,
    },
    emergingRisks: payload
      ? [
          {
            id: 'risk-horizon',
            title: `${surface.time.label} is still the main risk clock`,
            detail: `If nothing changes, the next breach window is still set by ${surface.time.label.toLowerCase()}.`,
          },
          {
            id: 'risk-spread',
            title: 'Watch nearby zones next',
            detail: resolvedPayload.affected_zone_ids && resolvedPayload.affected_zone_ids.length > 0
              ? `Watch ${resolvedPayload.affected_zone_ids.slice(0, 2).join(', ')} for spillover or recovery drift.`
              : 'Watch neighboring zones and dependent systems for spillover or recovery drift.',
          },
        ]
      : [
          {
            id: 'risk-watch',
            title: 'No active breach forecast',
            detail: 'Keep watching for the next drift window.',
          },
          {
            id: 'risk-evidence',
            title: 'Keep telemetry fresh',
            detail: 'If telemetry freshness drops, trust the twin less before escalating action.',
          },
        ],
  }
}
