"""
Contract management domain models for FM Commercial Intelligence.

Pydantic models matching the 018_commercial_schema.sql tables:
- Organizations (FM clients)
- Contracts (links organization to buildings)
- SLA Terms (per-contract SLA definitions)
- Asset Contracts (asset-level fee allocation)
- Condition Assessments (initial and periodic)
- Budgets (templates and allocations)
- SLA Performance (tracking)
- Contract Profitability (monthly roll-up)

Phase 48: Contract Management
"""

from datetime import date, datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field


# ============================================================================
# Enums (matching CHECK constraints in 018_commercial_schema.sql)
# ============================================================================


class OrganizationTier(str, Enum):
    """Organization tier matching organizations.tier CHECK constraint."""

    PLATINUM = "platinum"
    GOLD = "gold"
    SILVER = "silver"
    BRONZE = "bronze"


class OrganizationStatus(str, Enum):
    """Organization status matching organizations.status CHECK constraint."""

    ACTIVE = "active"
    SUSPENDED = "suspended"
    TERMINATED = "terminated"


class ContractStatus(str, Enum):
    """Contract lifecycle status matching contracts.status CHECK constraint."""

    DRAFT = "draft"
    PENDING_APPROVAL = "pending_approval"
    ACTIVE = "active"
    SUSPENDED = "suspended"
    EXPIRED = "expired"
    TERMINATED = "terminated"


class ContractType(str, Enum):
    """Contract type matching contracts.contract_type CHECK constraint."""

    COMPREHENSIVE = "comprehensive"
    PREVENTIVE = "preventive"
    REACTIVE = "reactive"
    HYBRID = "hybrid"


class SLAType(str, Enum):
    """SLA type matching sla_terms.sla_type CHECK constraint."""

    UPTIME = "uptime"
    RESPONSE_TIME = "response_time"
    RESOLUTION_TIME = "resolution_time"
    PPM_COMPLETION = "ppm_completion"
    FIRST_FIX_RATE = "first_fix_rate"


class SLAPriority(str, Enum):
    """SLA priority level matching sla_terms.priority CHECK constraint."""

    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    ALL = "all"


class MeasurementPeriod(str, Enum):
    """Measurement period matching sla_terms.measurement_period CHECK constraint."""

    MONTHLY = "monthly"
    QUARTERLY = "quarterly"
    ANNUALLY = "annually"


class PenaltyType(str, Enum):
    """Penalty type matching sla_terms.penalty_type CHECK constraint."""

    PERCENTAGE = "percentage"
    FIXED = "fixed"
    TIERED = "tiered"


class CoverageType(str, Enum):
    """Asset coverage type matching asset_contracts.coverage_type CHECK constraint."""

    FULL = "full"
    PARTS_ONLY = "parts_only"
    LABOR_ONLY = "labor_only"
    EXCLUDED = "excluded"


class CriticalityTier(str, Enum):
    """Asset criticality matching asset_contracts.criticality CHECK constraint."""

    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class AssessmentType(str, Enum):
    """Assessment type matching condition_assessments.assessment_type CHECK constraint."""

    INITIAL = "initial"
    ANNUAL = "annual"
    HANDOVER = "handover"
    AD_HOC = "ad_hoc"


class AssessmentStatus(str, Enum):
    """Assessment status matching condition_assessments.status CHECK constraint."""

    DRAFT = "draft"
    SUBMITTED = "submitted"
    APPROVED = "approved"
    DISPUTED = "disputed"


