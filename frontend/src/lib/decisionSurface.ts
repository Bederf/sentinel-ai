import { getBmsNavigationRoot } from '../config/bmsNavigationMap'
import { getEquipmentInstructions } from '../config/equipmentTypeMap'

export type DeploymentMode = 'ghost' | 'advisory' | 'supervised' | 'autonomous'

export interface DecisionSurfaceInput {
  building_id?: string | null
  primary_asset_id?: string | null
  alert_text?: string | null
  reasoning_summary?: string | null
  recommended_action?: string | null
  time_to_discomfort?: number | null
  time_confidence?: string | number | null
  estimated_impact?: unknown
  active_posture?: string | null
  posture_weights?: Record<string, number> | null
  urgency_components?: Record<string, number> | null
  building_metadata?: {
    deployment_mode?: string | null
  } | null
}

export interface BmsExecutionGuide {
  assetId: string | null
  navigationPath: string[]
  command: string
  verification: string
}

export interface DecisionSurfaceViewModel {
  mode: DeploymentMode
  modeLabel: string
  cause: string
  impact: string
  time: {
    label: string
    value: string
    detail: string
  }
  action: {
    summary: string
    operatorPrompt: string
    expectedOutcome: string
    tradeoff: string
    bmsGuide: BmsExecutionGuide | null
  }
  behavior: {
    showInstructions: boolean
    showApproval: boolean
    showResultOnly: boolean
  }
}

type ParsedAsset = {
  site: string | null
  type: string | null
  zone: string | null
}

function normalizeMode(mode: string | null | undefined): DeploymentMode {
  if (mode === 'advisory' || mode === 'supervised' || mode === 'autonomous') {
    return mode
  }
  return 'ghost'
}

function formatLabel(value: string): string {
  return value
    .replace(/_/g, ' ')
    .replace(/\b\w/g, (char) => char.toUpperCase())
}

function parseAsset(assetId: string | null | undefined): ParsedAsset {
  if (!assetId) {
    return { site: null, type: null, zone: null }
  }

  const [site, type, zone] = assetId.split('-')
  return {
    site: site ?? null,
    type: type?.toUpperCase() ?? null,
    zone: zone ?? null,
  }
}

function expandZone(zone: string | null): string {
  if (!zone) return 'Target equipment'
  if (zone === 'B1') return 'Basement B1'
  if (zone === 'G') return 'Ground'
  if (zone.startsWith('L')) return `Level ${zone.slice(1)}`
  return zone
}

function formatImpact(impact: unknown): string {
  if (typeof impact === 'string' && impact.trim().length > 0) {
    return impact
  }

  if (impact && typeof impact === 'object') {
    const entries = Object.entries(impact as Record<string, unknown>).filter(([, value]) => value !== null && value !== '')
    if (entries.length > 0) {
      return entries
        .slice(0, 3)
        .map(([key, value]) => `${formatLabel(key)}: ${String(value)}`)
        .join(' | ')
    }
  }

  return 'Impact is being assessed against comfort, uptime, and operating constraints.'
}

function getPrimaryMetricLabel(input: DecisionSurfaceInput): string {
  const buildingId = input.building_id ?? ''
  const assetId = input.primary_asset_id ?? ''
  if (buildingId === 'site-002' || assetId.startsWith('S002-')) {
    return 'Time to Discomfort'
  }
  return 'Time to Constraint Breach'
}

function formatPrimaryMetricValue(minutes: number | null | undefined): string {
  if (typeof minutes !== 'number' || Number.isNaN(minutes)) {
    return 'Unknown'
  }
  return `${minutes} min`
}

function formatConfidence(value: string | number | null | undefined): string {
  if (typeof value === 'number') {
    return `Confidence ${(value * 100).toFixed(0)}%`
  }
  if (typeof value === 'string' && value.trim().length > 0) {
    return `Confidence ${value}`
  }
  return 'Confidence unavailable'
}

function inferTradeoff(input: DecisionSurfaceInput): string {
  const posture = input.active_posture ?? ''
  const weights = input.posture_weights ?? {}
  const comfortWeight = weights.comfort ?? 0
  const costWeight = weights.cost ?? weights.energy ?? 0
  const assetWeight = weights.asset ?? 0

  if (posture.includes('comfort') || comfortWeight >= costWeight && comfortWeight >= assetWeight && comfortWeight >= 0.5) {
    return 'Prioritises comfort protection over energy savings while the fault remains active.'
  }

  if (posture.includes('energy') || posture.includes('cost') || costWeight >= comfortWeight && costWeight >= assetWeight) {
    return 'Accepts a tighter comfort margin to reduce energy or peak-demand exposure.'
  }

  if (assetWeight > 0) {
    return 'Protects equipment health first, even if the action is less energy-efficient in the short term.'
  }

  return 'Balances comfort, risk, and operating cost using the current site posture.'
}

