---
title: "Document and Retrieval Architecture Canonical Note"
type: "architecture"
status: "draft"
version: "1.0.0"
created: "2026-03-31"
updated: "2026-07-10"
tags: ["sentinel", "documentation"]
related: []
domain: "bms"
audience: "all"
complexity: "intermediate"
estimated_read_time: 10
---

# Document and Retrieval Architecture Canonical Note

## Purpose

This note defines the canonical names and boundaries for document retrieval, file intake, OCR, and related knowledge pipelines in the platform.

The goal is to stop using the term "RAG" as a blanket label for every file-related workflow.

Code is the source of truth. Documentation is guidance only where it matches live code.

---

## Central Naming Index

Use this table first. It is the single canonical naming reference for document/retrieval conversations, ADRs, tickets, and TODO updates.

| Canonical name | Use when talking about | Avoid aliases / deprecated terms |
|---|---|---|
| Canonical Document RAG | pgvector-backed shared document retrieval backbone | "Doc RAG" (ambiguous), "the RAG system" (blanket) |
| Concept Search Service | Concept document search and ranking path | "Concept RAG" (unless architecture is explicitly proven as RAG) |
| Technician Intake Pipeline | Telegram/field raw file intake and metadata capture | "intake RAG", "upload RAG" |
| Service Sheet OCR Pipeline | OCR extraction of service-sheet images to structured data | "OCR RAG" |
| Municipal Invoice Processing Pipeline | Municipal invoice parsing and reconciliation flow | "billing RAG", "invoice RAG" |
| OEM Manual Pipeline | OEM equipment manual ingestion, indexing, and checklist extraction | "manual scraping", "OEM RAG" |
| Shared Infrastructure | Reusable components used by one or more surfaces | Using infra names as product-surface names |

### Team usage rule

- In architecture docs and tickets, always use canonical names from this table.
- If a legacy name appears, include the canonical term in the same sentence and prefer canonical naming afterward.

---

## 1. Canonical Document RAG

### Definition

The Canonical Document RAG is the primary pgvector-based document retrieval backbone used for AI-assisted question answering over indexed text documents.

### Scope

This includes:
- system documentation indexed for AI chat
- chat-uploaded text documents that are extracted, chunked, embedded, and stored in the same retrieval backbone

### Core characteristics

- native text-first extraction
- chunking into retrievable text units
- local embeddings
- pgvector storage
- hybrid retrieval using dense similarity plus keyword/full-text matching
- query-time use by AI chat and RAG endpoints

### Canonical purpose

To provide retrieval-backed context for AI answers over approved indexed document corpora.

### Canonical name

**Canonical Document RAG**

### What it is not

It is not:
- the Concept retrieval layer
- Telegram technician raw intake
- service-sheet OCR
- municipal invoice parsing

---

## 2. Concept Search Service

### Definition

The Concept Search Service is a separate queryable retrieval surface for Concept-related documents and records.

### Scope

This includes:
- active concept document search routes and frontend flows
- concept-specific corpus boundaries
- concept-specific ranking and retrieval behavior

### Core characteristics

- queryable today
- separate architecture from the Canonical Document RAG
- not the same active pgvector retrieval path as the canonical backbone
- concept corpus is isolated from the canonical document corpus

### Canonical purpose

To retrieve Concept-related content for technical or Concept-specific workflows.

### Canonical name

**Concept Search Service**

### Important note

Do not refer to this service as the Canonical Document RAG. It is a separate retrieval layer.

### What it is not

It is not:
- the shared pgvector backbone used for system docs and chat-uploaded documents
- a generic catch-all "Concept RAG" label for every Concept file workflow

---

## 3. Technician Intake Pipeline

### Definition

The Technician Intake Pipeline is the Telegram-based raw file and photo intake workflow for technician-submitted material.

### Scope

This includes:
- technician uploads from Telegram
- raw file preservation
- intake metadata capture
- downstream storage for later operational handling

### Core characteristics

- accepts files and photos
- preserves raw artifacts
- stores intake metadata
- does not currently chunk, embed, index, or expose content through the active RAG retrieval path

### Canonical purpose

To receive and store technician-submitted documents and images for operational use.

### Canonical name

**Technician Intake Pipeline**

### Important note

This is an upload pipeline, not a retrieval system.

### What it is not

It is not:
- a RAG system
- a searchable knowledge corpus in the active AI question-answering path

---

## 4. Service Sheet OCR Pipeline

### Definition

The Service Sheet OCR Pipeline is the image-first extraction workflow used to convert technician-submitted service sheets into structured operational data.

### Scope

This includes:
- OCR processing of service-sheet images
- structured extraction and validation
- downstream workflow updates and correction handling

### Core characteristics

- image analysis and OCR
- structured data extraction
- workflow integration
- no active chunking, embedding, vector indexing, or retrieval-backed query path