class FailureRisk(str, Enum):
    """Failure risk level matching condition_assessments.estimated_failure_risk CHECK."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class BudgetStatus(str, Enum):
    """Budget status matching budgets.status CHECK constraint."""

    DRAFT = "draft"
    APPROVED = "approved"
    LOCKED = "locked"


class SLAPerformanceStatus(str, Enum):
    """SLA performance status matching sla_performance.status CHECK constraint."""

    PENDING = "pending"
    CALCULATED = "calculated"
    INVOICED = "invoiced"
    DISPUTED = "disputed"
    RESOLVED = "resolved"


class ProfitabilityStatus(str, Enum):
    """Profitability status matching contract_profitability.status CHECK constraint."""

    PRELIMINARY = "preliminary"
    FINAL = "final"
    AUDITED = "audited"


# ============================================================================
# Phase 49: Cost Tracking & Budgeting - Additional Enums
# ============================================================================


class LaborCostType(str, Enum):
    """Labor cost subcategory for detailed tracking."""

    PLANNED_MAINTENANCE = "planned_maintenance"
    EMERGENCY_CALLOUT = "emergency_callout"
    BREAKDOWN_REPAIR = "breakdown_repair"
    TRAVEL_TIME = "travel_time"
    OVERTIME = "overtime"


class PartsCostType(str, Enum):
    """Parts cost subcategory for detailed tracking."""

    SCHEDULED_REPLACEMENT = "scheduled_replacement"
    UNPLANNED_REPAIR = "unplanned_repair"
    CONSUMABLES = "consumables"
    CALIBRATION_MATERIALS = "calibration_materials"


class CalloutType(str, Enum):
    """Callout type for billing differentiation."""

    BUSINESS_HOURS = "business_hours"
    AFTER_HOURS = "after_hours"
    WEEKEND = "weekend"
    PUBLIC_HOLIDAY = "public_holiday"


# ============================================================================
# Phase 49: Cost Line Item and Budget Template Models
# ============================================================================


class CostLineItem(BaseModel):
    """Individual cost line item for work orders and service feedback."""

    model_config = ConfigDict(from_attributes=True)

    category: str = Field(..., description="Cost category: labor, parts, subcontractor, callout")
    subcategory: str = Field(..., description="Subcategory from LaborCostType, PartsCostType, etc.")
    description: str = Field(..., description="Line item description")
    quantity: float = Field(..., ge=0, description="Quantity (hours, units, etc.)")
    unit_price_zar: float = Field(..., ge=0, description="Unit price in ZAR with 2 decimal precision")
    total_zar: float = Field(..., ge=0, description="Total price = quantity * unit_price")
    equipment_type: Optional[str] = Field(None, description="Equipment type for template linking")
    work_order_id: Optional[str] = Field(None, description="Associated work order")
    recorded_at: datetime = Field(default_factory=datetime.now, description="Timestamp when recorded")


class BudgetTemplate(BaseModel):
    """Budget template for equipment-type specific budget defaults."""

    model_config = ConfigDict(from_attributes=True)

    equipment_type: str = Field(
        ..., description="Equipment type: chiller, ahu, generator, dali_controller, power_meter"
    )
    annual_hours_planned: int = Field(..., ge=0, description="Expected planned maintenance hours per year")
    callouts_per_year: int = Field(..., ge=0, description="Average emergency callouts per year")
    parts_replacement_cycle_months: int = Field(..., ge=1, description="Typical parts replacement cycle in months")
    labor_rate_zar: float = Field(..., ge=0, description="Standard labor rate per hour in ZAR")
    typical_monthly_breakdown: Dict[str, float] = Field(
        ..., description="Monthly budget breakdown by category: labor_budget_zar, parts_budget_zar, etc."
    )


# ============================================================================
# Phase 50: SLA Monitoring & Alerts - Additional Enums
# ============================================================================


class SLAMetricType(str, Enum):
    """SLA metric type for compliance tracking (Phase 50)."""

    RESPONSE_TIME = "response_time"  # Time to acknowledge
    RESOLUTION_TIME = "resolution_time"  # Time to fix
    UPTIME_PERCENTAGE = "uptime_percentage"
    MEAN_TIME_TO_REPAIR = "mean_time_to_repair"
    PREVENTIVE_MAINTENANCE = "preventive_maintenance"


class SLABreachSeverity(str, Enum):
    """SLA breach severity levels (Phase 50)."""

    MINOR = "minor"  # 10-20% breach
    MAJOR = "major"  # 20-50% breach
    CRITICAL = "critical"  # >50% breach or safety-critical failure


class SLAComplianceStatus(str, Enum):
    """SLA compliance status for real-time monitoring (Phase 50)."""

    COMPLIANT = "compliant"
    WARNING = "warning"  # 90-99% compliant
    BREACH = "breach"  # <90% compliant


# ============================================================================
# Organization Models
# ============================================================================


class OrganizationCreate(BaseModel):
    """Data required to create a new organization."""

    code: str = Field(..., description="Unique org code, e.g. 'SITE-002'")
    name: str = Field(..., description="Full legal name")
    trading_name: Optional[str] = None
    registration_number: Optional[str] = None
    vat_number: Optional[str] = None
    primary_contact_name: Optional[str] = None
    primary_contact_email: Optional[str] = None
    primary_contact_phone: Optional[str] = None
    billing_email: Optional[str] = None
    physical_address: Optional[str] = None
    postal_address: Optional[str] = None
    industry: Optional[str] = None
    tier: Optional[OrganizationTier] = None
    status: Optional[OrganizationStatus] = OrganizationStatus.ACTIVE


class OrganizationUpdate(BaseModel):
    """Partial update for an organization."""

    name: Optional[str] = None
    trading_name: Optional[str] = None
    registration_number: Optional[str] = None
    vat_number: Optional[str] = None
    primary_contact_name: Optional[str] = None
    primary_contact_email: Optional[str] = None
    primary_contact_phone: Optional[str] = None
    billing_email: Optional[str] = None
    physical_address: Optional[str] = None
    postal_address: Optional[str] = None
    industry: Optional[str] = None
    tier: Optional[OrganizationTier] = None
    status: Optional[OrganizationStatus] = None


class Organization(BaseModel):
    """Full organization record from database."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    code: str
    name: str
    trading_name: Optional[str] = None
    registration_number: Optional[str] = None
    vat_number: Optional[str] = None
    primary_contact_name: Optional[str] = None
    primary_contact_email: Optional[str] = None
    primary_contact_phone: Optional[str] = None
    billing_email: Optional[str] = None
    physical_address: Optional[str] = None
    postal_address: Optional[str] = None
    industry: Optional[str] = None
    tier: Optional[OrganizationTier] = None
    status: Optional[OrganizationStatus] = OrganizationStatus.ACTIVE
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


