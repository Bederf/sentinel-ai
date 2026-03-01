"""Dashboard Generator API endpoints.

Generates tailored dashboard configurations from discovered equipment:
  POST /api/dashboard-generator/generate/{site_id}   - Full dashboard config
  POST /api/dashboard-generator/preview/{site_id}     - Preview for wizard
  POST /api/dashboard-generator/classify              - Classify equipment list
  GET  /api/dashboard-generator/suggestions/{site_id} - Module suggestions

Phase 141-01: Core API routes.
"""

import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.services.auth_service import get_current_user
from app.models.user import User
from app.services.dashboard_generator import get_dashboard_generator

logger = logging.getLogger("sentinel.dashboard_generator")

router = APIRouter(prefix="/api/dashboard-generator", tags=["dashboard-generator"])


# --------------------------------------------------------------------------
# Request / Response models
# --------------------------------------------------------------------------


class EquipmentItem(BaseModel):
    """Equipment item for classification / generation."""

    code: str = Field(..., description="Equipment code (e.g., S002-CHILLER-B1-001)")
    type: Optional[str] = Field(None, description="Optional explicit type string")
    name: Optional[str] = Field(None, description="Equipment display name")
    status: Optional[str] = Field(None, description="Current status")
    health_score: Optional[int] = Field(None, description="Current health score (0-100)")


class GenerateRequest(BaseModel):
    """Optional body for generate endpoint."""

    equipment_list: Optional[List[EquipmentItem]] = Field(
        None, description="Equipment list. If omitted, loads from repository."
    )


class ClassifyRequest(BaseModel):
    """Body for classify endpoint."""

    equipment_list: List[EquipmentItem] = Field(..., description="Equipment list to classify")


# --------------------------------------------------------------------------
# Helper
# --------------------------------------------------------------------------


def _count_classes(classified: List[Dict[str, Any]]) -> Dict[str, int]:
    """Count equipment per class from classified list.

    Args:
        classified: List of dicts with 'equipment_class' key.

    Returns:
        Dict mapping class value to count.
    """
    counts: Dict[str, int] = {}
    for item in classified:
        cls_val = item.get("equipment_class", "unknown")
        if hasattr(cls_val, "value"):
            cls_val = cls_val.value
        counts[cls_val] = counts.get(cls_val, 0) + 1
    return counts


# --------------------------------------------------------------------------
# Endpoints
# --------------------------------------------------------------------------


@router.post("/generate/{site_id}")
async def generate_dashboard(
    site_id: str,
    body: Optional[GenerateRequest] = None,
    current_user: User = Depends(get_current_user),
):
    """Generate full dashboard configuration for a site.

    If equipment_list is provided in the body, uses that. Otherwise loads
    equipment from the repository.

    Returns complete config: cards, rules, health weights, module
    suggestions, and AI context.
    """
    try:
        generator = get_dashboard_generator()
        equipment_list = None
        if body and body.equipment_list:
            equipment_list = [item.model_dump(exclude_none=True) for item in body.equipment_list]

        result = generator.generate_for_site(site_id, equipment_list=equipment_list)
        return result
    except Exception as e:
        logger.error("Dashboard generation failed for %s: %s", site_id, e)
        raise HTTPException(status_code=500, detail="Dashboard generation failed") from e


@router.post("/preview/{site_id}")
async def preview_dashboard(
    site_id: str,
    body: GenerateRequest,
    current_user: User = Depends(get_current_user),
):
    """Preview dashboard for a given equipment list.

    Same as generate but adds ``preview: true`` to the response.
    Used by the BMS Connection Wizard to show what dashboards will look
    like before committing.
    """
    try:
        generator = get_dashboard_generator()
        equipment_list = None
        if body.equipment_list:
            equipment_list = [item.model_dump(exclude_none=True) for item in body.equipment_list]

        result = generator.generate_for_site(site_id, equipment_list=equipment_list)
        result["preview"] = True
        return result
    except Exception as e:
        logger.error("Dashboard preview failed for %s: %s", site_id, e)
        raise HTTPException(status_code=500, detail="Dashboard preview failed") from e


@router.post("/classify")
async def classify_equipment_list(
    body: ClassifyRequest,
    current_user: User = Depends(get_current_user),
):
    """Classify equipment list without full dashboard generation.

    Returns classified items with summary counts. Used by the wizard to
    show discovered equipment types.
    """
    try:
        generator = get_dashboard_generator()
        equipment_dicts = [item.model_dump(exclude_none=True) for item in body.equipment_list]
        classified = generator._classify_all(equipment_dicts)

        items = []
        for item in classified:
            items.append(
                {
                    "code": item.get("code", ""),
                    "type": item.get("type"),
                    "equipment_class": item["equipment_class"].value,
                }
            )

        return {
            "items": items,
            "summary": _count_classes(classified),
            "total": len(items),
        }
    except Exception as e:
        logger.error("Equipment classification failed: %s", e)
        raise HTTPException(status_code=500, detail="Classification failed") from e


@router.get("/suggestions/{site_id}")
async def get_suggestions(
    site_id: str,
    current_user: User = Depends(get_current_user),
):
    """Get module suggestions for a site.

    Runs full generation but returns only the suggestions array.
    Used for upgrade prompts in the UI.
    """
    try:
        generator = get_dashboard_generator()
        result = generator.generate_for_site(site_id)
        return {
            "site_id": site_id,
            "suggestions": result["module_suggestions"],
        }
    except Exception as e:
        logger.error("Module suggestions failed for %s: %s", site_id, e)
        raise HTTPException(status_code=500, detail="Failed to generate suggestions") from e
