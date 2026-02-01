"""Vector database service using Supabase + pgvector."""
from typing import List, Optional, Dict, Any
import logging

logger = logging.getLogger(__name__)


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

    def add_document(
        self,
        code: str,
        title: str,
        document_type: str,
        equipment_type: str,
        full_text: str,
        source: str = 'internal_procedure',
        manufacturer: Optional[str] = None,
        model: Optional[str] = None,
        summary: Optional[str] = None,
        keywords: Optional[List[str]] = None,
        failure_modes: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """Add a document to the RAG system."""
        result = self.client.table('documents').insert({
            'code': code,
            'title': title,
            'document_type': document_type,
            'equipment_type': equipment_type,
            'full_text': full_text,
            'source': source,
            'manufacturer': manufacturer,
            'model': model,
            'summary': summary,
            'keywords': keywords,
            'failure_modes': failure_modes,
            'indexing_status': 'pending'
        }).execute()
        return result.data[0] if result.data else None

    def chunk_and_embed_document(
        self,
        document_id: str,
        chunk_size: int = 500,
        chunk_overlap: int = 50
    ) -> int:
        """Chunk document text and generate embeddings."""
        # Get document
        doc = self.client.table('documents').select('*').eq('id', document_id).single().execute()
        document = doc.data

        if not document:
            logger.error(f"Document not found: {document_id}")
            return 0

        # Update status
        self.client.table('documents').update({
            'indexing_status': 'chunking'
        }).eq('id', document_id).execute()

        # Split into chunks
        text = document.get('full_text', '')
        if not text:
            logger.warning(f"Document {document_id} has no full_text")
            return 0

        chunks = self._split_into_chunks(text, chunk_size, chunk_overlap)

        # Generate embeddings
        embeddings = self.embedding_service.embed_batch([c['content'] for c in chunks])

        # Insert chunks with embeddings
        chunk_records = []
        for i, (chunk, embedding) in enumerate(zip(chunks, embeddings)):
            chunk_records.append({
                'document_id': document_id,
                'chunk_index': i,
                'content': chunk['content'],
                'content_length': len(chunk['content']),
                'section_title': chunk.get('section'),
                'embedding': embedding,
                'equipment_type': document['equipment_type'],
                'document_type': document['document_type'],
                'manufacturer': document.get('manufacturer'),
                'model': document.get('model'),
                'keywords': document.get('keywords'),
                'failure_modes': document.get('failure_modes')
            })

        if chunk_records:
            self.client.table('document_chunks').insert(chunk_records).execute()

        # Update document status
        self.client.table('documents').update({
            'indexing_status': 'embedded',
            'indexed_at': 'now()',
            'chunk_count': len(chunk_records)
        }).eq('id', document_id).execute()

        logger.info(f"Indexed document {document_id}: {len(chunk_records)} chunks")
        return len(chunk_records)

    def _split_into_chunks(
        self,
        text: str,
        chunk_size: int = 500,
        overlap: int = 50
    ) -> List[Dict[str, str]]:
        """Split text into overlapping chunks."""
        chunks = []
        words = text.split()

        if not words:
            return chunks

        i = 0
        while i < len(words):
            chunk_words = words[i:i + chunk_size]
            chunk_text = ' '.join(chunk_words)

            # Try to detect section headers
            section = None
            lines = chunk_text.split('\n')
            for line in lines[:3]:  # Check first 3 lines
                stripped = line.strip()
                if stripped.endswith(':') or (stripped.isupper() and len(stripped) > 3):
                    section = stripped
                    break

            chunks.append({
                'content': chunk_text,
                'section': section
            })

            i += chunk_size - overlap

        return chunks

    def search(
        self,
        query: str,
        n_results: int = 5,
        equipment_type: Optional[str] = None,
        document_type: Optional[str] = None,
        manufacturer: Optional[str] = None,
        similarity_threshold: float = 0.5
    ) -> List[Dict[str, Any]]:
        """Semantic search for relevant document chunks."""
        # Generate query embedding
        query_embedding = self.embedding_service.embed_text(query)

        # Call Supabase RPC function
        result = self.client.rpc('match_document_chunks', {
            'query_embedding': query_embedding,
            'match_count': n_results,
            'filter_equipment_type': equipment_type,
            'filter_document_type': document_type,
            'filter_manufacturer': manufacturer,
            'similarity_threshold': similarity_threshold
        }).execute()

        return result.data if result.data else []

    def search_knowledge(
        self,
        query: str,
        n_results: int = 5,
        equipment_type: Optional[str] = None,
        knowledge_type: Optional[str] = None,
        similarity_threshold: float = 0.5
    ) -> List[Dict[str, Any]]:
        """Search equipment knowledge base."""
        query_embedding = self.embedding_service.embed_text(query)

        result = self.client.rpc('match_equipment_knowledge', {
            'query_embedding': query_embedding,
            'match_count': n_results,
            'filter_equipment_type': equipment_type,
            'filter_knowledge_type': knowledge_type,
            'similarity_threshold': similarity_threshold
        }).execute()

        return result.data if result.data else []

    def hybrid_search(
        self,
        query: str,
        n_results: int = 5,
        equipment_type: Optional[str] = None,
        keyword_weight: float = 0.3,
        semantic_weight: float = 0.7
    ) -> List[Dict[str, Any]]:
        """Hybrid search combining keyword and semantic matching."""
        query_embedding = self.embedding_service.embed_text(query)

        result = self.client.rpc('hybrid_search_chunks', {
            'query_text': query,
            'query_embedding': query_embedding,
            'match_count': n_results,
            'filter_equipment_type': equipment_type,
            'keyword_weight': keyword_weight,
            'semantic_weight': semantic_weight
        }).execute()

        return result.data if result.data else []

    def add_knowledge(
        self,
        equipment_type: str,
        knowledge_type: str,
        title: str,
        description: str,
        code: Optional[str] = None,
        component: Optional[str] = None,
        manufacturer: Optional[str] = None,
        model: Optional[str] = None,
        symptoms: Optional[List[str]] = None,
        possible_causes: Optional[List[str]] = None,
        diagnostic_steps: Optional[List[str]] = None,
        solution: Optional[str] = None,
        parts_required: Optional[Dict] = None,
        estimated_labor_hours: Optional[float] = None,
        priority: Optional[str] = None
    ) -> Dict[str, Any]:
        """Add a knowledge entry with auto-generated embedding."""
        # Generate embedding from title + description
        embed_text = f"{title}. {description}"
        if symptoms:
            embed_text += f" Symptoms: {', '.join(symptoms)}"
        if code:
            embed_text += f" Fault code: {code}"

        embedding = self.embedding_service.embed_text(embed_text)

        result = self.client.table('equipment_knowledge').insert({
            'equipment_type': equipment_type,
            'knowledge_type': knowledge_type,
            'code': code,
            'title': title,
            'description': description,
            'component': component,
            'manufacturer': manufacturer,
            'model': model,
            'symptoms': symptoms,
            'possible_causes': possible_causes,
            'diagnostic_steps': diagnostic_steps,
            'solution': solution,
            'parts_required': parts_required,
            'estimated_labor_hours': estimated_labor_hours,
            'priority': priority,
            'embedding': embedding
        }).execute()

        return result.data[0] if result.data else None

    def get_document(self, document_id: str) -> Optional[Dict[str, Any]]:
        """Get a document by ID."""
        result = self.client.table('documents').select('*').eq('id', document_id).single().execute()
        return result.data

    def list_documents(
        self,
        equipment_type: Optional[str] = None,
        document_type: Optional[str] = None,
        limit: int = 50
    ) -> List[Dict[str, Any]]:
        """List documents with optional filters."""
        query = self.client.table('documents').select('id, code, title, equipment_type, document_type, manufacturer, model, indexing_status, chunk_count, created_at')

        if equipment_type:
            query = query.eq('equipment_type', equipment_type)
        if document_type:
            query = query.eq('document_type', document_type)

        result = query.limit(limit).order('created_at', desc=True).execute()
        return result.data if result.data else []


def get_vector_db_service(supabase_client) -> VectorDBService:
    """Factory function for VectorDBService."""
    return VectorDBService(supabase_client)