# ============================================================================
# Contract Models
# ============================================================================


class ContractCreate(BaseModel):
    """Data required to create a new contract."""

    code: str = Field(..., description="Unique contract code, e.g. 'CON-SITE-002-2026-001'")
    organization_id: str
    building_id: str
    contract_type: Optional[ContractType] = None
    start_date: date
    end_date: Optional[date] = None
    auto_renew: bool = False
    notice_period_days: int = 90
    monthly_fee_zar: float
    annual_escalation_pct: float = 6.0
    payment_terms_days: int = 30
    coverage_hours: Optional[Dict[str, Any]] = None
    included_callouts_per_month: int = 0
    callout_rate_zar: Optional[float] = None
    after_hours_rate_zar: Optional[float] = None
    notes: Optional[str] = None
    special_conditions: Optional[str] = None


class ContractUpdate(BaseModel):
    """Partial update for a contract."""

    contract_type: Optional[ContractType] = None
    end_date: Optional[date] = None
    auto_renew: Optional[bool] = None
    notice_period_days: Optional[int] = None
    monthly_fee_zar: Optional[float] = None
    annual_escalation_pct: Optional[float] = None
    payment_terms_days: Optional[int] = None
    coverage_hours: Optional[Dict[str, Any]] = None
    included_callouts_per_month: Optional[int] = None
    callout_rate_zar: Optional[float] = None
    after_hours_rate_zar: Optional[float] = None
    status: Optional[ContractStatus] = None
    approved_by: Optional[str] = None
    approved_at: Optional[datetime] = None
    notes: Optional[str] = None
    special_conditions: Optional[str] = None


class Contract(BaseModel):
    """Full contract record from database."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    code: str
    organization_id: str
    building_id: str
    contract_type: Optional[ContractType] = None
    start_date: date
    end_date: Optional[date] = None
    auto_renew: bool = False
    notice_period_days: int = 90
    monthly_fee_zar: float
    annual_escalation_pct: float = 6.0
    payment_terms_days: int = 30
    coverage_hours: Optional[Dict[str, Any]] = None
    included_callouts_per_month: int = 0
    callout_rate_zar: Optional[float] = None
    after_hours_rate_zar: Optional[float] = None
    status: ContractStatus = ContractStatus.DRAFT
    approved_by: Optional[str] = None
    approved_at: Optional[datetime] = None
    notes: Optional[str] = None
    special_conditions: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


# ============================================================================
# SLA Term Models
# ============================================================================


class SLATermCreate(BaseModel):
    """Data required to create an SLA term."""

    contract_id: str
    sla_type: SLAType
    target_value: float
    target_unit: str = Field(..., description="e.g. 'percent', 'hours', 'minutes'")
    priority: SLAPriority = SLAPriority.ALL
    measurement_period: MeasurementPeriod = MeasurementPeriod.MONTHLY
    penalty_type: Optional[PenaltyType] = None
    penalty_value: Optional[float] = None
    penalty_cap_pct: Optional[float] = None
    grace_period_hours: int = 0
    is_active: bool = True


class SLATermUpdate(BaseModel):
    """Partial update for an SLA term."""

    target_value: Optional[float] = None
    target_unit: Optional[str] = None
    priority: Optional[SLAPriority] = None
    measurement_period: Optional[MeasurementPeriod] = None
    penalty_type: Optional[PenaltyType] = None
    penalty_value: Optional[float] = None
    penalty_cap_pct: Optional[float] = None
    grace_period_hours: Optional[int] = None
    is_active: Optional[bool] = None


class SLATerm(BaseModel):
    """Full SLA term record from database."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    contract_id: str
    sla_type: SLAType
    target_value: float
    target_unit: str
    priority: SLAPriority = SLAPriority.ALL
    measurement_period: MeasurementPeriod = MeasurementPeriod.MONTHLY
    penalty_type: Optional[PenaltyType] = None
    penalty_value: Optional[float] = None
    penalty_cap_pct: Optional[float] = None
    grace_period_hours: int = 0
    is_active: bool = True
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


