"""
Compliance Models - Pydantic models for compliance management

Covers OHS Act, Fire Safety, Emergency Lighting, Legionella, Electrical, and Lift compliance.

Phase 28: SENTINEL Compliance
"""

from datetime import datetime
from enum import Enum
from typing import List, Optional, Dict, Any

from pydantic import BaseModel, Field, field_validator


# ============================================================================
# Enums
# ============================================================================


class ComplianceType(str, Enum):
    """Types of compliance requirements."""

    OHS = "OHS"
    FIRE = "Fire"
    ELECTRICAL = "Electrical"
    LEGIONELLA = "Legionella"
    LIFT_SAFETY = "LiftSafety"
    EMERGENCY = "Emergency"


class RiskLevel(str, Enum):
    """Risk classification levels."""

    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class AuditStatus(str, Enum):
    """Audit lifecycle status."""

    DRAFT = "draft"
    SUBMITTED = "submitted"
    APPROVED = "approved"
    REMEDIATION_PENDING = "remediation_pending"
    CLOSED = "closed"


class FireEquipmentType(str, Enum):
    """Types of fire safety equipment."""

    EXTINGUISHER = "extinguisher"
    HOSE_REEL = "hose_reel"
    HYDRANT = "hydrant"
    ALARM = "alarm"
    DETECTOR = "detector"


class ElectricalCertificateType(str, Enum):
    """Types of electrical certificates."""

    COC_NEW_INSTALLATION = "CoC_new_installation"
    COC_ALTERATIONS = "CoC_alterations"
    SABS_INSPECTION = "SABS_inspection"


class LiftInspectionType(str, Enum):
    """Types of lift inspections."""

    PERIODIC_6MONTHLY = "periodic_6monthly"
    ANNUAL_INSURANCE = "annual_insurance"
    AFTER_REPAIR = "after_repair"


class ComplianceChecklistStatus(str, Enum):
    """Status of equipment compliance."""

    ACTIVE = "active"
    OVERDUE = "overdue"
    OUT_OF_SERVICE = "out_of_service"
    DECOMMISSIONED = "decommissioned"


# ============================================================================
# Compliance Checklist Template Model
# ============================================================================


class ComplianceChecklistTemplate(BaseModel):
    """Template for compliance checklists."""

    id: Optional[str] = None
    compliance_type: ComplianceType
    requirement_standard: str  # e.g., 'NFPA 10', 'IEC 62034'
    template_name: str
    description: Optional[str] = None
    checklist_items: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="Array of {item_id, description, frequency, evidence_required}",
    )
    risk_level: RiskLevel = RiskLevel.MEDIUM
    is_active: bool = True
    version: int = 1
    created_by: str
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        json_schema_extra = {
            "example": {
                "compliance_type": "Fire",
                "requirement_standard": "NFPA 10",
                "template_name": "Fire Extinguisher Inspection",
                "checklist_items": [
                    {
                        "item_id": "FE-001",
                        "description": "Visual inspection of pressure gauge",
                        "frequency": "monthly",
                        "evidence_required": True,
                    }
                ],
                "risk_level": "high",
            }
        }


# ============================================================================
# Compliance Audit Model
# ============================================================================


class ComplianceAudit(BaseModel):
    """Comprehensive audit record for compliance."""

    id: Optional[str] = None
    site_id: str
    compliance_type: ComplianceType
    audit_type: str  # 'scheduled', 'unannounced', 'certification'
    auditor_id: Optional[str] = None
    auditor_role: Optional[str] = None  # 'Fire Safety Officer', 'Legionella Assessor'
    findings: Dict[str, Any] = Field(
        default_factory=dict,
        description="{critical_issues, recommendations, cost_estimates, action_items}",
    )
    status: AuditStatus = AuditStatus.DRAFT
    evidence_url: Optional[str] = None
    notes: Optional[str] = None
    audit_date: Optional[datetime] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    closed_date: Optional[datetime] = None

    @field_validator("audit_type")
    @classmethod
    def validate_audit_type(cls, v: str) -> str:
        """Validate audit type is one of allowed values."""
        allowed = ["scheduled", "unannounced", "certification"]
        if v not in allowed:
            raise ValueError(f"Audit type must be one of {allowed}")
        return v

    class Config:
        json_schema_extra = {
            "example": {
                "site_id": "site-002",
                "compliance_type": "Fire",
                "audit_type": "scheduled",
                "auditor_role": "Fire Safety Officer",
                "findings": {
                    "critical_issues": ["Extinguisher expired"],
                    "recommendations": ["Replace extinguisher"],
                    "cost_estimates": {"replacement": 500},
                },
                "status": "draft",
            }
        }


