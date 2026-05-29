export type CockpitRenderMode = 'embedded' | 'operator' | 'wall'
export type CockpitGuidanceMode = 'waiting' | 'none' | 'watch' | 'prepare' | 'intervene_soon' | 'act_now'

export interface CockpitMetricTone {
  tone: 'normal' | 'warning' | 'elevated' | 'critical'
}

export interface CockpitSitePulse extends CockpitMetricTone {
  attentionScore: number
  activeConditionCount: number
  emergingRiskCount: number
  equipmentWarningCount: number
  evidenceStrength: 'weak' | 'moderate' | 'strong'
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
  impact: string
  summary: string
  tradeoff: string
  confidence: string
}

export type CockpitTwinRiskLevel = 'stable' | 'drift' | 'approaching' | 'critical'

/** Email complaint cluster — surfaces in cockpit when email_count >= 3 */
export interface EmailClusterData {
  clusterId: string
  zoneId: string
  zoneName: string
  floor: string
  emailCount: number
  complaintType: string
  severity: 'low' | 'medium' | 'high' | 'critical'
  summary: string
}

export interface CockpitTwinFloor {
  id: string
  label: string
  meshId: string
  level: CockpitTwinRiskLevel
  intensity: number
  spread: number
  elevation: number
  isManaged?: boolean
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
  /** Occupant email cluster heatmap data — present when email_count >= 3 */
  intakeCluster?: EmailClusterData
}

export interface CockpitTwinFlowPath {
  id: string
  d: string
  fromFloorId: string | null
  toFloorId: string | null
  intensity: number
  direction: 'upward' | 'downward' | 'lateral' | 'contained' | 'building_wide'
}

export interface CockpitVisualTwin {
  headline: string
  activeLabel: string
  modeLabel: string
  motionProfile: 'waiting' | 'calm' | 'watch' | 'alert'
  breathingIntensity: number
  flowSpeed: number
  consumptionIntensity: number
  focusFloorId: string | null
  floors: CockpitTwinFloor[]
  zoneSignals: CockpitTwinZoneSignal[]
  flowPaths: CockpitTwinFlowPath[]
  energyCentre: {
    online: boolean
    totalKw: number
    hvacKw: number
    lightingKw: number
    powerKw: number
    loadRatio: number
    powerShareRatio: number
    stateLabel: 'low' | 'moderate' | 'high' | 'critical'
  }
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

/** Equipment warning surfaced from health-score thresholding — drives signal queue and modules block */
export interface CockpitEquipmentWarning {
  id: string
  equipmentId: string
  equipmentCode: string
  equipmentType: string
  floorId: string
  healthScore: number
  healthState: CockpitHealthState
  faultType?: string
  zoneId?: string
}

export type CockpitRiskBand = 'low' | 'medium' | 'high' | 'critical'
export type CockpitPolicyLevel = 'site_asset_criticality' | 'site_asset' | 'site' | 'posture' | 'system'
export type CockpitConstraintType = 'comfort' | 'asset' | 'cost' | 'compliance'
export type CockpitHealthState = 'healthy' | 'stable' | 'watch' | 'degraded' | 'critical'
export type CockpitHealthTrend = 'improving' | 'flat' | 'declining' | 'volatile'
export type CockpitCriticality = 'low' | 'medium' | 'high' | 'mission_critical'

export interface CockpitAffectedScope {
  zones: string[]
  assets: string[]
  occupantsEstimate: number | null
}

export interface CockpitSeverityInterpretation {
  riskScore: number | null
  riskBand: CockpitRiskBand | null
  thresholdReason: string | null
  policySource: string | null
  policyLevel: CockpitPolicyLevel | null
  constraintType: CockpitConstraintType | null
  timeToConstraintBreachMin: number | null
  affectedScope: CockpitAffectedScope | null
  healthScore: number | null
  healthState: CockpitHealthState | null
  healthTrend: CockpitHealthTrend | null
  healthReason: string | null
  assetClass: string | null
  criticality: CockpitCriticality | null
}

export interface BuildingGeometryData {
  floor_count: number
  shape: string
  setbacks: { floor: number; ratio: number }[]
  facade: string
  footprint_width_depth_ratio: number
  roof_equipment: boolean
  source: string
}

export interface CockpitState {
  site: {
    id: string
    name: string
    latitude: number | null
    longitude: number | null
    orientationDegrees: number | null
    onboardingPhase: 'shadow' | 'advisory' | 'supervised' | 'auto'
    posture: string
    mode: CockpitGuidanceMode
    renderState: 'waiting' | 'live'
    dataFreshnessLabel: string
    buildingGeometry?: BuildingGeometryData | null
  }
  sitePulse: CockpitSitePulse
  primaryMetric: CockpitPrimaryMetric
  activeCondition: CockpitActiveCondition
  decision: CockpitDecision
  visualTwin: CockpitVisualTwin
  evidence: CockpitEvidence
  severity: CockpitSeverityInterpretation
  emergingRisks: CockpitRiskItem[]
  /** Active equipment warnings from health-score thresholding — drives signal queue when secondary_tensions is empty */
  equipmentWarnings: CockpitEquipmentWarning[]
  /** Active occupant complaint clusters (count >= 3) — email heatmap signals */
  emailClusters: EmailClusterData[]
  /** Active system filter — when set, only zones/equipment of this system type render */
  systemFilter?: 'hvac' | 'energy' | 'lighting' | 'water' | 'fire' | 'security' | 'solar_bess' | null
}

export interface ModelReadiness {
  siteId: string
  trainingEnabled: boolean
  ready: boolean
  activeModelCount: number
  equipmentTypesCovered: string[]
  lastTrainingAt: string | null
  message: string
}
