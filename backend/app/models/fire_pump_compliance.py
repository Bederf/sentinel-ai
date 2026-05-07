"""
Fire Pump Compliance Models

Models for FNBFW:32335 regulatory compliance tracking.
Weekly fire pump run tests required for insurance/regulatory compliance.
"""

from dataclasses import dataclass, field
from datetime import date, datetime
from enum import StrEnum
from typing import Any
from uuid import UUID


class InspectionResult(StrEnum):
    """Result of a fire pump inspection test."""

    PASS = "pass"
    FAIL = "fail"
    INCONCLUSIVE = "inconclusive"


@dataclass
class FirePumpInspection:
    """Fire pump inspection record for regulatory compliance (FNBFW:32335)."""

    id: UUID
    site_code: str
    equipment_id: str
    scheduled_date: date
    completed_date: date | None = None
    result: InspectionResult | None = None
    certified_by: str | None = None
    notes: str | None = None
    regulatory_reference: str = "FNBFW:32335"
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for storage."""
        return {
            "id": str(self.id),
            "site_code": self.site_code,
            "equipment_id": self.equipment_id,
            "scheduled_date": self.scheduled_date.isoformat()
            if isinstance(self.scheduled_date, date)
            else self.scheduled_date,
            "completed_date": self.completed_date.isoformat()
            if isinstance(self.completed_date, date)
            else self.completed_date,
            "result": self.result.value if self.result else None,
            "certified_by": self.certified_by,
            "notes": self.notes,
            "regulatory_reference": self.regulatory_reference,
            "created_at": self.created_at.isoformat() if isinstance(self.created_at, datetime) else self.created_at,
            "updated_at": self.updated_at.isoformat() if isinstance(self.updated_at, datetime) else self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "FirePumpInspection":
        """Create instance from dictionary."""
        scheduled = data.get("scheduled_date")
        completed = data.get("completed_date")

        if isinstance(scheduled, str):
            scheduled = date.fromisoformat(scheduled)
        elif scheduled is None:
            scheduled = date.today()

        if isinstance(completed, str):
            completed = date.fromisoformat(completed)

        result_val = data.get("result")
        result = InspectionResult(result_val) if result_val else None

        created = data.get("created_at")
        updated = data.get("updated_at")

        if isinstance(created, str):
            created = datetime.fromisoformat(created)
        elif created is None:
            created = datetime.now()

        if isinstance(updated, str):
            updated = datetime.fromisoformat(updated)
        elif updated is None:
            updated = datetime.now()

        return cls(
            id=UUID(data["id"]) if isinstance(data.get("id"), str) else data["id"],
            site_code=data["site_code"],
            equipment_id=data["equipment_id"],
            scheduled_date=scheduled,
            completed_date=completed,
            result=result,
            certified_by=data.get("certified_by"),
            notes=data.get("notes"),
            regulatory_reference=data.get("regulatory_reference", "FNBFW:32335"),
            created_at=created,
            updated_at=updated,
        )


@dataclass
class OverdueAlert:
    """Overdue fire pump inspection alert."""

    equipment_id: str
    site_code: str
    last_test_date: date | None
    scheduled_date: date
    days_overdue: int
    regulatory_reference: str = "FNBFW:32335"

    def to_dict(self) -> dict[str, Any]:
        return {
            "equipment_id": self.equipment_id,
            "site_code": self.site_code,
            "last_test_date": self.last_test_date.isoformat() if self.last_test_date else None,
            "scheduled_date": self.scheduled_date.isoformat(),
            "days_overdue": self.days_overdue,
            "regulatory_reference": self.regulatory_reference,
        }


@dataclass
class ComplianceReport:
    """Fire pump compliance report for a site."""

    site_code: str
    start_date: date
    end_date: date
    total_tests: int
    passed: int
    failed: int
    inconclusive: int
    overdue_count: int
    compliance_rate: float
    regulatory_reference: str = "FNBFW:32335"

    def to_dict(self) -> dict[str, Any]:
        return {
            "site_code": self.site_code,
            "start_date": self.start_date.isoformat(),
            "end_date": self.end_date.isoformat(),
            "total_tests": self.total_tests,
            "passed": self.passed,
            "failed": self.failed,
            "inconclusive": self.inconclusive,
            "overdue_count": self.overdue_count,
            "compliance_rate": round(self.compliance_rate, 2),
            "regulatory_reference": self.regulatory_reference,
        }
