"""
Inspection Models - Pydantic models for inspection management

Phase 45: Routine Inspection & Maintenance
"""

from datetime import datetime
from enum import Enum
from typing import List, Optional, Dict, Any

from pydantic import BaseModel, Field


# ============================================================================
# Enums
# ============================================================================

class InspectionScheduleFrequency(str, Enum):
    """Frequency types for inspection schedules."""
    WEEKLY = "weekly"
    MONTHLY = "monthly"
    QUARTERLY = "quarterly"
    ANNUAL = "annual"
    CUSTOM = "custom"


class InspectionTaskStatus(str, Enum):
    """Status of inspection tasks."""
    SCHEDULED = "scheduled"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    OVERDUE = "overdue"
    CANCELLED = "cancelled"


class InspectionPriority(str, Enum):
    """Priority levels for inspections."""
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    URGENT = "urgent"


class InspectionOverallStatus(str, Enum):
    """Overall status of inspection results."""
    PASS = "pass"
    FAIL = "fail"
    PARTIAL = "partial"


class DeficiencySeverity(str, Enum):
    """Severity levels for deficiencies."""
    MINOR = "minor"
    MAJOR = "major"
    CRITICAL = "critical"
    SAFETY = "safety"


class DeficiencyCategory(str, Enum):
    """Categories for deficiencies."""
    MECHANICAL = "mechanical"
    ELECTRICAL = "electrical"
    OPERATIONAL = "operational"
    SAFETY = "safety"


# ============================================================================
# Inspection Schedule Models
# ============================================================================

class InspectionScheduleBase(BaseModel):
    """Base model for inspection schedules."""
    equipment_id: str = Field(..., description="Equipment to inspect")
    element_id: Optional[str] = Field(None, description="Specific element to inspect (optional)")

    schedule_name: str = Field(..., description="Name of the inspection schedule")
    schedule_description: Optional[str] = Field(None, description="Description of the schedule")

    frequency_type: InspectionScheduleFrequency = Field(..., description="Frequency of inspections")
    frequency_days: Optional[int] = Field(None, description="Custom frequency in days")

    day_of_week: Optional[int] = Field(None, description="For weekly: 0=Sunday, 1=Monday, etc.")
    day_of_month: Optional[int] = Field(None, description="For monthly: 1-31")

    estimated_duration_minutes: int = Field(default=60, description="Estimated inspection duration")
    preferred_time_of_day: Optional[str] = Field(None, description="Preferred time: morning, afternoon, any")

    assigned_to: Optional[str] = Field(None, description="Assigned technician")
    required_skills: Optional[List[str]] = Field(None, description="Required skills")

    is_active: bool = Field(default=True, description="Whether schedule is active")
    last_generated_date: Optional[datetime] = Field(None, description="Last task generation date")
    next_due_date: Optional[datetime] = Field(None, description="Next scheduled due date")


class InspectionScheduleCreate(InspectionScheduleBase):
    """Model for creating inspection schedule."""
    created_by: str = Field(..., description="Who created the schedule")


class InspectionSchedule(InspectionScheduleBase):
    """Model for inspection schedule record."""
    id: str = Field(..., description="Schedule ID")
    created_at: datetime
    updated_at: datetime

    class Config:
        json_schema_extra = {
            "example": {
                "id": "123e4567-e89b-12d3-a456-426614174000",
                "equipment_id": "generator-001",
                "schedule_name": "Monthly Generator Inspection",
                "schedule_description": "Monthly routine inspection with vibration analysis",
                "frequency_type": "monthly",
                "estimated_duration_minutes": 90,
                "assigned_to": "John Smith",
                "required_skills": ["generator_maintenance", "vibration_analysis"],
                "is_active": True,
                "created_by": "system"
            }
        }


# ============================================================================
# Inspection Checklist Template Models
# ============================================================================

class InspectionChecklistTemplateBase(BaseModel):
    """Base model for inspection checklist templates."""
    template_name: str = Field(..., description="Name of the template")
    equipment_type: str = Field(..., description="Equipment type this template applies to")
    inspection_type: str = Field(..., description="Type of inspection: routine, preventive, corrective")

    frequency_type: InspectionScheduleFrequency = Field(..., description="Frequency of inspection")
    estimated_duration_minutes: int = Field(default=60, description="Estimated duration")

    is_active: bool = Field(default=True, description="Whether template is active")
    version: int = Field(default=1, description="Template version")

    checklist_items: List[Dict[str, Any]] = Field(default_factory=list, description="Array of checklist items")
    required_tools: Optional[List[str]] = Field(None, description="Required tools")
    required_skills: Optional[List[str]] = Field(None, description="Required skills")
    safety_requirements: Optional[List[str]] = Field(None, description="Safety requirements")
    ppe_required: Optional[List[str]] = Field(None, description="Required PPE")