function inferCommand(assetType: string | null, actionSummary: string, assetId: string | null): string {
  const instructions = getEquipmentInstructions(assetType)
  return instructions.commandTemplate(assetId ?? 'the affected asset', actionSummary)
}

function inferVerification(assetType: string | null, primaryMetricLabel: string): string {
  const instructions = getEquipmentInstructions(assetType)
  return instructions.verificationTemplate('the equipment', primaryMetricLabel)
}

export function buildBmsExecutionGuide(input: DecisionSurfaceInput): BmsExecutionGuide | null {
  const assetId = input.primary_asset_id ?? null
  if (!assetId) {
    return null
  }

  const parsed = parseAsset(assetId)
  const locationLabel = expandZone(parsed.zone)
  const navigationRoot = getBmsNavigationRoot(parsed.site)

  const navigationPath = parsed.type === 'CHILLER'
    ? [...navigationRoot, locationLabel, 'Chillers', assetId]
    : parsed.type === 'AHU'
      ? [...navigationRoot, locationLabel, 'Air Handling Units', assetId]
      : parsed.type === 'FCU' || parsed.type === 'VAV'
        ? [...navigationRoot, locationLabel, 'Zone Equipment', assetId]
        : parsed.type === 'UPS' || parsed.type === 'GEN'
          ? [...navigationRoot, locationLabel, 'Critical Power', assetId]
          : [...navigationRoot, locationLabel, assetId]

  const primaryMetricLabel = getPrimaryMetricLabel(input)

  return {
    assetId,
    navigationPath,
    command: inferCommand(parsed.type, input.recommended_action ?? 'monitor', assetId),
    verification: inferVerification(parsed.type, primaryMetricLabel),
  }
}

function buildOperatorPrompt(mode: DeploymentMode): string {
  if (mode === 'advisory') {
    return 'Execute this now in the BMS using the mapped navigation path below.'
  }
  if (mode === 'supervised') {
    return '[HOLD TO APPROVE]'
  }
  if (mode === 'autonomous') {
    return 'Autonomous execution is active. Operator interaction is disabled.'
  }
  return 'Ghost mode is active. Observe the recommendation without executing a control change.'
}

function buildExpectedOutcome(mode: DeploymentMode, actionSummary: string): string {
  if (mode === 'advisory') {
    return `Expected outcome: operator applies "${actionSummary}" in the BMS and confirms the result in live telemetry.`
  }
  if (mode === 'supervised') {
    return 'Expected outcome: once approved, SENTINEL dispatches the command and verifies telemetry before marking the action complete.'
  }
  if (mode === 'autonomous') {
    return 'Expected outcome: SENTINEL executes and reports the verified result without waiting for operator approval.'
  }
  return 'Expected outcome: recommendation remains visible for review only; no write is performed from this surface.'
}

export function buildDecisionSurface(input: DecisionSurfaceInput): DecisionSurfaceViewModel {
  const mode = normalizeMode(input.building_metadata?.deployment_mode)
  const timeLabel = getPrimaryMetricLabel(input)
  const bmsGuide = buildBmsExecutionGuide(input)
  const actionSummary = input.recommended_action?.trim() || 'Monitor the condition and keep the system under observation.'

  return {
    mode,
    modeLabel: mode === 'ghost' ? 'Ghost' : formatLabel(mode),
    cause: input.alert_text?.trim() || 'Active condition detected.',
    impact: formatImpact(input.estimated_impact),
    time: {
      label: timeLabel,
      value: formatPrimaryMetricValue(input.time_to_discomfort),
      detail: formatConfidence(input.time_confidence),
    },
    action: {
      summary: actionSummary,
      operatorPrompt: buildOperatorPrompt(mode),
      expectedOutcome: buildExpectedOutcome(mode, actionSummary),
      tradeoff: inferTradeoff(input),
      bmsGuide,
    },
    behavior: {
      showInstructions: mode === 'advisory',
      showApproval: mode === 'supervised',
      showResultOnly: mode === 'autonomous' || mode === 'ghost',
    },
  }
}
