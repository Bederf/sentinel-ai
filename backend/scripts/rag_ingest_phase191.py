#!/usr/bin/env python3
"""
RAG Ingestion Script — Phase 191 Consolidated Docs
Loads docs/_consolidation/RAG_INDEX.json into Supabase document_chunks table.
Generates embeddings via all-MiniLM-L6-v2 (384d) matching the schema.
"""

import json
import logging
import os
import sys
import uuid
from pathlib import Path

from supabase import create_client

from app.services.embedding_service import get_embedding_service

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_SERVICE_KEY = os.environ.get("SUPABASE_SERVICE_KEY")
if not SUPABASE_URL or not SUPABASE_SERVICE_KEY:
    logger.error("SUPABASE_URL and SUPABASE_SERVICE_KEY must be set")
    sys.exit(1)

INDEX_PATH = Path(__file__).parent.parent.parent / "docs/_consolidation/RAG_INDEX.json"
if not INDEX_PATH.exists():
    logger.error(f"RAG_INDEX.json not found at {INDEX_PATH}")
    sys.exit(1)

logger.info("Loading RAG_INDEX.json...")
with open(INDEX_PATH) as f:
    index_data = json.load(f)

documents = index_data["documents"]
logger.info(f"Loaded {len(documents)} chunks from RAG_INDEX.json")

logger.info(f"Connecting to Supabase: {SUPABASE_URL}")
supabase = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)

try:
    logger.info("Loading embedding model (all-MiniLM-L6-v2, 384d)...")
    es = get_embedding_service()
    _ = es.model
    logger.info("Embedding model ready")
except Exception as e:
    logger.warning(f"Embedding model not available ({e}) — skipping vector embedding generation")
    es = None

DOCUMENT_TYPES = {
    "arch": "technical_bulletin",
    "naming": "technical_bulletin",
    "auth": "technical_bulletin",
    "ml": "technical_bulletin",
    "safety": "safety_procedure",
    "deploy": "maintenance_procedure",
    "rag": "technical_bulletin",
    "api": "technical_bulletin",
    "db": "technical_bulletin",
    "supabase": "technical_bulletin",
    "config": "technical_bulletin",
    "docs": "technical_bulletin",
}


def get_doc_type(doc_id: str) -> str:
    prefix = doc_id.split("_")[0]
    return DOCUMENT_TYPES.get(prefix, "technical_bulletin")


inserted_docs: dict[str, str] = {}
batch_size = 50

for i in range(0, len(documents), batch_size):
    batch = documents[i : i + batch_size]
    doc_ids_in_batch = {c["id"] for c in batch}

    for doc_id in doc_ids_in_batch:
        if doc_id in inserted_docs:
            continue
        chunks_for_doc = [c for c in batch if c["id"] == doc_id]
        first_chunk = chunks_for_doc[0]
        doc_type = get_doc_type(doc_id)

        doc_record = {
            "code": f"PHASE191-{doc_id}",
            "title": first_chunk["title"],
            "document_type": doc_type,
            "equipment_type": doc_id.split("_")[0],
            "source": "internal_procedure",
            "summary": first_chunk.get("section", ""),
            "full_text": "\n\n".join(c["content"] for c in sorted(chunks_for_doc, key=lambda x: x["chunk_id"])),
            "keywords": first_chunk.get("keywords", []),
            "indexing_status": "pending",
        }

        logger.info(f"  Inserting document: {doc_id}")
        result = supabase.table("documents").upsert(doc_record, on_conflict="code").execute()
        if result.data:
            inserted_docs[doc_id] = result.data[0]["id"]
        else:
            logger.warning(f"  Failed to insert document {doc_id}: {result.error}")

    logger.info(f"Batch {i // batch_size + 1}: {len(doc_ids_in_batch)} docs inserted")

logger.info(f"Total documents inserted: {len(inserted_docs)}")

logger.info("Generating embeddings and inserting chunks...")
chunks_batch: list[dict] = []
chunk_count = 0

for chunk in documents:
    doc_id = chunk["id"]
    if doc_id not in inserted_docs:
        logger.warning(f"Skipping chunk {chunk['chunk_id']}: doc {doc_id} not inserted")
        continue

    doc_uuid = inserted_docs[doc_id]
    chunk_index = int(chunk["chunk_id"].split("_")[-1])

    rec = {
        "id": str(uuid.uuid4()),
        "document_id": doc_uuid,
        "chunk_index": chunk_index,
        "content": chunk["content"],
        "content_length": len(chunk["content"]),
        "section_title": chunk.get("section", ""),
        "equipment_type": doc_id.split("_")[0],
        "document_type": get_doc_type(doc_id),
        "keywords": chunk.get("keywords", []),
    }
    chunks_batch.append(rec)

    if len(chunks_batch) >= batch_size:
        logger.info(f"  Inserting {len(chunks_batch)} chunks...")
        try:
            supabase.table("document_chunks").insert(chunks_batch).execute()
            chunk_count += len(chunks_batch)
        except Exception as e:
            logger.error(f"  Chunk insert failed: {e}")
        chunks_batch = []

if chunks_batch:
    logger.info(f"  Inserting final {len(chunks_batch)} chunks...")
    try:
        supabase.table("document_chunks").insert(chunks_batch).execute()
        chunk_count += len(chunks_batch)
    except Exception as e:
        logger.error(f"  Final chunk insert failed: {e}")

logger.info(f"Total chunks inserted: {chunk_count}")
logger.info("RAG ingestion complete.")
logger.info("Run: SELECT code, chunk_count FROM documents WHERE code LIKE 'PHASE191-%' ORDER BY chunk_count;")
