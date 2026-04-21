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
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

# ============================================================================
# Enums (matching CHECK constraints in 018_commercial_schema.sql)
# ============================================================================


class OrganizationTier(StrEnum):
    """Organization tier matching organizations.tier CHECK constraint."""

    PLATINUM = "platinum"
    GOLD = "gold"
    SILVER = "silver"
    BRONZE = "bronze"


class OrganizationStatus(StrEnum):
    """Organization status matching organizations.status CHECK constraint."""

    ACTIVE = "active"
    SUSPENDED = "suspended"
    TERMINATED = "terminated"


class ContractStatus(StrEnum):
    """Contract lifecycle status matching contracts.status CHECK constraint."""

    DRAFT = "draft"
    PENDING_APPROVAL = "pending_approval"
    ACTIVE = "active"
    SUSPENDED = "suspended"
    EXPIRED = "expired"
    TERMINATED = "terminated"


class ContractType(StrEnum):
    """Contract type matching contracts.contract_type CHECK constraint."""

    COMPREHENSIVE = "comprehensive"
    PREVENTIVE = "preventive"
    REACTIVE = "reactive"
    HYBRID = "hybrid"


class SLAType(StrEnum):
    """SLA type matching sla_terms.sla_type CHECK constraint."""

    UPTIME = "uptime"
    RESPONSE_TIME = "response_time"
    RESOLUTION_TIME = "resolution_time"
    PPM_COMPLETION = "ppm_completion"
    FIRST_FIX_RATE = "first_fix_rate"


class SLAPriority(StrEnum):
    """SLA priority level matching sla_terms.priority CHECK constraint."""

    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    ALL = "all"


class MeasurementPeriod(StrEnum):
    """Measurement period matching sla_terms.measurement_period CHECK constraint."""

    MONTHLY = "monthly"
    QUARTERLY = "quarterly"
    ANNUALLY = "annually"


class PenaltyType(StrEnum):
    """Penalty type matching sla_terms.penalty_type CHECK constraint."""

    PERCENTAGE = "percentage"
    FIXED = "fixed"
    TIERED = "tiered"


class CoverageType(StrEnum):
    """Asset coverage type matching asset_contracts.coverage_type CHECK constraint."""

    FULL = "full"
    PARTS_ONLY = "parts_only"
    LABOR_ONLY = "labor_only"
    EXCLUDED = "excluded"


class CriticalityTier(StrEnum):
    """Asset criticality matching asset_contracts.criticality CHECK constraint."""

    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class AssessmentType(StrEnum):
    """Assessment type matching condition_assessments.assessment_type CHECK constraint."""

    INITIAL = "initial"
    ANNUAL = "annual"
    HANDOVER = "handover"
    AD_HOC = "ad_hoc"


class AssessmentStatus(StrEnum):
    """Assessment status matching condition_assessments.status CHECK constraint."""

    DRAFT = "draft"
    SUBMITTED = "submitted"
    APPROVED = "approved"
    DISPUTED = "disputed"


