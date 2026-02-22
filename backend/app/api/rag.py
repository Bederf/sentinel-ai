"""RAG API endpoints for documentation search and LLM explanations."""

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from typing import Optional, List, Dict
import logging

from app.services.rag_service import get_rag_service
from app.services.vector_db import get_vector_db_service
from app.services.ollama_client import get_ollama_client
from app.database.supabase_client import get_supabase_client

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/rag", tags=["rag"])


# Request/Response Models


class QueryRequest(BaseModel):
    query: str
    equipment_type: Optional[str] = None
    use_hybrid: bool = True
    use_local_llm: bool = True


class QueryResponse(BaseModel):
    query: str
    response: str
    context_used: str
    equipment_type: Optional[str]
    llm_used: str


class DocumentRequest(BaseModel):
    code: str
    title: str
    document_type: str
    equipment_type: str
    full_text: str
    source: str = "internal_procedure"
    manufacturer: Optional[str] = None
    model: Optional[str] = None
    summary: Optional[str] = None
    keywords: Optional[List[str]] = None
    failure_modes: Optional[List[str]] = None


class KnowledgeRequest(BaseModel):
    equipment_type: str
    knowledge_type: str
    title: str
    description: str
    code: Optional[str] = None
    component: Optional[str] = None
    manufacturer: Optional[str] = None
    model: Optional[str] = None
    symptoms: Optional[List[str]] = None
    possible_causes: Optional[List[str]] = None
    diagnostic_steps: Optional[List[str]] = None
    solution: Optional[str] = None
    parts_required: Optional[Dict] = None
    estimated_labor_hours: Optional[float] = None
    priority: Optional[str] = None


# Endpoints


@router.post("/query", response_model=QueryResponse)
async def query_rag(request: QueryRequest):
    """Query the RAG system with natural language."""
    client = get_supabase_client()
    rag_service = get_rag_service(client)

    result = await rag_service.query(
        query=request.query,
        equipment_type=request.equipment_type,
        use_hybrid=request.use_hybrid,
        use_local_llm=request.use_local_llm,
    )

    return QueryResponse(**result)


@router.get("/search")
async def search_documents(
    query: str = Query(..., description="Search query"),
    equipment_type: Optional[str] = Query(None, description="Filter by equipment type"),
    document_type: Optional[str] = Query(None, description="Filter by document type"),
    n_results: int = Query(5, ge=1, le=20, description="Number of results"),
    similarity_threshold: float = Query(0.5, ge=0.0, le=1.0, description="Minimum similarity score"),
):
    """Search documents by semantic similarity."""
    client = get_supabase_client()
    vector_db = get_vector_db_service(client)

    results = vector_db.search(
        query=query,
        n_results=n_results,
        equipment_type=equipment_type,
        document_type=document_type,
        similarity_threshold=similarity_threshold,
    )

    return {"query": query, "count": len(results), "results": results}


@router.get("/search/knowledge")
async def search_knowledge(
    query: str = Query(..., description="Search query"),
    equipment_type: Optional[str] = Query(None, description="Filter by equipment type"),
    knowledge_type: Optional[str] = Query(None, description="Filter by knowledge type"),
    n_results: int = Query(5, ge=1, le=20, description="Number of results"),
):
    """Search equipment knowledge base."""
    client = get_supabase_client()
    vector_db = get_vector_db_service(client)

    results = vector_db.search_knowledge(
        query=query, n_results=n_results, equipment_type=equipment_type, knowledge_type=knowledge_type
    )

    return {"query": query, "count": len(results), "results": results}


@router.get("/search/hybrid")
async def hybrid_search(
    query: str = Query(..., description="Search query"),
    equipment_type: Optional[str] = Query(None, description="Filter by equipment type"),
    n_results: int = Query(5, ge=1, le=20, description="Number of results"),
    keyword_weight: float = Query(0.3, ge=0.0, le=1.0, description="Weight for keyword matching"),
    semantic_weight: float = Query(0.7, ge=0.0, le=1.0, description="Weight for semantic matching"),
):
    """Hybrid search combining keyword and semantic matching."""
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
    equipment_id: str, include_context: bool = Query(True, description="Include RAG context in response")
):
    """Get natural language explanation for equipment risk prediction."""
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

    # Fallback demo prediction
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

    return explanation


@router.post("/documents")
async def add_document(request: DocumentRequest):
    """Add a new document to the RAG system."""
    client = get_supabase_client()
    vector_db = get_vector_db_service(client)

    # Add document
    doc = vector_db.add_document(
        code=request.code,
        title=request.title,
        document_type=request.document_type,
        equipment_type=request.equipment_type,
        full_text=request.full_text,
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
async def add_knowledge(request: KnowledgeRequest):
    """Add a new knowledge entry to the RAG system."""
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
    equipment_type: Optional[str] = Query(None, description="Filter by equipment type"),
    document_type: Optional[str] = Query(None, description="Filter by document type"),
    limit: int = Query(50, ge=1, le=200, description="Maximum number of results"),
):
    """List documents in the RAG system."""
    client = get_supabase_client()
    vector_db = get_vector_db_service(client)

    documents = vector_db.list_documents(equipment_type=equipment_type, document_type=document_type, limit=limit)

    return {"count": len(documents), "documents": documents}


@router.get("/documents/{document_id}")
async def get_document(document_id: str):
    """Get a specific document."""
    client = get_supabase_client()
    vector_db = get_vector_db_service(client)

    doc = vector_db.get_document(document_id)
    if not doc:
        raise HTTPException(status_code=404, detail=f"Document not found: {document_id}")

    return doc


@router.post("/documents/{document_id}/reindex")
async def reindex_document(document_id: str):
    """Re-chunk and re-embed a document."""
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
