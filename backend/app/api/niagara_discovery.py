"""
Niagara point discovery and mapping API endpoints.

REST API for AI-assisted point discovery, classification, mapping review,
approval, and manual correction workflows. Enables rapid Niagara
commissioning with chat-based review.
"""

import logging
from enum import Enum
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from app.services.niagara.point_discovery import (
    DiscoveryResult,
    PointDiscoveryService,
    get_point_discovery_service,
)
from app.services.niagara.mapping_service import (
    PointMappingService,
    get_mapping_service,
)
from app.services.niagara.point_classifier import get_point_classifier

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/niagara", tags=["niagara-discovery"])


# ---------------------------------------------------------------------------
# Request/Response Models
# ---------------------------------------------------------------------------

class DiscoverRequest(BaseModel):
    """Request to trigger point discovery and classification."""

    device_ip: str = Field(..., description="IP address of the BACnet device (JACE/Supervisor)")
    site_id: str = Field(..., description="SENTINEL site ID for mapping (e.g., 'site-002')")
    device_bacnet_id: Optional[int] = Field(
        None, description="Optional BACnet device instance ID"
    )
    use_demo: bool = Field(
        True, description="Use demo data when BACnet device unavailable"
    )
    bms_vendor: Optional[str] = Field(
        None,
        description="BMS vendor identifier (niagara, desigo, metasys, honeywell, schneider, trend, generic)",
    )


class DiscoverResponse(BaseModel):
    """Response from point discovery."""

    discovery_id: str = Field(..., description="Unique discovery identifier")
    points_count: int = Field(0, description="Number of points discovered")
    equipment_count: int = Field(0, description="Number of equipment entities identified")
    status: str = Field("", description="Discovery status")
    summary: Dict[str, Any] = Field(default_factory=dict, description="Classification summary")


class MappingSummary(BaseModel):
    """Summary of a discovery's equipment mappings."""

    discovery_id: str
    status: str
    equipment: List[Dict[str, Any]] = Field(default_factory=list)
    validation: Dict[str, Any] = Field(default_factory=dict)
    total_points: int = 0
    equipment_count: int = 0
    confidence_breakdown: Dict[str, int] = Field(default_factory=dict)
    needs_review: int = 0


class ApproveResponse(BaseModel):
    """Response from mapping approval."""

    success: bool
    equipment_created: int = 0
    message: str = ""


class CorrectRequest(BaseModel):
    """Request to correct a point classification."""

    point_id: str = Field(..., description="Original point name to correct")
    equipment_id: Optional[str] = Field(
        None, description="New equipment ID to assign point to"
    )
    point_type: Optional[str] = Field(
        None, description="Corrected point type (sensor, setpoint, command, status, alarm)"
    )
    equipment_type: Optional[str] = Field(
        None, description="Corrected equipment type (chiller, ahu, fcu, etc.)"
    )


class CorrectResponse(BaseModel):
    """Response from point correction."""

    success: bool
    corrections: List[str] = Field(default_factory=list)
    message: str = ""


class WorkflowState(str, Enum):
    """Discovery workflow states."""
    DISCOVERING = "discovering"
    CLASSIFYING = "classifying"
    PENDING_REVIEW = "pending_review"
    APPROVED = "approved"
    ACTIVATED = "activated"
    ERROR = "error"


# In-memory workflow state tracker
_workflow_states: Dict[str, Dict[str, Any]] = {}


# ---------------------------------------------------------------------------
# POST /api/niagara/discover-and-classify
# ---------------------------------------------------------------------------

