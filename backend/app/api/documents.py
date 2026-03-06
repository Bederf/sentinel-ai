"""Document upload and management API endpoints."""

import logging
import uuid
from typing import Optional

from fastapi import APIRouter, File, Form, HTTPException, UploadFile, Request
from slowapi import Limiter
from slowapi.util import get_remote_address

from app.database.supabase_client import get_supabase_client
from app.security.document_scanner import validate_and_scan_upload
from app.services.document_extractor import extract_text
from app.services.storage_service import get_storage_service
from app.services.vector_db import get_vector_db_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/documents", tags=["documents"])
limiter = Limiter(key_func=get_remote_address)


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
    title: Optional[str] = Form(None),
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
    if scan_result.detected_type == "PDF" and scan_result.extracted_text.strip():
        extracted_text = scan_result.extracted_text
        metadata = {"size_bytes": len(file_content)}
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


@router.get("/health")
async def health():
    """Health check for document service."""
    return {"status": "ok"}
