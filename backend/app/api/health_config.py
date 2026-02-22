"""Health Calculation Configuration API endpoints.

CRUD operations for equipment health calculation parameters.
Engineers can configure how health scores are calculated per equipment type.
"""

import json
from pathlib import Path
from typing import Dict, Any, Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api/health-config", tags=["health-config"])

# Path to health calculation config
CONFIG_PATH = Path(__file__).parent.parent / "data" / "health_calculation_config.json"


class HealthWeights(BaseModel):
    """Weights for health score calculation (must sum to 1.0)."""

    age_factor: float = Field(..., ge=0, le=1)
    service_compliance: float = Field(..., ge=0, le=1)
    runtime_hours: float = Field(..., ge=0, le=1)
    fault_history: float = Field(..., ge=0, le=1)


class HealthThresholds(BaseModel):
    """Thresholds for health warnings and critical alerts."""

    runtime_hours_warning: int = Field(..., ge=0)
    runtime_hours_critical: int = Field(..., ge=0)
    age_warning_years: int = Field(..., ge=0)
    age_critical_years: int = Field(..., ge=0)
    service_overdue_days_warning: int = Field(..., ge=0)
    service_overdue_days_critical: int = Field(..., ge=0)


class FaultWeights(BaseModel):
    """Optional fault weights by fault type."""

    class Config:
        extra = "allow"


class EquipmentHealthConfig(BaseModel):
    """Health calculation configuration for an equipment type."""

    equipment_type: str
    expected_life_years: int = Field(..., ge=1, le=100)
    service_interval_days: int = Field(..., ge=1, le=365)
    weights: HealthWeights
    thresholds: HealthThresholds
    fault_weights: Optional[Dict[str, float]] = None


class HealthConfigUpdate(BaseModel):
    """Request model for updating health config."""

    expected_life_years: Optional[int] = Field(None, ge=1, le=100)
    service_interval_days: Optional[int] = Field(None, ge=1, le=365)
    weights: Optional[HealthWeights] = None
    thresholds: Optional[HealthThresholds] = None
    fault_weights: Optional[Dict[str, float]] = None


def load_config() -> Dict[str, Any]:
    """Load health calculation config from JSON file."""
    if not CONFIG_PATH.exists():
        return {}
    with open(CONFIG_PATH) as f:
        return json.load(f)


def save_config(config: Dict[str, Any]) -> None:
    """Save health calculation config to JSON file."""
    with open(CONFIG_PATH, "w") as f:
        json.dump(config, f, indent=2)


@router.get("")
async def list_health_configs():
    """List all equipment type health configurations."""
    config = load_config()
    return {
        "equipment_types": list(config.keys()),
        "configs": config,
        "total": len(config),
    }


@router.get("/{equipment_type}")
async def get_health_config(equipment_type: str):
    """Get health configuration for a specific equipment type."""
    config = load_config()

    if equipment_type not in config:
        raise HTTPException(status_code=404, detail=f"No health config found for equipment type: {equipment_type}")

    return config[equipment_type]


@router.put("/{equipment_type}")
async def update_health_config(equipment_type: str, update: HealthConfigUpdate):
    """Update health configuration for an equipment type.

    Only provided fields will be updated.
    """
    config = load_config()

    if equipment_type not in config:
        raise HTTPException(status_code=404, detail=f"No health config found for equipment type: {equipment_type}")

    current = config[equipment_type]

    # Update only provided fields
    if update.expected_life_years is not None:
        current["expected_life_years"] = update.expected_life_years

    if update.service_interval_days is not None:
        current["service_interval_days"] = update.service_interval_days

    if update.weights is not None:
        weights_dict = update.weights.model_dump()
        # Validate weights sum to 1.0 (with tolerance)
        total = sum(weights_dict.values())
        if not (0.99 <= total <= 1.01):
            raise HTTPException(status_code=400, detail=f"Weights must sum to 1.0, got {total:.2f}")
        current["weights"] = weights_dict

    if update.thresholds is not None:
        current["thresholds"] = update.thresholds.model_dump()

    if update.fault_weights is not None:
        # Validate fault weights sum to 1.0 (with tolerance)
        total = sum(update.fault_weights.values())
        if not (0.99 <= total <= 1.01):
            raise HTTPException(status_code=400, detail=f"Fault weights must sum to 1.0, got {total:.2f}")
        current["fault_weights"] = update.fault_weights

    config[equipment_type] = current
    save_config(config)

    return {
        "message": f"Health config updated for {equipment_type}",
        "config": current,
    }


@router.post("/{equipment_type}")
async def create_health_config(equipment_type: str, new_config: EquipmentHealthConfig):
    """Create health configuration for a new equipment type."""
    config = load_config()

    if equipment_type in config:
        raise HTTPException(
            status_code=409, detail=f"Health config already exists for equipment type: {equipment_type}"
        )

    # Validate weights sum to 1.0
    weights_dict = new_config.weights.model_dump()
    total = sum(weights_dict.values())
    if not (0.99 <= total <= 1.01):
        raise HTTPException(status_code=400, detail=f"Weights must sum to 1.0, got {total:.2f}")

    # Validate fault weights if provided
    if new_config.fault_weights:
        total = sum(new_config.fault_weights.values())
        if not (0.99 <= total <= 1.01):
            raise HTTPException(status_code=400, detail=f"Fault weights must sum to 1.0, got {total:.2f}")

    config[equipment_type] = new_config.model_dump()
    save_config(config)

    return {
        "message": f"Health config created for {equipment_type}",
        "config": config[equipment_type],
    }


