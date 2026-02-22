"""
Inspection Repository - Database operations for inspection management

Handles CRUD operations for:
- Inspection schedules
- Inspection tasks
- Inspection results
- Inspection deficiencies

Phase 45: Routine Inspection & Maintenance
"""

from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any
import uuid

from app.models.inspection import (
    InspectionSchedule,
    InspectionTask,
    InspectionResult,
    InspectionDeficiency,
    InspectionMeasurement,
)
from app.database.supabase_client import get_supabase_client


class InspectionRepository:
    """Repository for inspection database operations."""

    # ============================================================================
    # Inspection Schedule Operations
    # ============================================================================

    async def create_inspection_schedule(self, schedule_data: Dict[str, Any]) -> InspectionSchedule:
        """Create a new inspection schedule."""
        schedule_data["id"] = str(uuid.uuid4())
        schedule_data["created_at"] = datetime.now().isoformat()
        schedule_data["updated_at"] = datetime.now().isoformat()

        result = get_supabase_client().table("inspection_schedules").insert(schedule_data).execute()
        return InspectionSchedule(**result.data[0])

    async def get_inspection_schedule(self, schedule_id: str) -> Optional[InspectionSchedule]:
        """Get inspection schedule by ID."""
        result = get_supabase_client().table("inspection_schedules").select("*").eq("id", schedule_id).execute()
        if result.data:
            return InspectionSchedule(**result.data[0])
        return None

    async def get_active_schedules(self, equipment_id: Optional[str] = None) -> List[InspectionSchedule]:
        """Get all active inspection schedules."""
        query = get_supabase_client().table("inspection_schedules").select("*").eq("is_active", True)

        if equipment_id:
            query = query.eq("equipment_id", equipment_id)

        result = query.order("created_at").execute()
        return [InspectionSchedule(**row) for row in result.data]

    async def update_schedule_last_generated(self, schedule_id: str, last_generated_date: datetime):
        """Update schedule last_generated_date."""
        get_supabase_client().table("inspection_schedules").update(
            {"last_generated_date": last_generated_date, "updated_at": datetime.now().isoformat()}
        ).eq("id", schedule_id).execute()

    async def update_schedule_next_due(self, schedule_id: str, next_due_date: datetime):
        """Update schedule next_due_date."""
        get_supabase_client().table("inspection_schedules").update(
            {"next_due_date": next_due_date, "updated_at": datetime.now().isoformat()}
        ).eq("id", schedule_id).execute()

    async def deactivate_schedule(self, schedule_id: str):
        """Deactivate an inspection schedule."""
        get_supabase_client().table("inspection_schedules").update(
            {"is_active": False, "updated_at": datetime.now().isoformat()}
        ).eq("id", schedule_id).execute()

    # ============================================================================
    # Inspection Task Operations
    # ============================================================================

    async def create_inspection_task(self, task_data: Dict[str, Any]) -> InspectionTask:
        """Create a new inspection task."""
        task_data["id"] = str(uuid.uuid4())
        task_data["created_at"] = datetime.now().isoformat()
        task_data["updated_at"] = datetime.now().isoformat()

        result = get_supabase_client().table("inspection_tasks").insert(task_data).execute()
        return InspectionTask(**result.data[0])

    async def get_inspection_task(self, task_id: str) -> Optional[InspectionTask]:
        """Get inspection task by ID."""
        result = get_supabase_client().table("inspection_tasks").select("*").eq("id", task_id).execute()
        if result.data:
            return InspectionTask(**result.data[0])
        return None

    async def get_tasks_due_before(
        self, due_date: datetime, assigned_to: Optional[str] = None, equipment_id: Optional[str] = None
    ) -> List[InspectionTask]:
        """Get inspection tasks due before specified date."""
        query = (
            get_supabase_client()
            .table("inspection_tasks")
            .select("*")
            .eq("status", "scheduled")
            .lt("due_date", due_date.isoformat())
        )

        if assigned_to:
            query = query.eq("assigned_to", assigned_to)
        if equipment_id:
            query = query.eq("equipment_id", equipment_id)

        result = query.order("due_date").execute()
        return [InspectionTask(**row) for row in result.data]

    async def get_overdue_tasks(
        self, overdue_date: datetime, assigned_to: Optional[str] = None, equipment_id: Optional[str] = None
    ) -> List[InspectionTask]:
        """Get overdue inspection tasks."""
        query = (
            get_supabase_client()
            .table("inspection_tasks")
            .select("*")
            .eq("status", "scheduled")
            .lt("due_date", overdue_date.isoformat())
        )

        if assigned_to:
            query = query.eq("assigned_to", assigned_to)
        if equipment_id:
            query = query.eq("equipment_id", equipment_id)

        result = query.order("due_date").execute()
        return [InspectionTask(**row) for row in result.data]

    async def update_task_status(self, task_id: str, status: str, **kwargs) -> Optional[InspectionTask]:
        """Update inspection task status."""
        update_data = {"status": status, "updated_at": datetime.now().isoformat()}

        # Add optional fields
        if "started_at" in kwargs:
            update_data["started_at"] = kwargs["started_at"]
        if "completed_date" in kwargs:
            update_data["completed_date"] = kwargs["completed_date"]
        if "completed_by" in kwargs:
            update_data["completed_by"] = kwargs["completed_by"]
        if "completion_notes" in kwargs:
            update_data["completion_notes"] = kwargs["completion_notes"]
        if "actual_duration_minutes" in kwargs:
            update_data["actual_duration_minutes"] = kwargs["actual_duration_minutes"]

        result = get_supabase_client().table("inspection_tasks").update(update_data).eq("id", task_id).execute()
        if result.data:
            return InspectionTask(**result.data[0])
        return None

    async def update_task_scheduling(
        self, task_id: str, new_due_date: datetime, scheduling_notes: str
    ) -> Optional[InspectionTask]:
        """Update task scheduling."""
        update_data = {"due_date": new_due_date, "updated_at": datetime.now().isoformat()}

        # Append to existing notes
        task = await self.get_inspection_task(task_id)
        if task:
            existing_notes = task.completion_notes or ""
            update_data["completion_notes"] = f"{existing_notes}\n{scheduling_notes}".strip()

        result = get_supabase_client().table("inspection_tasks").update(update_data).eq("id", task_id).execute()
        if result.data:
            return InspectionTask(**result.data[0])
        return None

    async def update_task_assignment(
        self, task_id: str, assigned_to: str, assigned_by: str
    ) -> Optional[InspectionTask]:
        """Update task assignment."""
        update_data = {"assigned_to": assigned_to, "assigned_by": assigned_by, "updated_at": datetime.now().isoformat()}

        result = get_supabase_client().table("inspection_tasks").update(update_data).eq("id", task_id).execute()
        if result.data:
            return InspectionTask(**result.data[0])
        return None

    async def get_tasks_in_date_range(
        self,
        start_date: datetime,
        end_date: datetime,
        assigned_to: Optional[str] = None,
        equipment_id: Optional[str] = None,
    ) -> List[InspectionTask]:
        """Get tasks within date range."""
        query = (
            get_supabase_client()
            .table("inspection_tasks")
            .select("*")
            .gte("scheduled_date", start_date.isoformat())
            .lte("scheduled_date", end_date.isoformat())
        )

        if assigned_to:
            query = query.eq("assigned_to", assigned_to)
        if equipment_id:
            query = query.eq("equipment_id", equipment_id)

        result = query.order("scheduled_date").execute()
        return [InspectionTask(**row) for row in result.data]

    async def get_tasks_by_equipment(
        self, equipment_id: str, status: Optional[str] = None, limit: int = 100
    ) -> List[InspectionTask]:
        """Get tasks for specific equipment."""
        query = get_supabase_client().table("inspection_tasks").select("*").eq("equipment_id", equipment_id)

        if status:
            query = query.eq("status", status)

        result = query.order("scheduled_date", desc=True).limit(limit).execute()
        return [InspectionTask(**row) for row in result.data]

    async def get_completed_task_count(self, equipment_id: Optional[str] = None, days_back: int = 30) -> int:
        """Get count of completed tasks in last N days."""
        start_date = datetime.now() - timedelta(days=days_back)

        query = (
            get_supabase_client()
            .table("inspection_tasks")
            .select("id")
            .eq("status", "completed")
            .gte("completed_date", start_date.isoformat())
        )

        if equipment_id:
            query = query.eq("equipment_id", equipment_id)

        result = query.execute()
        return len(result.data)

    # ============================================================================
    # Inspection Result Operations
    # ============================================================================

    async def create_inspection_result(self, result_data: Dict[str, Any]) -> InspectionResult:
        """Create a new inspection result."""
        result_data["id"] = str(uuid.uuid4())
        result_data["created_at"] = datetime.now().isoformat()
        result_data["updated_at"] = datetime.now().isoformat()

        result = get_supabase_client().table("inspection_results").insert(result_data).execute()
        return InspectionResult(**result.data[0])

    async def get_inspection_result(self, result_id: str) -> Optional[InspectionResult]:
        """Get inspection result by ID."""
        result = get_supabase_client().table("inspection_results").select("*").eq("id", result_id).execute()
        if result.data:
            return InspectionResult(**result.data[0])
        return None

    async def get_results_by_task(self, task_id: str) -> List[InspectionResult]:
        """Get inspection results for a task."""
        result = (
            get_supabase_client()
            .table("inspection_results")
            .select("*")
            .eq("task_id", task_id)
            .order("inspection_date", desc=True)
            .execute()
        )
        return [InspectionResult(**row) for row in result.data]

    async def get_results_by_equipment(self, equipment_id: str, limit: int = 50) -> List[InspectionResult]:
        """Get inspection results for equipment."""
        result = (
            get_supabase_client()
            .table("inspection_results")
            .select("*")
            .eq("equipment_id", equipment_id)
            .order("inspection_date", desc=True)
            .limit(limit)
            .execute()
        )
        return [InspectionResult(**row) for row in result.data]

    # ============================================================================
    # Inspection Deficiency Operations
    # ============================================================================

    async def create_inspection_deficiency(self, deficiency_data: Dict[str, Any]) -> InspectionDeficiency:
        """Create a new inspection deficiency."""
        deficiency_data["id"] = str(uuid.uuid4())
        deficiency_data["reported_date"] = datetime.now().isoformat()
        deficiency_data["updated_at"] = datetime.now().isoformat()

        result = get_supabase_client().table("inspection_deficiencies").insert(deficiency_data).execute()
        return InspectionDeficiency(**result.data[0])

    async def get_inspection_deficiency(self, deficiency_id: str) -> Optional[InspectionDeficiency]:
        """Get inspection deficiency by ID."""
        result = get_supabase_client().table("inspection_deficiencies").select("*").eq("id", deficiency_id).execute()
        if result.data:
            return InspectionDeficiency(**result.data[0])
        return None

    async def get_deficiencies_by_equipment(
        self, equipment_id: str, resolved: Optional[bool] = None
    ) -> List[InspectionDeficiency]:
        """Get deficiencies for equipment."""
        query = get_supabase_client().table("inspection_deficiencies").select("*").eq("equipment_id", equipment_id)

        if resolved is not None:
            query = query.eq("is_resolved", resolved)

        result = query.order("reported_date", desc=True).execute()
        return [InspectionDeficiency(**row) for row in result.data]

    async def get_unresolved_deficiencies(
        self, equipment_id: Optional[str] = None, severity: Optional[str] = None
    ) -> List[InspectionDeficiency]:
        """Get unresolved deficiencies."""
        query = get_supabase_client().table("inspection_deficiencies").select("*").eq("is_resolved", False)

        if equipment_id:
            query = query.eq("equipment_id", equipment_id)
        if severity:
            query = query.eq("severity", severity)

        result = query.order("reported_date").execute()
        return [InspectionDeficiency(**row) for row in result.data]

    async def resolve_deficiency(
        self, deficiency_id: str, resolved_by: str, resolution_notes: str
    ) -> Optional[InspectionDeficiency]:
        """Mark a deficiency as resolved."""
        update_data = {
            "is_resolved": True,
            "resolved_date": datetime.now().isoformat(),
            "resolved_by": resolved_by,
            "resolution_notes": resolution_notes,
            "updated_at": datetime.now().isoformat(),
        }

        result = (
            get_supabase_client().table("inspection_deficiencies").update(update_data).eq("id", deficiency_id).execute()
        )
        if result.data:
            return InspectionDeficiency(**result.data[0])
        return None

    async def escalate_deficiency(
        self, deficiency_id: str, new_severity: str, escalation_notes: str
    ) -> Optional[InspectionDeficiency]:
        """Escalate deficiency severity."""
        update_data = {
            "severity": new_severity,
            "escalation_notes": escalation_notes,
            "updated_at": datetime.now().isoformat(),
        }

        result = (
            get_supabase_client().table("inspection_deficiencies").update(update_data).eq("id", deficiency_id).execute()
        )
        if result.data:
            return InspectionDeficiency(**result.data[0])
        return None

    # ============================================================================
    # Statistics and Reporting
    # ============================================================================

    async def get_schedule_statistics(self, equipment_id: Optional[str] = None) -> Dict[str, Any]:
        """Get inspection scheduling statistics."""
        stats = {
            "total_schedules": 0,
            "active_schedules": 0,
            "total_tasks_generated": 0,
            "tasks_by_status": {},
            "overdue_tasks": 0,
        }

        # Get schedule counts
        query = get_supabase_client().table("inspection_schedules").select("id")
        if equipment_id:
            query = query.eq("equipment_id", equipment_id)

        all_schedules = query.execute()
        active_schedules = query.eq("is_active", True).execute()

        stats["total_schedules"] = len(all_schedules.data)
        stats["active_schedules"] = len(active_schedules.data)

        # Get task statistics
        task_query = get_supabase_client().table("inspection_tasks").select("status", count="exact")
        if equipment_id:
            task_query = task_query.eq("equipment_id", equipment_id)

        task_counts = task_query.execute()
        stats["total_tasks_generated"] = task_counts.count

        # Get status breakdown
        if equipment_id:
            status_result = (
                get_supabase_client()
                .table("inspection_tasks")
                .select("status")
                .eq("equipment_id", equipment_id)
                .execute()
            )
        else:
            status_result = get_supabase_client().table("inspection_tasks").select("status").execute()

        for row in status_result.data:
            status = row["status"]
            stats["tasks_by_status"][status] = stats["tasks_by_status"].get(status, 0) + 1

        return stats

    async def get_deficiency_statistics(
        self, equipment_id: Optional[str] = None, days_back: int = 30
    ) -> Dict[str, Any]:
        """Get deficiency statistics."""
        start_date = datetime.now() - timedelta(days=days_back)

        query = (
            get_supabase_client()
            .table("inspection_deficiencies")
            .select("severity, is_resolved")
            .gte("reported_date", start_date.isoformat())
        )
        if equipment_id:
            query = query.eq("equipment_id", equipment_id)

        result = query.execute()

        stats = {"total_deficiencies": len(result.data), "by_severity": {}, "resolved": 0, "unresolved": 0}

        for row in result.data:
            severity = row["severity"]
            is_resolved = row["is_resolved"]

            stats["by_severity"][severity] = stats["by_severity"].get(severity, 0) + 1
            if is_resolved:
                stats["resolved"] += 1
            else:
                stats["unresolved"] += 1

        return stats

    # ============================================================================
    # Inspection Measurement Operations
    # ============================================================================

    async def create_inspection_measurement(self, measurement_data: Dict[str, Any]) -> InspectionMeasurement:
        """Create a new inspection measurement record."""
        measurement_data["id"] = str(uuid.uuid4())
        measurement_data["created_at"] = datetime.now().isoformat()

        result = get_supabase_client().table("inspection_measurements").insert(measurement_data).execute()
        return InspectionMeasurement(**result.data[0])

    async def get_measurements_by_result(self, result_id: str) -> List[InspectionMeasurement]:
        """Get all measurements for an inspection result."""
        result = (
            get_supabase_client()
            .table("inspection_measurements")
            .select("*")
            .eq("result_id", result_id)
            .order("measurement_date")
            .execute()
        )
        return [InspectionMeasurement(**row) for row in result.data]

    async def get_measurements_by_equipment(
        self, equipment_id: str, measurement_type: Optional[str] = None, limit: int = 100
    ) -> List[InspectionMeasurement]:
        """Get measurements for equipment."""
        query = get_supabase_client().table("inspection_measurements").select("*").eq("equipment_id", equipment_id)

        if measurement_type:
            query = query.eq("measurement_type", measurement_type)

        result = query.order("measurement_date", desc=True).limit(limit).execute()
        return [InspectionMeasurement(**row) for row in result.data]

    async def get_measurements_with_deviations(
        self, equipment_id: Optional[str] = None, status: str = "warning"
    ) -> List[InspectionMeasurement]:
        """Get measurements with baseline deviations."""
        query = (
            get_supabase_client()
            .table("inspection_measurements")
            .select("*")
            .in_("deviation_status", [status, "critical"])
        )

        if equipment_id:
            query = query.eq("equipment_id", equipment_id)

        result = query.order("measurement_date", desc=True).execute()
        return [InspectionMeasurement(**row) for row in result.data]
