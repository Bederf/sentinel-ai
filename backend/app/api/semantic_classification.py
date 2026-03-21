"""API endpoints for semantic point classification.

Phase 162: Semantic Control Foundation — Plan 02.
Provides interactive classification of individual points and full equipment batches.
"""

from __future__ import annotations

import time

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.models.point_classification import BatchClassificationResult, PointClassification
from app.services.simbiot.classifiers.rule_based_classifier import RuleBasedPointClassifier
from app.services.simbiot.semantic_dictionary import SemanticDictionaryService

router = APIRouter(prefix="/api/semantic-classification", tags=["semantic_classification"])

# Module-level singletons (lazy-initialised to avoid import-time file I/O)
_classifier: RuleBasedPointClassifier | None = None
_dictionary_service: SemanticDictionaryService | None = None


def _get_classifier() -> RuleBasedPointClassifier:
    global _classifier
    if _classifier is None:
        _classifier = RuleBasedPointClassifier()
    return _classifier


def _get_dictionary_service() -> SemanticDictionaryService:
    global _dictionary_service
    if _dictionary_service is None:
        _dictionary_service = SemanticDictionaryService()
        _dictionary_service.load()
    return _dictionary_service


# ------------------------------------------------------------------
# Request / response models
# ------------------------------------------------------------------


class ClassifyPointRequest(BaseModel):
    """Request to classify a single point."""

    site_id: str
    equipment_id: str | None = None
    point_data: dict  # See BasePointClassifier.classify_point docstring for schema


class ClassifyPointResponse(BaseModel):
    """Response from classifying a single point."""

    classification: PointClassification
    processing_time_ms: int


class ClassifyEquipmentRequest(BaseModel):
    """Request to discover and classify all points for one equipment."""

    site_id: str
    equipment_id: str
    points: list[dict]  # Pre-supplied point list (BACnet adapter output)


class ClassifyEquipmentResponse(BaseModel):
    """Response from a batch equipment classification."""

    batch_result: BatchClassificationResult


# ------------------------------------------------------------------
# Endpoints
# ------------------------------------------------------------------


@router.post("/classify-point", response_model=ClassifyPointResponse)
async def classify_point(request: ClassifyPointRequest) -> ClassifyPointResponse:
    """Classify a single BACnet/DALI point interactively.

    The ``point_data`` dict must include at minimum:
    - ``point_id``: unique identifier
    - ``point_name``: raw point name (e.g. "SAT")
    - ``equipment_type``: e.g. "AHU"

    Optional fields improve accuracy:
    - ``haystack_id``, ``metadata``, ``current_value``, ``data_quality_score``
    """
    # Inject site_id into point_data if caller didn't include it
    point_data = dict(request.point_data)
    point_data.setdefault("site_id", request.site_id)
    if request.equipment_id:
        point_data.setdefault("device_id", request.equipment_id)

    t0 = int(time.monotonic() * 1000)
    try:
        classifier = _get_classifier()
        classification = await classifier.classify_point(point_data)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    elapsed = int(time.monotonic() * 1000) - t0

    return ClassifyPointResponse(classification=classification, processing_time_ms=elapsed)


@router.post("/classify-equipment", response_model=ClassifyEquipmentResponse)
async def classify_equipment(request: ClassifyEquipmentRequest) -> ClassifyEquipmentResponse:
    """Classify all points for a single equipment.

    The caller must supply a ``points`` list (each element follows the same
    schema as ``classify_point``'s ``point_data``). In a future plan this will
    be auto-discovered via the BMS adapter; for now the caller provides them.
    """
    if not request.points:
        raise HTTPException(status_code=422, detail="points list must not be empty")

    # Propagate site_id / equipment_id into each point record
    points = []
    for p in request.points:
        pd = dict(p)
        pd.setdefault("site_id", request.site_id)
        pd.setdefault("device_id", request.equipment_id)
        points.append(pd)

    try:
        classifier = _get_classifier()
        batch_result = await classifier.classify_equipment_batch(
            equipment_id=request.equipment_id,
            points=points,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    return ClassifyEquipmentResponse(batch_result=batch_result)


@router.get("/dictionary/tags", response_model=list[str])
async def list_tags() -> list[str]:
    """List all available semantic tag names from the loaded dictionary."""
    svc = _get_dictionary_service()
    return svc.list_tags()


@router.get("/dictionary/tag/{tag_name}")
async def get_tag(tag_name: str) -> dict:
    """Get full details for a specific semantic tag.

    Returns the SemanticTag as a plain dict so the API is schema-stable
    even as the Pydantic model evolves.
    """
    svc = _get_dictionary_service()
    tag = svc.get_tag(tag_name)
    if tag is None:
        raise HTTPException(status_code=404, detail=f"Tag '{tag_name}' not found")
    return tag.model_dump()
