"""
Inspection Scheduling Engine

Automatically generates inspection tasks from schedules and manages inspection lifecycle.

Phase 45: Routine Inspection & Maintenance
"""

import logging
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Tuple
import asyncio

from app.models.inspection import (
    InspectionSchedule,
    InspectionTask,
    InspectionTaskStatus,
    InspectionScheduleFrequency
)
from app.database.repositories.inspection_repository import InspectionRepository
from app.services.baseline_service import get_baseline_service

logger = logging.getLogger(__name__)


class InspectionScheduler:
    """Service for generating and managing inspection tasks."""

    def __init__(self):
        self.repository = InspectionRepository()
        self.baseline_service = get_baseline_service()

    async def generate_inspection_tasks(self, equipment_id: Optional[str] = None) -> List[InspectionTask]:
        """
        Generate inspection tasks from active schedules.

        For each active schedule, create a task if:
        1. It's the first run (no last_generated_date)
        2. Enough time has passed based on frequency

        Args:
            equipment_id: Optional filter for specific equipment

        Returns:
            List of newly created inspection tasks
        """
        # Get active schedules
        schedules = await self.repository.get_active_schedules(equipment_id)
        created_tasks = []

        for schedule in schedules:
            try:
                # Check if task should be generated
                if not await self._should_generate_task(schedule):
                    continue

                # Generate next task
                task = await self._generate_single_task(schedule)
                created_tasks.append(task)

                # Update schedule last_generated_date
                await self.repository.update_schedule_last_generated(
                    schedule_id=schedule.id,
                    last_generated_date=datetime.now()
                )

                # Calculate next due date
                next_due = self._calculate_next_due_date(schedule)
                await self.repository.update_schedule_next_due(
                    schedule_id=schedule.id,
                    next_due_date=next_due
                )

                logger.info(f"Generated inspection task: {task.task_name} (ID: {task.id})")

            except Exception as e:
                logger.error(f"Failed to generate task for schedule {schedule.id}: {e}")

        logger.info(f"Generated {len(created_tasks)} inspection tasks")
        return created_tasks

    async def _should_generate_task(self, schedule: InspectionSchedule) -> bool:
        """Determine if a task should be generated for the schedule."""
        # If never generated before, generate now
        if not schedule.last_generated_date:
            return True

        # Calculate days since last generation
        days_since_last = (datetime.now() - schedule.last_generated_date).days

        # Check based on frequency type
        if schedule.frequency_type == InspectionScheduleFrequency.WEEKLY:
            return days_since_last >= 7
        elif schedule.frequency_type == InspectionScheduleFrequency.MONTHLY:
            return days_since_last >= 30
        elif schedule.frequency_type == InspectionScheduleFrequency.QUARTERLY:
            return days_since_last >= 90
        elif schedule.frequency_type == InspectionScheduleFrequency.ANNUAL:
            return days_since_last >= 365
        elif schedule.frequency_type == InspectionScheduleFrequency.CUSTOM:
            return days_since_last >= (schedule.frequency_days or 30)

        return False

    async def _generate_single_task(self, schedule: InspectionSchedule) -> InspectionTask:
        """Generate a single inspection task from a schedule."""
        # Determine task dates
        scheduled_date = datetime.now()
        due_date = self._calculate_due_date(schedule, scheduled_date)

        # Build task name
        element_desc = f" - {schedule.element_id}" if schedule.element_id else ""
        task_name = f"{schedule.schedule_name}{element_desc}"

        # Set priority based on critical elements
        is_critical = await self._is_inspection_critical(schedule)
        priority = "urgent" if is_critical else (
            "high" if schedule.frequency_type in [InspectionScheduleFrequency.WEEKLY] else "normal"
        )

        # Get baseline reference
        baseline_ref = None
        if schedule.equipment_id:
            baseline = await self.baseline_service.repository.get_active_equipment_baseline(
                schedule.equipment_id
            )
            baseline_ref = baseline.id if baseline else None

        # Create task
        task_data = {
            "schedule_id": schedule.id,
            "task_name": task_name,
            "task_description": schedule.schedule_description,
            "equipment_id": schedule.equipment_id,
            "element_id": schedule.element_id,
            "scheduled_date": scheduled_date,
            "due_date": due_date,
            "assigned_to": schedule.assigned_to,
            "assigned_by": "system",  # System generated
            "status": InspectionTaskStatus.SCHEDULED,
            "estimated_duration_minutes": schedule.estimated_duration_minutes,
            "priority": priority,
            "is_critical": is_critical,
            "baseline_reference_id": baseline_ref
        }

        return await self.repository.create_inspection_task(task_data)

    def _calculate_due_date(self, schedule: InspectionSchedule, scheduled_date: datetime) -> datetime:
        """Calculate due date for an inspection task."""
        # Default to 7 days for completion
        return scheduled_date + timedelta(days=7)

    def _calculate_next_due_date(self, schedule: InspectionSchedule) -> datetime:
        """Calculate next due date for a schedule."""
        now = datetime.now()

        if schedule.frequency_type == InspectionScheduleFrequency.WEEKLY:
            # Next weekly due date
            if schedule.day_of_week is not None:
                # Specific day of week
                days_ahead = schedule.day_of_week - now.weekday()
                if days_ahead <= 0:
                    days_ahead += 7
                return now + timedelta(days=days_ahead)
            else:
                return now + timedelta(days=7)

        elif schedule.frequency_type == InspectionScheduleFrequency.MONTHLY:
            # Next monthly due date
            if schedule.day_of_month:
                # Specific day of month
                try:
                    next_date = now.replace(day=schedule.day_of_month)
                    if next_date <= now:
                        # Move to next month
                        if now.month == 12:
                            next_date = now.replace(year=now.year + 1, month=1, day=schedule.day_of_month)
                        else:
                            next_date = now.replace(month=now.month + 1, day=schedule.day_of_month)
                    return next_date
                except ValueError:
                    # Day doesn't exist in month (e.g., Feb 30)
                    return now + timedelta(days=30)
            else:
                return now + timedelta(days=30)

        elif schedule.frequency_type == InspectionScheduleFrequency.QUARTERLY:
            return now + timedelta(days=90)

        elif schedule.frequency_type == InspectionScheduleFrequency.ANNUAL:
            return now + timedelta(days=365)

        elif schedule.frequency_type == InspectionScheduleFrequency.CUSTOM:
            days = schedule.frequency_days or 30
            return now + timedelta(days=days)

        # Default to monthly
        return now + timedelta(days=30)

    async def _is_inspection_critical(self, schedule: InspectionSchedule) -> bool:
        """Determine if inspection should be marked as critical."""
        # Check if schedule is for critical element
        if schedule.element_id:
            element = await self.baseline_service.repository.get_element_by_id(
                schedule.element_id
            )
            if element and element.criticality in ["high", "critical"]:
                return True

        # Check if equipment has critical elements
        if schedule.equipment_id:
            elements = await self.baseline_service.repository.get_equipment_elements(
                schedule.equipment_id
            )
            critical_count = sum(1 for e in elements if e.criticality in ["high", "critical"])
            return critical_count > 0

        return False

    async def get_due_inspections(
        self,
        assigned_to: Optional[str] = None,
        equipment_id: Optional[str] = None,
        days_ahead: int = 7
    ) -> List[InspectionTask]:
        """
        Get inspection tasks that are due or overdue.

        Args:
            assigned_to: Filter by assigned technician
            equipment_id: Filter by equipment
            days_ahead: Include tasks due within this many days

        Returns:
            List of due inspection tasks
        """
        now = datetime.now()
        due_before = now + timedelta(days=days_ahead)

        return await self.repository.get_tasks_due_before(
            due_date=due_before,
            assigned_to=assigned_to,
            equipment_id=equipment_id
        )

    async def get_overdue_inspections(
        self,
        assigned_to: Optional[str] = None,
        equipment_id: Optional[str] = None
    ) -> List[InspectionTask]:
        """Get inspection tasks that are overdue."""
        now = datetime.now()

        return await self.repository.get_overdue_tasks(
            overdue_date=now,
            assigned_to=assigned_to,
            equipment_id=equipment_id
        )

    async def mark_task_in_progress(
        self,
        task_id: str,
        started_by: str
    ) -> Optional[InspectionTask]:
        """Mark an inspection task as in progress."""
        return await self.repository.update_task_status(
            task_id=task_id,
            status=InspectionTaskStatus.IN_PROGRESS,
            started_at=datetime.now(),
            completed_by=started_by
        )

    async def mark_task_complete(
        self,
        task_id: str,
        completed_by: str,
        completion_notes: Optional[str] = None,
        actual_duration_minutes: Optional[int] = None
    ) -> Optional[InspectionTask]:
        """Mark an inspection task as completed."""
        return await self.repository.update_task_status(
            task_id=task_id,
            status=InspectionTaskStatus.COMPLETED,
            completed_date=datetime.now(),
            completed_by=completed_by,
            completion_notes=completion_notes,
            actual_duration_minutes=actual_duration_minutes
        )

    async def reschedule_task(
        self,
        task_id: str,
        new_due_date: datetime,
        reason: str,
        rescheduled_by: str
    ) -> Optional[InspectionTask]:
        """Reschedule an inspection task to a new due date."""
        # Create a note about the rescheduling
        notes = f"Rescheduled by {rescheduled_by}. Reason: {reason}"

        return await self.repository.update_task_scheduling(
            task_id=task_id,
            new_due_date=new_due_date,
            scheduling_notes=notes
        )

    async def cancel_task(
        self,
        task_id: str,
        cancellation_reason: str,
        cancelled_by: str
    ) -> Optional[InspectionTask]:
        """Cancel an inspection task."""
        return await self.repository.update_task_status(
            task_id=task_id,
            status=InspectionTaskStatus.CANCELLED,
            completion_notes=f"Cancelled by {cancelled_by}. Reason: {cancellation_reason}"
        )

    async def update_task_assignment(
        self,
        task_id: str,
        assigned_to: str,
        assigned_by: str
    ) -> Optional[InspectionTask]:
        """Reassign an inspection task to a different technician."""
        return await self.repository.update_task_assignment(
            task_id=task_id,
            assigned_to=assigned_to,
            assigned_by=assigned_by
        )

    async def bulk_generate_tasks(self, equipment_ids: List[str]) -> Dict[str, Any]:
        """
        Generate inspection tasks for multiple equipment in bulk.

        Args:
            equipment_ids: List of equipment IDs

        Returns:
            Summary of generated tasks
        """
        results = {
            "total_equipment": len(equipment_ids),
            "generated_tasks": 0,
            "skipped_equipment": 0,
            "errors": []
        }

        for equipment_id in equipment_ids:
            try:
                tasks = await self.generate_inspection_tasks(equipment_id)
                results["generated_tasks"] += len(tasks)

                if len(tasks) == 0:
                    results["skipped_equipment"] += 1

            except Exception as e:
                results["errors"].append({
                    "equipment_id": equipment_id,
                    "error": str(e)
                })

        logger.info(f"Bulk generation complete: {results['generated_tasks']} tasks for {results['total_equipment']} equipment")
        return results

    async def get_inspection_calendar(
        self,
        start_date: datetime,
        end_date: datetime,
        assigned_to: Optional[str] = None,
        equipment_id: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Get inspection tasks formatted for calendar display.

        Args:
            start_date: Calendar start date
            end_date: Calendar end date
            assigned_to: Filter by technician
            equipment_id: Filter by equipment

        Returns:
            List of calendar events
        """
        tasks = await self.repository.get_tasks_in_date_range(
            start_date=start_date,
            end_date=end_date,
            assigned_to=assigned_to,
            equipment_id=equipment_id
        )

        calendar_events = []
        for task in tasks:
            event = {
                "id": task.id,
                "title": task.task_name,
                "start": task.scheduled_date.isoformat(),
                "end": (task.scheduled_date + timedelta(
                    minutes=task.estimated_duration_minutes or 60
                )).isoformat(),
                "status": task.status,
                "priority": task.priority,
                "equipment_id": task.equipment_id,
                "assigned_to": task.assigned_to,
                "is_critical": task.is_critical
            }
            calendar_events.append(event)

        return calendar_events

    async def get_schedule_statistics(self, equipment_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Get inspection scheduling statistics.

        Args:
            equipment_id: Optional filter for specific equipment

        Returns:
            Statistics dictionary
        """
        stats = await self.repository.get_schedule_statistics(equipment_id)

        # Add overdue counts
        overdue_tasks = await self.get_overdue_inspections(equipment_id=equipment_id)
        stats["overdue_tasks"] = len(overdue_tasks)

        # Add completion rate (last 30 days)
        completed_last_30 = await self.repository.get_completed_task_count(
            equipment_id=equipment_id,
            days_back=30
        )
        stats["completed_last_30_days"] = completed_last_30

        return stats


# Singleton instance
_scheduler = None


def get_inspection_scheduler() -> InspectionScheduler:
    """Get singleton inspection scheduler instance."""
    global _scheduler
    if _scheduler is None:
        _scheduler = InspectionScheduler()
    return _scheduler
