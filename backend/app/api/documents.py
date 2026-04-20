"""Document upload and management API endpoints."""

import hashlib
import logging
import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from slowapi import Limiter
from slowapi.util import get_remote_address

from app.database.repositories.user_site_access_repository import UserSiteAccessRepository
from app.database.supabase_client import get_supabase_client
from app.middleware.auth_middleware import require_auth
from app.models.auth import AuthContext, AuthLevel, SentinelRole
from app.security.document_scanner import validate_and_scan_upload
from app.services.asset_id_resolver import AssetIDResolver
from app.services.document_adapter_manual import ManualUploadAdapter
from app.services.document_extractor import extract_text
from app.services.llm_extraction_service import LLMExtractionService
from app.services.simbiot_service import simbiot_service
from app.services.site_document_storage_policy_service import get_site_document_storage_policy_service
from app.services.storage_service import get_storage_service
from app.services.vector_db import get_vector_db_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/documents", tags=["documents"])
limiter = Limiter(key_func=get_remote_address)

TECHNICIAN_DOCUMENT_NAMES = {
    "Roof Guarantee Certificate",
    "Warranties",
    "Air-Handler Unit (AHU) Major Service",
    "Air-Handler Unit (AHU) Minor Service",
    "Air-Handler Unit (AHU) Weekly Inspection",
    "Cooling Tower (CT) Major Service",
    "Cooling Tower (CT) Minor Service",
    "Cooling Tower (CT) Weekly Inspection",
    "Chiller Major Service",
    "Chiller Minor Service",
    "Chiller Weekly Inspection",
    "Kitchen Canopy Manual Service",
    "Building Management System (BMS) Service",
    "Distribution Boards (DB) Maintenance",
    "Transformer Service",
    "Fire Pump System Inspection",
    "Generator Major Service",
    "Generator Minor Service",
    "Generator Weekly Test",
    "Lift Service",
    "Lift test Report",
    "Escalator Monthly Service",
    "Solar PV Weekly Inspection",
    "UPS Weekly Inspection",
    "Waste Management Service",
    "Structural Integrity Report",
    "Certificate of Compliance (COC)",
    "Earth Leakage Test",
    "Plumbing Certificate of Compliance",
    "Electrical Equipment Certificates",
    "Smoke Detectors Service",
    "ASIB Certificate",
    "Portable Electrical Tool Inspection",
    "Potable Water Test Results",
    "Pressure Vessel Test Certificate",
    "Spillage Incidents Report",
    "Water Consumption Reports",
    "Building Inspection Report",
    "Occupational Hygiene Surveys",
    "Waste disposal certificates",
    "Audit Reports",
    "BSI Audit certificate",
}

TECHNICIAN_SUB_CLASSES = {
    "HVAC",
    "Electrical",
    "Fire",
    "Plumbing",
    "Lifts",
    "Building Fabric",
    "Power Factor Correction",
    "UPS",
    "Solar PV",
    "General Facilities",
}

TECHNICIAN_CATEGORIES = {
    "Preventive Maintenance",
    "Corrective Maintenance",
    "Compliance",
    "Safety",
    "Energy",
    "Water",
    "Testing & Commissioning",
    "Incident & Repair",
}

ALERT_OFFSETS_DAYS = (90, 30, 7)
PDF_LOW_TEXT_NATIVE_THRESHOLD = 200

# Retention defaults (policy scaffold). Can be moved to DB-backed policy table.
RETENTION_RULE_DAYS = {
    "cert_regulatory": 365,
    "warranty_default": 365,
    "inspection_weekly": 30,
    "inspection_monthly": 90,
    "inspection_periodic": 180,
    "inspection_annual": 365,
    "inspection_default": 180,
    "service_report_default": 365,
    "test_default": 365,
    "incident_default": 365,
    "consumption_report": 365,
    "survey_default": 365,
    "audit_default": 365,
    "plan_default": 3650,
    "calibration_default": 365,
}

