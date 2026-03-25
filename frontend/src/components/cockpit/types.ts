import type { DeploymentMode } from '@/lib/decisionSurface'

export type CockpitRenderMode = 'embedded' | 'operator' | 'wall'

export interface CockpitMetricTone {
  tone: 'normal' | 'warning' | 'elevated' | 'critical'
}

export interface CockpitSitePulse extends CockpitMetricTone {
  attentionScore: number
  activeConditionCount: number
  emergingRiskCount: number
  evidenceStrength: 'strong' | 'moderate' | 'limited'
}

export interface CockpitPrimaryMetric extends CockpitMetricTone {
  label: string
  value: string
  detail: string
}

export interface CockpitActiveCondition {
  summary: string
  rationale: string
  confidenceLabel: string
}

export interface CockpitDecision {
  mode: DeploymentMode
  impact: string
  summary: string
  command: string
  operatorPrompt: string
  expectedOutcome: string
  tradeoff: string
  confidence: string
  verification: string
  navigationPath: string[]
}

export type CockpitTwinRiskLevel = 'stable' | 'drift' | 'approaching' | 'critical'

export interface CockpitTwinFloor {
  id: string
  label: string
  meshId: string
  level: CockpitTwinRiskLevel
  intensity: number
  spread: number
  elevation: number
}

export interface CockpitTwinZoneSignal {
  zoneId: string
  label: string
  floorId: string
  meshId: string
  level: CockpitTwinRiskLevel
  weight: number
  slot: number
  isPrimary: boolean
  actionLabel: string
}

export interface CockpitVisualTwin {
  headline: string
  activeLabel: string
  modeLabel: string
  motionProfile: 'calm' | 'watch' | 'alert'
  focusFloorId: string | null
  floors: CockpitTwinFloor[]
  zoneSignals: CockpitTwinZoneSignal[]
}

export interface CockpitEvidence {
  strength: 'strong' | 'moderate' | 'limited'
  summary: string
  refs: string[]
}

export interface CockpitRiskItem {
  id: string
  title: string
  detail: string
}

export type CockpitRiskBand = 'low' | 'medium' | 'high' | 'critical'

export interface CockpitSeverityInterpretation {
  riskScore: number | null
  riskBand: CockpitRiskBand | null
  thresholdReason: string | null
  policySource: 'default' | 'settings'
}

export interface CockpitState {
  site: {
    id: string
    name: string
    posture: string
    mode: DeploymentMode
    dataFreshnessLabel: string
  }
  sitePulse: CockpitSitePulse
  primaryMetric: CockpitPrimaryMetric
  activeCondition: CockpitActiveCondition
  decision: CockpitDecision
  visualTwin: CockpitVisualTwin
  evidence: CockpitEvidence
  severity: CockpitSeverityInterpretation
  emergingRisks: CockpitRiskItem[]
}
