"""
Baseline Repository - Database operations for baseline management

Handles CRUD operations for:
- Equipment baselines
- Equipment elements
- Element baselines
- Baseline comparisons

Phase 44: Asset Baseline Assessment
"""

from typing import List, Optional, Dict, Any
import uuid
from datetime import datetime

from app.models.baseline import (
    EquipmentBaseline,
    ElementBaseline,
    BaselineComparison,
    EquipmentElement
)
from app.database.supabase_client import supabase


class BaselineRepository:
    """Repository for baseline database operations."""

    # ============================================================================
    # Equipment Baseline Operations
    # ============================================================================

    async def create_equipment_baseline(
        self,
        equipment_id: str,
        captured_by: str,
        baseline_type: str,
        baseline_values: Dict[str, Any],
        measurement_conditions: Optional[Dict[str, Any]] = None,
        source_type: str = "manual",
        notes: Optional[str] = None,
        attachment_urls: Optional[List[str]] = None
    ) -> EquipmentBaseline:
        """Create a new equipment baseline record."""
        data = {
            "id": str(uuid.uuid4()),
            "equipment_id": equipment_id,
            "baseline_date": datetime.now().isoformat(),
            "captured_by": captured_by,
            "baseline_type": baseline_type,
            "status": "active",
            "baseline_values": baseline_values,
            "measurement_conditions": measurement_conditions or {},
            "source_type": source_type,
            "notes": notes,
            "attachment_urls": attachment_urls or [],
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat()
        }

        result = supabase.table("equipment_baselines").insert(data).execute()
        return EquipmentBaseline(**result.data[0])

    async def get_equipment_baseline(
        self,
        baseline_id: str
    ) -> Optional[EquipmentBaseline]:
        """Get equipment baseline by ID."""
        result = supabase.table("equipment_baselines").select("*").eq("id", baseline_id).execute()
        if result.data:
            return EquipmentBaseline(**result.data[0])
        return None

    async def get_active_equipment_baseline(
        self,
        equipment_id: str
    ) -> Optional[EquipmentBaseline]:
        """Get the most recent active baseline for equipment."""
        result = supabase.table("equipment_baselines").select("*").eq("equipment_id", equipment_id).eq("status", "active").order("baseline_date", desc=True).limit(1).execute()
        if result.data:
            return EquipmentBaseline(**result.data[0])
        return None

    async def get_equipment_baseline_history(
        self,
        equipment_id: str,
        limit: int = 10
    ) -> List[EquipmentBaseline]:
        """Get baseline history for equipment."""
        result = supabase.table("equipment_baselines").select("*").eq("equipment_id", equipment_id).order("baseline_date", desc=True).limit(limit).execute()
        return [EquipmentBaseline(**row) for row in result.data]

    async def archive_equipment_baseline(self, baseline_id: str):
        """Archive a baseline (set status to archived)."""
        supabase.table("equipment_baselines").update({"status": "archived"}).eq("id", baseline_id).execute()

    async def archive_old_baselines(self, equipment_id: str, keep_last: int = 5):
        """Archive old baselines, keeping only the last N active ones."""
        # Get all active baselines sorted by date
        result = supabase.table("equipment_baselines").select("id").eq("equipment_id", equipment_id).eq("status", "active").order("baseline_date", desc=True).execute()

        baselines = result.data
        if len(baselines) <= keep_last:
            return

        # Archive older baselines
        baselines_to_archive = baselines[keep_last:]
        for baseline in baselines_to_archive:
            await self.archive_equipment_baseline(baseline["id"])

    # ============================================================================
    # Equipment Element Operations
    # ============================================================================

    async def create_equipment_element(
        self,
        equipment_id: str,
        element_id: str,
        element_type: str,
        element_name: Optional[str] = None,
        manufacturer: Optional[str] = None,
        model: Optional[str] = None,
        serial_number: Optional[str] = None,
        installation_date: Optional[str] = None,
        expected_life_days: Optional[int] = None,
        criticality: str = "medium"
    ) -> EquipmentElement:
        """Create a new equipment element."""
        element_name = element_name or element_id.replace("_", " ").title()

        data = {
            "id": str(uuid.uuid4()),
            "equipment_id": equipment_id,
            "element_id": element_id,
            "element_type": element_type,
            "element_name": element_name,
            "manufacturer": manufacturer,
            "model": model,
            "serial_number": serial_number,
            "installation_date": installation_date,
            "expected_life_days": expected_life_days,
            "criticality": criticality,
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat()
        }

        result = supabase.table("equipment_elements").insert(data).execute()
        return EquipmentElement(**result.data[0])

    async def get_element(
        self,
        equipment_id: str,
        element_id: str
    ) -> Optional[EquipmentElement]:
        """Get equipment element by equipment_id and element_id."""
        result = supabase.table("equipment_elements").select("*").eq("equipment_id", equipment_id).eq("element_id", element_id).execute()
        if result.data:
            return EquipmentElement(**result.data[0])
        return None

    async def get_or_create_element(
        self,
        equipment_id: str,
        element_id: str,
        element_type: str
    ) -> EquipmentElement:
        """Get existing element or create if not exists."""
        element = await self.get_element(equipment_id, element_id)
        if element:
            return element

        # Format a nice name
        element_name = element_id.replace("_", " ").replace("-", " ").title()

        return await self.create_equipment_element(
            equipment_id=equipment_id,
            element_id=element_id,
            element_type=element_type,
            element_name=element_name,
            criticality="medium"  # Default, can be updated
        )

    async def get_equipment_elements(
        self,
        equipment_id: str
    ) -> List[EquipmentElement]:
        """Get all elements for equipment."""
        result = supabase.table("equipment_elements").select("*").eq("equipment_id", equipment_id).order("element_id").execute()
        return [EquipmentElement(**row) for row in result.data]

    # ============================================================================
    # Element Baseline Operations
    # ============================================================================

    async def create_element_baseline(
        self,
        element_id: str,
        captured_by: str,
        baseline_type: str,
        measurement_type: str,
        baseline_values: Dict[str, Any],
        measurement_conditions: Optional[Dict[str, Any]] = None,
        notes: Optional[str] = None,
        attachment_urls: Optional[List[str]] = None
    ) -> ElementBaseline:
        """Create a new element baseline record."""
        data = {
            "id": str(uuid.uuid4()),
            "element_id": element_id,
            "baseline_date": datetime.now().isoformat(),
            "captured_by": captured_by,
            "baseline_type": baseline_type,
            "status": "active",
            "baseline_values": baseline_values,
            "measurement_type": measurement_type,
            "measurement_conditions": measurement_conditions or {},
            "source_type": "mobile_sensor",  # Most element measurements from mobile
            "notes": notes,
            "attachment_urls": attachment_urls or [],
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat()
        }

        result = supabase.table("element_baselines").insert(data).execute()
        return ElementBaseline(**result.data[0])

    async def get_active_element_baseline(
        self,
        element_id: str
    ) -> Optional[ElementBaseline]:
        """Get most recent active baseline for element."""
        result = supabase.table("element_baselines").select("*").eq("element_id", element_id).eq("status", "active").order("baseline_date", desc=True).limit(1).execute()
        if result.data:
            return ElementBaseline(**result.data[0])
        return None

    async def get_element_baseline_history(
        self,
        element_id: str,
        limit: int = 10
    ) -> List[ElementBaseline]:
        """Get baseline history for element."""
        result = supabase.table("element_baselines").select("*").eq("element_id", element_id).order("baseline_date", desc=True).limit(limit).execute()
        return [ElementBaseline(**row) for row in result.data]

    # ============================================================================
    # Baseline Comparison Operations
    # ============================================================================

    async def create_baseline_comparison(
        self,
        comparison_type: str,
        baseline_id: str,
        equipment_id: str,
        comparison_results: Dict[str, Any],
        overall_status: str,
        max_deviation_percent: float,
        data_source: str,
        element_id: Optional[str] = None,
        comparison_notes: Optional[str] = None,
        alert_generated: bool = False,
        alert_id: Optional[str] = None
    ) -> BaselineComparison:
        """Create a new baseline comparison record."""
        data = {
            "id": str(uuid.uuid4()),
            "comparison_type": comparison_type,
            "baseline_id": baseline_id,
            "equipment_id": equipment_id,
            "element_id": element_id,
            "comparison_date": datetime.now().isoformat(),
            "comparison_results": comparison_results,
            "overall_status": overall_status,
            "max_deviation_percent": max_deviation_percent,
            "data_source": data_source,
            "comparison_notes": comparison_notes,
            "alert_generated": alert_generated,
            "alert_id": alert_id,
            "created_at": datetime.now().isoformat()
        }

        result = supabase.table("baseline_comparisons").insert(data).execute()
        return BaselineComparison(**result.data[0])

    async def get_recent_comparisons(
        self,
        equipment_id: str,
        limit: int = 10
    ) -> List[BaselineComparison]:
        """Get recent baseline comparisons for equipment."""
        result = supabase.table("baseline_comparisons").select("*").eq("equipment_id", equipment_id).order("comparison_date", desc=True).limit(limit).execute()
        return [BaselineComparison(**row) for row in result.data]

    async def get_critical_deviations(
        self,
        equipment_id: Optional[str] = None,
        days: int = 30
    ) -> List[BaselineComparison]:
        """Get critical deviation comparisons."""
        query = supabase.table("baseline_comparisons").select("*").eq("overall_status", "critical").gte("comparison_date", datetime.now() - timedelta(days=days).isoformat()).order("comparison_date", desc=True)

        if equipment_id:
            query = query.eq("equipment_id", equipment_id)

        result = query.execute()
        return [BaselineComparison(**row) for row in result.data]

    # ============================================================================
    # Summary and Reporting
    # ============================================================================

    async def get_baseline_summary(self, equipment_id: str) -> Dict[str, Any]:
        """Get baseline summary statistics for equipment."""
        # Get active baseline
        active_baseline = await self.get_active_equipment_baseline(equipment_id)

        # Get baseline count
        baseline_count = len(await self.get_equipment_baseline_history(equipment_id, limit=1000))

        # Get elements with baselines
        elements = await self.get_equipment_elements(equipment_id)
        elements_with_baselines = 0
        for element in elements:
            if await self.get_active_element_baseline(element.id):
                elements_with_baselines += 1

        return {
            "equipment_id": equipment_id,
            "has_active_baseline": active_baseline is not None,
            "total_baselines": baseline_count,
            "total_elements": len(elements),
            "elements_with_baselines": elements_with_baselines,
            "last_baseline_date": active_baseline.baseline_date if active_baseline else None
        }
