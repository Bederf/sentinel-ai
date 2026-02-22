"""Service record API endpoints for Phase 41 ML Engineer Knowledge Capture."""

from fastapi import APIRouter, Depends, HTTPException, status, File, UploadFile, Form
from typing import List, Optional, Dict, Any
from datetime import datetime

from app.models.service_record import (
    ServiceRecord,
    ServiceRecordDetail,
    ServiceRecordCreate,
    ServiceRecordUpdate,
    ServiceReading,
    ServiceAttachment,
    ServiceObservation,
    AttachmentType,
    ServiceStatus,
    ServiceType,
)
from app.database.repositories.service_record_repository import ServiceRecordRepository
from app.services.ml_template_service import MLTemplateService

router = APIRouter(prefix="/api/service-records", tags=["service-records"])


@router.post("", response_model=ServiceRecord, status_code=status.HTTP_201_CREATED)
async def create_service_record(
    record: ServiceRecordCreate,
    repository: ServiceRecordRepository = Depends(),
):
    """Create a new service record.

    Called when WO is assigned to technician. Notification sent via
    both email and Telegram. Data collection starts AFTER technician
    replies "done" to Telegram notification.

    Workflow:
    1. WO created → Email + Telegram notification sent
    2. Technician completes service work
    3. Technician replies "done" on Telegram
    4. Sequential prompts begin for ML data collection
    """
    import uuid

    # Generate unique code: SR-2026-XXXXXX
    code = f"SR-{datetime.now().year}-{str(uuid.uuid4())[:6].upper()}"

    service_record = await repository.create(
        {
            "code": code,
            "work_order_id": record.work_order_id,
            "equipment_id": record.equipment_id,
            "building_id": record.building_id,
            "service_type": record.service_type.value,
            "technician_id": record.technician_id,
            "technician_name": record.technician_name,
            "telegram_chat_id": record.telegram_chat_id,
            "status": ServiceStatus.NOTIFIED.value,
        }
    )

    return service_record


@router.get("/{record_id}", response_model=ServiceRecordDetail)
async def get_service_record(
    record_id: str,
    repository: ServiceRecordRepository = Depends(),
):
    """Get service record with all related data."""
    record = await repository.get_detail(record_id)
    if not record:
        raise HTTPException(status_code=404, detail="Service record not found")
    return record


@router.get("", response_model=List[ServiceRecord])
async def list_service_records(
    equipment_id: Optional[str] = None,
    technician_id: Optional[str] = None,
    status: Optional[ServiceStatus] = None,
    repository: ServiceRecordRepository = Depends(),
):
    """List service records with optional filtering."""
    filters = {}
    if equipment_id:
        filters["equipment_id"] = equipment_id
    if technician_id:
        filters["technician_id"] = technician_id
    if status:
        filters["status"] = status.value

    records = await repository.list(filters)
    return records


@router.get("/by-wo/{work_order_id}", response_model=List[ServiceRecord])
async def get_service_records_by_wo(
    work_order_id: str,
    repository: ServiceRecordRepository = Depends(),
):
    """Get all service records for a work order."""
    records = await repository.list({"work_order_id": work_order_id})
    return records


@router.patch("/{record_id}/status", response_model=ServiceRecord)
async def update_service_record_status(
    record_id: str,
    status_update: ServiceRecordUpdate,
    repository: ServiceRecordRepository = Depends(),
):
    """Update service record status."""
    record = await repository.update(record_id, status_update.dict(exclude_unset=True))
    if not record:
        raise HTTPException(status_code=404, detail="Service record not found")
    return record


@router.post("/{record_id}/reading", response_model=ServiceReading)
async def add_service_reading(
    record_id: str,
    reading: ServiceReading,
    repository: ServiceRecordRepository = Depends(),
):
    """Add a reading to service record."""
    # Verify record exists
    record = await repository.get_by_id(record_id)
    if not record:
        raise HTTPException(status_code=404, detail="Service record not found")

    # Add reading
    reading_data = await repository.add_reading(record_id, reading.dict())
    return reading_data


