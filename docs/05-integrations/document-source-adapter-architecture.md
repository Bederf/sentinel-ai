---
title: "Document Source Adapter Architecture"
type: "guide"
status: "draft"
version: "1.0.0"
created: "2026-04-05"
updated: "2026-04-05"
author: "Sentinel Development Team"
tags: ["documents", "intake", "adapters", "ocr", "mri", "sharepoint"]
related:
  - "maintenance-intake-architecture.md"
  - "sentry-telegram-document-intake.md"
  - "drive-intake-pipeline.md"
domain: "integration"
audience: "developers"
complexity: "intermediate"
estimated_read_time: 10
---

# Document Source Adapter Architecture

## Problem

Every site has multiple document sources — technician uploads, MRI service reports, SharePoint repositories, inspection certificates. These arrive in different formats through different channels, but all feed the same downstream pipeline: OCR → RAG embedding → Supabase storage → wiki compilation → technician chat.

The document intake layer is the adapter that sits between each source and the canonical `documents` table.

## Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                   SENTINEL Document Intake Layer                     │
├──────────────┬──────────────┬──────────────┬──────────────────────┤
│ MRI Adapter  │ SharePoint  │ Manual Upload│ Future adapters        │
│ (Phase 179) │ Adapter      │ Adapter      │                        │
│              │              │              │                        │
│ mri_document│ sharepoint_  │ document_    │ document_              │
│ _client      │ adapter_     │ adapter_     │ adapter_...            │
└──────┬───────┴──────┬───────┴──────┬───────┴──────────┬───────────┘
       │              │              │                  │
       ▼              ▼              ▼                  ▼
┌─────────────────────────────────────────────────────────────────────┐
│              documents  (canonical sink — same table)                │
│   source_system field identifies origin; source_document_id is       │
│   the upsert key (composite with source_system for multi-source)    │
└────────────────────────────┬────────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────────┐
│                   SENTINEL Document Pipeline                        │
│                                                                     │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────────┐ │
│  │ OCR / Docling│  │ RAG Embedding│  │ Compiler Queue            │ │
│  │ (Phase 180)  │  │ (Phase 181)  │  │ → wiki/S002/{asset}.md   │ │
│  └──────────────┘  └──────────────┘  └──────────────────────────┘ │
│                                                                     │
│  ┌──────────────────────────────────────────────────────────────┐  │
│  │ Tech Chat Query Routing (Phase 183)                          │  │
│  │ metadata lookup path + content/vector path → source_url link  │  │
│  └──────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────┘
```

**Rule: one adapter per source, one canonical table for all.**

## source vs source_system

These two fields serve different purposes and are written by different flows:

| Field | Written by | Purpose | Write-once? |
|-------|-----------|---------|-------------|
| `source` | `upload_technician_document` flow | Content-type classifier (SERVICE_REPORT, INSPECTION...) | Yes — set at first intake, never overwritten |
| `source_system` | `DocumentSourceAdapter._upsert()` | Ingestion provenance (CONCEPT_MRI, SHAREPOINT, MANUAL_UPLOAD) | Upsert key — updated on every sync |

This separation is critical: `documents.source` has a CHECK constraint; writing raw adapter values there would violate it. The adapter only writes `source_system`, `source_document_id`, and `site_id`.

## Canonical Schema: `documents` (Phase 179 additions)

```sql
ALTER TABLE documents ADD COLUMN source_system TEXT;
ALTER TABLE documents ADD COLUMN source_document_id TEXT;
ALTER TABLE documents ADD COLUMN site_id TEXT;

ALTER TABLE documents ADD CONSTRAINT documents_source_doc_site_unique
    UNIQUE (source_document_id, source_system);
```

The composite unique constraint `(source_document_id, source_system)` allows the same document ID from different adapters without conflict.

## Adapter Pattern

Each adapter follows the same interface:

```python
class DocumentSourceAdapter(ABC):
    """Base class for all document source adapters."""

    source_system: SourceSystem  # Identifies this adapter's origin system

    @abstractmethod
    async def fetch_new_documents(
        self, since: datetime | None, site_id: str | None
    ) -> list[DocumentRecord]:
        """Fetch new documents from the source system since last sync."""

    @abstractmethod
    def get_document_file(self, source_document_id: str) -> bytes:
        """Retrieve the raw file bytes for the given source_document_id."""

    async def run_sync(self, site_id: str | None = None) -> dict:
        """Fetch → upsert → update sync state."""
```

The base `DocumentSourceAdapter` provides:
- `_columns_exist()` — B1 fix: guard against missing columns (migration not applied)
- `_upsert()` — B1/B2 fix: upsert with column guard; only writes 3 new columns
- `_get_last_sync()` / `_update_sync_state()` — per-adapter sync tracking
- `run_sync()` — concrete full sync cycle

## Enums

### DocumentSource (content classifier — write-once)

```python
class DocumentSource(str, Enum):
    SERVICE_REPORT = "service_report"
    INSPECTION = "inspection"
    CERTIFICATE = "certificate"
    TEST_REPORT = "test_report"
    MANUAL = "manual"
    UNKNOWN = "unknown"
```

Classifies what the document IS. Set at first intake by the existing upload flow — never overwritten on update.

### SourceSystem (ingestion adapter — upsert key)

```python
class SourceSystem(str, Enum):
    CONCEPT_MRI = "concept_mri"
    SHAREPOINT = "sharepoint"
    MANUAL_UPLOAD = "manual_upload"
