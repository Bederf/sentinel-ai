---
title: "Data Sheet: RAG Knowledge Base"
type: "data-sheet"
status: "active"
version: "1.0.0"
created: "2026-02-23"
updated: "2026-02-23"
author: "SENTINEL Governance Team"
dataset_id: "ds-rag-knowledge-base"
tags: ["ai-governance", "data-sheet", "rag", "documents", "embeddings", "knowledge-base"]
domain: "compliance"
audience: ["developers", "data-scientists", "auditors"]
complexity: "intermediate"
---

# Data Sheet: RAG Knowledge Base

## 1. Overview

| Field | Value |
|-------|-------|
| **Dataset Name** | RAG Knowledge Base |
| **Dataset ID** | `ds-rag-knowledge-base` |
| **Owner** | SENTINEL Development Team |
| **Status** | Active |
| **Primary Consumers** | AI chat assistant (Sentry), document search, contextual recommendations |

## 2. Data Source

**Origin:** Building-scoped document uploads by authorized users (PDF, DOCX, TXT).

**Collection method:**
- User-initiated upload via `/api/documents/upload` endpoint
- Documents chunked, embedded, and indexed for retrieval-augmented generation (RAG)
- Building-scoped: each document is associated with a specific site/building
- Version-tracked: upload history maintained per document

**Document types typically uploaded:**
- Equipment manuals and specification sheets
- Building floor plans and as-built drawings
- Maintenance procedures and checklists
- Compliance certificates and inspection reports
- Energy audit reports
- Commissioning records

## 3. Collection Period and Refresh

| Field | Value |
|-------|-------|
| **Collection Start** | User-initiated (no fixed start date) |
| **Collection Mode** | On-demand upload |
| **Processing** | Immediate: chunk -> embed -> index on upload |
| **Chunk Size** | Configurable (default: 512 tokens with 50-token overlap) |
| **Embedding Model** | Configured per deployment |
| **Index Refresh** | Real-time on new upload; periodic reindex on embedding model update |

## 4. Data Quality Checks

| Check | Method | Threshold |
|-------|--------|-----------|
| **Chunk quality scoring** | Semantic coherence check per chunk | Low-quality chunks flagged for review |
| **Embedding validation** | Vector dimension and norm verification | Malformed embeddings rejected |
| **Duplicate detection** | Content hash comparison on upload | Duplicate documents flagged to uploader |
| **File format validation** | MIME type and extension verification | Only PDF, DOCX, TXT accepted |
| **File size limit** | Maximum upload size check | Configurable per deployment |
| **Encoding detection** | Character encoding validation | UTF-8 required; other encodings converted |

**Missing data policy:**
- Corrupted uploads: Rejected with user-facing error message
- Partially parseable documents: Best-effort extraction with quality warning
- Empty documents: Rejected at upload validation

**Knowledge gap awareness:**
- RAG coverage depends entirely on documents uploaded
- Gaps in documentation = gaps in AI knowledge
- No automated gap detection (manual review responsibility)

## 5. Sensitive Fields

| Field | Sensitivity | Control |
|-------|------------|---------|
| **Equipment manuals** | **Low sensitivity** | Manufacturer documentation, generally not confidential |
| **Floor plans** | **Medium sensitivity** | May contain building security information; access restricted per digital twin security policy |
| **Maintenance procedures** | **Low sensitivity** | Operational procedures, internal use |
| **Compliance certificates** | **Low sensitivity** | Regulatory documents, may be publicly required |
| **Energy audit data** | **Low sensitivity** | Building performance data |
| **Upload metadata** | **Low sensitivity** | Uploader identity, timestamp, building association |

**Security controls:**
- Building-scoped access: Users can only query documents for sites they have access to
- Floor plans and security-sensitive documents: Restricted per digital twin security policy
- No PII expected in building documentation (if found, flagged for removal)
- All uploads logged with user identity and timestamp

## 6. Known Bias and Skew

| Bias | Description | Mitigation |
|------|-------------|------------|
| **Coverage bias** | AI knowledge limited to uploaded documents; undocumented equipment or procedures create blind spots | Provide coverage dashboards; prompt users to upload missing documentation |
| **Recency bias** | Outdated documents may remain in the index if not replaced | Version tracking; encourage periodic document review and re-upload |
| **Language bias** | Documents primarily in English; multilingual support limited | Document language detection; flag non-English documents for translation |
| **Format bias** | PDF with images/diagrams may lose information during text extraction | Support OCR for scanned documents; flag image-heavy PDFs for manual review |
| **Manufacturer bias** | Documentation availability varies by manufacturer; well-documented equipment types have richer AI context | Track coverage by equipment type and manufacturer |

## 7. Retention and Lifecycle

| Policy | Value |
|--------|-------|
| **Document retention** | Permanent until user deletes |
| **Embedding vectors** | Retained with document; deleted when document deleted |
| **Upload history** | Permanent (audit trail) |
| **Chunk cache** | Regenerated on embedding model update |
| **Deletion policy** | User-initiated deletion removes document, chunks, and embeddings |
| **Backup** | Supabase storage for originals; vector store for embeddings |

## 8. Lawful Basis and Regulatory

| Regulation | Basis | Notes |
|------------|-------|-------|
| **POPIA** | Consent | User explicitly uploads documents; consent implied by upload action |
| **POPIA** | Legitimate interest | Building operational documentation for management purposes |
| **NIST AI RMF** | MS 2.5, MS 2.9 | Data sheet supports model documentation |
| **ISO 42001** | A.6.2.6 | AI system data documentation |
| **Copyright** | User responsibility | Uploader responsible for ensuring they have rights to upload documents |

## 9. Access Controls

| Role | Access Level |
|------|-------------|
| Site operators | Read/Write (upload and query documents for their sites) |
| AI chat assistant | Read (retrieve relevant chunks for RAG context) |
| Administrators | Read/Write/Delete (manage all documents across sites) |
| Auditors | Read (for compliance verification) |
| External parties | None (documents never shared externally) |

---

*This data sheet follows the SENTINEL AI Governance Framework. For updates, contact the SENTINEL Development Team.*