@router.post("/{record_id}/attachment", response_model=ServiceAttachment)
async def add_service_attachment(
    record_id: str,
    attachment_type: AttachmentType = Form(...),
    file: UploadFile = File(...),
    repository: ServiceRecordRepository = Depends(),
):
    """Upload and attach a file to service record."""
    # Verify record exists
    record = await repository.get_by_id(record_id)
    if not record:
        raise HTTPException(status_code=404, detail="Service record not found")

    # Upload to Supabase storage (placeholder - actual implementation)
    storage_path = f"service_records/{record_id}/{attachment_type.value}/{file.filename}"

    attachment_data = {
        "service_record_id": record_id,
        "attachment_type": attachment_type.value,
        "file_path": storage_path,
        "file_name": file.filename,
        "file_size_bytes": 0,  # Will be set after upload
        "mime_type": file.content_type,
    }

    attachment = await repository.add_attachment(attachment_data)
    return attachment


@router.post("/{record_id}/observation", response_model=ServiceObservation)
async def add_service_observation(
    record_id: str,
    note: str = Form(...),
    repository: ServiceRecordRepository = Depends(),
):
    """Add a text observation to service record."""
    observation_data = await repository.add_observation(record_id, {"observation_type": "text", "content": note})
    return observation_data


@router.get("/{record_id}/ml-status")
async def get_ml_collection_status(
    record_id: str,
    repository: ServiceRecordRepository = Depends(),
    template_service: MLTemplateService = Depends(),
):
    """Get ML data collection status (what items still needed)."""
    record = await repository.get_by_id(record_id)
    if not record:
        raise HTTPException(status_code=404, detail="Service record not found")

    # Get equipment type
    equipment = await repository.get_equipment_by_id(record["equipment_id"])
    if not equipment:
        raise HTTPException(status_code=404, detail="Equipment not found")

    # Get template
    template = template_service.get_template(equipment["type"], record["service_type"])

    # Get collected items
    collected_items = record.get("items_collected", [])

    # Determine what's still needed
    still_needed = []
    for item in template["required"]:
        if item not in collected_items:
            still_needed.append(item)

    # Next prompt
    next_prompt = None
    if still_needed:
        next_item = still_needed[0]
        next_prompt = template["prompts"].get(next_item)

    return {
        "service_record_id": record_id,
        "status": record["status"],
        "equipment_type": equipment["type"],
        "service_type": record["service_type"],
        "collected_items": collected_items,
        "still_needed": still_needed,
        "next_prompt": next_prompt,
        "progress": f"{len(collected_items)}/{len(template['required'])} required items",
    }


@router.post("/{record_id}/complete", response_model=Dict[str, Any])
async def complete_service_record(
    record_id: str,
    repository: ServiceRecordRepository = Depends(),
):
    """Mark service record as complete, trigger ML processing."""
    record = await repository.get_by_id(record_id)
    if not record:
        raise HTTPException(status_code=404, detail="Service record not found")

    # Update status
    await repository.update(record_id, {"status": ServiceStatus.COMPLETE.value})

    # TODO: Trigger ML processing pipeline
    # - OCR processing for service sheets
    # - Audio analysis for bearing detection
    # - Quality scoring

    return {
        "success": True,
        "service_record_id": record_id,
        "status": ServiceStatus.COMPLETE.value,
        "ml_processing_initiated": True,
    }


@router.get("/template/{equipment_type}/{service_type}")
async def get_ml_template(
    equipment_type: str,
    service_type: ServiceType,
    template_service: MLTemplateService = Depends(),
):
    """Get ML data collection template for equipment type and service."""
    template = template_service.get_template(equipment_type, service_type.value)
    if not template:
        raise HTTPException(status_code=404, detail="Template not found for equipment type and service")
    return template
