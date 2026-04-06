"""
BMS Simulator Orchestrator

Main orchestrator that coordinates point list export, trend generation,
and alarm generation for the mock BMS system.
"""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

from .generators.alarm_events import AlarmEventGenerator
from .generators.point_list import PointListExporter
from .generators.trend_data import TrendDataGenerator
from .models import SimulationConfig, VendorType

logger = logging.getLogger(__name__)


class BMSSimulator:
    """
    Main orchestrator for BMS data simulation.

    Coordinates:
    - Point list export (equipment and points in vendor format)
    - Trend data generation (time-series with patterns)
    - Alarm event generation (threshold and degradation alarms)
    """

    # Base paths
    DATA_DIR = Path(__file__).parent.parent.parent / "data"
    OUTPUT_DIR = DATA_DIR / "bms_simulator"

    def __init__(self, config: SimulationConfig | None = None):
        """
        Initialize the BMS simulator.

        Args:
            config: Simulation configuration
        """
        self.config = config or SimulationConfig()
        self.point_exporter = PointListExporter(config)
        self.trend_generator = TrendDataGenerator(config)
        self.alarm_generator = AlarmEventGenerator(config)

        # Ensure output directories exist
        self._ensure_directories()

    def _ensure_directories(self) -> None:
        """Create output directories if they don't exist."""
        for subdir in ["exports", "trends", "alarms"]:
            (self.OUTPUT_DIR / subdir).mkdir(parents=True, exist_ok=True)

    def generate(
        self,
        site_id: str | None = None,
        include_diffusers: bool = True,
        include_trends: bool = True,
        include_alarms: bool = True,
    ) -> dict[str, Any]:
        """
        Generate complete BMS simulation data.

        This is the main entry point for full simulation generation.
        Produces:
        - Point list CSV (vendor-formatted equipment and points)
        - Trend data CSV (30 days of time-series data)
        - Alarm events JSON (threshold and degradation alarms)

        Args:
            site_id: Site to simulate (default: from config)
            include_diffusers: Include generated Rickard diffusers
            include_trends: Generate trend data
            include_alarms: Generate alarm events

        Returns:
            Dictionary with paths to generated files and summary statistics
        """
        site_id = site_id or self.config.site_id
        start_time = datetime.now()

        logger.info(f"Starting BMS simulation for {site_id}")
        logger.info(f"Vendor: {self.config.vendor}")
        logger.info(f"Days: {self.config.days}")
        logger.info(f"Include diffusers: {include_diffusers}")
        logger.info(f"Degradation equipment: {self.config.degradation_equipment}")

        result = {
            "site_id": site_id,
            "config": self.config.model_dump(),
            "timestamp": start_time.isoformat(),
            "files": {},
            "summary": {},
        }

        # 1. Export point list
        logger.info("Exporting point list...")
        point_list_path = self.point_exporter.export_point_list(
            site_id=site_id,
            include_diffusers=include_diffusers,
        )
        result["files"]["point_list"] = point_list_path
        result["summary"]["points"] = self.point_exporter.get_point_summary(site_id)
        logger.info(f"Point list exported: {point_list_path}")

        # 2. Generate trend data
        if include_trends:
            logger.info("Generating trend data...")
            trend_paths = self.trend_generator.generate_all_trends(
                site_id=site_id,
                include_diffusers=include_diffusers,
            )
            result["files"]["trends"] = trend_paths
            n_intervals = self.config.days * 24 * 60 // self.config.interval_minutes
            result["summary"]["trends"] = {
                "days": self.config.days,
                "interval_minutes": self.config.interval_minutes,
                "total_intervals": n_intervals,
            }
            logger.info(f"Trend data generated: {trend_paths}")

        # 3. Generate alarm events
        if include_alarms:
            logger.info("Generating alarm events...")
            alarm_path = self.alarm_generator.export_alarms(site_id=site_id)
            result["files"]["alarms"] = alarm_path

            # Load alarms for summary
            with open(alarm_path) as f:
                alarms = json.load(f)
            result["summary"]["alarms"] = self.alarm_generator.get_alarm_summary(alarms)
            logger.info(f"Alarm events generated: {alarm_path}")

        # Calculate elapsed time
        elapsed = (datetime.now() - start_time).total_seconds()
        result["elapsed_seconds"] = elapsed
        logger.info(f"BMS simulation completed in {elapsed:.2f}s")

        # Save manifest
        manifest_path = self._save_manifest(result)
        result["files"]["manifest"] = manifest_path

        return result

    def export_points(
        self,
        site_id: str | None = None,
        vendor: VendorType | None = None,
    ) -> str:
        """
        Export only the point list.

        Args:
            site_id: Site to export
            vendor: Override vendor format

        Returns:
            Path to exported CSV file
        """
        site_id = site_id or self.config.site_id

        if vendor:
            # Create new exporter with different vendor
            config = SimulationConfig(
                site_id=site_id,
                vendor=vendor,
                include_diffusers=self.config.include_diffusers,
            )
            exporter = PointListExporter(config)
        else:
            exporter = self.point_exporter

        return exporter.export_point_list(
            site_id=site_id,
            include_diffusers=self.config.include_diffusers,
        )

    def generate_trends(
        self,
        site_id: str | None = None,
        equipment_id: str | None = None,
        days: int | None = None,
    ) -> list[str]:
        """
        Generate trend data.

        Args:
            site_id: Site to generate trends for
            equipment_id: Specific equipment (if None, generates for all)
            days: Override number of days

        Returns:
            List of output file paths
        """
        site_id = site_id or self.config.site_id

        if equipment_id:
            # Single equipment
            path = self.trend_generator.generate_equipment_trends(
                equipment_id=equipment_id,
                days=days,
            )
            return [path]
        else:
            # All equipment
            if days:
                original_days = self.config.days
                self.config.days = days

            paths = self.trend_generator.generate_all_trends(
                site_id=site_id,
                include_diffusers=self.config.include_diffusers,
            )

            if days:
                self.config.days = original_days

            return paths

    def generate_alarms(
        self,
        site_id: str | None = None,
    ) -> str:
        """
        Generate alarm events.

        Args:
            site_id: Site to generate alarms for

        Returns:
            Path to alarms JSON file
        """
        site_id = site_id or self.config.site_id
        return self.alarm_generator.export_alarms(site_id=site_id)

    def get_device_count(self, site_id: str | None = None) -> dict[str, int]:
        """
        Get count of devices by type.

        Args:
            site_id: Site to count devices for

        Returns:
            Dictionary of device type to count
        """
        site_id = site_id or self.config.site_id
        summary = self.point_exporter.get_point_summary(site_id)
        return summary.get("devices_by_type", {})

    def get_diffusers(self, site_id: str | None = None) -> list[dict[str, Any]]:
        """
        Get generated Rickard diffuser configurations.

        Args:
            site_id: Site to get diffusers for

        Returns:
            List of diffuser device dictionaries
        """
        site_id = site_id or self.config.site_id
        return self.point_exporter.generate_diffusers(site_id)

    def _save_manifest(self, result: dict[str, Any]) -> str:
        """
        Save simulation manifest with metadata.

        Args:
            result: Simulation result dictionary

        Returns:
            Path to manifest file
        """
        timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")
        manifest_path = self.OUTPUT_DIR / f"manifest_{result['site_id']}_{timestamp_str}.json"

        with open(manifest_path, "w") as f:
            json.dump(result, f, indent=2, default=str)

        return str(manifest_path)

    @classmethod
    def from_vendor(
        cls,
        vendor: VendorType,
        site_id: str = "site-002",
        days: int = 30,
        include_degradation: bool = True,
    ) -> "BMSSimulator":
        """
        Create simulator with specific vendor configuration.

        Args:
            vendor: Target vendor format
            site_id: Site to simulate
            days: Days of trend data
            include_degradation: Include degradation patterns

        Returns:
            Configured BMSSimulator instance
        """
        config = SimulationConfig(
            site_id=site_id,
            vendor=vendor,
            days=days,
            include_degradation=include_degradation,
            include_diffusers=True,
        )
        return cls(config)

    @classmethod
    def desigo(cls, site_id: str = "site-002", days: int = 30) -> "BMSSimulator":
        """Create simulator with Siemens Desigo format."""
        return cls.from_vendor(VendorType.SIEMENS_DESIGO, site_id, days)

    @classmethod
    def niagara(cls, site_id: str = "site-002", days: int = 30) -> "BMSSimulator":
        """Create simulator with Niagara format."""
        return cls.from_vendor(VendorType.NIAGARA, site_id, days)

    @classmethod
    def rickard(cls, site_id: str = "site-002", days: int = 30) -> "BMSSimulator":
        """Create simulator with Rickard DALI format."""
        return cls.from_vendor(VendorType.RICKARD, site_id, days)