# ============================================================================
# Asset Contract Models
# ============================================================================


class AssetContractCreate(BaseModel):
    """Data required to link equipment to a contract."""

    contract_id: str
    equipment_id: str
    allocated_fee_zar: Optional[float] = None
    fee_allocation_pct: Optional[float] = None
    coverage_type: CoverageType = CoverageType.FULL
    annual_parts_cap_zar: Optional[float] = None
    annual_labor_cap_zar: Optional[float] = None
    criticality: CriticalityTier = CriticalityTier.MEDIUM
    exclusions: Optional[str] = None
    notes: Optional[str] = None


class AssetContract(BaseModel):
    """Full asset contract link from database."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    contract_id: str
    equipment_id: str
    allocated_fee_zar: Optional[float] = None
    fee_allocation_pct: Optional[float] = None
    coverage_type: CoverageType = CoverageType.FULL
    annual_parts_cap_zar: Optional[float] = None
    annual_labor_cap_zar: Optional[float] = None
    criticality: CriticalityTier = CriticalityTier.MEDIUM
    exclusions: Optional[str] = None
    notes: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


# ============================================================================
# Condition Assessment Models
# ============================================================================


class ConditionAssessmentCreate(BaseModel):
    """Data required to create a condition assessment."""

    code: str = Field(..., description="Unique code, e.g. 'CA-001-2026-001'")
    building_id: Optional[str] = None
    equipment_id: Optional[str] = None
    contract_id: Optional[str] = None
    assessment_type: AssessmentType
    assessment_date: date
    assessor_name: str
    assessor_company: Optional[str] = None
    overall_score: Optional[int] = Field(None, ge=1, le=5)
    mechanical_score: Optional[int] = Field(None, ge=1, le=5)
    electrical_score: Optional[int] = Field(None, ge=1, le=5)
    controls_score: Optional[int] = Field(None, ge=1, le=5)
    documentation_score: Optional[int] = Field(None, ge=1, le=5)
    findings: Optional[str] = None
    defects: Optional[List[Dict[str, Any]]] = None
    recommendations: Optional[List[Dict[str, Any]]] = None
    photos: Optional[List[Dict[str, Any]]] = None
    estimated_failure_risk: Optional[FailureRisk] = None
    estimated_annual_cost_zar: Optional[float] = None
    recommended_budget_zar: Optional[float] = None


class ConditionAssessment(BaseModel):
    """Full condition assessment record from database."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    code: str
    building_id: Optional[str] = None
    equipment_id: Optional[str] = None
    contract_id: Optional[str] = None
    assessment_type: AssessmentType
    assessment_date: date
    assessor_name: str
    assessor_company: Optional[str] = None
    overall_score: Optional[int] = Field(None, ge=1, le=5)
    mechanical_score: Optional[int] = Field(None, ge=1, le=5)
    electrical_score: Optional[int] = Field(None, ge=1, le=5)
    controls_score: Optional[int] = Field(None, ge=1, le=5)
    documentation_score: Optional[int] = Field(None, ge=1, le=5)
    findings: Optional[str] = None
    defects: Optional[List[Dict[str, Any]]] = None
    recommendations: Optional[List[Dict[str, Any]]] = None
    photos: Optional[List[Dict[str, Any]]] = None
    estimated_failure_risk: Optional[FailureRisk] = None
    estimated_annual_cost_zar: Optional[float] = None
    recommended_budget_zar: Optional[float] = None
    status: AssessmentStatus = AssessmentStatus.DRAFT
    approved_by: Optional[str] = None
    approved_at: Optional[datetime] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


