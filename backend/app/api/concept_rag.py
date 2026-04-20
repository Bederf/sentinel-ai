"""Concept document ingestion endpoints."""


from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.database.supabase_client import get_supabase_client
from app.models.auth import AuthContext
from app.security.pipeline import require_role
from app.services.concept_vector_db import get_concept_vector_db_service

router = APIRouter(prefix="/api/concept-rag", tags=["concept-rag"])


class ConceptDocumentRequest(BaseModel):
    code: str
    title: str
    document_type: str
    equipment_type: str
    full_text: str
    concept_document_id: str
    concept_url: str
    site_id: str | None = None
    source: str | None = "concept_tsv"
    metadata: dict[str, str] | None = None


@router.post("/documents")
def ingest_concept_document(
    request: ConceptDocumentRequest,
    auth: AuthContext = Depends(require_role(2)),
):
    client = get_supabase_client()
    if not client:
        raise HTTPException(status_code=500, detail="Concept DB unavailable")

    vector_db = get_concept_vector_db_service(client)
    document = vector_db.add_document(
        code=request.code,
        title=request.title,
        document_type=request.document_type,
        equipment_type=request.equipment_type,
        full_text=request.full_text,
        concept_document_id=request.concept_document_id,
        concept_url=request.concept_url,
        site_id=request.site_id,
        source=request.source or "concept_tsv",
        metadata=request.metadata,
    )
    if not document:
        raise HTTPException(status_code=500, detail="Failed to create Concept document")

    chunk_count = vector_db.chunk_and_embed_document(document["id"])

    return {
        "id": document["id"],
        "code": document["code"],
        "chunk_count": chunk_count,
        "status": "embedded" if chunk_count > 0 else "pending",
    }
