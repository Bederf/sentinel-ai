export type CockpitRenderMode = 'embedded' | 'operator' | 'wall'
export type CockpitGuidanceMode = 'waiting' | 'none' | 'watch' | 'prepare' | 'intervene_soon' | 'act_now'

/** Canonical module ID — single source of truth for all module/tab references. */
export type CockpitModuleId =
  | 'overview'
  | 'hvac'
  | 'energy'
  | 'lighting'
  | 'water'
  | 'fire'
  | 'security'
  | 'solar_bess'
  | 'occupancy'
  | 'controls'

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

/** Water telemetry — fetched independently from the water API */
export interface WaterTelemetry {
  flowLpm: number | null
  pressureBar: number | null
  totalM3: number | null
  dailyM3: number | null
  leakDetected: boolean | null
  lastUpdated: string | null
  sourceHealthy: boolean
}

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
  /** Module IDs explicitly related to this evidence. Used for cross-system discovery. */
  relatedModuleIds?: CockpitModuleId[]
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

export interface CockpitHealthThresholds {
  healthy: number
  warning: number
  critical: number
}

export interface CockpitRiskThresholds {
  medium: number
  high: number
  critical: number
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
  /** Active module scope — when set, only this module's zones/equipment/evidence render */
  systemFilter?: CockpitModuleId | null
    /** Water telemetry — populated when systemFilter === 'water' */
  waterTelemetry?: WaterTelemetry
  /** Backend-resolved thresholds — single source of truth for cockpit rendering */
  thresholds: {
    health: CockpitHealthThresholds
    risk: CockpitRiskThresholds
  }
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

// ─── Phase 209 — Issue-based cockpit types ────────────────────────────────────

export type CockpitIssueSeverity = 'critical' | 'high' | 'medium' | 'low'
export type CockpitIssueSource = 'bms' | 'intake' | 'tech'
export type CockpitIssueStatus = 'new' | 'triaged' | 'in_progress' | 'resolved'
export type CockpitIssueActionType = 'acknowledge' | 'assign' | 'create_work_order' | 'escalate'
export type CockpitSourceHealthState = 'healthy' | 'stale' | 'degraded' | 'unavailable'

export interface CockpitIssueLocation {
  zone_ids: string[]
  asset_ids: string[]
  floor_id: string | null
}

export interface CockpitIssueItem {
  id: string
  title: string
  summary: string
  severity: CockpitIssueSeverity
  source: CockpitIssueSource
  status: CockpitIssueStatus
  owner: string | null
  owner_team: string | null
  opened_at: string
  updated_at: string
  sla_due_at: string | null
  stale: boolean
  impact_summary: string | null
  recommended_action: string | null
  confidence: number | null
  confidence_label: string | null
  subsystem: string | null
  location: CockpitIssueLocation
  // Phase 224 — cascade grouping
  is_group?: boolean
  member_count?: number
  member_ids?: string[]
  group_type?: string
}

export interface CockpitIssueSourceHealth {
  source: CockpitIssueSource
  label: string
  state: CockpitSourceHealthState
  badge_tone: 'normal' | 'warning' | 'critical'
  message: string
}

export interface CockpitIssuesPayload {
  issues: CockpitIssueItem[]
  selectedIssueId: string | null
  sourceHealth: CockpitIssueSourceHealth[]
  posture: string | null
  // Phase 224 — overflow rail
  overflow_issues?: CockpitIssueItem[]
  overflow_count?: number
}
