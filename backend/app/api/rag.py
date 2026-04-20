"""RAG API endpoints for documentation search and LLM explanations.

Security: All endpoints require authentication. Read operations require
AUDITOR (level 1), write operations require OPERATOR (level 2).
Health check endpoint is unauthenticated.
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from app.database.supabase_client import get_supabase_client
from app.models.auth import AuthContext
from app.security.pipeline import prompt_guard, require_role
from app.services.ollama_client import get_ollama_client
from app.services.rag_service import get_rag_service
from app.services.vector_db import get_vector_db_service
from app.utils.ai_provenance import get_claude_provenance

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/rag", tags=["rag"])


# Request/Response Models


class QueryRequest(BaseModel):
    query: str
    equipment_type: str | None = None
    use_hybrid: bool = True
    use_local_llm: bool = True


class QueryResponse(BaseModel):
    query: str
    response: str
    context_used: str
    equipment_type: str | None
    llm_used: str


class DocumentRequest(BaseModel):
    code: str
    title: str
    document_type: str
    equipment_type: str
    full_text: str
    site_id: str | None = None
    source: str = "internal_procedure"
    manufacturer: str | None = None
    model: str | None = None
    summary: str | None = None
    keywords: list[str] | None = None
    failure_modes: list[str] | None = None


class KnowledgeRequest(BaseModel):
    equipment_type: str
    knowledge_type: str
    title: str
    description: str
    code: str | None = None
    component: str | None = None
    manufacturer: str | None = None
    model: str | None = None
    symptoms: list[str] | None = None
    possible_causes: list[str] | None = None
    diagnostic_steps: list[str] | None = None
    solution: str | None = None
    parts_required: dict | None = None
    estimated_labor_hours: float | None = None
    priority: str | None = None


# Endpoints


@router.post("/query", tags=["llm_touching"])
async def query_rag(
    request: QueryRequest,
    auth: AuthContext = Depends(require_role(1)),
    guarded_query: str = Depends(prompt_guard(field="query", source="direct")),
):
    """Query the RAG system with natural language. Requires AUDITOR (level 1)."""
    client = get_supabase_client()
    rag_service = get_rag_service(client)

    result = await rag_service.query(
        query=guarded_query or request.query,
        equipment_type=request.equipment_type,
        use_hybrid=request.use_hybrid,
        use_local_llm=request.use_local_llm,
        user_role=auth.role.value if auth else None,
    )

    response = QueryResponse(**result)
    response_dict = response.model_dump()
    response_dict["ai_provenance"] = get_claude_provenance().model_dump()
    return response_dict


@router.get("/search")
async def search_documents(
    query: str = Query(..., description="Search query"),
    equipment_type: str | None = Query(None, description="Filter by equipment type"),
    document_type: str | None = Query(None, description="Filter by document type"),
    site_id: str | None = Query(None, description="Filter by site/building"),
    source: str | None = Query(None, description="Filter by document source"),
    n_results: int = Query(5, ge=1, le=20, description="Number of results"),
    similarity_threshold: float = Query(0.7, ge=0.0, le=1.0, description="Minimum similarity score"),
    auth: AuthContext = Depends(require_role(1)),
):
    """Search documents by semantic similarity. Requires AUDITOR (level 1)."""
    client = get_supabase_client()
    vector_db = get_vector_db_service(client)

    # If a source filter is provided, over-fetch and then filter locally so callers
    # still receive enough source-constrained hits.
    fetch_count = min(100, n_results * 5) if source else n_results
    results = vector_db.search(
        query=query,
        n_results=fetch_count,
        equipment_type=equipment_type,
        document_type=document_type,
        site_id=site_id,
        similarity_threshold=similarity_threshold,
    )

    if source:
        source_value = source.strip().lower()
        results = [row for row in results if str(row.get("source", "")).strip().lower() == source_value]

    results = results[:n_results]
    return {"query": query, "count": len(results), "results": results}


@router.get("/search/knowledge")
async def search_knowledge(
    query: str = Query(..., description="Search query"),
    equipment_type: str | None = Query(None, description="Filter by equipment type"),
    knowledge_type: str | None = Query(None, description="Filter by knowledge type"),
    n_results: int = Query(5, ge=1, le=20, description="Number of results"),
    auth: AuthContext = Depends(require_role(1)),
):
    """Search equipment knowledge base. Requires AUDITOR (level 1)."""
    client = get_supabase_client()
    vector_db = get_vector_db_service(client)

    results = vector_db.search_knowledge(
        query=query, n_results=n_results, equipment_type=equipment_type, knowledge_type=knowledge_type
    )

    return {"query": query, "count": len(results), "results": results}


@router.get("/search/hybrid")
async def hybrid_search(
    query: str = Query(..., description="Search query"),
    equipment_type: str | None = Query(None, description="Filter by equipment type"),
    n_results: int = Query(5, ge=1, le=20, description="Number of results"),
    keyword_weight: float = Query(0.3, ge=0.0, le=1.0, description="Weight for keyword matching"),
    semantic_weight: float = Query(0.7, ge=0.0, le=1.0, description="Weight for semantic matching"),
    auth: AuthContext = Depends(require_role(1)),
):
    """Hybrid search combining keyword and semantic matching. Requires AUDITOR (level 1)."""
    client = get_supabase_client()
    vector_db = get_vector_db_service(client)

    results = vector_db.hybrid_search(
        query=query,
        n_results=n_results,
        equipment_type=equipment_type,
        keyword_weight=keyword_weight,
        semantic_weight=semantic_weight,
    )

    return {"query": query, "count": len(results), "results": results}


@router.get("/explain/{equipment_id}")
async def explain_equipment_risk(
    equipment_id: str,
    include_context: bool = Query(True, description="Include RAG context in response"),
    auth: AuthContext = Depends(require_role(1)),
):
    """Get natural language explanation for equipment risk prediction. Requires AUDITOR (level 1)."""
    client = get_supabase_client()
    rag_service = get_rag_service(client)

    # Try to get prediction from various sources
    prediction = None

    # Check if we have equipment in the database
    try:
        equipment_result = client.table("equipment").select("*").eq("id", equipment_id).single().execute()
        if equipment_result.data:
            equipment = equipment_result.data
            prediction = {
                "equipment_type": equipment.get("equipment_type", "unknown"),
                "manufacturer": equipment.get("manufacturer"),
                "model": equipment.get("model"),
                "failure_probability_30d": 0.15,  # Demo value
                "predicted_failure": "General maintenance required",
                "anomaly_score": 0.002,
                "risk_level": "low",
                "contributing_factors": [],
            }
    except Exception as e:
        logger.warning(f"Equipment lookup failed: {e}")

    # Fallback seeded prediction
    if not prediction:
        prediction = {
            "equipment_type": "chiller",
            "manufacturer": "York",
            "model": "YCIV",
            "failure_probability_30d": 0.35,
            "predicted_failure": "Compressor bearing wear",
            "anomaly_score": 0.0045,
            "risk_level": "medium",
            "contributing_factors": [
                {"factor": "Runtime hours", "importance": 0.35},
                {"factor": "Vibration trend", "importance": 0.28},
                {"factor": "Oil analysis", "importance": 0.22},
                {"factor": "Age", "importance": 0.15},
            ],
        }

    explanation = await rag_service.explain_prediction(equipment_id, prediction)

    if not include_context:
        explanation.pop("context_sources", None)

    explanation["ai_provenance"] = get_claude_provenance().model_dump()
    return explanation


@router.post("/documents")
async def add_document(request: DocumentRequest, auth: AuthContext = Depends(require_role(2))):
    """Add a new document to the RAG system. Requires OPERATOR (level 2)."""
    client = get_supabase_client()
    vector_db = get_vector_db_service(client)

    # Add document
    doc = vector_db.add_document(
        code=request.code,
        title=request.title,
        document_type=request.document_type,
        equipment_type=request.equipment_type,
        full_text=request.full_text,
        site_id=request.site_id,
        source=request.source,
        manufacturer=request.manufacturer,
        model=request.model,
        summary=request.summary,
        keywords=request.keywords,
        failure_modes=request.failure_modes,
    )

    if not doc:
        raise HTTPException(status_code=500, detail="Failed to create document")

    # Chunk and embed
    chunk_count = vector_db.chunk_and_embed_document(doc["id"])

    return {
        "id": doc["id"],
        "code": doc["code"],
        "title": doc["title"],
        "chunk_count": chunk_count,
        "status": "indexed",
    }


@router.post("/knowledge")
async def add_knowledge(request: KnowledgeRequest, auth: AuthContext = Depends(require_role(2))):
    """Add a new knowledge entry to the RAG system. Requires OPERATOR (level 2)."""
    client = get_supabase_client()
    vector_db = get_vector_db_service(client)

    entry = vector_db.add_knowledge(
        equipment_type=request.equipment_type,
        knowledge_type=request.knowledge_type,
        title=request.title,
        description=request.description,
        code=request.code,
        component=request.component,
        manufacturer=request.manufacturer,
        model=request.model,
        symptoms=request.symptoms,
        possible_causes=request.possible_causes,
        diagnostic_steps=request.diagnostic_steps,
        solution=request.solution,
        parts_required=request.parts_required,
        estimated_labor_hours=request.estimated_labor_hours,
        priority=request.priority,
    )

    if not entry:
        raise HTTPException(status_code=500, detail="Failed to create knowledge entry")

    return {
        "id": entry["id"],
        "title": entry["title"],
        "equipment_type": entry["equipment_type"],
        "knowledge_type": entry["knowledge_type"],
        "status": "indexed",
    }


@router.get("/documents")
async def list_documents(
    equipment_type: str | None = Query(None, description="Filter by equipment type"),
    document_type: str | None = Query(None, description="Filter by document type"),
    limit: int = Query(50, ge=1, le=200, description="Maximum number of results"),
    auth: AuthContext = Depends(require_role(1)),
):
    """List documents in the RAG system. Requires AUDITOR (level 1)."""
    client = get_supabase_client()
    vector_db = get_vector_db_service(client)

    documents = vector_db.list_documents(equipment_type=equipment_type, document_type=document_type, limit=limit)

    return {"count": len(documents), "documents": documents}


@router.get("/documents/{document_id}")
async def get_document(document_id: str, auth: AuthContext = Depends(require_role(1))):
    """Get a specific document. Requires AUDITOR (level 1)."""
    client = get_supabase_client()
    vector_db = get_vector_db_service(client)

    doc = vector_db.get_document(document_id)
    if not doc:
        raise HTTPException(status_code=404, detail=f"Document not found: {document_id}")

    return doc


@router.post("/documents/{document_id}/reindex")
async def reindex_document(document_id: str, auth: AuthContext = Depends(require_role(2))):
    """Re-chunk and re-embed a document. Requires OPERATOR (level 2)."""
    client = get_supabase_client()
    vector_db = get_vector_db_service(client)

    # Delete existing chunks
    client.table("document_chunks").delete().eq("document_id", document_id).execute()

    # Re-chunk and embed
    chunk_count = vector_db.chunk_and_embed_document(document_id)

    return {"document_id": document_id, "chunk_count": chunk_count, "status": "reindexed"}


@router.get("/health")
async def rag_health():
    """Check RAG system health."""
    ollama = get_ollama_client()
    ollama_available = await ollama.is_available()

    # Check Supabase connection
    client = get_supabase_client()
    db_available = False
    document_count = 0
    chunk_count = 0
    knowledge_count = 0

    try:
        # Check documents table
        doc_result = client.table("documents").select("id", count="exact").execute()
        document_count = doc_result.count or 0

        # Check chunks table
        chunk_result = client.table("document_chunks").select("id", count="exact").execute()
        chunk_count = chunk_result.count or 0

        # Check knowledge table
        knowledge_result = client.table("equipment_knowledge").select("id", count="exact").execute()
        knowledge_count = knowledge_result.count or 0

        db_available = True
    except Exception as e:
        logger.error(f"Database health check failed: {e}")

    # Get Ollama models if available
    ollama_models = []
    if ollama_available:
        models = await ollama.list_models()
        ollama_models = [m.get("name", "unknown") for m in models]

    status = "healthy" if (ollama_available and db_available) else "degraded"
    if not db_available:
        status = "unhealthy"

    return {
        "status": status,
        "ollama": {
            "available": ollama_available,
            "url": ollama.base_url,
            "default_model": ollama.default_model,
            "models": ollama_models,
        },
        "database": {
            "available": db_available,
            "documents": document_count,
            "chunks": chunk_count,
            "knowledge_entries": knowledge_count,
        },
    }