# ============================================================================
# Budget Models
# ============================================================================


class BudgetCreate(BaseModel):
    """Data required to create a budget entry."""

    code: str = Field(..., description="Unique code, e.g. 'BUD-SITE-002-SANDTON-2026'")
    contract_id: str
    equipment_type: Optional[str] = None
    budget_year: int
    budget_month: Optional[int] = Field(None, ge=1, le=12)
    labor_budget_zar: float = 0.0
    parts_budget_zar: float = 0.0
    consumables_budget_zar: float = 0.0
    subcontractor_budget_zar: float = 0.0
    callout_budget_zar: float = 0.0
    warning_threshold_pct: float = 80.0
    critical_threshold_pct: float = 100.0
    notes: Optional[str] = None


class BudgetUpdate(BaseModel):
    """Partial update for a budget entry (typically actuals updates)."""

    labor_budget_zar: Optional[float] = None
    parts_budget_zar: Optional[float] = None
    consumables_budget_zar: Optional[float] = None
    subcontractor_budget_zar: Optional[float] = None
    callout_budget_zar: Optional[float] = None
    labor_actual_zar: Optional[float] = None
    parts_actual_zar: Optional[float] = None
    consumables_actual_zar: Optional[float] = None
    subcontractor_actual_zar: Optional[float] = None
    callout_actual_zar: Optional[float] = None
    warning_threshold_pct: Optional[float] = None
    critical_threshold_pct: Optional[float] = None
    status: Optional[BudgetStatus] = None
    approved_by: Optional[str] = None
    approved_at: Optional[datetime] = None
    notes: Optional[str] = None


class Budget(BaseModel):
    """Full budget record from database."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    code: str
    contract_id: str
    equipment_type: Optional[str] = None
    budget_year: int
    budget_month: Optional[int] = None
    labor_budget_zar: float = 0.0
    parts_budget_zar: float = 0.0
    consumables_budget_zar: float = 0.0
    subcontractor_budget_zar: float = 0.0
    callout_budget_zar: float = 0.0
    total_budget_zar: Optional[float] = None  # GENERATED column
    labor_actual_zar: float = 0.0
    parts_actual_zar: float = 0.0
    consumables_actual_zar: float = 0.0
    subcontractor_actual_zar: float = 0.0
    callout_actual_zar: float = 0.0
    total_actual_zar: Optional[float] = None  # GENERATED column
    variance_zar: Optional[float] = None  # GENERATED column
    warning_threshold_pct: float = 80.0
    critical_threshold_pct: float = 100.0
    status: BudgetStatus = BudgetStatus.DRAFT
    approved_by: Optional[str] = None
    approved_at: Optional[datetime] = None
    notes: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


# ============================================================================
# SLA Performance Models
# ============================================================================


class SLAPerformance(BaseModel):
    """SLA performance tracking record from database."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    contract_id: str
    sla_term_id: str
    period_start: date
    period_end: date
    target_value: float
    actual_value: float
    met_target: Optional[bool] = None  # GENERATED column
    penalty_applied: bool = False
    penalty_amount_zar: Optional[float] = None
    penalty_waived: bool = False
    waiver_reason: Optional[str] = None
    incidents_count: int = 0
    total_downtime_hours: Optional[float] = None
    details: Optional[Dict[str, Any]] = None
    status: SLAPerformanceStatus = SLAPerformanceStatus.PENDING
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class SLAPerformanceWithCompliance(BaseModel):
    """Extended SLA performance with compliance tracking (Phase 50)."""

    model_config = ConfigDict(from_attributes=True)

    # Base SLAPerformance fields
    id: str
    contract_id: str
    sla_term_id: str
    period_start: date
    period_end: date
    target_value: float
    actual_value: float
    met_target: Optional[bool] = None
    penalty_applied: bool = False
    penalty_amount_zar: Optional[float] = None
    penalty_waived: bool = False
    waiver_reason: Optional[str] = None
    incidents_count: int = 0
    total_downtime_hours: Optional[float] = None
    details: Optional[Dict[str, Any]] = None
    status: SLAPerformanceStatus = SLAPerformanceStatus.PENDING
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    # Phase 50 additions
    metric_type: SLAMetricType
    compliance_percentage: float  # actual/target * 100
    compliance_status: SLAComplianceStatus
    breach_count: int = 0
    breach_details: List[Dict[str, Any]] = Field(default_factory=list)
    clawback_amount_zar: float = 0.0