class FailureRisk(StrEnum):
    """Failure risk level matching condition_assessments.estimated_failure_risk CHECK."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class BudgetStatus(StrEnum):
    """Budget status matching budgets.status CHECK constraint."""

    DRAFT = "draft"
    APPROVED = "approved"
    LOCKED = "locked"


class SLAPerformanceStatus(StrEnum):
    """SLA performance status matching sla_performance.status CHECK constraint."""

    PENDING = "pending"
    CALCULATED = "calculated"
    INVOICED = "invoiced"
    DISPUTED = "disputed"
    RESOLVED = "resolved"


class ProfitabilityStatus(StrEnum):
    """Profitability status matching contract_profitability.status CHECK constraint."""

    PRELIMINARY = "preliminary"
    FINAL = "final"
    AUDITED = "audited"


# ============================================================================
# Phase 49: Cost Tracking & Budgeting - Additional Enums
# ============================================================================


class LaborCostType(StrEnum):
    """Labor cost subcategory for detailed tracking."""

    PLANNED_MAINTENANCE = "planned_maintenance"
    EMERGENCY_CALLOUT = "emergency_callout"
    BREAKDOWN_REPAIR = "breakdown_repair"
    TRAVEL_TIME = "travel_time"
    OVERTIME = "overtime"


class PartsCostType(StrEnum):
    """Parts cost subcategory for detailed tracking."""

    SCHEDULED_REPLACEMENT = "scheduled_replacement"
    UNPLANNED_REPAIR = "unplanned_repair"
    CONSUMABLES = "consumables"
    CALIBRATION_MATERIALS = "calibration_materials"


class CalloutType(StrEnum):
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
    equipment_type: str | None = Field(None, description="Equipment type for template linking")
    work_order_id: str | None = Field(None, description="Associated work order")
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
    typical_monthly_breakdown: dict[str, float] = Field(
        ..., description="Monthly budget breakdown by category: labor_budget_zar, parts_budget_zar, etc."
    )


# ============================================================================
# Phase 50: SLA Monitoring & Alerts - Additional Enums
# ============================================================================


class SLAMetricType(StrEnum):
    """SLA metric type for compliance tracking (Phase 50)."""

    RESPONSE_TIME = "response_time"  # Time to acknowledge
    RESOLUTION_TIME = "resolution_time"  # Time to fix
    UPTIME_PERCENTAGE = "uptime_percentage"
    MEAN_TIME_TO_REPAIR = "mean_time_to_repair"
    PREVENTIVE_MAINTENANCE = "preventive_maintenance"


class SLABreachSeverity(StrEnum):
    """SLA breach severity levels (Phase 50)."""

    MINOR = "minor"  # 10-20% breach
    MAJOR = "major"  # 20-50% breach
    CRITICAL = "critical"  # >50% breach or safety-critical failure


class SLAComplianceStatus(StrEnum):
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
    trading_name: str | None = None
    registration_number: str | None = None
    vat_number: str | None = None
    primary_contact_name: str | None = None
    primary_contact_email: str | None = None
    primary_contact_phone: str | None = None
    billing_email: str | None = None
    physical_address: str | None = None
    postal_address: str | None = None
    industry: str | None = None
    tier: OrganizationTier | None = None
    status: OrganizationStatus | None = OrganizationStatus.ACTIVE


class OrganizationUpdate(BaseModel):
    """Partial update for an organization."""

    name: str | None = None
    trading_name: str | None = None
    registration_number: str | None = None
    vat_number: str | None = None
    primary_contact_name: str | None = None
    primary_contact_email: str | None = None
    primary_contact_phone: str | None = None
    billing_email: str | None = None
    physical_address: str | None = None
    postal_address: str | None = None
    industry: str | None = None
    tier: OrganizationTier | None = None
    status: OrganizationStatus | None = None


class Organization(BaseModel):
    """Full organization record from database."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    code: str
    name: str
    trading_name: str | None = None
    registration_number: str | None = None
    vat_number: str | None = None
    primary_contact_name: str | None = None
    primary_contact_email: str | None = None
    primary_contact_phone: str | None = None
    billing_email: str | None = None
    physical_address: str | None = None
    postal_address: str | None = None
    industry: str | None = None
    tier: OrganizationTier | None = None
    status: OrganizationStatus | None = OrganizationStatus.ACTIVE
    created_at: datetime | None = None
    updated_at: datetime | None = None


# ============================================================================
# Contract Models
# ============================================================================


class ContractCreate(BaseModel):
    """Data required to create a new contract."""

    code: str = Field(..., description="Unique contract code, e.g. 'CON-SITE-002-2026-001'")
    organization_id: str
    site_id: str
    contract_type: ContractType | None = None
    start_date: date
    end_date: date | None = None
    auto_renew: bool = False
    notice_period_days: int = 90
    monthly_fee_zar: float
    annual_escalation_pct: float = 6.0
    payment_terms_days: int = 30
    coverage_hours: dict[str, Any] | None = None
    included_callouts_per_month: int = 0
    callout_rate_zar: float | None = None
    after_hours_rate_zar: float | None = None
    notes: str | None = None
    special_conditions: str | None = None


class ContractUpdate(BaseModel):
    """Partial update for a contract."""

    contract_type: ContractType | None = None
    end_date: date | None = None
    auto_renew: bool | None = None
    notice_period_days: int | None = None
    monthly_fee_zar: float | None = None
    annual_escalation_pct: float | None = None
    payment_terms_days: int | None = None
    coverage_hours: dict[str, Any] | None = None
    included_callouts_per_month: int | None = None
    callout_rate_zar: float | None = None
    after_hours_rate_zar: float | None = None
    status: ContractStatus | None = None
    approved_by: str | None = None
    approved_at: datetime | None = None
    notes: str | None = None
    special_conditions: str | None = None


