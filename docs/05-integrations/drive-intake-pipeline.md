---
title: "Google Drive Intake Pipeline"
type: "integration"
status: "planned"
version: "1.0.0"
created: "2026-03-05"
updated: "2026-03-05"
author: "SENTINEL Development Team"
tags: ["google-drive", "gws", "mri-evolution", "document-intake", "rag", "thorium"]
related: ["../02-architecture/hybrid-knowledge-layer.md", "../08-ai-ml/rag-integration-overview.md", "n8n-email-pipeline.md"]
domain: "integrations"
audience: "developers"
complexity: "intermediate"
estimated_read_time: 15
---

# Google Drive Intake Pipeline

Document ingestion from MRI Concept Evolution via Google Drive into SENTINEL's RAG layer.

## Overview

MRI Concept Evolution (CAFM) is the operational system of record for asset management, work orders, contracts, and maintenance schedules. Google Drive serves as the document exchange layer. SENTINEL consumes documents from Drive, scans them for security, indexes them, and makes them available to AI agents via RAG.

### Three-Layer Separation

| Layer | System | Role |
|-------|--------|------|
| Operational | MRI Concept Evolution | Asset data, work orders, contracts, PPM schedules |
| Exchange | Google Drive | Document storage, sharing, versioning |
| Intelligence | SENTINEL | AI reasoning, RAG retrieval, telemetry correlation |

This separation avoids coupling the AI system to the FM platform.

## Architecture

```
MRI Evolution (CAFM)
       |
       | exports / reports / attachments
       v
Google Drive (shared site folders)
       |
       | gws MCP (drive.files.list, drive.files.get)
       v
drive_intake_agent.py
       |
       v
thorium_scan_service.py (security gate)
       |
       v
doc_rag_service.py (indexing + embedding)
       |
       v
pgvector + RAG retrieval
       |
       v
SENTINEL agents (hybrid_query_service.py)
```

## Google Workspace CLI (gws)

**Tool:** `@googleworkspace/cli` (installed via npm)
**Purpose:** Exposes Google Workspace APIs as CLI commands and MCP tools

```bash
# Install
npm install -g @googleworkspace/cli

# Authenticate
gws auth setup

# Expose as MCP server for AI agents
gws mcp -s drive,gmail,calendar,sheets
```

### Key Commands

```bash
# List files in a folder
gws drive files list --params '{"q":"\"folder_id\" in parents"}'

# Download file
gws drive files get --params '{"fileId":"...", "alt":"media"}'

# Export Google Docs to PDF
gws drive files export --params '{"fileId":"...", "mimeType":"application/pdf"}'
```

### MCP Integration

When running `gws mcp -s drive,gmail,calendar`, these tools become available to SENTINEL agents:
- `drive.files.list` - List/search files
- `drive.files.get` - Download files
- `gmail.messages.search` - Search emails
- `calendar.events.list` - List calendar events

Gated by SENTINEL's `tool_security_registry.py` (default-deny + tiered access).

## Drive Folder Structure

Predictable mapping from facility to document type:

```
Drive/
   FM/
      Sandton/           -> facility_id: site-002
         Assets/
            HVAC/
            Generators/
         Contracts/
         SLA/
         Maintenance_Schedules/
         Inspections/
      Fairlands/          -> facility_id: site-003
         Assets/
         Contracts/
```

Each folder maps to a `facility_id` and `folder_type`.

## Document Types from MRI

| MRI Export | folder_type | RAG Use |
|-----------|-------------|---------|
| PPM schedule | `maintenance_schedule` | Agent knows when next service is due |
| Inspection report | `inspection_report` | Historical fault patterns |
| Asset register | `asset_register` | Equipment specs, serial numbers |
| Compliance certificate | `compliance` | Expiry tracking, audit readiness |
| Maintenance contract | `contract` | SLA terms, vendor obligations |
| Vendor quote | `vendor_quote` | Cost validation for work orders |
| OEM manual | `oem_manual` | Troubleshooting, specifications |

## Pipeline Components

### drive_intake_agent.py (new)

Replaces or supplements `email_intake_agent.py` for Drive-based document sources.

**Responsibilities:**
- List files in configured Drive folders
- Detect changes since last sync (delta based on `modifiedTime`)
- Download files or export Google Docs to safe format (PDF)
- Stage in local quarantine volume
- Emit `DocumentIngestedEvent`