class SLABreachEvent(BaseModel):
    """SLA breach event record for real-time tracking (Phase 50)."""

    model_config = ConfigDict(from_attributes=True)

    id: Optional[str] = None
    contract_id: str
    sla_term_id: str
    work_order_id: Optional[str] = None
    metric_type: SLAMetricType
    breach_severity: SLABreachSeverity
    target_value: float
    actual_value: float
    breach_percentage: float
    occurred_at: datetime
    detected_at: datetime
    clawback_amount_zar: float = 0.0
    notes: Optional[str] = None


# ============================================================================
# Contract Profitability Models
# ============================================================================


class ContractProfitability(BaseModel):
    """Contract profitability monthly roll-up from database."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    contract_id: str
    period_year: int
    period_month: int
    contract_fee_zar: float
    callout_revenue_zar: float = 0.0
    parts_markup_zar: float = 0.0
    other_revenue_zar: float = 0.0
    total_revenue_zar: Optional[float] = None  # GENERATED column
    labor_cost_zar: float = 0.0
    parts_cost_zar: float = 0.0
    subcontractor_cost_zar: float = 0.0
    travel_cost_zar: float = 0.0
    other_direct_cost_zar: float = 0.0
    total_direct_cost_zar: Optional[float] = None  # GENERATED column
    gross_margin_zar: Optional[float] = None  # GENERATED column
    sla_penalties_zar: float = 0.0
    net_margin_zar: Optional[float] = None  # GENERATED column
    work_order_count: int = 0
    callout_count: int = 0
    ppm_completion_pct: Optional[float] = None
    sla_compliance_pct: Optional[float] = None
    status: ProfitabilityStatus = ProfitabilityStatus.PRELIMINARY
    finalized_by: Optional[str] = None
    finalized_at: Optional[datetime] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


# ============================================================================
# Profitability Analytics Models (Phase 51)
# ============================================================================


class PortfolioMetrics(BaseModel):
    """Portfolio-wide profitability metrics aggregation."""

    total_contracts: int
    total_revenue_zar: float
    total_cost_zar: float
    gross_margin_zar: float
    gross_margin_percentage: float
    profit_contracts: int
    loss_contracts: int
    avg_margin_percentage: float
    period_start: date
    period_end: date


class ContractProfitabilityDetail(BaseModel):
    """Detailed per-contract profitability breakdown."""

    contract_id: str
    contract_name: str
    building_id: str
    building_name: Optional[str] = None

    # Revenue components
    monthly_revenue_zar: float
    clawbacks_zar: float = 0.0
    net_revenue_zar: float

    # Cost components
    labor_cost_zar: float = 0.0
    parts_cost_zar: float = 0.0
    subcontractor_cost_zar: float = 0.0
    callout_cost_zar: float = 0.0
    consumables_cost_zar: float = 0.0
    total_cost_zar: float

    # Profitability metrics
    gross_margin_zar: float
    gross_margin_percentage: float
    status: str  # "profitable", "break_even", "loss"

    # Trend analysis
    mom_change_pct: Optional[float] = None  # Month-over-month change
    ytd_margin_zar: Optional[float] = None  # Year-to-date margin

    # Asset metrics
    asset_count: int = 0
    cost_per_asset_zar: float = 0.0


class ProfitabilityTrend(BaseModel):
    """Monthly profitability trend data point."""

    contract_id: str
    period: str  # "2026-01" format
    revenue_zar: float
    cost_zar: float
    margin_zar: float
    margin_pct: float
    trend: str  # "improving", "stable", "declining"


class LossLeaderAnalysis(BaseModel):
    """Loss-making contract analysis with root causes."""

    contract_id: str
    contract_name: str
    loss_amount_zar: float
    loss_percentage: float
    root_causes: List[str] = Field(
        default_factory=list, description="Identified root causes, e.g., ['high_labor_costs', 'frequent_breakdowns']"
    )
    recommendation: str = Field(..., description="Actionable recommendation to address losses")
    months_in_loss: int = 1
    cumulative_loss_zar: float = 0.0
