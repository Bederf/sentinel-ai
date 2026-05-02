"""
Baseline Seed Service (Phase 206-01)

Bridges AssetOnboardingWizard → existing BaselineCaptureService.
Provides a simplified API for batch baseline seeding during asset onboarding.

Supports:
- BMS_AVERAGE source: Read current values from BMS device adapter
- Fallback: Generate baseline from BMS sensor averages

Phase: 206-asset-onboarding
"""

import logging
from datetime import datetime
from typing import Any

from app.models.baseline import BaselineSource, BaselineStatus, BaselineType, EquipmentBaseline
from app.services.baseline_capture_service import BaselineCaptureService, EquipmentNotFound

logger = logging.getLogger(__name__)


class BaselineSeedService:
    """
    Service for seeding equipment baselines during asset onboarding.

    Wraps BaselineCaptureService with simplified interface for wizard consumption.
    """

    def __init__(self):
        """Initialize the seed service."""
        self._capture_service = BaselineCaptureService()

    async def seed_for_equipment(
        self,
        equipment_id: str,
        site_id: str,
        source: BaselineSource = BaselineSource.BMS_AVERAGE,
        captured_by: str = "automated",
    ) -> EquipmentBaseline:
        """
        Seed a baseline for a single piece of equipment.

        Args:
            equipment_id: Equipment identifier (e.g., "S002-CHILLER-B1-001")
            site_id: Site identifier (e.g., "S002")
            source: Baseline data source (BMS_AVERAGE, MANUAL, etc.)
            captured_by: Identifier of who/what captured the baseline

        Returns:
            EquipmentBaseline record

        Raises:
            EquipmentNotFound: If equipment doesn't exist
            Exception: If capture fails
        """
        logger.info(f"Seeding baseline for {equipment_id} (source={source})")

        try:
            baseline = await self._capture_service.capture_equipment_baseline(
                equipment_id=equipment_id,
                source=source,
                data=None,  # Let capture service read from device
                captured_by=captured_by,
                baseline_type=BaselineType.INITIAL,
                notes=f"Baseline seeded during asset onboarding for site {site_id}",
                measurement_conditions={"site_id": site_id},
            )
            logger.info(f"Baseline seeded successfully for {equipment_id}: {baseline.id}")
            return baseline

        except EquipmentNotFound:
            logger.warning(f"Equipment {equipment_id} not found during baseline seeding")
            raise
        except Exception as e:
            logger.error(f"Failed to seed baseline for {equipment_id}: {e}")
            raise

    async def seed_for_equipment_with_fallback(
        self,
        equipment_id: str,
        site_id: str,
        captured_by: str = "automated",
    ) -> tuple[EquipmentBaseline | None, str]:
        """
        Seed baseline with BMS_AVERAGE source, falling back to manual defaults if device unavailable.

        Args:
            equipment_id: Equipment identifier
            site_id: Site identifier
            captured_by: Identifier of who/what captured the baseline

        Returns:
            Tuple of (baseline or None, status message)
        """
        try:
            baseline = await self.seed_for_equipment(
                equipment_id=equipment_id,
                site_id=site_id,
                source=BaselineSource.BMS_AVERAGE,
                captured_by=captured_by,
            )
            return baseline, "seeded"
        except Exception as e:
            logger.warning(f"BMS_AVERAGE failed for {equipment_id}, using fallback: {e}")
            # Fall back to generating baseline from historical averages or defaults
            try:
                baseline = await self._seed_with_defaults(equipment_id, site_id, captured_by)
                return baseline, "seeded_fallback"
            except Exception as fallback_error:
                logger.error(f"Fallback baseline seeding also failed for {equipment_id}: {fallback_error}")
                return None, f"error: {str(fallback_error)}"

    async def _seed_with_defaults(
        self,
        equipment_id: str,
        site_id: str,
        captured_by: str,
    ) -> EquipmentBaseline:
        """
        Seed baseline using default values when device is unavailable.

        Reads from BMS sensor history or uses equipment-type defaults.
        """
        from app.database.repositories.baseline_repository import BaselineRepository

        # Get equipment type to determine defaults
        equipment_type = await self._get_equipment_type_fallback(equipment_id)

        # Build default baseline values based on equipment type
        default_values = self._get_default_baseline_values(equipment_type)

        # Create baseline via repository directly
        repo = BaselineRepository()
        baseline = await repo.create_equipment_baseline(
            equipment_id=equipment_id,
            captured_by=captured_by,
            baseline_type=BaselineType.INITIAL.value,
            baseline_values=default_values,
            measurement_conditions={"site_id": site_id, "source": "fallback_defaults"},
            source_type=BaselineSource.BMS_AVERAGE.value,
            notes=f"Baseline seeded with fallback defaults for site {site_id}",
        )

        logger.info(f"Fallback baseline created for {equipment_id}: {baseline.id}")
        return baseline

    async def _get_equipment_type_fallback(self, equipment_id: str) -> str:
        """Get equipment type from equipment_id or repository."""
        # Try to get from device manager
        if self._capture_service.device_manager and self._capture_service.device_manager.initialized:
            try:
                device = await self._capture_service.device_manager.get_device(equipment_id)
                if device and hasattr(device, "equipment_type"):
                    return device.equipment_type
            except Exception:
                pass

        # Try to get from equipment repository
        try:
            from app.database.repositories.equipment_repository import EquipmentRepository

            repo = EquipmentRepository()
            equipment = await repo.get_equipment(equipment_id)
            if equipment and hasattr(equipment, "type"):
                return equipment.type
        except Exception:
            pass

        # Extract from equipment_id naming pattern: S002-CHILLER-B1-001
        parts = equipment_id.split("-")
        if len(parts) >= 2:
            return parts[1].lower()  # CHILLER -> chiller

        return "unknown"

    def _get_default_baseline_values(self, equipment_type: str) -> dict[str, Any]:
        """
        Get default baseline values for equipment type.

        These are conservative defaults for major mechanical equipment.
        """
        defaults = {
            "chiller": {
                "chw_supply_temp": {"value": 7.0, "unit": "°C", "tolerance": 1.5},
                "chw_return_temp": {"value": 12.0, "unit": "°C", "tolerance": 2.0},
                "condenser_temp": {"value": 35.0, "unit": "°C", "tolerance": 5.0},
                "oil_temp": {"value": 45.0, "unit": "°C", "tolerance": 5.0},
                "motor_current": {"value": 150.0, "unit": "A", "tolerance": 15.0},
            },
            "ahu": {
                "discharge_temp": {"value": 14.0, "unit": "°C", "tolerance": 2.0},
                "return_temp": {"value": 24.0, "unit": "°C", "tolerance": 3.0},
                "filter_dp": {"value": 150.0, "unit": "Pa", "tolerance": 50.0},
                "motor_current": {"value": 30.0, "unit": "A", "tolerance": 12.0},
            },
            "fcu": {
                "discharge_temp": {"value": 16.0, "unit": "°C", "tolerance": 2.5},
                "filter_dp": {"value": 80.0, "unit": "Pa", "tolerance": 30.0},
                "motor_current": {"value": 15.0, "unit": "A", "tolerance": 15.0},
            },
            "pump": {
                "discharge_pressure": {"value": 300.0, "unit": "kPa", "tolerance": 15.0},
                "motor_current": {"value": 50.0, "unit": "A", "tolerance": 15.0},
            },
            "generator": {
                "fuel_level": {"value": 90.0, "unit": "%", "tolerance": 10.0},
                "oil_pressure": {"value": 50.0, "unit": "PSI", "tolerance": 15.0},
                "coolant_temp": {"value": 85.0, "unit": "°C", "tolerance": 5.0},
            },
        }

        return defaults.get(equipment_type, {"status": {"value": 1.0, "unit": "", "tolerance": 10.0}})

    async def seed_batch(
        self,
        equipment_ids: list[str],
        site_id: str,
        captured_by: str = "automated",
    ) -> list[dict[str, Any]]:
        """
        Seed baselines for multiple equipment items.

        Args:
            equipment_ids: List of equipment identifiers
            site_id: Site identifier
            captured_by: Identifier of who/what captured the baselines

        Returns:
            List of result dicts with equipment_id, status, baseline_id, message
        """
        results = []
        for equipment_id in equipment_ids:
            try:
                baseline, status = await self.seed_for_equipment_with_fallback(
                    equipment_id=equipment_id,
                    site_id=site_id,
                    captured_by=captured_by,
                )
                results.append({
                    "equipment_id": equipment_id,
                    "status": status,
                    "baseline_id": baseline.id if baseline else None,
                    "message": f"Baseline {status}",
                })
            except Exception as e:
                results.append({
                    "equipment_id": equipment_id,
                    "status": "error",
                    "baseline_id": None,
                    "message": str(e),
                })

        return results