DOCUMENT_RETENTION_KEY = {
    "Warranties": "warranty_default",
    "Roof Guarantee Certificate": "cert_regulatory",
    "Certificate of Compliance (COC)": "cert_regulatory",
    "Plumbing Certificate of Compliance": "cert_regulatory",
    "Electrical Equipment Certificates": "cert_regulatory",
    "ASIB Certificate": "cert_regulatory",
    "BSI Audit certificate": "cert_regulatory",
    "Audit Reports": "audit_default",
    "Water Consumption Reports": "consumption_report",
    "Spillage Incidents Report": "incident_default",
}


def _validate_iso_date(value: str, field_name: str) -> str:
    try:
        return datetime.strptime(value, "%Y-%m-%d").date().isoformat()
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Invalid {field_name}. Expected YYYY-MM-DD.") from exc


def _resolve_site_for_authenticated_upload(auth: AuthContext, site_id_override: str | None) -> str:
    """Resolve upload site from authenticated user context.

    Non-admin users are site-bound to their assigned sites. If exactly one site
    is assigned, it is auto-selected.
    """
    if auth.role == SentinelRole.ADMIN:
        if site_id_override:
            return site_id_override
        raise HTTPException(status_code=400, detail="site_id is required for admin uploads")

    if not auth.email:
        raise HTTPException(status_code=403, detail="Authenticated user email missing; cannot resolve site")

    repo = UserSiteAccessRepository()
    site_ids = repo.get_accessible_site_ids(auth.email, auth.role)
    if not site_ids:
        raise HTTPException(status_code=403, detail="No site allocation found for this user")

    if len(site_ids) == 1:
        return site_ids[0]

    if site_id_override and site_id_override in site_ids:
        return site_id_override

    raise HTTPException(
        status_code=400,
        detail="Multiple site allocations found; provide site_id explicitly",
    )


def _get_retention_key(document_name: str) -> str:
    if document_name in DOCUMENT_RETENTION_KEY:
        return DOCUMENT_RETENTION_KEY[document_name]
    return "service_report_default"


def _calculate_expiry_date(trigger_date_iso: str, retention_rule_key: str) -> str:
    from datetime import timedelta

    base = datetime.strptime(trigger_date_iso, "%Y-%m-%d").date()
    days = RETENTION_RULE_DAYS.get(retention_rule_key, 365)
    return (base + timedelta(days=days)).isoformat()


def _is_expired(expiry_date_iso: str) -> bool:
    expiry = datetime.strptime(expiry_date_iso, "%Y-%m-%d").date()
    return datetime.utcnow().date() > expiry


def _extract_keyword_map(keywords: list[str] | None) -> dict[str, str]:
    mapped: dict[str, str] = {}
    for item in keywords or []:
        if ":" not in item:
            continue
        key, value = item.split(":", 1)
        mapped[key] = value
    return mapped


def _resolve_site_code(site_id: str) -> str | None:
    try:
        client = get_supabase_client()
        res = client.table("sites").select("code").eq("id", site_id).single().execute()
        if res.data:
            return res.data.get("code")
    except Exception as exc:
        logger.debug("Failed to resolve site code for %s: %s", site_id, exc)
    return None


class DocumentUploadResponse:
    """Response model for document upload."""

    def __init__(
        self,
        document_id: str,
        title: str,
        chunk_count: int,
        indexing_status: str,
        storage_path: str,
    ):
        self.document_id = document_id
        self.title = title
        self.chunk_count = chunk_count
        self.indexing_status = indexing_status
        self.storage_path = storage_path

    def dict(self):
        return {
            "document_id": self.document_id,
            "title": self.title,
            "chunk_count": self.chunk_count,
            "indexing_status": self.indexing_status,
            "storage_path": self.storage_path,
        }


