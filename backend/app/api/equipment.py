"""Equipment API endpoints."""

import json
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

router = APIRouter()

# Load data directory
DATA_DIR = Path(__file__).parent.parent / "data"


def load_equipment() -> list[dict]:
    """Load equipment from JSON file."""
    equipment_file = DATA_DIR / "equipment.json"
    if equipment_file.exists():
        with open(equipment_file) as f:
            return json.load(f)
    return []


def load_sensors() -> list[dict]:
    """Load sensors from JSON file."""
    sensors_file = DATA_DIR / "sensors.json"
    if sensors_file.exists():
        with open(sensors_file) as f:
            return json.load(f)
    return []


def load_alerts() -> list[dict]:
    """Load alerts from JSON file."""
    alerts_file = DATA_DIR / "alerts.json"
    if alerts_file.exists():
        with open(alerts_file) as f:
            return json.load(f)
    return []


class EquipmentBase(BaseModel):
    """Base equipment model."""

    id: str
    site_id: str
    type: str
    name: str
    manufacturer: str
    model: str
    capacity: str
    install_date: str
    last_service: str
    status: str
    health_score: int
    location: str
    serial_number: str


class EquipmentResponse(EquipmentBase):
    """Equipment response with computed fields."""

    sensor_count: int = 0
    active_alerts: int = 0


class EquipmentListResponse(BaseModel):
    """Response for equipment list."""

    total: int
    equipment: list[EquipmentResponse]


@router.get("/equipment", response_model=EquipmentListResponse)
async def list_equipment(
    site_id: Optional[str] = Query(None, description="Filter by site ID"),
    equipment_type: Optional[str] = Query(None, alias="type", description="Filter by equipment type"),
    status: Optional[str] = Query(None, description="Filter by status (normal, warning, critical)"),
    min_health: Optional[int] = Query(None, ge=0, le=100, description="Minimum health score"),
    max_health: Optional[int] = Query(None, ge=0, le=100, description="Maximum health score"),
) -> EquipmentListResponse:
    """
    List all equipment with optional filtering.

    Args:
        site_id: Filter by site ID
        equipment_type: Filter by type (ahu, chiller, ups, generator, etc.)
        status: Filter by status (normal, warning, critical)
        min_health: Minimum health score (0-100)
        max_health: Maximum health score (0-100)

    Returns:
        EquipmentListResponse with total count and list of equipment.
    """
    equipment = load_equipment()
    sensors = load_sensors()
    alerts = load_alerts()

    # Apply filters
    if site_id:
        equipment = [e for e in equipment if e["site_id"] == site_id]
    if equipment_type:
        equipment = [e for e in equipment if e["type"].lower() == equipment_type.lower()]
    if status:
        equipment = [e for e in equipment if e["status"].lower() == status.lower()]
    if min_health is not None:
        equipment = [e for e in equipment if e["health_score"] >= min_health]
    if max_health is not None:
        equipment = [e for e in equipment if e["health_score"] <= max_health]

    # Enrich with counts
    result = []
    for eq in equipment:
        eq_sensors = [s for s in sensors if s.get("equipment_id") == eq["id"]]
        eq_alerts = [
            a for a in alerts
            if a.get("equipment_id") == eq["id"] and a.get("status") == "active"
        ]
        result.append(
            EquipmentResponse(
                **eq,
                sensor_count=len(eq_sensors),
                active_alerts=len(eq_alerts),
            )
        )

    return EquipmentListResponse(total=len(result), equipment=result)


@router.get("/equipment/{equipment_id}", response_model=EquipmentResponse)
async def get_equipment(equipment_id: str) -> EquipmentResponse:
    """
    Get a single equipment item by ID.

    Args:
        equipment_id: The equipment identifier.

    Returns:
        EquipmentResponse with equipment details.

    Raises:
        HTTPException: If equipment not found.
    """
    equipment = load_equipment()
    sensors = load_sensors()
    alerts = load_alerts()

    eq = next((e for e in equipment if e["id"] == equipment_id), None)
    if not eq:
        raise HTTPException(status_code=404, detail=f"Equipment {equipment_id} not found")

    eq_sensors = [s for s in sensors if s.get("equipment_id") == equipment_id]
    eq_alerts = [
        a for a in alerts
        if a.get("equipment_id") == equipment_id and a.get("status") == "active"
    ]

    return EquipmentResponse(
        **eq,
        sensor_count=len(eq_sensors),
        active_alerts=len(eq_alerts),
    )


class EquipmentTypeStats(BaseModel):
    """Statistics for an equipment type."""

    type: str
    count: int
    avg_health: float
    warning_count: int
    critical_count: int


class EquipmentStatsResponse(BaseModel):
    """Equipment statistics response."""

    total: int
    by_type: list[EquipmentTypeStats]
    avg_health: float
    warning_count: int
    critical_count: int


@router.get("/equipment-stats", response_model=EquipmentStatsResponse)
async def get_equipment_stats(
    site_id: Optional[str] = Query(None, description="Filter by site ID"),
) -> EquipmentStatsResponse:
    """
    Get equipment statistics.

    Args:
        site_id: Optional site ID to filter by.

    Returns:
        EquipmentStatsResponse with aggregated statistics.
    """
    equipment = load_equipment()

    if site_id:
        equipment = [e for e in equipment if e["site_id"] == site_id]

    if not equipment:
        return EquipmentStatsResponse(
            total=0,
            by_type=[],
            avg_health=0,
            warning_count=0,
            critical_count=0,
        )

    # Calculate stats by type
    type_stats: dict[str, dict] = {}
    for eq in equipment:
        eq_type = eq["type"]
        if eq_type not in type_stats:
            type_stats[eq_type] = {
                "type": eq_type,
                "count": 0,
                "total_health": 0,
                "warning_count": 0,
                "critical_count": 0,
            }
        type_stats[eq_type]["count"] += 1
        type_stats[eq_type]["total_health"] += eq["health_score"]
        if eq["status"] == "warning":
            type_stats[eq_type]["warning_count"] += 1
        elif eq["status"] == "critical":
            type_stats[eq_type]["critical_count"] += 1

    by_type = [
        EquipmentTypeStats(
            type=stats["type"],
            count=stats["count"],
            avg_health=round(stats["total_health"] / stats["count"], 1),
            warning_count=stats["warning_count"],
            critical_count=stats["critical_count"],
        )
        for stats in type_stats.values()
    ]

    total_health = sum(eq["health_score"] for eq in equipment)
    warning_count = sum(1 for eq in equipment if eq["status"] == "warning")
    critical_count = sum(1 for eq in equipment if eq["status"] == "critical")

    return EquipmentStatsResponse(
        total=len(equipment),
        by_type=sorted(by_type, key=lambda x: -x.count),
        avg_health=round(total_health / len(equipment), 1),
        warning_count=warning_count,
        critical_count=critical_count,
    )
