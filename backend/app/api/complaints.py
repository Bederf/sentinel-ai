"""
Comfort Complaint API Endpoints
===============================
REST API for desk-level comfort complaint handling.

The hero endpoint: POST /api/complaints/submit?desk_id=25&complaint_type=too_hot
Returns instant AI diagnosis with BMS context and actionable suggestions.
"""

from typing import List, Optional

from fastapi import APIRouter, HTTPException

from app.security.prompt_guard import score_prompt
from app.services.complaint_handler import get_complaint_handler, reload_complaint_handler

router = APIRouter(prefix="/api/complaints", tags=["Comfort Complaints"])


@router.post("/submit", tags=["llm_touching"])
async def submit_complaint(
    desk_id: str,
    complaint_type: str = "too_hot",
    user_name: Optional[str] = None,
    description: Optional[str] = None,
) -> dict:
    """
    Submit a comfort complaint and get instant AI diagnosis.

    This is the hero endpoint:
    POST /api/complaints/submit?desk_id=25&complaint_type=too_hot

    Args:
        desk_id: Desk identifier (accepts "25", "L12-25", "Desk 25", etc.)
        complaint_type: Type of complaint - too_hot, too_cold, stuffy, drafty, other
        user_name: Optional name of the person reporting
        description: Optional additional description

    Returns:
        - complaint_id: Unique identifier for the complaint
        - desk: Desk context (location, near_window, zone)
        - zone: Zone BMS status (temp, setpoint, FCU status)
        - diagnosis: AI diagnosis (root cause, confidence)
        - suggestions: Actionable suggestions
        - auto_action_taken: Any automatic action taken
        - needs_dispatch: Whether technician dispatch is needed
    """
    # Guard description if provided (user-supplied text flows to AI diagnosis)
    guarded_description = description
    if description:
        guard_result = score_prompt(description, "direct")
        if not guard_result.allow:
            raise HTTPException(status_code=400, detail="Prompt injection detected in description")
        if guard_result.rewritten_text:
            guarded_description = guard_result.rewritten_text

    handler = get_complaint_handler()
    diagnosis = handler.handle_complaint(desk_id, complaint_type, user_name, guarded_description)
    return {
        "complaint_id": diagnosis.complaint_id,
        "desk": diagnosis.desk.to_dict(),
        "zone": diagnosis.zone.to_dict(),
        "diagnosis": diagnosis.diagnosis,
        "root_cause": diagnosis.root_cause,
        "confidence": diagnosis.confidence,
        "suggestions": diagnosis.suggestions,
        "auto_action_taken": diagnosis.auto_action_taken,
        "needs_dispatch": diagnosis.needs_dispatch,
    }


@router.get("/desk/{desk_id}")
async def get_desk_info(desk_id: str) -> dict:
    """
    Get desk location and BMS mapping info.

    Args:
        desk_id: Desk identifier (accepts "25", "L12-25", "Desk 25", etc.)

    Returns:
        - desk: Desk metadata (location, floor, zone mapping)
        - bms_context: BMS equipment and sensor context for the desk's zone
    """
    handler = get_complaint_handler()
    desk = handler.get_desk(desk_id)
    if not desk:
        raise HTTPException(status_code=404, detail=f"Desk '{desk_id}' not found")
    bms_context = handler.lookup_desk_bms(desk_id)
    return {"desk": desk.to_dict(), "bms_context": bms_context}


@router.get("/zone/{zone_id}")
async def get_zone_context(zone_id: str) -> dict:
    """
    Get combined HVAC + lighting context for a zone.

    Args:
        zone_id: Zone identifier (e.g., "Zone-L12-N")

    Returns:
        - zone: Zone metadata and current status
        - context: Combined HVAC, lighting, and occupancy analysis
    """
    handler = get_complaint_handler()
    zone = handler.get_zone(zone_id)
    if not zone:
        raise HTTPException(status_code=404, detail=f"Zone '{zone_id}' not found")
    context = handler.get_zone_context(zone_id)
    return {"zone": zone.to_dict(), "context": context}


@router.get("/history")
async def get_complaint_history(
    desk_id: Optional[str] = None,
    zone_id: Optional[str] = None,
    hours: int = 24,
) -> List[dict]:
    """
    Get complaint history for pattern analysis.

    Args:
        desk_id: Optional filter by desk ID
        zone_id: Optional filter by zone ID
        hours: Time window in hours (default 24)

    Returns:
        List of complaint records with timestamps and status
    """
    handler = get_complaint_handler()
    if desk_id:
        complaints = handler.get_complaint_history(desk_id=desk_id)
    elif zone_id:
        complaints = handler.get_complaint_history(zone_id=zone_id)
    else:
        complaints = handler.get_recent_complaints(hours=hours)
    return [c.to_dict() for c in complaints]


@router.get("/desks")
async def list_desks(
    floor: Optional[str] = None,
    zone_id: Optional[str] = None,
) -> List[dict]:
    """
    List all desks with optional filters.

    Args:
        floor: Optional filter by floor (e.g., "Level 12")
        zone_id: Optional filter by zone ID

    Returns:
        List of desk records with location and BMS mapping
    """
    handler = get_complaint_handler()
    desks = handler.get_all_desks()
    if floor:
        desks = [d for d in desks if d.floor == floor]
    if zone_id:
        desks = [d for d in desks if d.zone_id == zone_id]
    return [d.to_dict() for d in desks]


@router.get("/zones")
async def list_hvac_zones() -> List[dict]:
    """
    List all HVAC zones with current status.

    Returns:
        List of zone records with BMS equipment and current readings
    """
    handler = get_complaint_handler()
    return [z.to_dict() for z in handler.get_all_zones()]


@router.post("/reload")
async def reload_data() -> dict:
    """
    Reload desk and zone data from building configuration.
    Use this after updating desk/zone JSON files without restarting the backend.

    Returns:
        Summary of loaded data counts
    """
    handler = reload_complaint_handler()
    desks = handler.get_all_desks()
    zones = handler.get_all_zones()
    return {
        "status": "reloaded",
        "desks_loaded": len(desks),
        "zones_loaded": len(zones),
        "message": f"Loaded {len(desks)} desks and {len(zones)} zones",
    }