### Canonical purpose

To transform service-sheet images into usable structured records for operations.

### Canonical name

**Service Sheet OCR Pipeline**

### Important note

This is an OCR and workflow pipeline, not a RAG system.

### What it is not

It is not:
- part of the Canonical Document RAG
- a searchable document retrieval corpus

---

## 5. Municipal Invoice Processing Pipeline

### Definition

The Municipal Invoice Processing Pipeline is the PDF extraction and reconciliation workflow for municipal billing documents.

### Scope

This includes:
- municipal invoice upload
- PDF extraction
- optional OCR fallback where implemented
- reconciliation and billing-related downstream logic

### Core characteristics

- business-document parsing
- operational reconciliation
- no active vector retrieval path
- no active use as a document RAG corpus

### Canonical purpose

To process and reconcile municipal billing documents.

### Canonical name

**Municipal Invoice Processing Pipeline**

### Important note

This is a business-document processing pipeline, not a RAG system.

### What it is not

It is not:
- part of the Canonical Document RAG
- a queryable AI document retrieval backbone

---

## 6. Shared Infrastructure

### Definition

Shared Infrastructure refers to reusable technical components that support one or more document or retrieval surfaces.

### Typical examples

- embedding service
- vector database service
- storage services
- file scanning and validation
- OCR utilities
- retrieval SQL functions
- LLM orchestration services

### Important note

Shared infrastructure does not mean shared product behavior. Two surfaces can share components without being the same retrieval system.

---

## 7. Classification Rules

Use the following rules when describing a surface:

### Call it a RAG system only if all are true

- content is extracted or otherwise normalized for retrieval
- content is chunked or indexed for retrieval
- embeddings or a retrieval index are built
- a query path exists that returns relevant context
- that context is used to answer user or system questions

### Call it a retrieval system if

- it supports queryable search over a persistent corpus
- even if it does not use the canonical pgvector RAG architecture

### Call it an upload pipeline if

- it receives and stores files
- but does not currently make them queryable through retrieval

### Call it an OCR pipeline if

- it extracts structured information from images or PDFs
- but does not index them for question answering

---

## 8. Current Canonical View

### True dense document RAG backbone

- **Canonical Document RAG**

### Separate queryable retrieval layer

- **Concept Search Service**

### Upload or processing pipelines that are not RAG

- **Technician Intake Pipeline**
- **Service Sheet OCR Pipeline**
- **Municipal Invoice Processing Pipeline**
- **OEM Manual Pipeline** — equipment manual ingestion (Phase 234); indexed and searchable through Canonical Document RAG filters, not a separate retrieval system

---

## 9. Naming Rules for Teams

### Allowed names

- Canonical Document RAG
- Concept Search Service
- Technician Intake Pipeline
- Service Sheet OCR Pipeline
- Municipal Invoice Processing Pipeline
- OEM Manual Pipeline

### Avoid

- "the RAG system" when referring to all document surfaces
- "Concept RAG" unless explicitly referring to a proven retrieval architecture
- calling upload or OCR pipelines "RAG" unless they are actually indexed and queryable

---

## 10. Source of Truth

### Source priority

1. live code paths
2. active schemas and migrations
3. runtime configuration
4. documentation

### Important note

Where docs conflict with code, code wins.

Examples include terminology drift such as:
- `building_id` in older docs
- `site_id` in live code and migrations

---

## 11. Immediate Implications

- Architecture discussions must use the canonical names above.
- New file workflows must be classified as retrieval system, upload pipeline, OCR pipeline, or shared infrastructure.
- No team member should describe a surface as RAG without proving the retrieval path exists.
- Future consolidation decisions should explicitly state whether a surface will remain separate or join the Canonical Document RAG.

---

## 12. Open Decisions

The following still require product and architecture decisions:
- whether Concept Search Service should remain separate or converge onto the Canonical Document RAG
- whether any technician intake artifacts should become queryable in future
- whether OCR outputs should remain workflow-only or become retrieval-backed knowledge
- whether multimodal retrieval should be added to the Canonical Document RAG

---

## Slack Summary

Current architecture summary

1. Canonical Document RAG  
The only canonical pgvector document RAG backbone. Used for system docs and chat-uploaded text docs.

2. Concept Search Service  
A separate queryable retrieval layer for Concept content. Not the same architecture as the Canonical Document RAG.

3. Technician Intake Pipeline  
Telegram-based raw file and photo intake. Stores files and metadata. Not RAG.

4. Service Sheet OCR Pipeline  
OCR and structured extraction workflow for technician service sheets. Not RAG.

5. Municipal Invoice Processing Pipeline  
PDF extraction and reconciliation workflow for municipal invoices. Not RAG.

Rule going forward  
Do not use "RAG" as a blanket term for every file workflow. A surface is only RAG if it is indexed and queryable through a retrieval path.