class InspectionChecklistTemplateCreate(InspectionChecklistTemplateBase):
    """Model for creating checklist template."""
    created_by: str = Field(..., description="Who created the template")


class InspectionChecklistTemplate(InspectionChecklistTemplateBase):
    """Model for checklist template record."""
    id: str = Field(..., description="Template ID")
    created_at: datetime
    updated_at: datetime


# ============================================================================
# Inspection Task Models
# ============================================================================

class InspectionTaskBase(BaseModel):
    """Base model for inspection tasks."""
    schedule_id: Optional[str] = Field(None, description="Source schedule ID")

    task_name: str = Field(..., description="Name of the inspection task")
    task_description: Optional[str] = Field(None, description="Task description")

    equipment_id: str = Field(..., description="Equipment to inspect")
    element_id: Optional[str] = Field(None, description="Specific element to inspect")

    scheduled_date: datetime = Field(..., description="Scheduled date")
    due_date: datetime = Field(..., description="Due date")

    assigned_to: Optional[str] = Field(None, description="Assigned technician")
    assigned_by: Optional[str] = Field(None, description="Who assigned the task")

    status: InspectionTaskStatus = Field(default=InspectionTaskStatus.SCHEDULED, description="Task status")

    completed_date: Optional[datetime] = Field(None, description="Completion date")
    completed_by: Optional[str] = Field(None, description="Who completed the task")
    completion_notes: Optional[str] = Field(None, description="Completion notes")

    estimated_duration_minutes: Optional[int] = Field(None, description="Estimated duration")
    actual_duration_minutes: Optional[int] = Field(None, description="Actual duration")

    priority: InspectionPriority = Field(default=InspectionPriority.NORMAL, description="Task priority")
    is_critical: bool = Field(default=False, description="Whether this is a critical inspection")

    checklist_template_id: Optional[str] = Field(None, description="Checklist template used")
    baseline_reference_id: Optional[str] = Field(None, description="Reference baseline for comparison")


class InspectionTaskCreate(InspectionTaskBase):
    """Model for creating inspection task."""
    pass


class InspectionTask(InspectionTaskBase):
    """Model for inspection task record."""
    id: str = Field(..., description="Task ID")
    created_at: datetime
    updated_at: datetime

    class Config:
        json_schema_extra = {
            "example": {
                "id": "123e4567-e89b-12d3-a456-426614174001",
                "schedule_id": "123e4567-e89b-12d3-a456-426614174000",
                "task_name": "Monthly Generator Inspection - Generator 001",
                "equipment_id": "generator-001",
                "scheduled_date": "2026-03-01T08:00:00Z",
                "due_date": "2026-03-08T17:00:00Z",
                "assigned_to": "John Smith",
                "status": "scheduled",
                "priority": "high",
                "is_critical": True,
                "estimated_duration_minutes": 90
            }
        }


# ============================================================================
# Inspection Result Models
# ============================================================================

class InspectionResultBase(BaseModel):
    """Base model for inspection results."""
    task_id: str = Field(..., description="Source task ID")
    inspected_by: str = Field(..., description="Who performed the inspection")
    inspection_date: datetime = Field(default_factory=datetime.now, description="Inspection date")

    overall_status: InspectionOverallStatus = Field(..., description="Overall inspection status")

    item_results: List[Dict[str, Any]] = Field(default_factory=list, description="Results for each checklist item")
    measurements: Optional[Dict[str, Any]] = Field(None, description="Measurements captured")

    deficiencies_found: int = Field(default=0, description="Number of deficiencies found")
    critical_findings: int = Field(default=0, description="Number of critical findings")

    ambient_conditions: Optional[Dict[str, Any]] = Field(None, description="Environmental conditions")

    started_at: Optional[datetime] = Field(None, description="When inspection started")
    completed_at: Optional[datetime] = Field(None, description="When inspection completed")

    general_notes: Optional[str] = Field(None, description="General notes and observations")
    recommendations: Optional[str] = Field(None, description="Recommendations")

    photo_urls: Optional[List[str]] = Field(None, description="URLs to inspection photos")
    recommended_next_inspection_date: Optional[datetime] = Field(None, description="Recommended next inspection date")