class Contract(BaseModel):
    """Full contract record from database."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    code: str
    organization_id: str
    site_id: str
    contract_type: ContractType | None = None
    start_date: date
    end_date: date | None = None
    auto_renew: bool = False
    notice_period_days: int = 90
    monthly_fee_zar: float
    annual_escalation_pct: float = 6.0
    payment_terms_days: int = 30
    coverage_hours: dict[str, Any] | None = None
    included_callouts_per_month: int = 0
    callout_rate_zar: float | None = None
    after_hours_rate_zar: float | None = None
    status: ContractStatus = ContractStatus.DRAFT
    approved_by: str | None = None
    approved_at: datetime | None = None
    notes: str | None = None
    special_conditions: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


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
    penalty_type: PenaltyType | None = None
    penalty_value: float | None = None
    penalty_cap_pct: float | None = None
    grace_period_hours: int = 0
    is_active: bool = True


class SLATermUpdate(BaseModel):
    """Partial update for an SLA term."""

    target_value: float | None = None
    target_unit: str | None = None
    priority: SLAPriority | None = None
    measurement_period: MeasurementPeriod | None = None
    penalty_type: PenaltyType | None = None
    penalty_value: float | None = None
    penalty_cap_pct: float | None = None
    grace_period_hours: int | None = None
    is_active: bool | None = None


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
    penalty_type: PenaltyType | None = None
    penalty_value: float | None = None
    penalty_cap_pct: float | None = None
    grace_period_hours: int = 0
    is_active: bool = True
    created_at: datetime | None = None
    updated_at: datetime | None = None


# ============================================================================
# Asset Contract Models
# ============================================================================


class AssetContractCreate(BaseModel):
    """Data required to link equipment to a contract."""

    contract_id: str
    equipment_id: str
    allocated_fee_zar: float | None = None
    fee_allocation_pct: float | None = None
    coverage_type: CoverageType = CoverageType.FULL
    annual_parts_cap_zar: float | None = None
    annual_labor_cap_zar: float | None = None
    criticality: CriticalityTier = CriticalityTier.MEDIUM
    exclusions: str | None = None
    notes: str | None = None


class AssetContract(BaseModel):
    """Full asset contract link from database."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    contract_id: str
    equipment_id: str
    allocated_fee_zar: float | None = None
    fee_allocation_pct: float | None = None
    coverage_type: CoverageType = CoverageType.FULL
    annual_parts_cap_zar: float | None = None
    annual_labor_cap_zar: float | None = None
    criticality: CriticalityTier = CriticalityTier.MEDIUM
    exclusions: str | None = None
    notes: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


# ============================================================================
# Condition Assessment Models
# ============================================================================


class ConditionAssessmentCreate(BaseModel):
    """Data required to create a condition assessment."""

    code: str = Field(..., description="Unique code, e.g. 'CA-001-2026-001'")
    site_id: str | None = None
    equipment_id: str | None = None
    contract_id: str | None = None
    assessment_type: AssessmentType
    assessment_date: date
    assessor_name: str
    assessor_company: str | None = None
    overall_score: int | None = Field(None, ge=1, le=5)
    mechanical_score: int | None = Field(None, ge=1, le=5)
    electrical_score: int | None = Field(None, ge=1, le=5)
    controls_score: int | None = Field(None, ge=1, le=5)
    documentation_score: int | None = Field(None, ge=1, le=5)
    findings: str | None = None
    defects: list[dict[str, Any]] | None = None
    recommendations: list[dict[str, Any]] | None = None
    photos: list[dict[str, Any]] | None = None
    estimated_failure_risk: FailureRisk | None = None
    estimated_annual_cost_zar: float | None = None
    recommended_budget_zar: float | None = None