@router.delete("/{equipment_type}")
async def delete_health_config(equipment_type: str):
    """Delete health configuration for an equipment type."""
    config = load_config()

    if equipment_type not in config:
        raise HTTPException(status_code=404, detail=f"No health config found for equipment type: {equipment_type}")

    # Prevent deletion of core HVAC types
    core_types = ["chiller", "ahu", "fcu", "vav", "cooling_tower", "pump"]
    if equipment_type in core_types:
        raise HTTPException(status_code=400, detail=f"Cannot delete core equipment type: {equipment_type}")

    del config[equipment_type]
    save_config(config)

    return {
        "message": f"Health config deleted for {equipment_type}",
    }


@router.post("/reset/{equipment_type}")
async def reset_health_config(equipment_type: str):
    """Reset health configuration for an equipment type to defaults.

    Only works for core equipment types (chiller, ahu, fcu, vav, cooling_tower, pump).
    """
    # Default configurations
    defaults = {
        "chiller": {
            "equipment_type": "chiller",
            "expected_life_years": 20,
            "service_interval_days": 90,
            "weights": {"age_factor": 0.2, "service_compliance": 0.3, "runtime_hours": 0.2, "fault_history": 0.3},
            "thresholds": {
                "runtime_hours_warning": 20000,
                "runtime_hours_critical": 40000,
                "age_warning_years": 15,
                "age_critical_years": 18,
                "service_overdue_days_warning": 30,
                "service_overdue_days_critical": 90,
            },
            "fault_weights": {
                "compressor_failure": 0.4,
                "refrigerant_leak": 0.3,
                "electrical_fault": 0.2,
                "sensor_failure": 0.1,
            },
        },
        "ahu": {
            "equipment_type": "ahu",
            "expected_life_years": 25,
            "service_interval_days": 60,
            "weights": {"age_factor": 0.15, "service_compliance": 0.35, "runtime_hours": 0.2, "fault_history": 0.3},
            "thresholds": {
                "runtime_hours_warning": 30000,
                "runtime_hours_critical": 50000,
                "age_warning_years": 20,
                "age_critical_years": 23,
                "service_overdue_days_warning": 20,
                "service_overdue_days_critical": 60,
            },
            "fault_weights": {
                "fan_motor_failure": 0.35,
                "belt_wear": 0.25,
                "coil_fouling": 0.2,
                "damper_actuator": 0.2,
            },
        },
        "fcu": {
            "equipment_type": "fcu",
            "expected_life_years": 15,
            "service_interval_days": 90,
            "weights": {"age_factor": 0.2, "service_compliance": 0.3, "runtime_hours": 0.15, "fault_history": 0.35},
            "thresholds": {
                "runtime_hours_warning": 15000,
                "runtime_hours_critical": 25000,
                "age_warning_years": 12,
                "age_critical_years": 14,
                "service_overdue_days_warning": 30,
                "service_overdue_days_critical": 90,
            },
            "fault_weights": {
                "fan_motor_failure": 0.4,
                "valve_actuator": 0.25,
                "filter_blockage": 0.2,
                "thermostat_failure": 0.15,
            },
        },
        "vav": {
            "equipment_type": "vav",
            "expected_life_years": 20,
            "service_interval_days": 120,
            "weights": {"age_factor": 0.15, "service_compliance": 0.25, "runtime_hours": 0.2, "fault_history": 0.4},
            "thresholds": {
                "runtime_hours_warning": 25000,
                "runtime_hours_critical": 40000,
                "age_warning_years": 15,
                "age_critical_years": 18,
                "service_overdue_days_warning": 45,
                "service_overdue_days_critical": 120,
            },
            "fault_weights": {
                "damper_actuator": 0.4,
                "airflow_sensor": 0.3,
                "controller_failure": 0.2,
                "duct_leakage": 0.1,
            },
        },
        "cooling_tower": {
            "equipment_type": "cooling_tower",
            "expected_life_years": 25,
            "service_interval_days": 30,
            "weights": {"age_factor": 0.2, "service_compliance": 0.35, "runtime_hours": 0.15, "fault_history": 0.3},
            "thresholds": {
                "runtime_hours_warning": 35000,
                "runtime_hours_critical": 50000,
                "age_warning_years": 20,
                "age_critical_years": 23,
                "service_overdue_days_warning": 14,
                "service_overdue_days_critical": 45,
            },
            "fault_weights": {
                "fan_motor_failure": 0.3,
                "fill_media_degradation": 0.25,
                "water_treatment_issue": 0.25,
                "drift_eliminator": 0.2,
            },
        },
        "pump": {
            "equipment_type": "pump",
            "expected_life_years": 15,
            "service_interval_days": 90,
            "weights": {"age_factor": 0.2, "service_compliance": 0.3, "runtime_hours": 0.25, "fault_history": 0.25},
            "thresholds": {
                "runtime_hours_warning": 20000,
                "runtime_hours_critical": 35000,
                "age_warning_years": 12,
                "age_critical_years": 14,
                "service_overdue_days_warning": 30,
                "service_overdue_days_critical": 90,
            },
            "fault_weights": {
                "bearing_failure": 0.35,
                "seal_leakage": 0.3,
                "impeller_wear": 0.2,
                "motor_failure": 0.15,
            },
        },
    }

    if equipment_type not in defaults:
        raise HTTPException(status_code=400, detail=f"No default config available for equipment type: {equipment_type}")

    config = load_config()
    config[equipment_type] = defaults[equipment_type]
    save_config(config)

    return {
        "message": f"Health config reset to defaults for {equipment_type}",
        "config": config[equipment_type],
    }
