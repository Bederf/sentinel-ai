"""Vector database service using Supabase + pgvector."""
from typing import List, Optional, Dict, Any
import re
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

    def _split_markdown_into_chunks(
        self,
        text: str,
        max_chunk_size: int = 800,
        overlap_ratio: float = 0.15
    ) -> List[Dict[str, Any]]:
        """Split markdown text into section-aware chunks with heading paths.

        Inspired by aimthelaw's legal document chunking:
        - Respects heading boundaries (never splits mid-section)
        - Tracks heading hierarchy for each chunk
        - Uses paragraph-level splitting within large sections
        - Local overlap only within the same section
        """
        chunks = []
        lines = text.split('\n')

        # Build sections from heading structure
        sections = []
        current_headings = {}  # level -> heading text
        current_lines = []
        current_level = 0

        for line in lines:
            heading_match = re.match(r'^(#{1,4})\s+(.+)$', line)
            if heading_match:
                # Save accumulated content as a section
                if current_lines:
                    content = '\n'.join(current_lines).strip()
                    if content:
                        heading_path = [
                            current_headings[k]
                            for k in sorted(current_headings.keys())
                            if k <= current_level
                        ]
                        sections.append({
                            'content': content,
                            'heading_path': list(heading_path),
                            'section_title': current_headings.get(current_level, ''),
                            'level': current_level,
                        })
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
            content = '\n'.join(current_lines).strip()
            if content:
                heading_path = [
                    current_headings[k]
                    for k in sorted(current_headings.keys())
                    if k <= current_level
                ]
                sections.append({
                    'content': content,
                    'heading_path': list(heading_path),
                    'section_title': current_headings.get(current_level, ''),
                    'level': current_level,
                })

        # Process each section into chunks
        overlap_chars = int(max_chunk_size * overlap_ratio)

        for section in sections:
            section_text = section['content']

            if len(section_text) <= max_chunk_size:
                # Section fits in one chunk
                if section_text.strip():
                    chunks.append({
                        'content': section_text.strip(),
                        'section': section['section_title'],
                        'heading_path': section['heading_path'],
                    })
            else:
                # Split large sections at paragraph boundaries
                paragraphs = re.split(r'\n\s*\n', section_text)
                current_chunk = ''

                for para in paragraphs:
                    para = para.strip()
                    if not para:
                        continue

                    if len(current_chunk) + len(para) + 2 <= max_chunk_size:
                        current_chunk = (current_chunk + '\n\n' + para).strip()
                    else:
                        # Save current chunk
                        if current_chunk.strip():
                            chunks.append({
                                'content': current_chunk.strip(),
                                'section': section['section_title'],
                                'heading_path': section['heading_path'],
                            })
                        # Start new chunk with overlap from end of previous
                        if overlap_chars > 0 and current_chunk:
                            overlap_text = current_chunk[-overlap_chars:]
                            current_chunk = overlap_text + '\n\n' + para
                        else:
                            current_chunk = para

                        # Handle paragraphs larger than max_chunk_size
                        if len(current_chunk) > max_chunk_size:
                            # Split by sentences
                            sentences = re.split(r'(?<=[.!?])\s+', current_chunk)
                            current_chunk = ''
                            for sentence in sentences:
                                if len(current_chunk) + len(sentence) + 1 <= max_chunk_size:
                                    current_chunk = (current_chunk + ' ' + sentence).strip()
                                else:
                                    if current_chunk.strip():
                                        chunks.append({
                                            'content': current_chunk.strip(),
                                            'section': section['section_title'],
                                            'heading_path': section['heading_path'],
                                        })
                                    current_chunk = sentence

                # Don't forget remaining content
                if current_chunk.strip():
                    chunks.append({
                        'content': current_chunk.strip(),
                        'section': section['section_title'],
                        'heading_path': section['heading_path'],
                    })

        return chunks

    def chunk_and_embed_markdown(
        self,
        document_id: str,
        doc_title: str = '',
        doc_type: str = '',
        max_chunk_size: int = 800,
    ) -> int:
        """Chunk markdown document with section awareness and context-enhanced embeddings.

        Uses heading-aware chunking and prepends context headers to improve
        embedding quality (document title + heading path + type).
        Original content is stored without the header.
        """
        doc = self.client.table('documents').select('*').eq('id', document_id).single().execute()
        document = doc.data
        if not document:
            logger.error(f"Document not found: {document_id}")
            return 0

        self.client.table('documents').update({
            'indexing_status': 'chunking'
        }).eq('id', document_id).execute()

        text = document.get('full_text', '')
        if not text:
            return 0

        title = doc_title or document.get('title', '')
        dtype = doc_type or document.get('document_type', '')

        # Use markdown-aware chunking
        chunks = self._split_markdown_into_chunks(text, max_chunk_size)

        if not chunks:
            return 0

        # Build context-enhanced texts for embedding (not for storage)
        embed_texts = []
        for chunk in chunks:
            heading_path = ' > '.join(chunk.get('heading_path', []))
            context_header = f"Document: {title}\n"
            if heading_path:
                context_header += f"Section: {heading_path}\n"
            if dtype:
                context_header += f"Type: {dtype}\n"
            context_header += "---\n"
            embed_texts.append(context_header + chunk['content'])

        # Generate embeddings from context-enhanced text
        embeddings = self.embedding_service.embed_batch(embed_texts)

        # Store chunks with original content (no context header)
        chunk_records = []
        for i, (chunk, embedding) in enumerate(zip(chunks, embeddings)):
            heading_path = chunk.get('heading_path', [])
            chunk_records.append({
                'document_id': document_id,
                'chunk_index': i,
                'content': chunk['content'],
                'content_length': len(chunk['content']),
                'section_title': chunk.get('section', ''),
                'embedding': embedding,
                'equipment_type': document['equipment_type'],
                'document_type': document['document_type'],
                'manufacturer': document.get('manufacturer'),
                'model': document.get('model'),
                'keywords': document.get('keywords'),
                'failure_modes': document.get('failure_modes'),
                'metadata': {
                    'heading_path': heading_path,
                    'context_enhanced': True,
                }
            })

        if chunk_records:
            # Insert in batches to avoid payload limits
            batch_size = 50
            for j in range(0, len(chunk_records), batch_size):
                batch = chunk_records[j:j + batch_size]
                self.client.table('document_chunks').insert(batch).execute()

        self.client.table('documents').update({
            'indexing_status': 'embedded',
            'indexed_at': 'now()',
            'chunk_count': len(chunk_records)
        }).eq('id', document_id).execute()

        logger.info(f"Indexed markdown document {document_id}: {len(chunk_records)} chunks (section-aware)")
        return len(chunk_records)

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