@router.post("/upload")
@limiter.limit("10/minute")
async def upload_document(
    request: Request,
    file: UploadFile = File(...),
    site_id: str = Form(...),
    title: str | None = Form(None),
    document_type: str = Form("building_manual"),
) -> dict:
    """Upload a building-scoped document for RAG indexing.

    Supported file types: PDF, DOCX, TXT (max 10MB each)

    The document is:
    1. Extracted to text
    2. Stored in Supabase Storage
    3. Indexed into the RAG system with building association
    4. Made available for semantic search when chatting about that building

    Args:
        file: Document file (PDF, DOCX, or TXT)
        site_id: Building UUID (user must have access to this building)
        title: Optional document title (defaults to filename)
        document_type: Document classification (default: "building_manual")

    Returns:
        Upload confirmation with document ID and chunk count

    Raises:
        HTTPException: 400 if file is invalid or oversized
        HTTPException: 401 if user lacks building access
        HTTPException: 500 if indexing fails
    """
    client = get_supabase_client()

    # 1. Validate building exists and user has access
    # TODO: Add user access check via user_site_access table
    try:
        building = client.table("sites").select("id, code").eq("id", site_id).single().execute()
        if not building.data:
            raise HTTPException(status_code=404, detail="Building not found")
    except Exception as e:
        logger.error(f"Failed to verify building: {e}")
        raise HTTPException(status_code=404, detail="Building not found")

    # 2. Security scan — validate file with the document scanner pipeline
    if not file.filename:
        raise HTTPException(status_code=400, detail="File must have a name")

    file_content = await file.read()
    # Reset file position for downstream consumers
    await file.seek(0)

    # Extract user info from request state (set by auth middleware)
    user_id = getattr(request.state, "user_id", "anonymous")
    user_role = getattr(request.state, "user_role", "operator")

    scan_result = await validate_and_scan_upload(
        file_content=file_content,
        filename=file.filename,
        user_id=user_id,
        user_role=user_role,
        site_id=site_id,
    )

    if not scan_result.allowed:
        raise HTTPException(status_code=400, detail=f"Upload rejected: {scan_result.rejection_reason}")

    if scan_result.trust_level == "QUARANTINED":
        raise HTTPException(
            status_code=400,
            detail="Upload quarantined: potential injection patterns detected in document",
        )

    # Use scanner-extracted text for PDFs, fall back to extractor for other types
    if (
        scan_result.detected_type == "PDF"
        and scan_result.extracted_text.strip()
        and len(scan_result.extracted_text.strip()) >= PDF_LOW_TEXT_NATIVE_THRESHOLD
    ):
        extracted_text = scan_result.extracted_text
        metadata = {
            "size_bytes": len(file_content),
            "file_type": ".pdf",
            "extraction_mode": "native_scanner",
            "native_text_length": len(scan_result.extracted_text.strip()),
            "ocr_used": False,
        }
    else:
        # 3. Extract text (for non-PDF types or when scanner text is empty)
        try:
            extracted_text, metadata = await extract_text(file)

            # Validate extracted text is not empty
            if not extracted_text.strip():
                raise HTTPException(status_code=400, detail="File appears to be empty or unreadable")

        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        except ImportError as e:
            logger.error(f"Missing dependency: {e}")
            raise HTTPException(status_code=500, detail="File extraction not available")
        except Exception as e:
            logger.error(f"Error extracting text: {e}")
            raise HTTPException(status_code=400, detail="Failed to extract text from file")

    # 4. Upload to storage
    storage_service = get_storage_service(client)
    try:
        storage_path = await storage_service.upload_document(site_id, file)
    except Exception as e:
        logger.error(f"Storage upload failed: {e}")
        raise HTTPException(status_code=500, detail="Failed to upload file to storage")

    # 5. Create document record in database
    document_id = str(uuid.uuid4())
    doc_title = title or file.filename
    document_code = f"USER-DOC-{site_id[:8]}-{uuid.uuid4().hex[:8]}".upper()

    try:
        doc_record = (
            client.table("documents")
            .insert(
                {
                    "id": document_id,
                    "code": document_code,
                    "title": doc_title,
                    "document_type": document_type,
                    "equipment_type": "general",  # User-uploaded docs are general
                    "source": "user_upload",
                    "source_file_path": storage_path,
                    "full_text": extracted_text,
                    "summary": extracted_text[:500],  # First 500 chars as summary
                    "file_size_bytes": metadata["size_bytes"],
                    "site_id": site_id,
                    "indexing_status": "pending",
                }
            )
            .execute()
        )

        if not doc_record.data:
            raise Exception("Failed to create document record")

    except Exception as e:
        logger.error(f"Failed to create document record: {e}")
        raise HTTPException(status_code=500, detail="Failed to save document metadata")

    # 6. Chunk and embed document
    vector_db = get_vector_db_service(client)
    try:
        chunk_count = vector_db.chunk_and_embed_markdown(
            document_id=document_id,
            doc_title=doc_title,
            doc_type=document_type,
            max_chunk_size=800,
        )

        # Update chunks with site_id
        client.table("document_chunks").update({"site_id": site_id}).eq("document_id", document_id).execute()

        logger.info(f"Successfully indexed document {document_id} with {chunk_count} chunks for building {site_id}")

    except Exception as e:
        logger.error(f"Error indexing document: {e}")
        # Document record was created but indexing failed
        # Update status so we can retry later
        client.table("documents").update({"indexing_status": "failed"}).eq("id", document_id).execute()
        raise HTTPException(status_code=500, detail="Document uploaded but indexing failed. Please try again.")

    # 7. Return success response
    response = DocumentUploadResponse(
        document_id=document_id,
        title=doc_title,
        chunk_count=chunk_count,
        indexing_status="embedded",
        storage_path=storage_path,
    )

    return response.dict()


