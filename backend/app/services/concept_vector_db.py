"""Vector store for Concept-specific documents."""

import logging
import re
from datetime import UTC, datetime
from typing import Any

logger = logging.getLogger(__name__)
DOCUMENT_EMBED_BATCH_SIZE = 500


class ConceptVectorDBService:
    """Supabase pgvector wrapper for Concept RAG documents."""

    def __init__(self, supabase_client):
        self.client = supabase_client
        self._embedding_service = None

    @property
    def embedding_service(self):
        if self._embedding_service is None:
            from app.services.embedding_service import get_embedding_service

            self._embedding_service = get_embedding_service()
        return self._embedding_service

    def _resolve_site_uuid(self, site_id: str | None) -> str | None:
        if not site_id:
            return None
        if re.fullmatch(r"[0-9a-fA-F-]{36}", site_id):
            return site_id
        try:
            result = self.client.table("sites").select("id").eq("code", site_id).limit(1).execute()
            if result.data:
                return result.data[0]["id"]
        except Exception as exc:
            logger.warning("Failed to resolve site %s: %s", site_id, exc)
        return site_id

    def add_document(
        self,
        code: str,
        title: str,
        document_type: str,
        equipment_type: str,
        full_text: str,
        concept_document_id: str,
        concept_url: str,
        site_id: str | None = None,
        source: str = "concept_tsv",
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Insert a new Concept document."""
        resolved_site = self._resolve_site_uuid(site_id)
        result = (
            self.client.table("concept_documents")
            .insert(
                {
                    "code": code,
                    "title": title,
                    "document_type": document_type,
                    "equipment_type": equipment_type,
                    "full_text": full_text,
                    "concept_document_id": concept_document_id,
                    "concept_url": concept_url,
                    "site_id": resolved_site,
                    "source": source,
                    "metadata": metadata or {},
                    "indexing_status": "pending",
                }
            )
            .execute()
        )
        return result.data[0] if result.data else {}

    def chunk_and_embed_document(self, document_id: str, chunk_size: int = 500, chunk_overlap: int = 50) -> int:
        doc_resp = self.client.table("concept_documents").select("*").eq("id", document_id).single().execute()
        document = doc_resp.data
        if not document:
            logger.error("Concept document not found: %s", document_id)
            return 0

        self.client.table("concept_documents").update({"indexing_status": "chunking"}).eq("id", document_id).execute()

        text = document.get("full_text", "")
        if not text:
            logger.warning("Document %s has no text", document_id)
            return 0

        chunks = self._split_into_chunks(text, chunk_size, chunk_overlap)
        embeddings = self.embedding_service.embed_documents(
            [c["content"] for c in chunks],
            batch_size=DOCUMENT_EMBED_BATCH_SIZE,
        )

        chunk_records = []
        for i, (chunk, embedding) in enumerate(zip(chunks, embeddings, strict=False)):
            chunk_records.append(
                {
                    "document_id": document_id,
                    "chunk_index": i,
                    "content": chunk["content"],
                    "content_length": len(chunk["content"]),
                    "section_title": chunk.get("section"),
                    "page_number": chunk.get("page"),
                    "equipment_type": document["equipment_type"],
                    "document_type": document["document_type"],
                    "manufacturer": document.get("metadata", {}).get("manufacturer"),
                    "model": document.get("metadata", {}).get("model"),
                    "metadata": chunk.get("metadata", {}),
                    "embedding": embedding,
                }
            )

        if chunk_records:
            self.client.table("concept_document_chunks").insert(chunk_records).execute()

        self.client.table("concept_documents").update(
            {
                "indexing_status": "embedded",
                "indexed_at": datetime.now(UTC).isoformat(),
                "chunk_count": len(chunk_records),
            }
        ).eq("id", document_id).execute()

        logger.info("Ingested Concept document %s: %d chunks", document_id, len(chunk_records))
        return len(chunk_records)

    def _split_into_chunks(self, text: str, chunk_size: int, overlap: int) -> list[dict[str, Any]]:
        chunks = []
        words = text.split()
        i = 0
        while i < len(words):
            chunk_words = words[i : i + chunk_size]
            chunk_text = " ".join(chunk_words)
            section = None
            lines = chunk_text.split("\n")
            for line in lines[:3]:
                stripped = line.strip()
                if stripped.endswith(":") or (stripped.isupper() and len(stripped) > 3):
                    section = stripped
                    break
            chunks.append({"content": chunk_text, "section": section})
            i += chunk_size - overlap
        return chunks


def get_concept_vector_db_service(supabase_client):
    return ConceptVectorDBService(supabase_client)
