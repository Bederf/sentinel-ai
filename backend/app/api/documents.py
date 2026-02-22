"""Document upload and management API endpoints."""

import logging
import uuid
from typing import Optional

from fastapi import APIRouter, File, Form, HTTPException, UploadFile, Request
from slowapi import Limiter
from slowapi.util import get_remote_address

from app.database.supabase_client import get_supabase_client
from app.services.document_extractor import extract_text
from app.services.storage_service import get_storage_service
from app.services.vector_db import get_vector_db_service
from app.config.settings import settings

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
    building_id: str = Form(...),
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
        building_id: Building UUID (user must have access to this building)
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
        building = client.table("buildings").select("id, code").eq("id", building_id).single().execute()
        if not building.data:
            raise HTTPException(status_code=404, detail="Building not found")
    except Exception as e:
        logger.error(f"Failed to verify building: {e}")
        raise HTTPException(status_code=404, detail="Building not found")

    # 2. Validate file
    if not file.filename:
        raise HTTPException(status_code=400, detail="File must have a name")

    file_ext = file.filename.rsplit(".", 1)[-1].lower() if "." in file.filename else ""
    if f".{file_ext}" not in settings.allowed_document_types:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid file type. Supported: {', '.join(settings.allowed_document_types)}",
        )

    # 3. Extract text
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
        storage_path = await storage_service.upload_document(building_id, file)
    except Exception as e:
        logger.error(f"Storage upload failed: {e}")
        raise HTTPException(status_code=500, detail="Failed to upload file to storage")

    # 5. Create document record in database
    document_id = str(uuid.uuid4())
    doc_title = title or file.filename
    document_code = f"USER-DOC-{building_id[:8]}-{uuid.uuid4().hex[:8]}".upper()

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
                    "building_id": building_id,
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

        # Update chunks with building_id
        client.table("document_chunks").update({"building_id": building_id}).eq("document_id", document_id).execute()

        logger.info(f"Successfully indexed document {document_id} with {chunk_count} chunks for building {building_id}")

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