class ConditionAssessment(BaseModel):
    """Full condition assessment record from database."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    code: str
    site_id: str | None = None
    equipment_id: str | None = None
    contract_id: str | None = None
    assessment_type: AssessmentType
    assessment_date: date
    assessor_name: str
    assessor_company: str | None = None
    overall_score: int | None = Field(None, ge=1, le=5)
    mechanical_score: int | None = Field(None, ge=1, le=5)
    electrical_score: int | None = Field(None, ge=1, le=5)
    controls_score: int | None = Field(None, ge=1, le=5)
    documentation_score: int | None = Field(None, ge=1, le=5)
    findings: str | None = None
    defects: list[dict[str, Any]] | None = None
    recommendations: list[dict[str, Any]] | None = None
    photos: list[dict[str, Any]] | None = None
    estimated_failure_risk: FailureRisk | None = None
    estimated_annual_cost_zar: float | None = None
    recommended_budget_zar: float | None = None
    status: AssessmentStatus = AssessmentStatus.DRAFT
    approved_by: str | None = None
    approved_at: datetime | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


# ============================================================================
# Budget Models
# ============================================================================


class BudgetCreate(BaseModel):
    """Data required to create a budget entry."""

    code: str = Field(..., description="Unique code, e.g. 'BUD-SITE-002-SANDTON-2026'")
    contract_id: str
    equipment_type: str | None = None
    budget_year: int
    budget_month: int | None = Field(None, ge=1, le=12)
    labor_budget_zar: float = 0.0
    parts_budget_zar: float = 0.0
    consumables_budget_zar: float = 0.0
    subcontractor_budget_zar: float = 0.0
    callout_budget_zar: float = 0.0
    warning_threshold_pct: float = 80.0
    critical_threshold_pct: float = 100.0
    notes: str | None = None


class BudgetUpdate(BaseModel):
    """Partial update for a budget entry (typically actuals updates)."""

    labor_budget_zar: float | None = None
    parts_budget_zar: float | None = None
    consumables_budget_zar: float | None = None
    subcontractor_budget_zar: float | None = None
    callout_budget_zar: float | None = None
    labor_actual_zar: float | None = None
    parts_actual_zar: float | None = None
    consumables_actual_zar: float | None = None
    subcontractor_actual_zar: float | None = None
    callout_actual_zar: float | None = None
    warning_threshold_pct: float | None = None
    critical_threshold_pct: float | None = None
    status: BudgetStatus | None = None
    approved_by: str | None = None
    approved_at: datetime | None = None
    notes: str | None = None


class Budget(BaseModel):
    """Full budget record from database."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    code: str
    contract_id: str
    equipment_type: str | None = None
    budget_year: int
    budget_month: int | None = None
    labor_budget_zar: float = 0.0
    parts_budget_zar: float = 0.0
    consumables_budget_zar: float = 0.0
    subcontractor_budget_zar: float = 0.0
    callout_budget_zar: float = 0.0
    total_budget_zar: float | None = None  # GENERATED column
    labor_actual_zar: float = 0.0
    parts_actual_zar: float = 0.0
    consumables_actual_zar: float = 0.0
    subcontractor_actual_zar: float = 0.0
    callout_actual_zar: float = 0.0
    total_actual_zar: float | None = None  # GENERATED column
    variance_zar: float | None = None  # GENERATED column
    warning_threshold_pct: float = 80.0
    critical_threshold_pct: float = 100.0
    status: BudgetStatus = BudgetStatus.DRAFT
    approved_by: str | None = None
    approved_at: datetime | None = None
    notes: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


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
    met_target: bool | None = None  # GENERATED column
    penalty_applied: bool = False
    penalty_amount_zar: float | None = None
    penalty_waived: bool = False
    waiver_reason: str | None = None
    incidents_count: int = 0
    total_downtime_hours: float | None = None
    details: dict[str, Any] | None = None
    status: SLAPerformanceStatus = SLAPerformanceStatus.PENDING
    created_at: datetime | None = None
    updated_at: datetime | None = None


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
    met_target: bool | None = None
    penalty_applied: bool = False
    penalty_amount_zar: float | None = None
    penalty_waived: bool = False
    waiver_reason: str | None = None
    incidents_count: int = 0
    total_downtime_hours: float | None = None
    details: dict[str, Any] | None = None
    status: SLAPerformanceStatus = SLAPerformanceStatus.PENDING
    created_at: datetime | None = None
    updated_at: datetime | None = None

    # Phase 50 additions
    metric_type: SLAMetricType
    compliance_percentage: float  # actual/target * 100
    compliance_status: SLAComplianceStatus
    breach_count: int = 0
    breach_details: list[dict[str, Any]] = Field(default_factory=list)
    clawback_amount_zar: float = 0.0


class SLABreachEvent(BaseModel):
    """SLA breach event record for real-time tracking (Phase 50)."""

    model_config = ConfigDict(from_attributes=True)

    id: str | None = None
    contract_id: str
    sla_term_id: str
    work_order_id: str | None = None
    metric_type: SLAMetricType
    breach_severity: SLABreachSeverity
    target_value: float
    actual_value: float
    breach_percentage: float
    occurred_at: datetime
    detected_at: datetime
    clawback_amount_zar: float = 0.0
    notes: str | None = None


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
    total_revenue_zar: float | None = None  # GENERATED column
    labor_cost_zar: float = 0.0
    parts_cost_zar: float = 0.0
    subcontractor_cost_zar: float = 0.0
    travel_cost_zar: float = 0.0
    other_direct_cost_zar: float = 0.0
    total_direct_cost_zar: float | None = None  # GENERATED column
    gross_margin_zar: float | None = None  # GENERATED column
    sla_penalties_zar: float = 0.0
    net_margin_zar: float | None = None  # GENERATED column
    work_order_count: int = 0
    callout_count: int = 0
    ppm_completion_pct: float | None = None
    sla_compliance_pct: float | None = None
    status: ProfitabilityStatus = ProfitabilityStatus.PRELIMINARY
    finalized_by: str | None = None
    finalized_at: datetime | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


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
    site_id: str
    site_name: str | None = None

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
    mom_change_pct: float | None = None  # Month-over-month change
    ytd_margin_zar: float | None = None  # Year-to-date margin

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
    root_causes: list[str] = Field(
        default_factory=list, description="Identified root causes, e.g., ['high_labor_costs', 'frequent_breakdowns']"
    )
    recommendation: str = Field(..., description="Actionable recommendation to address losses")
    months_in_loss: int = 1
    cumulative_loss_zar: float = 0.0