# ============================================================================
# Fire Equipment Tracking Model
# ============================================================================


class FireEquipmentTracking(BaseModel):
    """Track fire safety equipment and inspection schedule."""

    id: Optional[str] = None
    site_id: str
    zone_id: Optional[str] = None
    equipment_type: FireEquipmentType
    location_description: str
    unique_identifier: Optional[str] = None  # Serial number
    last_inspection_date: Optional[datetime] = None
    next_inspection_date: Optional[datetime] = None
    inspection_frequency_months: int = 12
    charge_pressure: Optional[float] = None  # PSI
    pressure_test_date: Optional[datetime] = None
    certification_expiry: Optional[datetime] = None
    certified_by: Optional[str] = None
    status: str = "active"
    created_by: str = "system"
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    @field_validator("inspection_frequency_months")
    @classmethod
    def validate_frequency(cls, v: int) -> int:
        """Fire equipment typically inspected annually."""
        if v < 1 or v > 24:
            raise ValueError("Inspection frequency must be 1-24 months")
        return v

    class Config:
        json_schema_extra = {
            "example": {
                "site_id": "S002",
                "equipment_type": "extinguisher",
                "location_description": "L1 Corridor B",
                "unique_identifier": "FE-2024-001",
                "inspection_frequency_months": 12,
                "charge_pressure": 150.0,
                "status": "active",
            }
        }


# ============================================================================
# Emergency Light Testing Model
# ============================================================================


class EmergencyLightTesting(BaseModel):
    """Emergency lighting compliance (IEC 62034)."""

    id: Optional[str] = None
    site_id: str
    light_code: str
    fixture_location: str
    control_point_id: Optional[str] = None
    last_test_date: Optional[datetime] = None
    test_interval_days: int = 365
    next_test_date: Optional[datetime] = None
    auto_test_enabled: bool = True
    auto_test_time_utc: str = "01:00"
    battery_health_percent: int = 100
    battery_health_trend: List[Dict[str, Any]] = Field(default_factory=list)
    battery_alert_threshold: int = 75
    test_results_history: List[Dict[str, Any]] = Field(default_factory=list)
    created_by: str = "system"
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    @field_validator("battery_health_percent")
    @classmethod
    def validate_battery_health(cls, v: int) -> int:
        """Battery health must be 0-100%."""
        if v < 0 or v > 100:
            raise ValueError("Battery health must be 0-100%")
        return v

    @field_validator("test_interval_days")
    @classmethod
    def validate_test_interval(cls, v: int) -> int:
        """IEC 62034 typically requires annual (365d) testing."""
        if v < 30:
            raise ValueError("Test interval must be at least 30 days")
        return v

    class Config:
        json_schema_extra = {
            "example": {
                "site_id": "S002",
                "light_code": "S002-EMERG-L2-001",
                "fixture_location": "Level 2, Corridor A",
                "test_interval_days": 365,
                "auto_test_enabled": True,
                "battery_health_percent": 100,
                "battery_alert_threshold": 75,
            }
        }


# ============================================================================
# Legionella Risk Assessment Model
# ============================================================================


class LegionellaRiskAssessment(BaseModel):
    """Legionella management for cooling towers (SABS standard)."""

    id: Optional[str] = None
    site_id: str
    tower_code: str
    equipment_id: Optional[str] = None
    risk_level: RiskLevel = RiskLevel.MEDIUM
    water_temperature: Optional[float] = None
    water_test_date: Optional[datetime] = None
    water_test_result_cfu: Optional[int] = None  # CFU/mL
    biocide_treatment_date: Optional[datetime] = None
    biocide_treatment_interval_days: int = 30
    temperature_monitoring: bool = True
    temperature_setpoint_celsius: float = 30.0
    control_measures: Dict[str, Any] = Field(
        default_factory=dict,
        description="{UV_systems: bool, filtration: TEXT, treatment_type: TEXT}",
    )
    notes: Optional[str] = None
    assessed_by: Optional[str] = None
    assessment_date: Optional[datetime] = None
    status: str = "at_risk"
    created_by: str = "system"
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    @field_validator("water_temperature")
    @classmethod
    def validate_water_temp(cls, v: Optional[float]) -> Optional[float]:
        """Water temperature validation (reasonable range)."""
        if v is not None and (v < 0 or v > 100):
            raise ValueError("Water temperature must be 0-100°C")
        return v

    @field_validator("biocide_treatment_interval_days")
    @classmethod
    def validate_treatment_interval(cls, v: int) -> int:
        """Biocide treatment interval validation."""
        if v < 7 or v > 90:
            raise ValueError("Treatment interval must be 7-90 days")
        return v

    class Config:
        json_schema_extra = {
            "example": {
                "site_id": "S002",
                "tower_code": "S002-CT-B1-001",
                "risk_level": "high",
                "water_temperature": 30.0,
                "biocide_treatment_interval_days": 30,
                "temperature_monitoring": True,
                "status": "at_risk",
            }
        }


