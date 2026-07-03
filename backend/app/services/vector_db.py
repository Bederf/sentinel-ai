"""Vector database service using Supabase + pgvector."""

import logging
import re
import uuid
from collections import OrderedDict
from datetime import UTC, datetime
from typing import Any, Literal

logger = logging.getLogger(__name__)
DOCUMENT_EMBED_BATCH_SIZE = 500


class VectorDBService:
    """Supabase pgvector wrapper for RAG operations."""

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
        """Resolve a site code like ``site-001`` to the canonical UUID."""
        if not site_id:
            return None
        if re.fullmatch(r"[0-9a-fA-F-]{36}", site_id):
            return site_id
        try:
            result = self.client.table("sites").select("id").eq("code", site_id).limit(1).execute()
            if result.data:
                return result.data[0]["id"]
        except Exception as exc:
            logger.warning("Failed to resolve site code %s to UUID: %s", site_id, exc)
        return site_id

    def _validate_doc_class(self, doc_class: str) -> Literal["system", "site"]:
        """Force callers to declare whether chunks are platform docs or site docs."""
        if doc_class not in {"system", "site"}:
            raise ValueError("doc_class must be either 'system' or 'site'")
        return doc_class  # type: ignore[return-value]

    def add_document(
        self,
        code: str,
        title: str,
        document_type: str,
        equipment_type: str,
        full_text: str,
        site_id: str | None = None,
        source: str = "internal_procedure",
        manufacturer: str | None = None,
        model: str | None = None,
        summary: str | None = None,
        keywords: list[str] | None = None,
        failure_modes: list[str] | None = None,
    ) -> dict[str, Any]:
        """Add a document to the RAG system."""
        resolved_site_id = self._resolve_site_uuid(site_id)
        result = (
            self.client.table("documents")
            .insert(
                {
                    "code": code,
                    "title": title,
                    "document_type": document_type,
                    "equipment_type": equipment_type,
                    "full_text": full_text,
                    "site_id": resolved_site_id,
                    "source": source,
                    "manufacturer": manufacturer,
                    "model": model,
                    "summary": summary,
                    "keywords": keywords,
                    "failure_modes": failure_modes,
                    "indexing_status": "pending",
                }
            )
            .execute()
        )
        return result.data[0] if result.data else None

    def chunk_and_embed_document(
        self,
        document_id: str,
        *,
        doc_class: Literal["system", "site"],
        chunk_size: int = 500,
        chunk_overlap: int = 50,
    ) -> int:
        """Chunk document text and generate embeddings."""
        doc_class = self._validate_doc_class(doc_class)
        # Get document
        doc = self.client.table("documents").select("*").eq("id", document_id).single().execute()
        document = doc.data

        if not document:
            logger.error(f"Document not found: {document_id}")
            return 0

        self.client.table("documents").update({"indexing_status": "embedding"}).eq("id", document_id).execute()

        # Split into chunks
        text = document.get("full_text", "")
        if not text:
            logger.warning(f"Document {document_id} has no full_text")
            return 0

        chunks = self._split_into_chunks(text, chunk_size, chunk_overlap)

        # Generate embeddings
        embeddings = self.embedding_service.embed_documents(
            [c["content"] for c in chunks],
            batch_size=DOCUMENT_EMBED_BATCH_SIZE,
        )

        # Insert chunks with embeddings
        chunk_records = []
        for i, (chunk, embedding) in enumerate(zip(chunks, embeddings, strict=False)):
            chunk_records.append(
                self._build_chunk_record(
                    document=document,
                    document_id=document_id,
                    chunk_index=i,
                    chunk=chunk,
                    embedding=embedding,
                    doc_class=doc_class,
                )
            )

        if chunk_records:
            self.client.table("document_chunks").insert(chunk_records).execute()

        # Update document status
        self.client.table("documents").update(
            {
                "indexing_status": "complete",
                "indexed_at": datetime.now(UTC).isoformat(),
                "chunk_count": len(chunk_records),
            }
        ).eq("id", document_id).execute()

        logger.info(f"Indexed document {document_id}: {len(chunk_records)} chunks")
        return len(chunk_records)

    def _split_into_chunks(self, text: str, chunk_size: int = 500, overlap: int = 50) -> list[dict[str, Any]]:
        """Split text into overlapping chunks."""
        chunks = []
        words = text.split()

        if not words:
            return chunks

        i = 0
        while i < len(words):
            chunk_words = words[i : i + chunk_size]
            chunk_text = " ".join(chunk_words)

            # Try to detect section headers
            section = None
            lines = chunk_text.split("\n")
            for line in lines[:3]:  # Check first 3 lines
                stripped = line.strip()
                if stripped.endswith(":") or (stripped.isupper() and len(stripped) > 3):
                    section = stripped
                    break

            chunks.append({"content": chunk_text, "section": section, "page_number": None})

            i += chunk_size - overlap

        return chunks

    def _split_markdown_into_chunks(
        self, text: str, max_chunk_size: int = 800, overlap_ratio: float = 0.15
    ) -> list[dict[str, Any]]:
        """Split markdown text into section-aware chunks with heading paths.

        Inspired by aimthelaw's legal document chunking:
        - Respects heading boundaries (never splits mid-section)
        - Tracks heading hierarchy for each chunk
        - Uses paragraph-level splitting within large sections
        - Local overlap only within the same section
        """
        chunks = []
        lines = text.split("\n")

        # Build sections from heading structure
        sections = []
        current_headings = {}  # level -> heading text
        current_lines = []
        current_level = 0

        for line in lines:
            heading_match = re.match(r"^(#{1,4})\s+(.+)$", line)
            if heading_match:
                # Save accumulated content as a section
                if current_lines:
                    content = "\n".join(current_lines).strip()
                    if content:
                        heading_path = [
                            current_headings[k] for k in sorted(current_headings.keys()) if k <= current_level
                        ]
                        sections.append(
                            {
                                "content": content,
                                "heading_path": list(heading_path),
                                "section_title": current_headings.get(current_level, ""),
                                "level": current_level,
                            }
                        )
                    current_lines = []

                level = len(heading_match.group(1))
                heading_text = heading_match.group(2).strip()
                current_level = level
                current_headings[level] = heading_text
                # Clear deeper headings
                for k in list(current_headings.keys()):
                    if k > level:
                        del current_headings[k]
            else:
                current_lines.append(line)

        # Don't forget the last section
        if current_lines:
            content = "\n".join(current_lines).strip()
            if content:
                heading_path = [current_headings[k] for k in sorted(current_headings.keys()) if k <= current_level]
                sections.append(
                    {
                        "content": content,
                        "heading_path": list(heading_path),
                        "section_title": current_headings.get(current_level, ""),
                        "level": current_level,
                    }
                )

        # Process each section into chunks
        overlap_chars = int(max_chunk_size * overlap_ratio)

        for section in sections:
            section_text = section["content"]

            if len(section_text) <= max_chunk_size:
                # Section fits in one chunk
                if section_text.strip():
                    chunks.append(
                        {
                            "content": section_text.strip(),
                            "section": section["section_title"],
                            "heading_path": section["heading_path"],
                        }
                    )
            else:
                # Split large sections at paragraph boundaries
                paragraphs = re.split(r"\n\s*\n", section_text)
                current_chunk = ""

                for para in paragraphs:
                    para = para.strip()
                    if not para:
                        continue

                    if len(current_chunk) + len(para) + 2 <= max_chunk_size:
                        current_chunk = (current_chunk + "\n\n" + para).strip()
                    else:
                        # Save current chunk
                        if current_chunk.strip():
                            chunks.append(
                                {
                                    "content": current_chunk.strip(),
                                    "section": section["section_title"],
                                    "heading_path": section["heading_path"],
                                }
                            )
                        # Start new chunk with overlap from end of previous
                        if overlap_chars > 0 and current_chunk:
                            overlap_text = current_chunk[-overlap_chars:]
                            current_chunk = overlap_text + "\n\n" + para
                        else:
                            current_chunk = para

                        # Handle paragraphs larger than max_chunk_size
                        if len(current_chunk) > max_chunk_size:
                            # Split by sentences
                            sentences = re.split(r"(?<=[.!?])\s+", current_chunk)
                            current_chunk = ""
                            for sentence in sentences:
                                if len(current_chunk) + len(sentence) + 1 <= max_chunk_size:
                                    current_chunk = (current_chunk + " " + sentence).strip()
                                else:
                                    if current_chunk.strip():
                                        chunks.append(
                                            {
                                                "content": current_chunk.strip(),
                                                "section": section["section_title"],
                                                "heading_path": section["heading_path"],
                                            }
                                        )
                                    current_chunk = sentence

                # Don't forget remaining content
                if current_chunk.strip():
                    chunks.append(
                        {
                            "content": current_chunk.strip(),
                            "section": section["section_title"],
                            "heading_path": section["heading_path"],
                        }
                    )

        return chunks

    def chunk_and_embed_markdown(
        self,
        document_id: str,
        *,
        doc_class: Literal["system", "site"],
        doc_title: str = "",
        doc_type: str = "",
        max_chunk_size: int = 800,
    ) -> int:
        """Chunk markdown document with section awareness and context-enhanced embeddings.

        Uses heading-aware chunking and prepends context headers to improve
        embedding quality (document title + heading path + type).
        Original content is stored without the header.
        """
        doc_class = self._validate_doc_class(doc_class)
        doc = self.client.table("documents").select("*").eq("id", document_id).single().execute()
        document = doc.data
        if not document:
            logger.error(f"Document not found: {document_id}")
            return 0

        self.client.table("documents").update({"indexing_status": "embedding"}).eq("id", document_id).execute()

        text = document.get("full_text", "")
        if not text:
            return 0

        title = doc_title or document.get("title", "")
        dtype = doc_type or document.get("document_type", "")

        # Use markdown-aware chunking
        chunks = self._split_markdown_into_chunks(text, max_chunk_size)

        if not chunks:
            return 0

        # Build context-enhanced texts for embedding (not for storage)
        embed_texts = []
        for chunk in chunks:
            heading_path = " > ".join(chunk.get("heading_path", []))
            context_header = f"Document: {title}\n"
            if heading_path:
                context_header += f"Section: {heading_path}\n"
            if dtype:
                context_header += f"Type: {dtype}\n"
            context_header += "---\n"
            embed_texts.append(context_header + chunk["content"])

        # Generate embeddings from context-enhanced text
        embeddings = self._embed_chunk_texts(
            [{"document_id": document_id, "text": text} for text in embed_texts],
        )

        # Store chunks with original content (no context header)
        chunk_records = []
        for i, (chunk, embedding) in enumerate(zip(chunks, embeddings, strict=False)):
            chunk_records.append(
                self._build_chunk_record(
                    document=document,
                    document_id=document_id,
                    chunk_index=i,
                    chunk={
                        **chunk,
                        "metadata": {
                            "heading_path": chunk.get("heading_path", []),
                            "context_enhanced": True,
                        },
                    },
                    embedding=embedding,
                    doc_class=doc_class,
                )
            )

        if chunk_records:
            # Insert in batches to avoid payload limits
            batch_size = 50
            for j in range(0, len(chunk_records), batch_size):
                batch = chunk_records[j : j + batch_size]
                self.client.table("document_chunks").insert(batch).execute()

        self.client.table("documents").update(
            {"indexing_status": "complete", "indexed_at": "now()", "chunk_count": len(chunk_records)}
        ).eq("id", document_id).execute()

        logger.info(f"Indexed markdown document {document_id}: {len(chunk_records)} chunks (section-aware)")
        return len(chunk_records)

    def _build_chunk_record(
        self,
        *,
        document: dict[str, Any],
        document_id: str,
        chunk_index: int,
        chunk: dict[str, Any],
        embedding: Any,
        doc_class: Literal["system", "site"],
    ) -> dict[str, Any]:
        """Build a chunk record with stable citation grounding metadata."""
        doc_class = self._validate_doc_class(doc_class)
        chunk_uuid = str(uuid.uuid4())
        section_title = chunk.get("section")
        page_number = chunk.get("page_number")
        metadata = self._build_grounding_metadata(
            document=document,
            document_id=document_id,
            chunk_id=chunk_uuid,
            chunk_index=chunk_index,
            section_title=section_title,
            page_number=page_number,
            existing_metadata=chunk.get("metadata") if isinstance(chunk.get("metadata"), dict) else None,
        )

        return {
            "id": chunk_uuid,
            "document_id": document_id,
            "chunk_index": chunk_index,
            "content": chunk["content"],
            "content_length": len(chunk["content"]),
            "section_title": section_title,
            "page_number": page_number,
            "embedding": embedding,
            "equipment_type": document["equipment_type"],
            "document_type": document["document_type"],
            "site_id": document.get("site_id"),
            "manufacturer": document.get("manufacturer"),
            "model": document.get("model"),
            "keywords": document.get("keywords"),
            "failure_modes": document.get("failure_modes"),
            "metadata": metadata,
            "doc_class": doc_class,
        }

    def _embed_chunk_texts(self, chunk_inputs: list[dict[str, str]]) -> list[list[float]]:
        """Embed chunk texts, optionally grouping by document for contextualized embeddings."""
        if not chunk_inputs:
            return []

        from app.config.settings import settings

        if not settings.embedding_contextualized_enabled:
            return self.embedding_service.embed_documents(
                [item["text"] for item in chunk_inputs],
                batch_size=DOCUMENT_EMBED_BATCH_SIZE,
            )

        grouped: OrderedDict[str, list[str]] = OrderedDict()
        for item in chunk_inputs:
            grouped.setdefault(item["document_id"], []).append(item["text"])

        grouped_embeddings = self.embedding_service.embed_contextualized_documents(list(grouped.values()))
        if len(grouped_embeddings) != len(grouped):
            raise ValueError("Contextualized embedding group count mismatch")

        per_document: dict[str, list[list[float]]] = {
            document_id: list(embeddings) for document_id, embeddings in zip(grouped.keys(), grouped_embeddings)
        }
        for document_id, texts in grouped.items():
            if len(per_document[document_id]) != len(texts):
                raise ValueError(f"Contextualized embedding chunk count mismatch for document {document_id}")

        offsets = dict.fromkeys(grouped, 0)
        flattened: list[list[float]] = []
        for item in chunk_inputs:
            document_id = item["document_id"]
            offset = offsets[document_id]
            flattened.append(per_document[document_id][offset])
            offsets[document_id] = offset + 1

        if len(flattened) != len(chunk_inputs):
            raise ValueError("Contextualized embedding flatten mismatch")
        return flattened

    def _build_grounding_metadata(
        self,
        *,
        document: dict[str, Any],
        document_id: str,
        chunk_id: str,
        chunk_index: int,
        section_title: str | None,
        page_number: int | None,
        existing_metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        base_metadata: dict[str, Any] = dict(existing_metadata or {})
        base_metadata["grounding"] = {
            "document_id": document_id,
            "chunk_id": chunk_id,
            "chunk_index": chunk_index,
            "document_title": document.get("title"),
            "section_title": section_title,
            "page_number": page_number,
            "source": document.get("source"),
        }
        return base_metadata

    def search(
        self,
        query: str,
        n_results: int = 5,
        equipment_type: str | None = None,
        document_type: str | None = None,
        manufacturer: str | None = None,
        site_id: str | None = None,
        similarity_threshold: float = 0.5,
        doc_class: str | None = None,
    ) -> list[dict[str, Any]]:
        """Semantic search for relevant document chunks.

        Args:
            query: Search query text
            n_results: Number of results to return
            equipment_type: Optional filter by equipment type
            document_type: Optional filter by document type
            manufacturer: Optional filter by manufacturer
            site_id: Optional filter by building (includes system docs if None)
            similarity_threshold: Minimum similarity score
            doc_class: Optional filter: "system" or "site"

        Returns:
            List of matching document chunks
        """
        # Resolve site code to UUID if needed
        resolved_site_id = self._resolve_site_uuid(site_id)

        # Generate query embedding
        query_embedding = self.embedding_service.embed_query(query)

        # Call Supabase RPC function
        result = self.client.rpc(
            "match_document_chunks",
            {
                "query_embedding": query_embedding,
                "match_count": n_results,
                "filter_equipment_type": equipment_type,
                "filter_document_type": document_type,
                "filter_manufacturer": manufacturer,
                "filter_site_id": resolved_site_id,
                "similarity_threshold": similarity_threshold,
                "filter_doc_class": doc_class,
            },
        ).execute()

        return self._attach_grounding_metadata(result.data if result.data else [])

    def search_knowledge(
        self,
        query: str,
        n_results: int = 5,
        equipment_type: str | None = None,
        knowledge_type: str | None = None,
        similarity_threshold: float = 0.5,
    ) -> list[dict[str, Any]]:
        """Search equipment knowledge base."""
        query_embedding = self.embedding_service.embed_query(query)
        result = self.client.rpc(
            "match_equipment_knowledge",
            {
                "query_embedding": query_embedding,
                "match_count": n_results,
                "filter_equipment_type": equipment_type,
                "filter_knowledge_type": knowledge_type,
                "similarity_threshold": similarity_threshold,
            },
        ).execute()

        return result.data if result.data else []

    async def hybrid_search(
        self,
        query: str,
        n_results: int = 5,
        equipment_type: str | None = None,
        site_id: str | None = None,
        keyword_weight: float = 0.3,
        semantic_weight: float = 0.7,
        use_hyde: bool = False,
        doc_class: str | None = None,
    ) -> list[dict[str, Any]]:
        """Hybrid search combining keyword and semantic matching.

        Args:
            query: Search query text
            n_results: Number of results to return
            equipment_type: Optional filter by equipment type
            site_id: Optional filter by building (includes system docs if None)
            keyword_weight: Weight for keyword matching (0-1)
            semantic_weight: Weight for semantic matching (0-1)
            use_hyde: Use Hypothetical Document Embedding — generates a hypothetical
                answer with Haiku, embeds that instead of the raw query to resolve
                vocabulary mismatches between informal queries and formal documents.
                Keyword component always uses the original query.
            doc_class: Optional filter: "system" or "site"

        Returns:
            List of matching document chunks with hybrid scores
        """
        if use_hyde:
            query_embedding = await self._hyde_embed(query)
        else:
            query_embedding = self.embedding_service.embed_query(query)

        resolved_site_id = self._resolve_site_uuid(site_id)

        result = self.client.rpc(
            "hybrid_search_chunks",
            {
                "query_text": query,
                "query_embedding": query_embedding,
                "match_count": n_results,
                "filter_equipment_type": equipment_type,
                "filter_site_id": resolved_site_id,
                "keyword_weight": keyword_weight,
                "semantic_weight": semantic_weight,
                "filter_doc_class": doc_class,
            },
        ).execute()

        return self._attach_grounding_metadata(result.data if result.data else [])

    async def _hyde_embed(self, query: str) -> list[float]:
        """Generate hypothetical answer and embed it for better retrieval.

        Uses Haiku to produce a brief hypothetical answer, then embeds that
        instead of the raw query. Resolves vocabulary mismatch between informal
        user queries and formally-written documentation.
        """
        from app.services.model_gateway import model_gateway

        system = (
            "You are a technical documentation writer. Write one brief hypothetical "
            "answer (2-4 sentences) that a BMS expert might include in official "
            "SENTINEL documentation. Focus on technical terms and concrete details. "
            "Do not speculate. Do not prefix your answer."
        )
        try:
            hypothetical = await model_gateway.call(
                task_class="extraction",
                messages=[{"role": "user", "content": query}],
                system=system,
                max_tokens=256,
            )
        except Exception as e:
            logger.warning("HyDE generation failed, falling back to raw query embed: %s", e)
            return self.embedding_service.embed_query(query)

        return self.embedding_service.embed_document(hypothetical)

    def add_knowledge(
        self,
        equipment_type: str,
        knowledge_type: str,
        title: str,
        description: str,
        code: str | None = None,
        component: str | None = None,
        manufacturer: str | None = None,
        model: str | None = None,
        symptoms: list[str] | None = None,
        possible_causes: list[str] | None = None,
        diagnostic_steps: list[str] | None = None,
        solution: str | None = None,
        parts_required: dict | None = None,
        estimated_labor_hours: float | None = None,
        priority: str | None = None,
    ) -> dict[str, Any]:
        """Add a knowledge entry with auto-generated embedding."""
        # Generate embedding from title + description
        embed_text = f"{title}. {description}"
        if symptoms:
            embed_text += f" Symptoms: {', '.join(symptoms)}"
        if code:
            embed_text += f" Fault code: {code}"

        embedding = self.embedding_service.embed_document(embed_text)

        result = (
            self.client.table("equipment_knowledge")
            .insert(
                {
                    "equipment_type": equipment_type,
                    "knowledge_type": knowledge_type,
                    "code": code,
                    "title": title,
                    "description": description,
                    "component": component,
                    "manufacturer": manufacturer,
                    "model": model,
                    "symptoms": symptoms,
                    "possible_causes": possible_causes,
                    "diagnostic_steps": diagnostic_steps,
                    "solution": solution,
                    "parts_required": parts_required,
                    "estimated_labor_hours": estimated_labor_hours,
                    "priority": priority,
                    "embedding": embedding,
                }
            )
            .execute()
        )

        return result.data[0] if result.data else None

    def get_document(self, document_id: str) -> dict[str, Any] | None:
        """Get a document by ID."""
        result = self.client.table("documents").select("*").eq("id", document_id).single().execute()
        return result.data

    def list_documents(
        self, equipment_type: str | None = None, document_type: str | None = None, limit: int = 50
    ) -> list[dict[str, Any]]:
        """List documents with optional filters."""
        query = self.client.table("documents").select(
            "id, code, title, equipment_type, document_type, manufacturer, "
            "model, indexing_status, chunk_count, created_at"
        )

        if equipment_type:
            query = query.eq("equipment_type", equipment_type)
        if document_type:
            query = query.eq("document_type", document_type)

        result = query.limit(limit).order("created_at", desc=True).execute()
        return result.data if result.data else []

    def _attach_grounding_metadata(self, results: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Attach normalized grounding metadata for citation-ready responses."""
        if not results:
            return results

        chunk_ids = [str(r.get("chunk_id") or r.get("id")) for r in results if r.get("chunk_id") or r.get("id")]
        if not chunk_ids:
            return results

        try:
            chunk_rows = (
                self.client.table("document_chunks")
                .select("id, document_id, chunk_index, section_title, page_number, metadata")
                .in_("id", chunk_ids)
                .execute()
            )
            chunk_map = {str(row["id"]): row for row in (chunk_rows.data or [])}
        except Exception as exc:
            logger.debug("Unable to enrich chunk grounding metadata: %s", exc)
            return results

        for result in results:
            chunk_id = str(result.get("chunk_id") or result.get("id") or "")
            if not chunk_id:
                continue
            row = chunk_map.get(chunk_id)
            if not row:
                continue

            row_meta = row.get("metadata") if isinstance(row.get("metadata"), dict) else {}
            grounding = row_meta.get("grounding") if isinstance(row_meta.get("grounding"), dict) else {}
            section_title = row.get("section_title") or result.get("section_title")
            page_number = row.get("page_number")
            document_id = str(row.get("document_id") or result.get("document_id") or grounding.get("document_id") or "")

            result["chunk_id"] = chunk_id
            if document_id:
                result["document_id"] = document_id
            if section_title:
                result["section_title"] = section_title
            if page_number is not None:
                result["page_number"] = page_number

            result["grounding"] = {
                "document_id": document_id or grounding.get("document_id"),
                "chunk_id": chunk_id,
                "chunk_index": row.get("chunk_index", grounding.get("chunk_index")),
                "document_title": result.get("document_title") or grounding.get("document_title"),
                "section_title": section_title or grounding.get("section_title"),
                "page_number": page_number if page_number is not None else grounding.get("page_number"),
                "source": result.get("source") or result.get("document_source") or grounding.get("source"),
            }

        return results


def get_vector_db_service(supabase_client) -> VectorDBService:
    """Factory function for VectorDBService."""
    return VectorDBService(supabase_client)