```

Identifies which adapter ingested the document. Composite upsert key with `source_document_id`.

## Implemented Adapters

### ManualUploadAdapter (Phase 179-02)

File: `backend/app/services/document_adapter_manual.py`

Used by technician uploads via `upload_technician_document` endpoint. Maps `document_name` to `DocumentSource` via `_DOCUMENT_NAME_TO_SOURCE` lookup:

```python
_DOCUMENT_NAME_TO_SOURCE = {
    "chiller_report": DocumentSource.SERVICE_REPORT,
    "maintenance_log": DocumentSource.SERVICE_REPORT,
    "refrigerant_log": DocumentSource.SERVICE_REPORT,
    "inspection_report": DocumentSource.INSPECTION,
    "safety_certificate": DocumentSource.CERTIFICATE,
    "test_report": DocumentSource.TEST_REPORT,
}
```

### ConceptMRIAdapter (Phase 179-03)

Files: `backend/app/services/mri_document_client.py`, `backend/app/services/document_adapter_mri.py`

Polls MRI Evolution REST API (separate from work-order endpoint). `FIELD_MAP` is PROVISIONAL — field names need vendor confirmation.

Configuration:
```
MRI_DOCUMENT_BASE_URL=https://{tenant}.mrisoftware.com/Evolution/api/v1
MRI_DOCUMENT_API_KEY={from vendor}
DOCUMENT_SYNC_INTERVAL_HOURS=4
```

API: `POST /api/documents/sync`, `GET /api/documents/sync/status/{adapter}`

APScheduler job: `document_mri_sync`, runs every 4h in shadow mode (`ENABLE_SITE002_SOURCE=false`).

### SharePointAdapter (Phase 182 — planned)

Future adapter for SharePoint document libraries.

## Phase 181: OCR + LLM Extraction Pipeline

Phase 181 completes the upload pipeline wiring from scanned PDF to resolved asset_id:

```
Scanned PDF upload
      ↓
extract_text(file) — raw OCR text (PyPDF2 or pytesseract fallback)
      ↓ (if raw_text.strip() >= 50 chars)
LLMExtractionService.extract_equipment_description(raw_text)
      ↓ (equipment_description: free-text string)
adapter.normalise_upload(response, form_data, site_id, equipment_description)
      ↓
adapter._upsert(doc_record) — writes equipment_description to DB
      ↓
AssetIDResolver.resolve_and_apply(document_id)
      → asset_id resolved, quarantined if LOW/none, compiler_queue triggered
```

**Services added (Phase 181):**

| Service | File | Purpose |
|---------|------|---------|
| `DoclingExtractionService` | `app/services/docling_extraction_service.py` | docling OCR with graceful fallback; 3-tier: PyPDF2 → docling → pytesseract |
| `LLMExtractionService` | `app/services/llm_extraction_service.py` | Extract equipment_description from raw OCR text via LLM |

**Key decisions (Phase 181):**

1. **Ordering**: LLM extraction MUST happen BEFORE `_upsert`. AssetIDResolver reads `equipment_description` from DB after `_upsert`. If extraction happens after, the field is lost.

2. **equipment_description vs equipment_id**: `equipment_description` = OCR+LLM free-text description. `equipment_id` (from upload form) = canonical asset ID. Stored separately in DocumentRecord.

3. **C1 JSON injection fix**: `email_intake_agent.py` prompt embeds raw email body. All user-supplied fields (`from_name`, `from_email`, `subject`, `body_plain`) passed through `_esc_jinja()` before prompt formatting.

4. **Column guard**: `_columns_exist("documents", "equipment_description")` guard must be OUTSIDE `if record.equipment_description:` — never gate it inside, else the guard is ineffective when field is truthy.

## Graceful Migration Degradation (B1 Fix)

The `_columns_exist()` guard prevents 500 errors when the migration has not yet been applied:

```python
async def _columns_exist(self, table: str, *columns: str) -> bool:
    result = (
        self.db.table("information_schema.columns")
        .select("column_name")
        .eq("table_name", table)
        .in_("column_name", list(columns))
        .execute()
    )
    if len(result.data) != len(columns):
        logger.warning("[%s] _columns_exist: table=%s columns=%s — missing", ...)
        return False
    return True
```

Both `_upsert()` and `fetch_new_documents()` (via the ABC guard) check `_columns_exist` before querying or writing. If columns are missing, `_upsert` returns `""` and `fetch_new_documents` returns `[]` — the sync job stays healthy.

## Sync State Per Adapter

```sql
CREATE TABLE document_connector_sync (
    id                      UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    adapter_source          TEXT NOT NULL,               -- 'concept_mri', 'sharepoint', 'manual_upload'
    site_id                 UUID REFERENCES sites(id),
    last_successful_sync    TIMESTAMPTZ,
    last_sync_attempted     TIMESTAMPTZ,
    records_ingested        INTEGER DEFAULT 0,
    records_updated         INTEGER DEFAULT 0,
    errors                  INTEGER DEFAULT 0
);
```

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/documents/sync` | Trigger sync for an adapter |
| `GET`  | `/api/documents/sync/status/{adapter}` | Return last sync state |
| `POST` | `/api/documents/upload` | Existing technician upload endpoint |

## Downstream Pipeline

Phase 179 establishes the adapter layer. Remaining pipeline phases:

| Phase | Component | Status |
|-------|-----------|--------|
| 180 | Asset ID resolver | SHIPPED |
| 181 | OCR + LLM Extraction Pipeline | SHIPPED |
| 182 | Compiler queue worker | SHIPPED |
| 183 | Tech chat query routing | Planned |
