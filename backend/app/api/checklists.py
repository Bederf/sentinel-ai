"""
Checklist Generation API - REST endpoints for OEM-specific checklist generation

Phase 66: OEM-Specific Checklist Generation
Task 66-03: Checklist Generation API Endpoint

Provides endpoints for:
- Generating OEM-specific inspection checklists for equipment
- Retrieving generated checklist templates
- Querying templates by equipment type, manufacturer, and model
- OEM template lookup with cascade matching
"""

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Path, Query, status
from pydantic import BaseModel, Field

from app.database.repositories.checklist_template_repository import (
    get_checklist_template_repository,
)
from app.models.user import User
from app.services.auth_service import get_current_user
from app.services.checklist_generator_service import (
    get_checklist_generator_service,
)

router = APIRouter(prefix="/api/checklists", tags=["checklists"])


# ============================================================================
# Request/Response Models
# ============================================================================


class ChecklistGenerateRequest(BaseModel):
    """Request to generate OEM-specific checklists for equipment."""

    equipment_code: str = Field(..., description="Equipment code (e.g., 'S002-CHILLER-B1-001')")
    force: bool = Field(False, description="Force regeneration even if templates already exist")


class ChecklistItemResponse(BaseModel):
    """Single checklist item in a template."""

    item_id: str
    question: str
    item_type: str
    category: str
    required: bool
    tolerance_min: float | None = None
    tolerance_max: float | None = None
    unit: str | None = None


class ChecklistTemplateResponse(BaseModel):
    """Complete checklist template."""

    id: str
    template_name: str
    equipment_type: str
    inspection_type: str
    manufacturer: str | None = None
    model: str | None = None
    frequency_type: str | None = None
    estimated_duration_minutes: int | None = None
    checklist_items: list[ChecklistItemResponse] = []
    required_tools: list[str] | None = None
    required_skills: list[str] | None = None
    safety_requirements: list[str] | None = None
    ppe_required: list[str] | None = None
    version: int = 1
    is_active: bool = True


class ChecklistGenerateResponse(BaseModel):
    """Response from checklist generation request."""

    status: str = Field("success", description="Status of generation: success, error, skipped")
    equipment_code: str
    generated_templates: list[dict[str, Any]] = Field(
        default_factory=list, description="List of generated templates with id and template_name"
    )
    message: str | None = None


class ChecklistOemLookupResponse(BaseModel):
    """Response from OEM template lookup."""

    template: ChecklistTemplateResponse | None = None
    message: str | None = None


# ============================================================================
# Checklist Generation Endpoints
# ============================================================================


@router.post(
    "/generate",
    response_model=ChecklistGenerateResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Generate OEM-specific checklists",
    description="Generate 3 checklist variants (routine, preventive, annual) for equipment with OEM metadata",
)
async def generate_checklists_for_equipment(
    request: ChecklistGenerateRequest, current_user: User = Depends(get_current_user)
):
    """Generate OEM-specific inspection and maintenance checklists.

    Generates 3 template variants per equipment:
    - routine_inspection (weekly/monthly)
    - preventive_maintenance (quarterly)
    - annual_major_service (annual)

    Returns generated template IDs and metadata.
    """
    generator = get_checklist_generator_service()

    try:
        # Generate checklists using equipment code
        templates = await generator.generate_for_equipment(request.equipment_code, force_regenerate=request.force)

        # Format response
        generated = []
        for template in templates:
            generated.append(
                {
                    "id": template.get("id", "unknown"),
                    "template_name": template.get("template_name", "Unknown"),
                    "inspection_type": template.get("inspection_type", "unknown"),
                }
            )

        return ChecklistGenerateResponse(
            status="success",
            equipment_code=request.equipment_code,
            generated_templates=generated,
            message=f"Generated {len(generated)} checklist(s) for {request.equipment_code}",
        )

    except ValueError as e:
        # Equipment not found or missing OEM metadata
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        # Log error without exposing stack trace
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to generate checklists: {e!s}"
        )


# ============================================================================
# Template Retrieval Endpoints
# ============================================================================


@router.get(
    "/{template_id}",
    response_model=ChecklistTemplateResponse,
    summary="Get checklist template",
    description="Retrieve a complete checklist template by ID",
)
async def get_checklist_template(
    template_id: str = Path(..., description="Template UUID"), current_user: User = Depends(get_current_user)
):
    """Retrieve a complete checklist template by ID."""
    repo = get_checklist_template_repository()

    template = repo.get_template(template_id)
    if not template:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Template {template_id} not found")

    return ChecklistTemplateResponse(**template)


@router.get(
    "/equipment/{equipment_type}",
    response_model=list[ChecklistTemplateResponse],
    summary="List templates for equipment type",
    description="Get all active checklist templates for a specific equipment type",
)
async def list_templates_for_equipment_type(
    equipment_type: str = Path(..., description="Equipment type (e.g., chiller, ahu)"),
    is_active: bool = Query(True, description="Filter by active status"),
    current_user: User = Depends(get_current_user),
):
    """List all templates for a specific equipment type."""
    repo = get_checklist_template_repository()

    templates = repo.get_templates_for_equipment_type(equipment_type, is_active=is_active)
    return [ChecklistTemplateResponse(**t) for t in templates]


@router.get(
    "/oem/lookup",
    response_model=ChecklistOemLookupResponse,
    summary="Lookup OEM-specific template",
    description="Find the most specific OEM template matching equipment specs (model → manufacturer → generic)",
)
async def lookup_oem_template(
    equipment_type: str = Query(..., description="Equipment type (e.g., chiller)"),
    manufacturer: str = Query(..., description="Manufacturer name (e.g., Carrier)"),
    model: str | None = Query(None, description="Model identifier (e.g., 30HXC0800)"),
    inspection_type: str | None = Query(None, description="Inspection type (routine, preventive, annual)"),
    current_user: User = Depends(get_current_user),
):
    """Lookup OEM-specific template with cascade matching.

    Searches for templates in this priority order:
    1. Exact model + manufacturer match
    2. Manufacturer-only match
    3. Generic template for equipment type

    Returns the most specific available template or null if none found.
    """
    repo = get_checklist_template_repository()

    template = repo.get_oem_template(
        equipment_type=equipment_type, manufacturer=manufacturer, model=model, inspection_type=inspection_type
    )

    if template:
        return ChecklistOemLookupResponse(
            template=ChecklistTemplateResponse(**template), message="Found OEM-specific template"
        )
    else:
        return ChecklistOemLookupResponse(
            template=None, message=f"No template found for {manufacturer} {model or ''} {equipment_type}"
        )


@router.get(
    "",
    response_model=list[ChecklistTemplateResponse],
    summary="List all templates",
    description="Get all active checklist templates",
)
async def list_all_templates(
    is_active: bool = Query(True, description="Filter by active status"), current_user: User = Depends(get_current_user)
):
    """List all available checklist templates."""
    repo = get_checklist_template_repository()

    templates = repo.list_all_templates(is_active=is_active)
    return [ChecklistTemplateResponse(**t) for t in templates]