**Provenance captured per file:**
- `drive_file_id`
- `drive_revision_id`
- `mimeType`
- `modifiedTime`
- `owners` / shared drive info
- `sha256` of downloaded bytes
- `ingest_timestamp`

**Message contract:**
```python
@dataclass
class DocumentIngestedEvent:
    doc_id: str
    source: str  # "drive"
    drive_file_id: str
    revision_id: str
    facility_id: str
    folder_type: str  # inspection_report, contract, etc.
    mime_type: str
    sha256: str
    staged_path: str
    modified_time: str
```

### thorium_scan_service.py (new)

Security gate before indexing. Extends SENTINEL's existing document scanning (v39.0 Phase 137-05).

**Scan pipeline:**
- ClamAV malware scan
- YARA rule matching
- File type validation (magic bytes)
- Macro/embedded object detection
- EXIF metadata stripping

**Trust level mapping:**

| Scan Result | Trust Level | Action |
|------------|-------------|--------|
| Clean | VERIFIED | Continue to indexing |
| Suspicious | UNTRUSTED | Quarantine, alert, block indexing |
| Malware | QUARANTINED | Quarantine, alert, reject |

**Output:**
```python
@dataclass
class DocumentScanResult:
    doc_id: str
    trust_level: str  # VERIFIED, UNTRUSTED, QUARANTINED
    scan_summary: dict
    extraction_allowed: bool
```

### doc_rag_service.py (existing, extended)

Accepts `DocumentScanResult` events. If `trust_level >= STANDARD`:

1. Extract text (PDF via PyPDF2, DOCX via python-docx, etc.)
2. Chunk with stable chunk IDs (prevents duplicates on re-index)
3. Embed chunks
4. Upsert to pgvector with metadata
5. Map ACLs from `folder_acl` table

## Database Schema

### ingested_documents

| Column | Type | Description |
|--------|------|-------------|
| doc_id | UUID PK | Document identifier |
| drive_file_id | TEXT | Google Drive file ID |
| revision_id | TEXT | Drive revision ID |
| facility_id | TEXT | Site/facility identifier |
| folder_type | TEXT | Document category |
| mime_type | TEXT | File MIME type |
| sha256 | TEXT | Content hash |
| trust_level | TEXT | VERIFIED/UNTRUSTED/QUARANTINED |
| scan_summary | JSONB | Scan results |
| extracted_metadata | JSONB | Extracted document metadata |
| created_at | TIMESTAMPTZ | Ingestion time |
| indexed_at | TIMESTAMPTZ | RAG indexing time |

### document_chunks

| Column | Type | Description |
|--------|------|-------------|
| chunk_id | UUID PK | Chunk identifier |
| doc_id | UUID FK | Parent document |
| chunk_index | INT | Chunk sequence number |
| text | TEXT | Chunk text content |
| embedding | VECTOR | pgvector embedding |
| page_number | INT | Source page (if PDF) |
| offset_start | INT | Character offset start |
| offset_end | INT | Character offset end |

### folder_acl

| Column | Type | Description |
|--------|------|-------------|
| folder_id | TEXT PK | Drive folder ID |
| facility_id | TEXT | Mapped facility |
| allowed_roles | TEXT[] | Roles that can retrieve |
| allowed_agents | TEXT[] | Agent types that can retrieve |

## Security Controls

### Rate Limits
- Cache discovery API responses (gws handles this)
- Throttle Drive downloads (configurable per-folder)
- Use incremental sync based on `modifiedTime`
- Maintain local ingest cursor per folder

### Access Scopes
- Separate service account per environment
- Restrict Drive access to specific Shared Drive or folder subtree
- Least-privilege OAuth scopes

### Audit
- Log every `gws` MCP tool call through `tool_security_registry.py`
- Log `doc_id` and `drive_file_id` for every retrieval result
- All scan results stored in `ingested_documents.scan_summary`

### Agent Permissions
- **Read-only agents:** Retrieval only, no Drive writes/deletes
- **Automation agents:** Can write summaries back to Drive, update Sheets tracker (approved flows only)

## Related Documents

- [Hybrid Knowledge Layer](../02-architecture/hybrid-knowledge-layer.md) - Context assembly using all data layers
- [Brick Ontology Layer](../02-architecture/brick-ontology-layer.md) - Asset graph for equipment relationships
- [RAG Integration Overview](../08-ai-ml/rag-integration-overview.md) - Existing vector database setup
- [n8n Email Pipeline](n8n-email-pipeline.md) - Existing email-based document intake
- [Security Pipeline](../09-security/) - Document scanning and trust levels
