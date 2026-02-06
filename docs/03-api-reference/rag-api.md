---
title: "RAG API Reference"
type: "reference"
status: "approved"
version: "1.0.0"
created: "2026-02-06"
updated: "2026-02-06"
author: "Sentinel Development Team"
tags: ["api", "rag", "vector-search", "knowledge-base", "ollama"]
domain: "general"
audience: "developers"
complexity: "intermediate"
estimated_read_time: 8
---

# RAG API Reference

Phase 44-01 Retrieval-Augmented Generation endpoints. Vector search over equipment knowledge base with Ollama-powered response generation.

Base path: `/api/rag`

## Query

### POST `/api/rag/query`

Query the RAG system with natural language.

**Request Body:**
```json
{
  "query": "What are common chiller compressor failure modes?",
  "equipment_type": "chiller",
  "use_hybrid": true,
  "use_local_llm": true
}
```

**Response:**
```json
{
  "query": "What are common chiller compressor failure modes?",
  "response": "The most common chiller compressor failures are...",
  "context_used": 3,
  "equipment_type": "chiller",
  "llm_used": "ollama"
}
```

## Search

### GET `/api/rag/search`

Semantic similarity search over documents.

**Query Parameters:**
| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| query | string | required | Search query |
| equipment_type | string | null | Filter by type |
| document_type | string | null | Filter by doc type |
| n_results | int | 5 | Results (1-20) |
| similarity_threshold | float | 0.5 | Min similarity (0-1) |

### GET `/api/rag/search/knowledge`

Search equipment knowledge base entries.

**Query Parameters:**
| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| query | string | required | Search query |
| equipment_type | string | null | Filter by type |
| knowledge_type | string | null | Filter by knowledge type |
| n_results | int | 5 | Results |

### GET `/api/rag/search/hybrid`

Hybrid search combining keyword and semantic matching.

**Query Parameters:**
| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| query | string | required | Search query |
| equipment_type | string | null | Filter by type |
| n_results | int | 5 | Results |
| keyword_weight | float | 0.3 | Keyword match weight |
| semantic_weight | float | 0.7 | Semantic match weight |

## Equipment Explanations

### GET `/api/rag/explain/{equipment_id}`

Natural language explanation of equipment risk prediction.

**Query Parameters:**
| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| include_context | bool | true | Include RAG context |

## Document Management

### POST `/api/rag/documents`

Add a document to the RAG system. Automatically chunked and embedded.

**Request Body:**
```json
{
  "code": "DOC-CHILLER-001",
  "title": "Chiller Maintenance Manual",
  "document_type": "manual",
  "equipment_type": "chiller",
  "full_text": "...",
  "source": "manufacturer",
  "manufacturer": "Carrier",
  "model": "30XA",
  "summary": "...",
  "keywords": ["compressor", "refrigerant", "oil"],
  "failure_modes": ["compressor_overload", "refrigerant_leak"]
}
```

**Response:**
```json
{
  "id": "doc_abc123",
  "code": "DOC-CHILLER-001",
  "title": "Chiller Maintenance Manual",
  "chunk_count": 12,
  "status": "indexed"
}
```

### GET `/api/rag/documents`

List documents. Filter by `equipment_type`, `document_type`. Paginate with `limit` (1-200).

### GET `/api/rag/documents/{document_id}`

Get specific document.

### POST `/api/rag/documents/{document_id}/reindex`

Re-chunk and re-embed a document.

## Knowledge Management

### POST `/api/rag/knowledge`

Add knowledge entry (troubleshooting guides, best practices, etc.).

## Health

### GET `/api/rag/health`

RAG system health: Ollama availability, database status, document/chunk/knowledge counts.
