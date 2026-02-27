"""
Sensor data formatter for DALI occupancy systems.

Provides utilities to enrich sensor data with zone assignments and desk information
by parsing equipment metadata and linking to zone/desk data.
"""

from typing import Dict, Any, List
from app.database.supabase_client import get_supabase_client


def format_sensor_with_zone(sensor_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Format a sensor equipment record to include zone and desk information.

    Args:
        sensor_data: Equipment record from database

    Returns:
        Enhanced sensor data with zone_id, zone_name, and associated_desks
    """
    formatted = sensor_data.copy()

    # Extract zone info from device_info
    device_info = sensor_data.get("device_info") or {}

    zone_id = device_info.get("zone_id")
    zone_uuid = device_info.get("zone_uuid")

    # Add to formatted output
    formatted["zone_id"] = zone_id
    formatted["zone_uuid"] = zone_uuid

    # Remove "Desk: -" - use Zone instead
    # Frontend will display: "Zone: Zone-L2-A" instead of "Desk: -"

    return formatted


async def get_sensors_with_zones(building_id: str) -> List[Dict[str, Any]]:
    """
    Get all sensors for a building with zone assignments.

    Args:
        building_id: Building UUID

    Returns:
        List of sensors with zone information
    """
    client = get_supabase_client()

    # Get all DALI equipment (sensors)
    result = client.table("equipment").select("*").eq("building_id", building_id).eq("type", "dali").execute()

    sensors = []
    for sensor in result.data:
        formatted = format_sensor_with_zone(sensor)
        sensors.append(formatted)

    return sensors


def get_desks_in_zone(zone_id: str) -> List[Dict[str, Any]]:
    """
    Get all desks in a specific zone.

    Args:
        zone_id: Zone UUID

    Returns:
        List of desks in the zone
    """
    client = get_supabase_client()

    result = client.table("desks").select("*").eq("zone_id", zone_id).execute()

    return result.data or []


async def format_sensor_with_zone_and_desks(sensor_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Enrich a DALI sensor dict with zone and desk information from Equipment table.

    Attempts to find the corresponding Equipment record and extract zone assignments
    and associated desks.

    Args:
        sensor_data: Sensor dict from lighting_service (with sensor_id, name, zone_id, etc.)

    Returns:
        Enhanced sensor data with zone_id, zone_name, and desks_in_zone information
    """
    formatted = sensor_data.copy()

    # Try to find matching Equipment record
    client = get_supabase_client()

    # Strategy: Match by sensor name or sensor_id
    # Common patterns: "site-002-DALI-L2-A", "S002-DALI-L2-A"
    sensor_id = sensor_data.get("sensor_id", "")
    _sensor_name = sensor_data.get("name", "")

    equipment_record = None

    # Try to find by name/sensor_id match
    try:
        # Search for Equipment records with matching code (equipment.code contains sensor_id)
        result = client.table("equipment").select("*").ilike("code", f"%{sensor_id}%").eq("type", "dali").execute()

        if result.data:
            equipment_record = result.data[0]  # Take first match
    except Exception:
        # Equipment lookup failed, continue with DALI service data
        pass

    # Extract zone info from Equipment.device_info if found
    if equipment_record:
        device_info = equipment_record.get("device_info") or {}
        zone_id = device_info.get("zone_id")
        zone_uuid = device_info.get("zone_uuid")

        if zone_id:
            formatted["zone_id"] = zone_id
            formatted["zone_uuid"] = zone_uuid
            formatted["zone_name"] = zone_id  # Use zone_id as display name

            # Get desks in this zone
            try:
                desks_result = client.table("desks").select("*").eq("zone_id", zone_uuid or zone_id).execute()

                desks = desks_result.data or []
                formatted["desks_in_zone"] = desks
                formatted["desk_count"] = len(desks)
                formatted["desk_numbers"] = [d.get("number") for d in desks if d.get("number")]
            except Exception:
                # Desk lookup failed, continue
                formatted["desks_in_zone"] = []
                formatted["desk_count"] = 0
                formatted["desk_numbers"] = []
        else:
            # Equipment found but no zone assignment yet
            formatted["zone_name"] = sensor_data.get("zone_id", "unassigned")
            formatted["desks_in_zone"] = []
            formatted["desk_count"] = 0
            formatted["desk_numbers"] = []
    else:
        # Equipment not found, use DALI service zone_id if available
        zone_id = sensor_data.get("zone_id")
        if zone_id:
            formatted["zone_name"] = zone_id
        formatted["desks_in_zone"] = []
        formatted["desk_count"] = 0
        formatted["desk_numbers"] = []

    return formatted
