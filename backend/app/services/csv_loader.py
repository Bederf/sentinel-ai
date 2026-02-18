"""CSV Data Loader Service.

Loads work orders, assets, sites, alarms, and energy readings from CSV files.
Provides structured data for API endpoints and AI context.
"""

import csv
from datetime import datetime
from pathlib import Path
from typing import Any

# Data directory path
DATA_DIR = Path(__file__).parent.parent / "data"


def parse_date(date_str: str) -> datetime | None:
    """Parse date string to datetime object."""
    if not date_str or date_str.strip() == "":
        return None
    try:
        # Try datetime format first
        if " " in date_str:
            return datetime.strptime(date_str, "%Y-%m-%d %H:%M:%S")
        # Then date only
        return datetime.strptime(date_str, "%Y-%m-%d")
    except ValueError:
        return None


def parse_bool(val: str) -> bool:
    """Parse boolean string."""
    return val.upper() == "TRUE" if val else False


def parse_float(val: str) -> float:
    """Parse float string."""
    try:
        return float(val) if val else 0.0
    except ValueError:
        return 0.0


def parse_int(val: str) -> int:
    """Parse int string."""
    try:
        return int(val) if val else 0
    except ValueError:
        return 0


def load_csv(filename: str) -> list[dict[str, Any]]:
    """Load CSV file and return list of dictionaries."""
    filepath = DATA_DIR / filename
    if not filepath.exists():
        return []

    with open(filepath, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        return list(reader)


class WorkOrderData:
    """Work order data manager."""

    _cache: list[dict[str, Any]] | None = None

    @classmethod
    def load(cls, force_reload: bool = False) -> list[dict[str, Any]]:
        """Load work orders from CSV."""
        if cls._cache is not None and not force_reload:
            return cls._cache

        raw_data = load_csv("work_orders.csv")
        cls._cache = []

        for row in raw_data:
            cls._cache.append({
                "id": row.get("work_order_id", ""),
                "work_order_id": row.get("work_order_id", ""),
                "site_id": row.get("site_id", ""),
                "site_name": row.get("site_name", ""),
                "asset_id": row.get("asset_id", ""),
                "asset_tag": row.get("asset_tag", ""),
                "asset_category": row.get("asset_category", ""),
                "reported_date": parse_date(row.get("reported_date", "")),
                "acknowledged_date": parse_date(row.get("acknowledged_date", "")),
                "arrived_date": parse_date(row.get("arrived_date", "")),
                "completed_date": parse_date(row.get("completed_date", "")),
                "closed_date": parse_date(row.get("closed_date", "")),
                "fault_code": row.get("fault_code", ""),
                "category": row.get("category", ""),
                "priority": row.get("priority", ""),
                "type": row.get("type", ""),
                "description": row.get("description", ""),
                "resolution": row.get("resolution", ""),
                "technician_notes": row.get("technician_notes", ""),
                "technician_name": row.get("technician_name", ""),
                "labour_hours": parse_float(row.get("labour_hours", "")),
                "labour_cost": parse_float(row.get("labour_cost", "")),
                "parts_cost": parse_float(row.get("parts_cost", "")),
                "contractor_cost": parse_float(row.get("contractor_cost", "")),
                "total_cost": parse_float(row.get("total_cost", "")),
                "sla_target_hours": parse_int(row.get("sla_target_hours", "")),
                "sla_met": parse_bool(row.get("sla_met", "")),
                "repeat_call": parse_bool(row.get("repeat_call", "")),
                "related_wo": row.get("related_wo", ""),
            })

        return cls._cache

    @classmethod
    def get_by_asset(cls, asset_id: str) -> list[dict[str, Any]]:
        """Get work orders for a specific asset."""
        all_wo = cls.load()
        return [wo for wo in all_wo if wo["asset_id"] == asset_id]

    @classmethod
    def get_by_site(cls, site_id: str) -> list[dict[str, Any]]:
        """Get work orders for a specific site."""
        all_wo = cls.load()
        return [wo for wo in all_wo if wo["site_id"] == site_id]

    @classmethod
    def get_repeat_calls(cls) -> list[dict[str, Any]]:
        """Get all repeat call work orders."""
        all_wo = cls.load()
        return [wo for wo in all_wo if wo["repeat_call"]]

    @classmethod
    def get_critical(cls) -> list[dict[str, Any]]:
        """Get all critical priority work orders."""
        all_wo = cls.load()
        return [wo for wo in all_wo if wo["priority"] == "critical"]

    @classmethod
    def get_failure_chain(cls, asset_id: str) -> list[dict[str, Any]]:
        """Get chronological work order chain for an asset showing failure progression."""
        wo_list = cls.get_by_asset(asset_id)
        # Sort by reported date
        return sorted(wo_list, key=lambda x: x["reported_date"] or datetime.min)


class AssetData:
    """Asset data manager."""

    _cache: list[dict[str, Any]] | None = None

    @classmethod
    def load(cls, force_reload: bool = False) -> list[dict[str, Any]]:
        """Load assets from CSV."""
        if cls._cache is not None and not force_reload:
            return cls._cache

        raw_data = load_csv("assets.csv")
        cls._cache = []

        for row in raw_data:
            install_date = parse_date(row.get("install_date", ""))
            expected_life = parse_int(row.get("expected_life_years", ""))

            # Calculate age and remaining life
            age_years = 0
            remaining_life = expected_life
            if install_date:
                age_years = (datetime.now() - install_date).days // 365
                remaining_life = max(0, expected_life - age_years)

            cls._cache.append({
                "id": row.get("asset_id", ""),
                "asset_id": row.get("asset_id", ""),
                "site_id": row.get("site_id", ""),
                "site_name": row.get("site_name", ""),
                "asset_tag": row.get("asset_tag", ""),
                "asset_category": row.get("asset_category", ""),
                "make": row.get("make", ""),
                "model": row.get("model", ""),
                "serial_number": row.get("serial_number", ""),
                "install_date": install_date,
                "warranty_expiry": parse_date(row.get("warranty_expiry", "")),
                "expected_life_years": expected_life,
                "age_years": age_years,
                "remaining_life_years": remaining_life,
                "criticality": row.get("criticality", ""),
                "condition": row.get("condition", ""),
                "last_service_date": parse_date(row.get("last_service_date", "")),
                "next_service_date": parse_date(row.get("next_service_date", "")),
                "notes": row.get("notes", ""),
            })

        return cls._cache

    @classmethod
    def get_by_id(cls, asset_id: str) -> dict[str, Any] | None:
        """Get asset by ID."""
        all_assets = cls.load()
        for asset in all_assets:
            if asset["asset_id"] == asset_id:
                return asset
        return None

    @classmethod
    def get_by_site(cls, site_id: str) -> list[dict[str, Any]]:
        """Get assets for a specific site."""
        all_assets = cls.load()
        return [a for a in all_assets if a["site_id"] == site_id]

    @classmethod
    def get_critical(cls) -> list[dict[str, Any]]:
        """Get all critical assets."""
        all_assets = cls.load()
        return [a for a in all_assets if a["criticality"] == "critical"]

    @classmethod
    def get_poor_condition(cls) -> list[dict[str, Any]]:
        """Get assets in poor condition."""
        all_assets = cls.load()
        return [a for a in all_assets if a["condition"] == "poor"]

    @classmethod
    def get_end_of_life(cls, threshold_years: int = 2) -> list[dict[str, Any]]:
        """Get assets approaching end of life."""
        all_assets = cls.load()
        return [a for a in all_assets if a["remaining_life_years"] <= threshold_years]


class SiteData:
    """Site data manager."""

    _cache: list[dict[str, Any]] | None = None

    @classmethod
    def load(cls, force_reload: bool = False) -> list[dict[str, Any]]:
        """Load sites from CSV or generate from assets."""
        if cls._cache is not None and not force_reload:
            return cls._cache

        # Try to load from sites.csv
        raw_data = load_csv("sites.csv")

        if raw_data:
            cls._cache = []
            for row in raw_data:
                cls._cache.append({
                    "id": row.get("site_id", ""),
                    "site_id": row.get("site_id", ""),
                    "name": row.get("site_name", ""),
                    "site_name": row.get("site_name", ""),
                    "client_id": row.get("client_id", ""),
                    "client_name": row.get("client_name", ""),
                    "address": row.get("address", ""),
                    "region": row.get("region", ""),
                    "gla_sqm": parse_float(row.get("gla_sqm", "")),
                    "building_age_years": parse_int(row.get("building_age_years", "")),
                    "bms_type": row.get("bms_type", ""),
                    "bms_vendor": row.get("bms_vendor", ""),
                    "data_availability": row.get("data_availability", ""),
                    "contract_start": parse_date(row.get("contract_start", "")),
                    "annual_contract_value": parse_float(row.get("annual_contract_value", "")),
                    "sla_critical_hours": parse_int(row.get("sla_critical_hours", "")),
                    "sla_high_hours": parse_int(row.get("sla_high_hours", "")),
                    "sla_medium_hours": parse_int(row.get("sla_medium_hours", "")),
                    "last_audit_date": parse_date(row.get("last_audit_date", "")),
                    "notes": row.get("notes", ""),
                })
        else:
            # Generate from assets data
            assets = AssetData.load()
            sites_map = {}
            for asset in assets:
                site_id = asset["site_id"]
                if site_id not in sites_map:
                    sites_map[site_id] = {
                        "id": site_id,
                        "site_id": site_id,
                        "name": asset["site_name"],
                        "asset_count": 0,
                    }
                sites_map[site_id]["asset_count"] += 1

            cls._cache = list(sites_map.values())

        return cls._cache

    @classmethod
    def get_by_id(cls, site_id: str) -> dict[str, Any] | None:
        """Get site by ID."""
        all_sites = cls.load()
        for site in all_sites:
            if site["site_id"] == site_id:
                return site
        return None

    @classmethod
    def get_by_client(cls, client_id: str) -> list[dict[str, Any]]:
        """Get sites for a specific client."""
        all_sites = cls.load()
        return [s for s in all_sites if s.get("client_id") == client_id]

    @classmethod
    def get_by_region(cls, region: str) -> list[dict[str, Any]]:
        """Get sites in a specific region."""
        all_sites = cls.load()
        return [s for s in all_sites if s.get("region") == region]

    @classmethod
    def get_total_contract_value(cls) -> float:
        """Get total annual contract value across all sites."""
        all_sites = cls.load()
        return sum(s.get("annual_contract_value", 0) for s in all_sites)


class AlarmData:
    """Alarm data manager."""

    _cache: list[dict[str, Any]] | None = None

    @classmethod
    def load(cls, force_reload: bool = False) -> list[dict[str, Any]]:
        """Load alarms from CSV."""
        if cls._cache is not None and not force_reload:
            return cls._cache

        raw_data = load_csv("alarms.csv")
        cls._cache = []

        for row in raw_data:
            cls._cache.append({
                "id": row.get("alarm_id", ""),
                "alarm_id": row.get("alarm_id", ""),
                "site_id": row.get("site_id", ""),
                "site_name": row.get("site_name", ""),
                "asset_id": row.get("asset_id", ""),
                "asset_tag": row.get("asset_tag", ""),
                "alarm_code": row.get("alarm_code", ""),
                "alarm_description": row.get("alarm_description", ""),
                "severity": row.get("severity", ""),
                "source": row.get("source", ""),
                "triggered_at": parse_date(row.get("triggered_at", "")),
                "acknowledged_at": parse_date(row.get("acknowledged_at", "")),
                "acknowledged_by": row.get("acknowledged_by", ""),
                "cleared_at": parse_date(row.get("cleared_at", "")),
                "work_order_created": row.get("work_order_created", ""),
                "false_alarm": parse_bool(row.get("false_alarm", "")),
                "alarm_value": parse_float(row.get("alarm_value", "")),
                "alarm_threshold": parse_float(row.get("alarm_threshold", "")),
                "alarm_unit": row.get("alarm_unit", ""),
                "notes": row.get("notes", ""),
            })

        return cls._cache

    @classmethod
    def get_by_asset(cls, asset_id: str) -> list[dict[str, Any]]:
        """Get alarms for a specific asset."""
        all_alarms = cls.load()
        return [a for a in all_alarms if a["asset_id"] == asset_id]

    @classmethod
    def get_by_site(cls, site_id: str) -> list[dict[str, Any]]:
        """Get alarms for a specific site."""
        all_alarms = cls.load()
        return [a for a in all_alarms if a["site_id"] == site_id]

    @classmethod
    def get_critical(cls) -> list[dict[str, Any]]:
        """Get critical severity alarms."""
        all_alarms = cls.load()
        return [a for a in all_alarms if a["severity"] == "critical"]

    @classmethod
    def get_with_work_orders(cls) -> list[dict[str, Any]]:
        """Get alarms that generated work orders."""
        all_alarms = cls.load()
        return [a for a in all_alarms if a["work_order_created"]]

    @classmethod
    def get_false_alarms(cls) -> list[dict[str, Any]]:
        """Get false alarms."""
        all_alarms = cls.load()
        return [a for a in all_alarms if a["false_alarm"]]


class GeneratorTelemetryData:
    """Generator telemetry data from DeepSea controllers."""

    _cache: list[dict[str, Any]] | None = None

    @classmethod
    def load(cls, force_reload: bool = False) -> list[dict[str, Any]]:
        """Load generator telemetry from CSV."""
        if cls._cache is not None and not force_reload:
            return cls._cache

        raw_data = load_csv("generator_telemetry.csv")
        cls._cache = []

        for row in raw_data:
            cls._cache.append({
                "id": row.get("timestamp", "") + "_" + row.get("asset_id", ""),
                "timestamp": parse_date(row.get("timestamp", "")),
                "site_id": row.get("site_id", ""),
                "site_name": row.get("site_name", ""),
                "asset_id": row.get("asset_id", ""),
                "asset_tag": row.get("asset_tag", ""),
                "controller_model": row.get("controller_model", ""),
                "reading_source": row.get("reading_source", ""),
                "engine_rpm": parse_int(row.get("engine_rpm", "")),
                "oil_pressure_kpa": parse_float(row.get("oil_pressure_kpa", "")),
                "coolant_temp_c": parse_float(row.get("coolant_temp_c", "")),
                "run_hours": parse_float(row.get("run_hours", "")),
                "battery_voltage": parse_float(row.get("battery_voltage", "")),
                "charger_current_a": parse_float(row.get("charger_current_a", "")),
                "fuel_level_pct": parse_float(row.get("fuel_level_pct", "")),
                "fuel_rate_lph": parse_float(row.get("fuel_rate_lph", "")),
                "gen_voltage_l1": parse_float(row.get("gen_voltage_l1", "")),
                "gen_voltage_l2": parse_float(row.get("gen_voltage_l2", "")),
                "gen_voltage_l3": parse_float(row.get("gen_voltage_l3", "")),
                "gen_current_l1": parse_float(row.get("gen_current_l1", "")),
                "gen_current_l2": parse_float(row.get("gen_current_l2", "")),
                "gen_current_l3": parse_float(row.get("gen_current_l3", "")),
                "gen_frequency_hz": parse_float(row.get("gen_frequency_hz", "")),
                "gen_kw": parse_float(row.get("gen_kw", "")),
                "gen_kva": parse_float(row.get("gen_kva", "")),
                "power_factor": parse_float(row.get("power_factor", "")),
                "mains_available": parse_bool(row.get("mains_available", "")),
                "engine_running": parse_bool(row.get("engine_running", "")),
                "on_load": parse_bool(row.get("on_load", "")),
                "start_attempt": parse_int(row.get("start_attempt", "")),
                "alarm_code": row.get("alarm_code", ""),
                "alarm_description": row.get("alarm_description", ""),
                "notes": row.get("notes", ""),
            })

        return cls._cache

    @classmethod
    def get_by_asset(cls, asset_id: str) -> list[dict[str, Any]]:
        """Get telemetry for a specific generator."""
        all_data = cls.load()
        return sorted(
            [d for d in all_data if d["asset_id"] == asset_id],
            key=lambda x: x["timestamp"] or datetime.min
        )

    @classmethod
    def get_battery_trend(cls, asset_id: str) -> list[dict[str, Any]]:
        """Get battery voltage trend for predictive analysis."""
        data = cls.get_by_asset(asset_id)
        # Filter to standby readings (best indicator of battery health)
        return [d for d in data if not d["engine_running"] and d["battery_voltage"] > 0]

    @classmethod
    def get_start_failures(cls) -> list[dict[str, Any]]:
        """Get all failed start attempts."""
        all_data = cls.load()
        return [d for d in all_data if d["alarm_code"] in ["FAIL_TO_START", "OVERCRANK"]]

    @classmethod
    def get_alarms(cls) -> list[dict[str, Any]]:
        """Get all readings with alarms."""
        all_data = cls.load()
        return [d for d in all_data if d["alarm_code"]]


class HVACTelemetryData:
    """HVAC telemetry data from BACnet/BMS systems (AHUs, chillers)."""

    _cache: list[dict[str, Any]] | None = None

    @classmethod
    def load(cls, force_reload: bool = False) -> list[dict[str, Any]]:
        """Load HVAC telemetry from CSV."""
        if cls._cache is not None and not force_reload:
            return cls._cache

        raw_data = load_csv("hvac_telemetry.csv")
        cls._cache = []

        for row in raw_data:
            cls._cache.append({
                "id": row.get("timestamp", "") + "_" + row.get("asset_id", ""),
                "timestamp": parse_date(row.get("timestamp", "")),
                "site_id": row.get("site_id", ""),
                "site_name": row.get("site_name", ""),
                "asset_id": row.get("asset_id", ""),
                "asset_tag": row.get("asset_tag", ""),
                "asset_category": row.get("asset_category", ""),
                "equipment_make": row.get("equipment_make", ""),
                "equipment_model": row.get("equipment_model", ""),
                "reading_source": row.get("reading_source", ""),
                # Temperature readings
                "supply_air_temp_c": parse_float(row.get("supply_air_temp_c", "")),
                "return_air_temp_c": parse_float(row.get("return_air_temp_c", "")),
                "mixed_air_temp_c": parse_float(row.get("mixed_air_temp_c", "")),
                "outside_air_temp_c": parse_float(row.get("outside_air_temp_c", "")),
                "supply_air_setpoint_c": parse_float(row.get("supply_air_setpoint_c", "")),
                # Pressure and airflow
                "duct_static_pressure_pa": parse_float(row.get("duct_static_pressure_pa", "")),
                "duct_static_setpoint_pa": parse_float(row.get("duct_static_setpoint_pa", "")),
                # Fan data
                "supply_fan_speed_pct": parse_float(row.get("supply_fan_speed_pct", "")),
                "supply_fan_status": row.get("supply_fan_status", ""),
                "supply_fan_vfd_hz": parse_float(row.get("supply_fan_vfd_hz", "")),
                "supply_fan_current_a": parse_float(row.get("supply_fan_current_a", "")),
                "return_fan_speed_pct": parse_float(row.get("return_fan_speed_pct", "")),
                "return_fan_status": row.get("return_fan_status", ""),
                # Filter and valves
                "filter_dp_pa": parse_float(row.get("filter_dp_pa", "")),
                "cooling_valve_pct": parse_float(row.get("cooling_valve_pct", "")),
                "heating_valve_pct": parse_float(row.get("heating_valve_pct", "")),
                "oa_damper_pct": parse_float(row.get("oa_damper_pct", "")),
                "ra_damper_pct": parse_float(row.get("ra_damper_pct", "")),
                # Chilled water
                "chw_supply_temp_c": parse_float(row.get("chw_supply_temp_c", "")),
                "chw_return_temp_c": parse_float(row.get("chw_return_temp_c", "")),
                # Status
                "occupancy_mode": row.get("occupancy_mode", ""),
                "run_hours": parse_float(row.get("run_hours", "")),
                "alarm_code": row.get("alarm_code", ""),
                "alarm_description": row.get("alarm_description", ""),
                "notes": row.get("notes", ""),
            })

        return cls._cache

    @classmethod
    def get_by_asset(cls, asset_id: str) -> list[dict[str, Any]]:
        """Get telemetry for a specific HVAC asset."""
        all_data = cls.load()
        return sorted(
            [d for d in all_data if d["asset_id"] == asset_id],
            key=lambda x: x["timestamp"] or datetime.min
        )

    @classmethod
    def get_vibration_events(cls) -> list[dict[str, Any]]:
        """Get all vibration alarm events (VIB_WARN, VIB_HIGH, VIB_CRIT)."""
        all_data = cls.load()
        return [d for d in all_data if d["alarm_code"] and d["alarm_code"].startswith("VIB")]

    @classmethod
    def get_motor_events(cls) -> list[dict[str, Any]]:
        """Get motor-related events (overload, failure)."""
        all_data = cls.load()
        return [d for d in all_data if d["alarm_code"] and d["alarm_code"].startswith("MOTOR")]

    @classmethod
    def get_current_trend(cls, asset_id: str) -> list[dict[str, Any]]:
        """Get motor current trend for an asset (predictive indicator)."""
        data = cls.get_by_asset(asset_id)
        return [d for d in data if d["supply_fan_current_a"] > 0]

    @classmethod
    def get_filter_dp_trend(cls, asset_id: str) -> list[dict[str, Any]]:
        """Get filter differential pressure trend."""
        data = cls.get_by_asset(asset_id)
        return [d for d in data if d["filter_dp_pa"] > 0]


class VSDTelemetryData:
    """VSD (Variable Speed Drive) telemetry from Modbus/BACnet."""

    _cache: list[dict[str, Any]] | None = None

    @classmethod
    def load(cls, force_reload: bool = False) -> list[dict[str, Any]]:
        """Load VSD telemetry from CSV."""
        if cls._cache is not None and not force_reload:
            return cls._cache

        raw_data = load_csv("vsd_telemetry.csv")
        cls._cache = []

        for row in raw_data:
            cls._cache.append({
                "id": row.get("timestamp", "") + "_" + row.get("asset_id", ""),
                "timestamp": parse_date(row.get("timestamp", "")),
                "site_id": row.get("site_id", ""),
                "site_name": row.get("site_name", ""),
                "asset_id": row.get("asset_id", ""),
                "asset_tag": row.get("asset_tag", ""),
                "asset_category": row.get("asset_category", ""),
                "vsd_make": row.get("vsd_make", ""),
                "vsd_model": row.get("vsd_model", ""),
                "motor_application": row.get("motor_application", ""),
                "reading_source": row.get("reading_source", ""),
                # Output parameters
                "output_frequency_hz": parse_float(row.get("output_frequency_hz", "")),
                "output_voltage_v": parse_float(row.get("output_voltage_v", "")),
                "output_current_a": parse_float(row.get("output_current_a", "")),
                "motor_power_kw": parse_float(row.get("motor_power_kw", "")),
                "dc_bus_voltage_v": parse_float(row.get("dc_bus_voltage_v", "")),
                # Temperatures
                "heatsink_temp_c": parse_float(row.get("heatsink_temp_c", "")),
                "control_card_temp_c": parse_float(row.get("control_card_temp_c", "")),
                # Motor parameters
                "motor_speed_rpm": parse_float(row.get("motor_speed_rpm", "")),
                "motor_torque_pct": parse_float(row.get("motor_torque_pct", "")),
                # Runtime and energy
                "run_hours": parse_float(row.get("run_hours", "")),
                "energy_kwh": parse_float(row.get("energy_kwh", "")),
                # Input power
                "input_voltage_l1": parse_float(row.get("input_voltage_l1", "")),
                "input_voltage_l2": parse_float(row.get("input_voltage_l2", "")),
                "input_voltage_l3": parse_float(row.get("input_voltage_l3", "")),
                "input_current_a": parse_float(row.get("input_current_a", "")),
                "power_factor": parse_float(row.get("power_factor", "")),
                # Status and alarms
                "vsd_status": row.get("vsd_status", ""),
                "alarm_code": row.get("alarm_code", ""),
                "alarm_description": row.get("alarm_description", ""),
                "fault_log_count": parse_int(row.get("fault_log_count", "")),
                "last_fault_date": parse_date(row.get("last_fault_date", "")),
                "notes": row.get("notes", ""),
            })

        return cls._cache

    @classmethod
    def get_by_asset(cls, asset_id: str) -> list[dict[str, Any]]:
        """Get telemetry for a specific VSD."""
        all_data = cls.load()
        return sorted(
            [d for d in all_data if d["asset_id"] == asset_id],
            key=lambda x: x["timestamp"] or datetime.min
        )

    @classmethod
    def get_faults(cls) -> list[dict[str, Any]]:
        """Get all VSD fault events."""
        all_data = cls.load()
        return [d for d in all_data if d["vsd_status"] == "FAULT"]

    @classmethod
    def get_warnings(cls) -> list[dict[str, Any]]:
        """Get all VSD warning events."""
        all_data = cls.load()
        return [d for d in all_data if d["vsd_status"] == "WARNING"]

    @classmethod
    def get_by_make(cls, make: str) -> list[dict[str, Any]]:
        """Get VSDs by manufacturer (Danfoss, ABB, Schneider)."""
        all_data = cls.load()
        return [d for d in all_data if d["vsd_make"].lower() == make.lower()]

    @classmethod
    def get_high_temp_events(cls, threshold_c: float = 60) -> list[dict[str, Any]]:
        """Get events where heatsink temperature exceeded threshold."""
        all_data = cls.load()
        return [d for d in all_data if d["heatsink_temp_c"] > threshold_c]


class ChillerTelemetryData:
    """Chiller telemetry data from BACnet/BMS systems."""

    _cache: list[dict[str, Any]] | None = None

    @classmethod
    def load(cls, force_reload: bool = False) -> list[dict[str, Any]]:
        """Load chiller telemetry from CSV."""
        if cls._cache is not None and not force_reload:
            return cls._cache

        raw_data = load_csv("chiller_telemetry.csv")
        cls._cache = []

        for row in raw_data:
            cls._cache.append({
                "id": row.get("timestamp", "") + "_" + row.get("asset_id", ""),
                "timestamp": parse_date(row.get("timestamp", "")),
                "site_id": row.get("site_id", ""),
                "site_name": row.get("site_name", ""),
                "asset_id": row.get("asset_id", ""),
                "asset_tag": row.get("asset_tag", ""),
                "chiller_type": row.get("chiller_type", ""),
                "chiller_make": row.get("chiller_make", ""),
                "chiller_model": row.get("chiller_model", ""),
                "capacity_tons": parse_float(row.get("capacity_tons", "")),
                "reading_source": row.get("reading_source", ""),
                # Chilled water
                "chw_supply_temp_c": parse_float(row.get("chw_supply_temp_c", "")),
                "chw_return_temp_c": parse_float(row.get("chw_return_temp_c", "")),
                "chw_setpoint_c": parse_float(row.get("chw_setpoint_c", "")),
                "chw_flow_lps": parse_float(row.get("chw_flow_lps", "")),
                # Condenser water
                "cond_water_in_c": parse_float(row.get("cond_water_in_c", "")),
                "cond_water_out_c": parse_float(row.get("cond_water_out_c", "")),
                # Refrigeration pressures
                "evap_pressure_kpa": parse_float(row.get("evap_pressure_kpa", "")),
                "cond_pressure_kpa": parse_float(row.get("cond_pressure_kpa", "")),
                "evap_superheat_c": parse_float(row.get("evap_superheat_c", "")),
                "cond_subcool_c": parse_float(row.get("cond_subcool_c", "")),
                # Compressor
                "compressor_status": row.get("compressor_status", ""),
                "compressor_load_pct": parse_float(row.get("compressor_load_pct", "")),
                "compressor_current_a": parse_float(row.get("compressor_current_a", "")),
                "compressor_vfd_hz": parse_float(row.get("compressor_vfd_hz", "")),
                # Oil system
                "oil_pressure_kpa": parse_float(row.get("oil_pressure_kpa", "")),
                "oil_temp_c": parse_float(row.get("oil_temp_c", "")),
                # Temperatures
                "discharge_temp_c": parse_float(row.get("discharge_temp_c", "")),
                "suction_temp_c": parse_float(row.get("suction_temp_c", "")),
                # Power and efficiency
                "power_kw": parse_float(row.get("power_kw", "")),
                "efficiency_kw_ton": parse_float(row.get("efficiency_kw_ton", "")),
                # Runtime
                "run_hours": parse_float(row.get("run_hours", "")),
                "starts_count": parse_int(row.get("starts_count", "")),
                # Alarms
                "alarm_code": row.get("alarm_code", ""),
                "alarm_description": row.get("alarm_description", ""),
                # Oil analysis
                "oil_analysis_date": parse_date(row.get("oil_analysis_date", "")),
                "oil_analysis_result": row.get("oil_analysis_result", ""),
                # Vibration
                "vibration_mm_s": parse_float(row.get("vibration_mm_s", "")),
                "notes": row.get("notes", ""),
            })

        return cls._cache

    @classmethod
    def get_by_asset(cls, asset_id: str) -> list[dict[str, Any]]:
        """Get telemetry for a specific chiller."""
        all_data = cls.load()
        return sorted(
            [d for d in all_data if d["asset_id"] == asset_id],
            key=lambda x: x["timestamp"] or datetime.min
        )

    @classmethod
    def get_vibration_events(cls) -> list[dict[str, Any]]:
        """Get all vibration alarm events."""
        all_data = cls.load()
        return [d for d in all_data if d["alarm_code"] and "VIB" in d["alarm_code"]]

    @classmethod
    def get_oil_analysis_issues(cls) -> list[dict[str, Any]]:
        """Get readings with abnormal oil analysis."""
        all_data = cls.load()
        return [d for d in all_data if d["oil_analysis_result"] and "ELEVATED" in d["oil_analysis_result"]]

    @classmethod
    def get_high_vibration(cls, threshold_mm_s: float = 4.0) -> list[dict[str, Any]]:
        """Get readings with high vibration levels."""
        all_data = cls.load()
        return [d for d in all_data if d["vibration_mm_s"] > threshold_mm_s]

    @classmethod
    def get_efficiency_trend(cls, asset_id: str) -> list[dict[str, Any]]:
        """Get efficiency trend for a chiller (kW/ton)."""
        data = cls.get_by_asset(asset_id)
        return [d for d in data if d["efficiency_kw_ton"] > 0]

    @classmethod
    def get_by_type(cls, chiller_type: str) -> list[dict[str, Any]]:
        """Get chillers by type (screw, centrifugal)."""
        all_data = cls.load()
        return [d for d in all_data if d["chiller_type"].lower() == chiller_type.lower()]


class PumpTelemetryData:
    """Pump telemetry data from Modbus/BACnet (CHW pumps, CW pumps)."""

    _cache: list[dict[str, Any]] | None = None

    @classmethod
    def load(cls, force_reload: bool = False) -> list[dict[str, Any]]:
        """Load pump telemetry from CSV."""
        if cls._cache is not None and not force_reload:
            return cls._cache

        raw_data = load_csv("pump_telemetry.csv")
        cls._cache = []

        for row in raw_data:
            cls._cache.append({
                "id": row.get("timestamp", "") + "_" + row.get("asset_id", ""),
                "timestamp": parse_date(row.get("timestamp", "")),
                "site_id": row.get("site_id", ""),
                "site_name": row.get("site_name", ""),
                "asset_id": row.get("asset_id", ""),
                "asset_tag": row.get("asset_tag", ""),
                "pump_type": row.get("pump_type", ""),
                "pump_make": row.get("pump_make", ""),
                "pump_model": row.get("pump_model", ""),
                "motor_kw": parse_float(row.get("motor_kw", "")),
                "reading_source": row.get("reading_source", ""),
                # Flow and pressure
                "flow_rate_lps": parse_float(row.get("flow_rate_lps", "")),
                "discharge_pressure_kpa": parse_float(row.get("discharge_pressure_kpa", "")),
                "suction_pressure_kpa": parse_float(row.get("suction_pressure_kpa", "")),
                "differential_pressure_kpa": parse_float(row.get("differential_pressure_kpa", "")),
                # Motor parameters
                "pump_speed_rpm": parse_float(row.get("pump_speed_rpm", "")),
                "motor_current_a": parse_float(row.get("motor_current_a", "")),
                "motor_power_kw": parse_float(row.get("motor_power_kw", "")),
                "motor_temp_c": parse_float(row.get("motor_temp_c", "")),
                # Bearing temperatures
                "bearing_temp_de_c": parse_float(row.get("bearing_temp_de_c", "")),
                "bearing_temp_nde_c": parse_float(row.get("bearing_temp_nde_c", "")),
                # Vibration (DE = drive end, NDE = non-drive end)
                "vibration_de_mm_s": parse_float(row.get("vibration_de_mm_s", "")),
                "vibration_nde_mm_s": parse_float(row.get("vibration_nde_mm_s", "")),
                # Seal status
                "seal_leakage": row.get("seal_leakage", ""),
                # Runtime
                "run_hours": parse_float(row.get("run_hours", "")),
                # VSD status
                "vsd_frequency_hz": parse_float(row.get("vsd_frequency_hz", "")),
                "vsd_status": row.get("vsd_status", ""),
                "pump_status": row.get("pump_status", ""),
                # Alarms
                "alarm_code": row.get("alarm_code", ""),
                "alarm_description": row.get("alarm_description", ""),
                "notes": row.get("notes", ""),
            })

        return cls._cache

    @classmethod
    def get_by_asset(cls, asset_id: str) -> list[dict[str, Any]]:
        """Get telemetry for a specific pump."""
        all_data = cls.load()
        return sorted(
            [d for d in all_data if d["asset_id"] == asset_id],
            key=lambda x: x["timestamp"] or datetime.min
        )

    @classmethod
    def get_vibration_events(cls) -> list[dict[str, Any]]:
        """Get all vibration alarm events."""
        all_data = cls.load()
        return [d for d in all_data if d["alarm_code"] and "VIB" in d["alarm_code"]]

    @classmethod
    def get_high_bearing_temp(cls, threshold_c: float = 55) -> list[dict[str, Any]]:
        """Get readings with high bearing temperatures."""
        all_data = cls.load()
        return [d for d in all_data if d["bearing_temp_de_c"] > threshold_c or d["bearing_temp_nde_c"] > threshold_c]

    @classmethod
    def get_seal_leakage(cls) -> list[dict[str, Any]]:
        """Get pumps with seal leakage."""
        all_data = cls.load()
        return [d for d in all_data if d["seal_leakage"] and d["seal_leakage"] != "NONE"]

    @classmethod
    def get_by_type(cls, pump_type: str) -> list[dict[str, Any]]:
        """Get pumps by type (chw-primary, chw-secondary, condenser)."""
        all_data = cls.load()
        return [d for d in all_data if d["pump_type"].lower() == pump_type.lower()]

    @classmethod
    def get_by_make(cls, make: str) -> list[dict[str, Any]]:
        """Get pumps by manufacturer (Grundfos, KSB)."""
        all_data = cls.load()
        return [d for d in all_data if d["pump_make"].lower() == make.lower()]

    @classmethod
    def get_flow_trend(cls, asset_id: str) -> list[dict[str, Any]]:
        """Get flow rate trend for a pump."""
        data = cls.get_by_asset(asset_id)
        return [d for d in data if d["flow_rate_lps"] > 0]


class EnergyData:
    """Energy readings data manager."""

    _cache: list[dict[str, Any]] | None = None

    @classmethod
    def load(cls, force_reload: bool = False) -> list[dict[str, Any]]:
        """Load energy readings from CSV."""
        if cls._cache is not None and not force_reload:
            return cls._cache

        raw_data = load_csv("energy_readings.csv")
        cls._cache = []

        for row in raw_data:
            cls._cache.append({
                "id": row.get("reading_id", ""),
                "reading_id": row.get("reading_id", ""),
                "site_id": row.get("site_id", ""),
                "site_name": row.get("site_name", ""),
                "meter_id": row.get("meter_id", ""),
                "reading_type": row.get("reading_type", ""),
                "reading_source": row.get("reading_source", ""),
                "period_start": parse_date(row.get("period_start", "")),
                "period_end": parse_date(row.get("period_end", "")),
                "consumption": parse_float(row.get("consumption", "")),
                "unit": row.get("unit", ""),
                "cost_zar": parse_float(row.get("cost_zar", "")),
                "gla_sqm": parse_float(row.get("gla_sqm", "")),
                "kwh_per_sqm": parse_float(row.get("kwh_per_sqm", "")),
                "notes": row.get("notes", ""),
            })

        return cls._cache

    @classmethod
    def get_by_site(cls, site_id: str) -> list[dict[str, Any]]:
        """Get energy readings for a specific site."""
        all_readings = cls.load()
        return [r for r in all_readings if r["site_id"] == site_id]

    @classmethod
    def get_by_type(cls, reading_type: str) -> list[dict[str, Any]]:
        """Get readings by type (electricity, water, diesel)."""
        all_readings = cls.load()
        return [r for r in all_readings if r["reading_type"] == reading_type]

    @classmethod
    def get_total_cost(cls) -> float:
        """Get total energy cost across all readings."""
        all_readings = cls.load()
        return sum(r["cost_zar"] for r in all_readings)

    @classmethod
    def get_site_efficiency_trend(cls, site_id: str) -> list[dict[str, Any]]:
        """Get efficiency trend for a site (electricity only, sorted by date)."""
        readings = [r for r in cls.get_by_site(site_id) if r["reading_type"] == "electricity"]
        return sorted(readings, key=lambda x: x["period_start"] or datetime.min)


def get_ai_context_summary() -> str:
    """Generate a summary of all data for AI context."""
    work_orders = WorkOrderData.load()
    assets = AssetData.load()
    sites = SiteData.load()
    alarms = AlarmData.load()
    energy = EnergyData.load()

    # Calculate key metrics
    total_wo = len(work_orders)
    critical_wo = len([wo for wo in work_orders if wo["priority"] == "critical"])
    repeat_calls = len([wo for wo in work_orders if wo["repeat_call"]])
    total_cost = sum(wo["total_cost"] for wo in work_orders)

    poor_assets = AssetData.get_poor_condition()
    eol_assets = AssetData.get_end_of_life()

    # Build summary
    lines = [
        "## Portfolio Overview",
        f"- **Sites**: {len(sites)}",
        f"- **Assets**: {len(assets)}",
        f"- **Work Orders**: {total_wo} (Critical: {critical_wo}, Repeat calls: {repeat_calls})",
        f"- **Total Maintenance Cost**: R{total_cost:,.0f}",
        "",
        "## Assets Requiring Attention",
    ]

    # Poor condition assets
    if poor_assets:
        lines.append("\n### Poor Condition:")
        for asset in poor_assets:
            lines.append(f"- **{asset['asset_tag']}** at {asset['site_name']}: {asset['notes']}")

    # End of life assets
    if eol_assets:
        lines.append("\n### Approaching End of Life:")
        for asset in eol_assets:
            lines.append(f"- **{asset['asset_tag']}** ({asset['make']} {asset['model']}): {asset['age_years']} years old, {asset['remaining_life_years']} years remaining")

    # Key failure stories
    lines.extend([
        "",
        "## Key Failure Stories",
        "",
        "### Centurion Mall AHU-002 (Catastrophic Failure - May 2025)",
        "- 8 work orders over 14 months",
        "- Technician warned 4 times about bearing wear",
        "- Quote for R28,500 sat unapproved for 8 months",
        "- Final cost: R63,300 + R150,000+ tenant revenue loss",
        "- Food court closed for 2 days",
        "",
        "### Gateway Chiller (Active Risk - Same Pattern)",
        "- 4 work orders showing identical progression",
        "- Technician explicitly states 'EXACTLY like Centurion'",
        "- Oil analysis confirms metal contamination (28ppm vs <15ppm normal)",
        "- Quote R45,000 pending approval",
        "- Predicted failure in 4-8 weeks if not addressed",
        "- Potential cost if failure: R180,000+ and 2-3 weeks downtime",
        "",
        "### Centurion Mall AHU-001 (Proactive Save - Nov 2025)",
        "- Twin unit to failed AHU-002",
        "- Client approved proactive replacement immediately",
        "- Cost: R28,300 vs R63,300+ if waited",
        "- Demonstrates value of predictive maintenance",
    ])

    # Add energy insights
    total_energy_cost = sum(e["cost_zar"] for e in energy)
    lines.extend([
        "",
        "## Energy & Utility Data",
        f"- **Total Energy Cost**: R{total_energy_cost:,.0f}",
        f"- **Readings**: {len(energy)} utility readings across portfolio",
        "",
        "### Gateway Chiller - Energy Impact of Degradation",
        "The failing Gateway chiller is showing measurable efficiency loss:",
    ])

    # Get Gateway efficiency trend
    gateway_trend = EnergyData.get_site_efficiency_trend("SITE-005")
    if gateway_trend:
        for e in gateway_trend[-3:]:  # Last 3 months
            if e["period_start"]:
                month = e["period_start"].strftime("%b %Y")
                lines.append(f"- {month}: {e['kwh_per_sqm']:.2f} kWh/sqm - {e['notes']}")

        # Calculate efficiency loss
        if len(gateway_trend) >= 2:
            first_reading = gateway_trend[0]["kwh_per_sqm"]
            last_reading = gateway_trend[-1]["kwh_per_sqm"]
            if first_reading and last_reading:
                pct_increase = ((last_reading - first_reading) / first_reading) * 100
                lines.append(f"- **Efficiency loss: {pct_increase:.0f}% increase in energy consumption**")

    # Centurion load shedding impact
    centurion_diesel = [e for e in energy if e["site_id"] == "SITE-003" and e["reading_type"] == "diesel"]
    if centurion_diesel:
        total_diesel_cost = sum(e["cost_zar"] for e in centurion_diesel)
        lines.extend([
            "",
            "### Load Shedding Impact - Centurion Mall Generator",
            f"- Total diesel cost: R{total_diesel_cost:,.0f}",
        ])
        for e in centurion_diesel:
            if e["period_start"]:
                period = e["period_start"].strftime("%b") + "-" + (e["period_end"].strftime("%b %Y") if e["period_end"] else "")
                lines.append(f"- {period}: {e['consumption']:,.0f}L (R{e['cost_zar']:,.0f}) - {e['notes']}")

    # Alarm summary
    critical_alarms = AlarmData.get_critical()
    false_alarms = AlarmData.get_false_alarms()
    lines.extend([
        "",
        "## BCC Alarm History",
        f"- **Total Alarms**: {len(alarms)}",
        f"- **Critical Alarms**: {len(critical_alarms)}",
        f"- **False Alarms**: {len(false_alarms)} ({len(false_alarms)/len(alarms)*100:.0f}% false positive rate)" if alarms else "",
    ])

    # Generator Telemetry (DeepSea Controllers)
    gen_telemetry = GeneratorTelemetryData.load()
    if gen_telemetry:
        start_failures = GeneratorTelemetryData.get_start_failures()
        gen_alarms = GeneratorTelemetryData.get_alarms()

        lines.extend([
            "",
            "## Generator Telemetry (DeepSea Controllers)",
            f"- **Total Readings**: {len(gen_telemetry)}",
            f"- **Start Failures**: {len(start_failures)} events",
            f"- **Alarm Events**: {len(gen_alarms)} (including temp warnings, overcrank)",
            "",
            "### Battery Degradation Story - Centurion Mall (ASSET-012)",
            "DeepSea DSE7320 controller telemetry shows classic battery failure progression:",
        ])

        # Centurion Mall battery trend
        centurion_battery = GeneratorTelemetryData.get_battery_trend("ASSET-012")
        if centurion_battery:
            for reading in centurion_battery[:3]:  # First few readings
                if reading["timestamp"]:
                    date_str = reading["timestamp"].strftime("%Y-%m-%d")
                    notes = reading['notes'] or "Standby"
                    lines.append(f"- {date_str}: {reading['battery_voltage']:.1f}V - {notes}")

            # Find the failure point
            failure_events = [r for r in GeneratorTelemetryData.get_by_asset("ASSET-012")
                           if r["alarm_code"] == "OVERCRANK"]
            if failure_events:
                lines.extend([
                    "",
                    "**September 2025 - Complete Failure:**",
                ])
                for event in failure_events:
                    if event["timestamp"]:
                        desc = event['alarm_description'] or event['notes'] or "Overcrank shutdown"
                        lines.append(f"- {event['timestamp'].strftime('%H:%M')}: {event['battery_voltage']:.1f}V - {desc}")

            lines.extend([
                "- **Root Cause**: Charger current dropped from 2.1A to 1.8A over 9 months",
                "- **AI Detection**: Voltage trend below 26V baseline = 85% battery failure probability",
                "- **Outcome**: Overcrank shutdown during power outage, site without backup",
                "- **Fix**: New batteries installed October 2025 - back to 27.4V",
            ])

        lines.extend([
            "",
            "### Hospital Near-Miss - Mediclinic Sandton (ASSET-031)",
            "DSE8610 controller data shows critical hospital backup generator event:",
        ])

        # Mediclinic event
        mediclinic_data = GeneratorTelemetryData.get_by_asset("ASSET-031")
        start_events = [r for r in mediclinic_data if r["start_attempt"] > 0]
        for event in start_events[:4]:  # First few start attempts
            if event["timestamp"]:
                time_str = event["timestamp"].strftime("%H:%M:%S")
                attempt = event["start_attempt"]
                voltage = event["battery_voltage"]
                alarm = event["alarm_description"] or event["notes"]
                lines.append(f"- {time_str}: Attempt {attempt} @ {voltage:.1f}V - {alarm}")

        lines.extend([
            "",
            "**Impact:**",
            "- Hospital on UPS for **12 minutes** during Eskom outage",
            "- ICU, theatres, pharmacy all on battery backup",
            "- Generator started on 3rd attempt at 25.2V (critical threshold)",
            "- **Emergency battery replacement completed within 7 days**",
            "",
            "### Healthy Baseline - Standard Bank Durban (ASSET-050)",
            "New DSE7320 installation shows optimal parameters:",
            "- Battery: 27.4V (excellent)",
            "- Oil Pressure: 420 kPa (manufacturer spec)",
            "- Starts first attempt every time",
            "- Run hours: 1,850 (low utilization)",
        ])

    # HVAC Telemetry (BACnet data from AHUs and Chillers)
    hvac_telemetry = HVACTelemetryData.load()
    if hvac_telemetry:
        vibration_events = HVACTelemetryData.get_vibration_events()
        motor_events = HVACTelemetryData.get_motor_events()

        lines.extend([
            "",
            "## HVAC Telemetry (BACnet/BMS Data)",
            f"- **Total Readings**: {len(hvac_telemetry)}",
            f"- **Vibration Alarms**: {len(vibration_events)} events",
            f"- **Motor Events**: {len(motor_events)} (overload/failure)",
            "",
            "### AHU-002 Failure Progression (BACnet Evidence)",
            "Real-time BACnet data captured the bearing failure as it developed:",
        ])

        # AHU-002 telemetry progression
        ahu002_data = HVACTelemetryData.get_by_asset("ASSET-011")
        for reading in ahu002_data:
            if reading["timestamp"] and reading["alarm_code"]:
                date_str = reading["timestamp"].strftime("%Y-%m-%d %H:%M")
                current = reading["supply_fan_current_a"]
                filter_dp = reading["filter_dp_pa"]
                alarm = reading["alarm_code"]
                notes = reading["notes"] or reading["alarm_description"]
                lines.append(f"- {date_str}: {alarm} | Current: {current:.1f}A | Filter DP: {filter_dp:.0f}Pa")
                lines.append(f"  *{notes}*")

        # Current draw trend
        current_trend = HVACTelemetryData.get_current_trend("ASSET-011")
        if current_trend and len(current_trend) >= 2:
            first_current = current_trend[0]["supply_fan_current_a"]
            last_current = current_trend[-1]["supply_fan_current_a"]
            if first_current > 0:
                pct_increase = ((last_current - first_current) / first_current) * 100
                lines.extend([
                    "",
                    f"**Motor Current Trend**: {first_current:.1f}A → {last_current:.1f}A ({pct_increase:.0f}% increase)",
                    "- Rated motor current: 38A",
                    "- Final reading before failure: 72A (89% overload)",
                    "- **AI Detection**: Current >10% above baseline = bearing degradation",
                ])

        lines.extend([
            "",
            "### Gateway Chiller - Same Pattern Emerging",
            "BACnet vibration data shows identical progression to AHU-002:",
        ])

        # Gateway chiller progression
        chiller_data = HVACTelemetryData.get_by_asset("ASSET-020")
        for reading in chiller_data:
            if reading["timestamp"] and reading["alarm_code"]:
                date_str = reading["timestamp"].strftime("%Y-%m-%d")
                alarm = reading["alarm_code"]
                notes = reading["notes"] or reading["alarm_description"]
                lines.append(f"- {date_str}: {alarm} - {notes}")

        lines.extend([
            "",
            "### AHU-001 Proactive Success",
            "Twin unit learned from AHU-002 failure:",
        ])

        # AHU-001 proactive fix
        ahu001_data = HVACTelemetryData.get_by_asset("ASSET-010")
        for reading in ahu001_data[-2:]:  # Last two readings
            if reading["timestamp"]:
                date_str = reading["timestamp"].strftime("%Y-%m-%d")
                current = reading["supply_fan_current_a"]
                notes = reading["notes"] or "Normal operation"
                lines.append(f"- {date_str}: {current:.1f}A - {notes}")

    # VSD Telemetry (Variable Speed Drives)
    vsd_telemetry = VSDTelemetryData.load()
    if vsd_telemetry:
        vsd_faults = VSDTelemetryData.get_faults()
        vsd_warnings = VSDTelemetryData.get_warnings()
        high_temp_events = VSDTelemetryData.get_high_temp_events(60)

        lines.extend([
            "",
            "## VSD Telemetry (Variable Speed Drives)",
            f"- **Total Readings**: {len(vsd_telemetry)}",
            f"- **Fault Events**: {len(vsd_faults)}",
            f"- **Warning Events**: {len(vsd_warnings)}",
            f"- **High Temperature Events**: {len(high_temp_events)}",
            "",
            "### V&A Waterfront VSD Failure - ASSET-015",
            "Danfoss VLT FC102 showing classic end-of-life pattern:",
        ])

        # V&A VSD progression
        vw_vsd = VSDTelemetryData.get_by_asset("ASSET-015")
        for reading in vw_vsd:
            if reading["timestamp"]:
                date_str = reading["timestamp"].strftime("%Y-%m-%d %H:%M")
                status = reading["vsd_status"]
                alarm = reading["alarm_code"] or ""
                fault_count = reading["fault_log_count"]
                notes = reading["notes"] or ""
                if alarm or "NEW VSD" in notes or "fault" in notes.lower():
                    lines.append(f"- {date_str}: {status} {alarm} (Faults: {fault_count}) - {notes}")

        lines.extend([
            "",
            "**Pattern Recognition:**",
            "- AL29 (Inverter Overload) = IGBT degradation",
            "- 2 faults in 2 months = proactive replacement recommended",
            "- Run hours: 50,000+ = typical 10-year lifespan reached",
            "- **Replacement cost**: ~R85,000 (vs R150,000+ emergency + downtime)",
            "",
            "### Standard Bank CHW Pump - Motor Thermistor Warning",
            "ABB ACS880 showing motor overheating:",
        ])

        # Standard Bank pump
        sb_pump = VSDTelemetryData.get_by_asset("ASSET-042")
        for reading in sb_pump:
            if reading["timestamp"] and reading["alarm_code"]:
                date_str = reading["timestamp"].strftime("%Y-%m-%d %H:%M")
                heatsink = reading["heatsink_temp_c"]
                alarm = reading["alarm_code"]
                notes = reading["notes"] or ""
                lines.append(f"- {date_str}: {alarm} | Heatsink: {heatsink:.0f}°C - {notes}")

        lines.extend([
            "",
            "**Resolution:** Cleaning motor ventilation resolved overheating",
            "**AI Detection:** Heatsink >60°C sustained = investigate cooling",
            "",
            "### VSD Fleet Summary by Make:",
        ])

        # Fleet summary
        makes = {}
        for v in vsd_telemetry:
            make = v["vsd_make"]
            if make not in makes:
                makes[make] = {"count": 0, "faults": 0}
            makes[make]["count"] += 1
            if v["vsd_status"] == "FAULT":
                makes[make]["faults"] += 1

        for make, stats in makes.items():
            lines.append(f"- **{make}**: {stats['count']} readings, {stats['faults']} faults")

    # Chiller Telemetry (detailed refrigeration data)
    chiller_telemetry = ChillerTelemetryData.load()
    if chiller_telemetry:
        chiller_vib = ChillerTelemetryData.get_vibration_events()
        oil_issues = ChillerTelemetryData.get_oil_analysis_issues()
        high_vib = ChillerTelemetryData.get_high_vibration(4.0)

        lines.extend([
            "",
            "## Chiller Telemetry (Detailed Refrigeration Data)",
            f"- **Total Readings**: {len(chiller_telemetry)}",
            f"- **Vibration Alarms**: {len(chiller_vib)} events",
            f"- **Oil Analysis Issues**: {len(oil_issues)} readings with elevated metals",
            f"- **High Vibration (>4mm/s)**: {len(high_vib)} readings",
            "",
            "### Gateway Theatre Chiller - DETAILED FAILURE PREDICTION",
            "York YVAA 300-ton screw chiller showing compressor bearing failure pattern:",
        ])

        # Gateway chiller progression with detailed data
        gateway = ChillerTelemetryData.get_by_asset("ASSET-020")
        for reading in gateway:
            if reading["timestamp"]:
                date_str = reading["timestamp"].strftime("%Y-%m-%d")
                vib = reading["vibration_mm_s"]
                oil = reading["oil_analysis_result"] or "Not tested"
                alarm = reading["alarm_code"] or "-"
                current = reading["compressor_current_a"]
                oil_press = reading["oil_pressure_kpa"]
                notes = reading["notes"] or ""
                lines.append(f"- {date_str}: Vib {vib:.1f}mm/s | Oil: {oil} | {alarm}")
                if "CRITICAL" in notes or "metal" in notes.lower() or "failure" in notes.lower():
                    lines.append(f"  *{notes}*")

        lines.extend([
            "",
            "**Predictive Indicators:**",
            "- Vibration trend: 2.8 → 3.8 → 4.2 → 4.6 → 5.2 mm/s",
            "- Oil analysis: NORMAL → ELEVATED (28ppm iron vs <15ppm normal)",
            "- Oil pressure dropping: 520 → 515 → 508 → 498 → 485 kPa",
            "- **AI Confidence: 95% failure within 4-8 weeks**",
            "",
            "**Cost Analysis:**",
            "- Proactive bearing replacement: ~R45,000",
            "- Emergency compressor replacement: ~R180,000",
            "- Downtime during summer: 2-3 weeks = R500,000+ lost revenue",
            "- **Savings potential: R635,000**",
            "",
            "### Chiller Fleet Efficiency Comparison:",
        ])

        # Fleet efficiency comparison
        centrifugal = ChillerTelemetryData.get_by_type("centrifugal")
        screw = ChillerTelemetryData.get_by_type("screw")

        if centrifugal:
            avg_eff = sum(c["efficiency_kw_ton"] for c in centrifugal if c["efficiency_kw_ton"] > 0) / len([c for c in centrifugal if c["efficiency_kw_ton"] > 0])
            lines.append(f"- **Centrifugal chillers**: {avg_eff:.2f} kW/ton average (Carrier, Trane)")

        if screw:
            avg_eff = sum(c["efficiency_kw_ton"] for c in screw if c["efficiency_kw_ton"] > 0) / len([c for c in screw if c["efficiency_kw_ton"] > 0])
            lines.append(f"- **Screw chillers**: {avg_eff:.2f} kW/ton average (York, Carrier)")

        lines.extend([
            "",
            "### Mediclinic Hospital Chiller - Critical Environment",
            "Carrier 30XW screw chiller serving operating theatres:",
        ])

        # Mediclinic chiller
        mediclinic = ChillerTelemetryData.get_by_asset("ASSET-030")
        for reading in mediclinic:
            if reading["timestamp"] and reading["alarm_code"]:
                date_str = reading["timestamp"].strftime("%Y-%m-%d %H:%M")
                chw_temp = reading["chw_supply_temp_c"]
                alarm = reading["alarm_code"]
                notes = reading["notes"] or ""
                lines.append(f"- {date_str}: CHW {chw_temp:.1f}°C | {alarm} - {notes}")

    # Pump Telemetry (CHW and Condenser Water Pumps)
    pump_telemetry = PumpTelemetryData.load()
    if pump_telemetry:
        pump_vib = PumpTelemetryData.get_vibration_events()
        high_bearing = PumpTelemetryData.get_high_bearing_temp(55)
        seal_leaks = PumpTelemetryData.get_seal_leakage()

        lines.extend([
            "",
            "## Pump Telemetry (CHW & Condenser Water Pumps)",
            f"- **Total Readings**: {len(pump_telemetry)}",
            f"- **Vibration Alarms**: {len(pump_vib)} events",
            f"- **High Bearing Temp Events**: {len(high_bearing)} (>55°C)",
            f"- **Seal Leakage Detected**: {len(seal_leaks)} pumps",
            "",
            "### Sandton City CHW Pump - ASSET-008",
            "Grundfos TPE 100-250 showing early bearing wear pattern:",
        ])

        # Sandton City pump progression
        sc_pump = PumpTelemetryData.get_by_asset("ASSET-008")
        for reading in sc_pump:
            if reading["timestamp"]:
                date_str = reading["timestamp"].strftime("%Y-%m-%d")
                vib_de = reading["vibration_de_mm_s"]
                vib_nde = reading["vibration_nde_mm_s"]
                bearing_de = reading["bearing_temp_de_c"]
                seal = reading["seal_leakage"]
                alarm = reading["alarm_code"] or "-"
                notes = reading["notes"] or ""
                lines.append(f"- {date_str}: DE {vib_de:.1f}mm/s | NDE {vib_nde:.1f}mm/s | Bearing {bearing_de:.0f}°C | Seal: {seal} | {alarm}")
                if "similar to" in notes.lower() or "monitor" in notes.lower() or "trace" in notes.lower():
                    lines.append(f"  *{notes}*")

        lines.extend([
            "",
            "**Predictive Indicators:**",
            "- Vibration trend (DE): 2.2 → 2.5 → 3.2 → 3.5 mm/s",
            "- Bearing temp trend: 48 → 52 → 56 → 58°C",
            "- Seal status: NONE → TRACE (early leakage detected)",
            "- **AI Confidence: 75% bearing failure within 6 months if not addressed**",
            "",
            "### Centurion Mall CHW Pump - ASSET-018",
            "KSB Etanorm showing impact of AHU-002 failure:",
        ])

        # Centurion pump
        cm_pump = PumpTelemetryData.get_by_asset("ASSET-018")
        for reading in cm_pump:
            if reading["timestamp"] and reading["alarm_code"]:
                date_str = reading["timestamp"].strftime("%Y-%m-%d")
                motor_temp = reading["motor_temp_c"]
                alarm = reading["alarm_code"]
                notes = reading["notes"] or ""
                lines.append(f"- {date_str}: Motor {motor_temp:.0f}°C | {alarm} - {notes}")

        lines.extend([
            "",
            "**Key Insight:** When AHU-002 failed, the pump experienced increased load",
            "(system attempting to compensate through higher flow). Motor temperature",
            "spike was an early warning of the cascading failure scenario.",
            "",
            "### Pump Fleet Summary by Make:",
        ])

        # Fleet summary
        makes = {}
        for p in pump_telemetry:
            make = p["pump_make"]
            if make not in makes:
                makes[make] = {"count": 0, "alarms": 0}
            makes[make]["count"] += 1
            if p["alarm_code"]:
                makes[make]["alarms"] += 1

        for make, stats in makes.items():
            lines.append(f"- **{make}**: {stats['count']} readings, {stats['alarms']} alarm events")

    return "\n".join(lines)


def get_work_order_detail(work_order_id: str) -> str:
    """Get detailed work order information for AI context."""
    wo = None
    for w in WorkOrderData.load():
        if w["work_order_id"] == work_order_id:
            wo = w
            break

    if not wo:
        return f"Work order {work_order_id} not found."

    lines = [
        f"## Work Order: {wo['work_order_id']}",
        f"**Site**: {wo['site_name']}",
        f"**Asset**: {wo['asset_tag']} ({wo['asset_category']})",
        f"**Priority**: {wo['priority'].upper()}",
        f"**Type**: {wo['type']}",
        "",
        f"**Description**: {wo['description']}",
        f"**Resolution**: {wo['resolution']}",
        "",
        f"**Technician Notes**: {wo['technician_notes']}",
        f"**Technician**: {wo['technician_name']}",
        "",
        f"**Costs**: Labour R{wo['labour_cost']:,.0f} | Parts R{wo['parts_cost']:,.0f} | Total R{wo['total_cost']:,.0f}",
        f"**SLA Met**: {'Yes' if wo['sla_met'] else 'No'} (Target: {wo['sla_target_hours']}h)",
        f"**Repeat Call**: {'Yes' if wo['repeat_call'] else 'No'}",
    ]

    return "\n".join(lines)


def get_asset_history(asset_id: str) -> str:
    """Get complete asset history for AI context."""
    asset = AssetData.get_by_id(asset_id)
    if not asset:
        return f"Asset {asset_id} not found."

    work_orders = WorkOrderData.get_failure_chain(asset_id)

    lines = [
        f"## Asset: {asset['asset_tag']}",
        f"**Location**: {asset['site_name']}",
        f"**Make/Model**: {asset['make']} {asset['model']}",
        f"**Age**: {asset['age_years']} years (Expected life: {asset['expected_life_years']} years)",
        f"**Condition**: {asset['condition'].upper()}",
        f"**Criticality**: {asset['criticality']}",
        "",
        f"**Notes**: {asset['notes']}",
        "",
        "## Work Order History",
    ]

    for wo in work_orders:
        date_str = wo["reported_date"].strftime("%Y-%m-%d") if wo["reported_date"] else "Unknown"
        lines.append(f"\n### {wo['work_order_id']} ({date_str})")
        lines.append(f"**{wo['priority'].upper()}** - {wo['description']}")
        lines.append(f"*Technician Notes*: {wo['technician_notes']}")
        if wo["repeat_call"]:
            lines.append("**REPEAT CALL**")

    return "\n".join(lines)