class InspectionResultCreate(InspectionResultBase):
    """Model for creating inspection result."""
    equipment_id: str = Field(..., description="Equipment inspected")


class InspectionResult(InspectionResultBase):
    """Model for inspection result record."""
    id: str = Field(..., description="Result ID")
    equipment_id: str = Field(..., description="Equipment inspected")
    created_at: datetime
    updated_at: datetime

    class Config:
        json_schema_extra = {
            "example": {
                "id": "123e4567-e89b-12d3-a456-426614174002",
                "task_id": "123e4567-e89b-12d3-a456-426614174001",
                "equipment_id": "generator-001",
                "inspected_by": "John Smith",
                "inspection_date": "2026-03-01T10:30:00Z",
                "overall_status": "pass",
                "item_results": [
                    {
                        "item_id": "gen_001",
                        "status": "pass",
                        "measurement_value": "Normal",
                        "notes": "Oil level OK"
                    },
                    {
                        "item_id": "gen_002",
                        "status": "fail",
                        "measurement_value": "Leak present",
                        "notes": "Oil leak at gasket worsened",
                        "photos": ["https://storage.example.com/leak.jpg"]
                    }
                ],
                "deficiencies_found": 1,
                "critical_findings": 0,
                "general_notes": "Generator running well except for oil leak"
            }
        }


# ============================================================================
# Inspection Deficiency Models
# ============================================================================

class InspectionDeficiencyBase(BaseModel):
    """Base model for inspection deficiencies."""
    result_id: str = Field(..., description="Source result ID")
    task_id: str = Field(..., description="Source task ID")
    equipment_id: str = Field(..., description="Equipment with deficiency")
    element_id: Optional[str] = Field(None, description="Element with deficiency")

    deficiency_title: str = Field(..., description="Title/summary of deficiency")
    deficiency_description: Optional[str] = Field(None, description="Detailed description")

    severity: DeficiencySeverity = Field(..., description="Severity level")
    category: Optional[DeficiencyCategory] = Field(None, description="Category")

    location_detail: Optional[str] = Field(None, description="Specific location on equipment")
    checklist_item_id: Optional[str] = Field(None, description="Checklist item where found")

    impact_description: Optional[str] = Field(None, description="Description of impact")
    urgency: Optional[str] = Field(None, description="Urgency level")

    recommended_action: Optional[str] = Field(None, description="Recommended corrective action")
    estimated_repair_cost_min: Optional[float] = Field(None, description="Min estimated repair cost")
    estimated_repair_cost_max: Optional[float] = Field(None, description="Max estimated repair cost")
    estimated_repair_hours: Optional[int] = Field(None, description="Estimated repair hours")

    is_resolved: bool = Field(default=False, description="Whether deficiency is resolved")
    resolved_date: Optional[datetime] = Field(None, description="Resolution date")
    resolved_by: Optional[str] = Field(None, description="Who resolved it")
    resolution_notes: Optional[str] = Field(None, description="Resolution notes")

    work_order_id: Optional[str] = Field(None, description="Associated work order ID")
    photo_urls: Optional[List[str]] = Field(None, description="Photo evidence URLs")


class InspectionDeficiencyCreate(InspectionDeficiencyBase):
    """Model for creating inspection deficiency."""
    reported_by: str = Field(..., description="Who reported the deficiency")


class InspectionDeficiency(InspectionDeficiencyBase):
    """Model for inspection deficiency record."""
    id: str = Field(..., description="Deficiency ID")
    reported_by: str = Field(..., description="Who reported the deficiency")
    reported_date: datetime
    created_at: datetime
    updated_at: datetime

    class Config:
        json_schema_extra = {
            "example": {
                "id": "123e4567-e89b-12d3-a456-426614174003",
                "result_id": "123e4567-e89b-12d3-a456-426614174002",
                "task_id": "123e4567-e89b-12d3-a456-426614174001",
                "equipment_id": "generator-001",
                "deficiency_title": "Oil leak at pan gasket",
                "deficiency_description": "Oil leak has worsened from 2 drops/min to 8 drops/min",
                "severity": "major",
                "category": "mechanical",
                "recommended_action": "Replace oil pan gasket",
                "estimated_repair_cost_min": 1500.00,
                "estimated_repair_cost_max": 2500.00,
                "estimated_repair_hours": 4,
                "is_resolved": False,
                "reported_by": "John Smith",
                "reported_date": "2026-03-01T10:30:00Z"
            }
        }