@router.post("/discover-and-classify", response_model=DiscoverResponse)
async def discover_and_classify(request: DiscoverRequest):
    """
    Trigger point discovery and AI classification.

    Scans a BACnet device for all points, classifies them using
    Haystack/Brick ontology, groups into equipment, and stores
    results for review.

    Returns a discovery_id for tracking the workflow.
    """
    try:
        discovery_service = get_point_discovery_service()
        mapping_service = get_mapping_service()

        # Run discovery and classification
        result = await discovery_service.discover_and_classify(
            device_ip=request.device_ip,
            site_id=request.site_id,
            device_bacnet_id=request.device_bacnet_id,
            use_demo=request.use_demo,
            bms_vendor=request.bms_vendor,
        )

        if result.status == "error":
            raise HTTPException(
                status_code=500,
                detail=f"Discovery failed: {result.error}",
            )

        # Auto-generate mappings from classified points
        classifier = get_point_classifier()
        classified_points = classifier.classify_points(result.raw_points)
        mappings = mapping_service.map_points_to_equipment(
            classified_points, request.site_id
        )
        mapping_service.save_mappings(
            result.discovery_id, mappings, request.site_id
        )

        # Update workflow state
        _workflow_states[result.discovery_id] = {
            "state": WorkflowState.PENDING_REVIEW,
            "device_ip": request.device_ip,
            "site_id": request.site_id,
            "bms_vendor": request.bms_vendor,
            "points_count": len(result.classified_points),
            "equipment_count": len(result.summary.get("unique_equipment", {})),
        }

        return DiscoverResponse(
            discovery_id=result.discovery_id,
            points_count=len(result.classified_points),
            equipment_count=len(result.summary.get("unique_equipment", {})),
            status=WorkflowState.PENDING_REVIEW,
            summary=result.summary,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Discovery failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------------------------
# GET /api/niagara/mappings/{discovery_id}
# ---------------------------------------------------------------------------

@router.get("/mappings/{discovery_id}", response_model=MappingSummary)
async def get_mapping_summary(discovery_id: str):
    """
    Get mapping summary for a discovery.

    Returns equipment list with classified points, confidence scores,
    and validation results for FM team review.
    """
    mapping_service = get_mapping_service()
    mappings = mapping_service.get_mappings(discovery_id)

    if mappings is None:
        raise HTTPException(
            status_code=404,
            detail=f"Discovery {discovery_id} not found",
        )

    # Build equipment list
    equipment_list = []
    for eid, mapping in mappings.items():
        equipment_list.append(mapping.to_dict())

    # Run validation
    validation = mapping_service.validate_mappings(mappings)

    # Calculate confidence breakdown
    confidence_counts: Dict[str, int] = {}
    total_points = 0
    for mapping in mappings.values():
        for p in mapping.points:
            conf = p.get("confidence", "unknown")
            confidence_counts[conf] = confidence_counts.get(conf, 0) + 1
            total_points += 1

    needs_review = confidence_counts.get("low", 0) + confidence_counts.get("unknown", 0)

    # Get workflow state
    workflow = _workflow_states.get(discovery_id, {})
    state = workflow.get("state", WorkflowState.PENDING_REVIEW)

    return MappingSummary(
        discovery_id=discovery_id,
        status=state,
        equipment=equipment_list,
        validation=validation.to_dict(),
        total_points=total_points,
        equipment_count=len([e for e in equipment_list if e.get("equipment_id") != "UNASSIGNED"]),
        confidence_breakdown=confidence_counts,
        needs_review=needs_review,
    )


# ---------------------------------------------------------------------------
# POST /api/niagara/mappings/{discovery_id}/approve
# ---------------------------------------------------------------------------

@router.post("/mappings/{discovery_id}/approve", response_model=ApproveResponse)
async def approve_mapping(
    discovery_id: str,
    approved_by: str = Query("system", description="Name of the approver"),
):
    """
    Approve and activate a mapping.

    Creates equipment models from approved mappings and saves them
    to the buildings directory for device manager integration.
    """
    mapping_service = get_mapping_service()
    mappings = mapping_service.get_mappings(discovery_id)

    if mappings is None:
        raise HTTPException(
            status_code=404,
            detail=f"Discovery {discovery_id} not found",
        )

    try:
        result = mapping_service.approve_mappings(discovery_id, approved_by)

        if result.get("success"):
            # Update workflow state
            workflow_info = _workflow_states.get(discovery_id, {})
            _workflow_states[discovery_id] = {
                **workflow_info,
                "state": WorkflowState.ACTIVATED,
                "approved_by": approved_by,
            }

            # Check if any approved equipment is DALI type and auto-register
            site_id = workflow_info.get("site_id", "")
            _register_dali_if_discovered(discovery_id, site_id, mappings)

            return ApproveResponse(
                success=True,
                equipment_created=result.get("equipment_created", 0),
                message=f"Approved {result['equipment_created']} equipment. Models saved.",
            )
        else:
            return ApproveResponse(
                success=False,
                message=result.get("error", "Approval failed"),
            )

    except Exception as e:
        logger.error("Approval failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------------------------
# DALI auto-registration after approval
# ---------------------------------------------------------------------------

DALI_EQUIPMENT_TYPES = {"dali_controller", "luminaire", "light_sensor"}


def _register_dali_if_discovered(
    discovery_id: str,
    site_id: str,
    mappings: Dict[str, Any],
):
    """Check approved mappings for DALI equipment and auto-register with DALIService."""
    if not site_id:
        return

    has_dali = False
    for mapping in mappings.values():
        eq_type = ""
        if hasattr(mapping, "equipment_type"):
            eq_type = mapping.equipment_type or ""
        elif isinstance(mapping, dict):
            eq_type = mapping.get("equipment_type", "")
        if eq_type.lower() in DALI_EQUIPMENT_TYPES:
            has_dali = True
            break

    if not has_dali:
        return

    try:
        from app.services.dali_service import get_dali_service
        dali_service = get_dali_service()
        site_name = site_id  # Default; could resolve from building registry
        try:
            from app.database.repositories.building_repository import BuildingRepository
            building_repo = BuildingRepository()
            building = building_repo.get_by_id(site_id)
            if building:
                site_name = building.get("name", site_id)
        except Exception:
            pass

        dali_service.register_niagara_site(site_id, site_name)
        logger.info(
            "DALI lighting system discovered and registered for %s (discovery %s)",
            site_name, discovery_id,
        )
    except Exception as e:
        logger.error("Failed to auto-register DALI site %s: %s", site_id, e)


# ---------------------------------------------------------------------------
# POST /api/niagara/mappings/{discovery_id}/correct
# ---------------------------------------------------------------------------

@router.post("/mappings/{discovery_id}/correct", response_model=CorrectResponse)
async def correct_point_mapping(
    discovery_id: str,
    request: CorrectRequest,
):
    """
    Manually correct a point classification.

    Allows FM team to reassign points to different equipment,
    change point types, or update equipment type classifications.
    """
    mapping_service = get_mapping_service()
    mappings = mapping_service.get_mappings(discovery_id)

    if mappings is None:
        raise HTTPException(
            status_code=404,
            detail=f"Discovery {discovery_id} not found",
        )

    try:
        result = mapping_service.correct_point(
            discovery_id=discovery_id,
            point_name=request.point_id,
            new_equipment_id=request.equipment_id,
            new_point_type=request.point_type,
            new_equipment_type=request.equipment_type,
        )

        if result.get("success"):
            return CorrectResponse(
                success=True,
                corrections=result.get("corrections", []),
                message=f"Point '{request.point_id}' corrected successfully",
            )
        else:
            return CorrectResponse(
                success=False,
                message=result.get("error", "Correction failed"),
            )

    except Exception as e:
        logger.error("Correction failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))