# ============================================================================
# Electrical Compliance Model
# ============================================================================


class ElectricalCompliance(BaseModel):
    """Electrical Certificate of Compliance tracking."""

    id: Optional[str] = None
    site_id: str
    certificate_type: ElectricalCertificateType
    certificate_number: Optional[str] = None
    issued_by: str
    issued_by_license: Optional[str] = None
    issued_by_contact: Optional[str] = None
    issue_date: datetime
    expiry_date: Optional[datetime] = None
    scope: str
    equipment_codes: List[str] = Field(default_factory=list)
    status: str = "active"
    certificate_url: Optional[str] = None
    created_by: str = "system"
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    @field_validator("issue_date")
    @classmethod
    def validate_issue_date(cls, v: datetime) -> datetime:
        """Issue date cannot be in future."""
        if v > datetime.now():
            raise ValueError("Issue date cannot be in the future")
        return v

    def validate_expiry_date(self) -> None:
        """Validate expiry date is set and valid (5 years from issue in SA)."""
        if not self.expiry_date:
            # Auto-calculate 5-year validity (South African standard)
            self.expiry_date = self.issue_date + __import__("datetime").timedelta(
                days=365 * 5
            )

    class Config:
        json_schema_extra = {
            "example": {
                "site_id": "S002",
                "certificate_type": "CoC_new_installation",
                "issued_by": "John Smith - SABS #12345",
                "issue_date": "2024-01-15T00:00:00Z",
                "scope": "L1-L2 distribution board upgrade",
                "status": "active",
            }
        }


# ============================================================================
# Lift Inspection Tracking Model
# ============================================================================


class LiftInspectionTracking(BaseModel):
    """Lift/Elevator safety inspection and test results."""

    id: Optional[str] = None
    site_id: str
    lift_code: str
    equipment_id: Optional[str] = None
    location_description: str
    inspection_type: LiftInspectionType
    last_inspection_date: Optional[datetime] = None
    next_inspection_date: Optional[datetime] = None
    inspector_name: Optional[str] = None
    inspector_license_number: Optional[str] = None
    inspector_company: Optional[str] = None
    test_results: Dict[str, Any] = Field(
        default_factory=dict,
        description="{brake_load_test, speed_governor, emergency_stop_time, shaft_pressure}",
    )
    test_date: Optional[datetime] = None
    non_compliance_items: List[str] = Field(default_factory=list)
    is_compliant: bool = True
    status: str = "pending"
    inspection_report_url: Optional[str] = None
    inspection_notes: Optional[str] = None
    created_by: str = "system"
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        json_schema_extra = {
            "example": {
                "site_id": "S002",
                "lift_code": "S002-LIFT-R-001",
                "location_description": "Roof Level - Main Lift",
                "inspection_type": "periodic_6monthly",
                "inspector_license_number": "LSA-2024-001",
                "test_results": {
                    "brake_load_test": "pass",
                    "speed_governor": "pass",
                    "emergency_stop_time": 0.8,
                },
                "is_compliant": True,
                "status": "completed",
            }
        }


# ============================================================================
# Compliance Status Summary Model
# ============================================================================


class ComplianceStatus(BaseModel):
    """Aggregate compliance status for dashboard reporting."""

    site_id: str
    critical_issues_count: int = 0
    high_risk_items_count: int = 0
    items_expiring_30days: int = 0
    overdue_inspections: int = 0
    last_audit_date: Optional[datetime] = None
    compliance_score_percent: int = 100
    summary: Dict[str, Any] = Field(
        default_factory=dict,
        description="{ohs_status, fire_status, electrical_status, legionella_status, lift_status}",
    )

    class Config:
        json_schema_extra = {
            "example": {
                "site_id": "S002",
                "critical_issues_count": 2,
                "high_risk_items_count": 5,
                "items_expiring_30days": 3,
                "overdue_inspections": 1,
                "compliance_score_percent": 75,
                "summary": {
                    "fire_status": "at_risk",
                    "electrical_status": "compliant",
                    "legionella_status": "high_risk",
                },
            }
        }