@router.post("/technician/upload")
@limiter.limit("10/minute")
async def upload_technician_document(
    request: Request,
    file: UploadFile = File(...),
    equipment_id: str = Form(...),
    document_name: str = Form(...),
    document_sub_class: str = Form(...),
    category_discipline: str = Form(...),
    document_creation_date: str = Form(...),
    trigger_date: str = Form(...),
    title: str | None = Form(None),
    site_id: str | None = Form(None),
    auth: AuthContext = Depends(require_auth(AuthLevel.AUTHENTICATED)),
) -> dict:
    """Technician-focused document upload with strict metadata validation.

    Identity and site binding are derived from login context for non-admin users.
    """
    if document_name not in TECHNICIAN_DOCUMENT_NAMES:
        raise HTTPException(status_code=400, detail="Invalid technician document type")
    if document_sub_class not in TECHNICIAN_SUB_CLASSES:
        raise HTTPException(status_code=400, detail="Invalid document_sub_class")
    if category_discipline not in TECHNICIAN_CATEGORIES:
        raise HTTPException(status_code=400, detail="Invalid category_discipline")

    creation_date = _validate_iso_date(document_creation_date, "document_creation_date")
    trigger = _validate_iso_date(trigger_date, "trigger_date")
    if trigger < creation_date:
        raise HTTPException(status_code=400, detail="trigger_date cannot be before document_creation_date")

    resolved_site_id = _resolve_site_for_authenticated_upload(auth, site_id_override=site_id)
    resolved_site_code = _resolve_site_code(resolved_site_id)
    policy = get_site_document_storage_policy_service().resolve(resolved_site_id, resolved_site_code)
    storage_mode = policy.get("mode", "local")
    dual_write = bool(policy.get("dual_write", False))
    fallback_to_local = bool(policy.get("fallback_to_local", True))
    retention_rule_key = _get_retention_key(document_name)
    expiry_date = _calculate_expiry_date(trigger, retention_rule_key)
    is_expired = _is_expired(expiry_date)
    alert_offsets = ",".join(str(v) for v in ALERT_OFFSETS_DAYS)

    # Duplicate checks before upload.
    file_content = await file.read()
    await file.seek(0)
    file_hash = hashlib.sha256(file_content).hexdigest()

    client = get_supabase_client()
    existing_docs = (
        client.table("documents")
        .select("id, keywords")
        .eq("site_id", resolved_site_id)
        .eq("source", "technician_notes")
        .limit(500)
        .execute()
    )

    for rec in existing_docs.data or []:
        keyword_map = _extract_keyword_map(rec.get("keywords"))
        if keyword_map.get("file_hash") == file_hash:
            raise HTTPException(
                status_code=409,
                detail="Duplicate file detected (same file hash already uploaded for this site)",
            )
        if (
            keyword_map.get("technician_document_name") == document_name
            and keyword_map.get("document_creation_date") == creation_date
            and keyword_map.get("equipment_id") == equipment_id
        ):
            raise HTTPException(
                status_code=409,
                detail=(
                    "Potential duplicate detected (same document type, creation date, and equipment). "
                    "Use versioning or replace flow."
                ),
            )

    # Reuse existing ingestion pipeline and/or route to site-network storage.
    response: dict
    local_written = False

    if storage_mode in {"local", "cloud"} or dual_write:
        response = await upload_document(
            request=request,
            file=file,
            site_id=resolved_site_id,
            title=title or document_name,
            document_type="service_report",
        )
        local_written = True
    else:
        response = {
            "document_id": None,
            "title": title or document_name,
            "chunk_count": 0,
            "indexing_status": "site_network_only",
            "storage_path": None,
        }

    if storage_mode == "site_network":
        try:
            remote_result = await simbiot_service.upload_document(
                file_bytes=file_content,
                filename=file.filename or f"{document_name}.bin",
                site_id=resolved_site_id,
                metadata={
                    "document_name": document_name,
                    "document_sub_class": document_sub_class,
                    "category_discipline": category_discipline,
                    "equipment_id": equipment_id,
                    "document_creation_date": creation_date,
                    "trigger_date": trigger,
                    "retention_rule_key": retention_rule_key,
                    "expiry_date": expiry_date,
                    "uploaded_by_user_id": auth.user_id,
                },
            )
            response["remote_storage"] = {"mode": "site_network", "status": "uploaded", "result": remote_result}
        except Exception as exc:
            logger.warning("Site-network upload failed for %s: %s", resolved_site_id, exc)
            if not local_written and fallback_to_local:
                response = await upload_document(
                    request=request,
                    file=file,
                    site_id=resolved_site_id,
                    title=title or document_name,
                    document_type="service_report",
                )
                local_written = True
                response["remote_storage"] = {
                    "mode": "site_network",
                    "status": "failed_fallback_to_local",
                    "error": str(exc),
                }
            else:
                raise HTTPException(status_code=502, detail=f"Site-network upload failed: {exc}")

    if local_written and response.get("document_id"):
        try:
            client.table("documents").update(
                {
                    "source": "technician_notes",
                    "keywords": [
                        f"technician_document_name:{document_name}",
                        f"document_sub_class:{document_sub_class}",
                        f"category_discipline:{category_discipline}",
                        f"equipment_id:{equipment_id}",
                        f"document_creation_date:{creation_date}",
                        f"trigger_date:{trigger}",
                        f"retention_rule_key:{retention_rule_key}",
                        f"expiry_date:{expiry_date}",
                        f"is_expired:{str(is_expired).lower()}",
                        f"alert_offsets_days:{alert_offsets}",
                        f"file_hash:{file_hash}",
                        f"uploaded_by_user_id:{auth.user_id}",
                        f"site_id:{resolved_site_id}",
                    ],
                }
            ).eq("id", response["document_id"]).execute()
        except Exception as exc:
            logger.warning("Technician metadata update failed for %s: %s", response.get("document_id"), exc)

    # Wire ManualUploadAdapter — creates DocumentRecord with source_system="manual_upload"
    # B1 fix: _upsert gracefully no-ops if migration not applied (no 500)
    # B4/B5 fix: _upsert only writes source_system, source_document_id, site_id
    # existing upload_technician_document endpoint continues to own source/document_type
    # Phase 181-03: LLM extraction BEFORE _upsert — equipment_description must be in DB
    # before AssetIDResolver.resolve_and_apply() reads it (ordering constraint)
    if response.get("document_id"):
        try:
            # Phase 181-03: Extract equipment_description via LLM BEFORE _upsert.
            # upload_document() stored full_text in DB but didn't return it.
            # Fetch it now so we can run LLM extraction before the adapter flow.
            equipment_description: str | None = None
            try:
                doc_row = client.table("documents").select("full_text").eq("id", response["document_id"]).execute()
                raw_text = ""
                if doc_row.data:
                    raw_text = doc_row.data[0].get("full_text") or ""
                if raw_text and len(raw_text.strip()) > 50:
                    extractor = LLMExtractionService(db=client, site_id=resolved_site_id)
                    equipment_description = await extractor.extract_equipment_description(raw_text)
                    logger.info(
                        "[upload] LLM extracted equipment_description for doc=%s: %.50s",
                        response["document_id"],
                        equipment_description or "(empty)",
                    )
                else:
                    logger.debug(
                        "[upload] skipping LLM extraction for doc=%s: text_length=%d",
                        response["document_id"],
                        len(raw_text),
                    )
            except Exception as exc:
                # Graceful degradation: LLM extraction failure must not fail the upload
                logger.warning(
                    "[upload] LLM extraction failed for document_id=%s: %s",
                    response.get("document_id"),
                    exc,
                )

            adapter = ManualUploadAdapter()
            form_data = {
                "equipment_id": equipment_id,
                "document_name": document_name,
                "document_sub_class": document_sub_class,
                "category_discipline": category_discipline,
                "document_creation_date": creation_date,
                "trigger_date": trigger,
                "title": title,
                "uploaded_by_user_id": auth.user_id,
            }
            doc_record = adapter.normalise_upload(response, form_data, resolved_site_id, equipment_description)
            await adapter._upsert(doc_record)  # fire-and-forget; no-op on migration-missing

            # Wire AssetIDResolver — resolve equipment_description → asset_id
            # Only invoke when equipment_description is non-empty (API sources set this;
            # manual uploads have it as None and equipment_id is already validated canonical form)
            if doc_record.equipment_description:
                try:
                    resolver = AssetIDResolver(db=adapter.db, site_id=resolved_site_id)
                    result = await resolver.resolve_and_apply(response["document_id"])
                    if result.needs_review:
                        logger.info(
                            "[upload] asset resolution needs review: doc=%s asset=%s method=%s confidence=%.2f",
                            response["document_id"],
                            result.asset_id,
                            result.method.value,
                            result.confidence,
                        )
                except Exception as exc:
                    logger.warning(
                        "[upload] asset resolution failed for document_id=%s: %s",
                        response.get("document_id"),
                        exc,
                    )
                    # Never fail the upload because of resolution failure
        except Exception as exc:
            logger.warning(
                "[manual_upload] _upsert failed for document_id=%s: %s",
                response.get("document_id"),
                exc,
            )

    return {
        **response,
        "site_id": resolved_site_id,
        "uploaded_by_user_id": auth.user_id,
        "document_name": document_name,
        "document_sub_class": document_sub_class,
        "category_discipline": category_discipline,
        "document_creation_date": creation_date,
        "trigger_date": trigger,
        "retention_rule_key": retention_rule_key,
        "expiry_date": expiry_date,
        "is_expired": is_expired,
        "alert_offsets_days": list(ALERT_OFFSETS_DAYS),
        "storage_mode": storage_mode,
    }


@router.get("/health")
async def health():
    """Health check for document service."""
    return {"status": "ok"}