# ============================================================================
# Inspection Measurement Models
# ============================================================================

class InspectionMeasurementBase(BaseModel):
    """Base model for inspection measurements."""
    result_id: str = Field(..., description="Source inspection result ID")
    task_id: str = Field(..., description="Source inspection task ID")
    equipment_id: str = Field(..., description="Equipment being measured")

    measurement_type: str = Field(..., description="Type: temperature, pressure, vibration, etc.")
    measurement_point: str = Field(..., description="Sensor ID or measurement location")

    measured_value: float = Field(..., description="The measured value")
    unit: str = Field(..., description="Unit of measurement: C, bar, mm/s, dBA, etc.")

    measurement_date: datetime = Field(..., description="When measurement was taken")
    measured_by: str = Field(..., description="Who took the measurement")

    # Baseline comparison (optional)
    baseline_value: Optional[float] = Field(None, description="Baseline value for comparison")
    baseline_deviation_percent: Optional[float] = Field(None, description="Deviation from baseline as percentage")
    deviation_status: Optional[str] = Field(None, description="Status: normal, warning, critical")

    notes: Optional[str] = Field(None, description="Additional notes")


class InspectionMeasurementCreate(InspectionMeasurementBase):
    """Model for creating inspection measurement."""
    pass


class InspectionMeasurement(InspectionMeasurementBase):
    """Model for inspection measurement record."""
    id: str = Field(..., description="Measurement ID")
    created_at: datetime

    class Config:
        json_schema_extra = {
            "example": {
                "id": "123e4567-e89b-12d3-a456-426614174004",
                "result_id": "123e4567-e89b-12d3-a456-426614174002",
                "task_id": "123e4567-e89b-12d3-a456-426614174001",
                "equipment_id": "generator-001",
                "measurement_type": "vibration",
                "measurement_point": "engine_block_top",
                "measured_value": 3.5,
                "unit": "mm/s",
                "measurement_date": "2026-03-01T10:45:00Z",
                "measured_by": "John Smith",
                "baseline_value": 3.2,
                "baseline_deviation_percent": 9.4,
                "deviation_status": "normal"
            }
        }


# ============================================================================
# Request/Response Models
# ============================================================================

class InspectionTaskAssignmentRequest(BaseModel):
    """Request to assign inspection task."""
    assigned_to: str = Field(..., description="Technician to assign to")
    assigned_by: str = Field(..., description="Who is assigning")


class InspectionTaskRescheduleRequest(BaseModel):
    """Request to reschedule inspection task."""
    new_due_date: datetime = Field(..., description="New due date")
    reason: str = Field(..., description="Reason for rescheduling")
    rescheduled_by: str = Field(..., description="Who is rescheduling")


class InspectionTaskCompleteRequest(BaseModel):
    """Request to complete inspection task."""
    completed_by: str = Field(..., description="Who completed the inspection")
    completion_notes: Optional[str] = Field(None, description="Completion notes")
    actual_duration_minutes: Optional[int] = Field(None, description="Actual duration in minutes")


class InspectionCalendarRequest(BaseModel):
    """Request for inspection calendar."""
    start_date: datetime = Field(..., description="Calendar start date")
    end_date: datetime = Field(..., description="Calendar end date")
    assigned_to: Optional[str] = Field(None, description="Filter by technician")
    equipment_id: Optional[str] = Field(None, description="Filter by equipment")


class BulkTaskGenerationRequest(BaseModel):
    """Request for bulk task generation."""
    equipment_ids: List[str] = Field(..., description="List of equipment IDs")
    baseline_type: str = Field(default="periodic", description="Type of baseline to use")


# ============================================================================
# Summary Models
# ============================================================================

class InspectionOverviewResponse(BaseModel):
    """Response with inspection overview statistics."""
    equipment_id: str
    equipment_name: str
    equipment_type: str

    active_schedules: int
    scheduled_tasks: int
    in_progress_tasks: int
    overdue_tasks: int
    completed_last_30_days: int
    open_deficiencies: int
    critical_deficiencies: int


class InspectionTaskSummary(BaseModel):
    """Summary of inspection task statistics."""
    total_tasks_generated: int
    tasks_by_status: Dict[str, int]
    overdue_tasks: int
    completed_last_30_days: int
    total_schedules: int
    active_schedules: int


class InspectionDeficiencySummary(BaseModel):
    """Summary of deficiency statistics."""
    total_deficiencies: int
    by_severity: Dict[str, int]
    resolved: int
    unresolved: int