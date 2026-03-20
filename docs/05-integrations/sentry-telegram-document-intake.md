---
title: "Sentry Telegram Document Intake"
type: "integration"
status: "implemented"
version: "1.0.0"
created: "2026-03-17"
updated: "2026-03-17"
author: "SENTINEL Development Team"
tags: ["sentry", "telegram", "concept", "document-intake", "site-002"]
related:
  - "05-integrations/SENTRY_INTEGRATION.md"
  - "05-integrations/simbiot-concept-connector.md"
domain: "integrations"
audience: "developers"
complexity: "intermediate"
estimated_read_time: 10
---

# Sentry Telegram Document Intake

## Purpose

Phase 2 adds a guided document intake workflow through the Sentry Telegram bot.

This is not chat and not document analysis. It is assisted capture of the minimum metadata required to save a raw technician-uploaded file into Concept in a predictable location with a predictable name.

## Scope

When a technician sends a photo or document file to the Sentry bot:

1. Sentry detects the upload
2. Sentry resolves the technician's `site_id`
3. Sentry asks a short guided metadata flow
4. SENTINEL downloads the Telegram file
5. SENTINEL writes the raw file to the Concept raw-document store
6. SENTINEL returns the saved reference to Sentry

Important boundary:

- The upload path saves the raw file only
- A separate ingestion script or timer later reads new Concept files and indexes them into SENTINEL search

The upload request path does not run retrieval indexing.

## Site Resolution

The bot does not ask the technician to choose a building for this phase.

- `telegram_user_id` is mapped to a technician record
- the technician record resolves to a primary `site_id`
- if no site mapping exists, the intake flow must stop with an admin-facing setup message

The user sees the building name, but the stored scope key is always `site_id`.

Example:

- user-facing label: `Centre Court`
- stored value: `site-002`

## Guided Flow

### Trigger

Technician sends a photo or file to the Sentry bot.

### Bot flow

1. Confirm the resolved site context
2. Ask equipment type
3. Ask document type
4. Ask for one optional free-text note
5. Show confirmation
6. Save

### Prompt sequence

Bot:

```text
I received a document for Centre Court. Let's file it correctly.

What type of equipment is this for?
```

Options:

- Generator
- Lift
- HVAC
- Pump
- Electrical panel
- Fire system
- Other

Next prompt:

```text
What type of record is this?
```

Options:

- Service sheet
- Job card
- Inspection sheet
- Certificate
- Maintenance report
- Commissioning sheet
- Other

Notes prompt:

```text
Any extra notes?

Reply with one message, or tap Skip.
```

Confirmation prompt:

```text
Please confirm before save:

Building: Centre Court
Equipment type: Generator
Document type: Service sheet
Notes: Quarterly service. Gen 2.
```

Actions:

- Save to Concept
- Cancel

## Session State

The intake flow uses a dedicated Telegram conversation session.

Session states:

- `file_received`
- `awaiting_equipment_type`
- `awaiting_document_type`
- `awaiting_notes`
- `awaiting_confirmation`
- `processing`
- `saved`
- `failed`

The session is keyed by `chat_id` and reuses the existing Sentry conversation session timeout.

## Metadata Contract

### Required fields

```json
{
  "source": "telegram_sentry",
  "site_id": "site-002",
  "telegram_file_id": "abc123",
  "telegram_user_id": "tg_456",
  "telegram_chat_id": "chat_789",
  "equipment_type": "generator",
  "document_type": "service_sheet",
  "received_at": "2026-03-17T10:15:00Z"
}
```

### Optional fields

```json
{
  "notes": "Quarterly service. Gen 2. Contractor on site."
}
```

## Naming and Path Rules

The technician does not type the final file name.

SENTINEL generates the file name from:

- site name
- equipment type
- document type
- received date
- file extension

Example generated name:

```text
CENTRE-COURT_GENERATOR_SERVICE-SHEET_2026-03-17.jpg
```

Concept path rule for the raw upload store:

```text
{Site Name}/{Equipment Type}/{Document Type}/
```

Example:

```text
Centre Court/Generator/Service Sheet/
```

## Current Implementation Boundary

The current repository implementation uses a dedicated raw-document adapter service for Concept document storage.

That adapter is intentionally isolated because:

- the Telegram flow should not know Concept storage details
- the live Concept file-write integration may differ from development storage
- the later ingestion job should consume a stable raw-document location

In development, the adapter persists raw files and metadata under the repository data directory while preserving the same `site_id`, naming, and path semantics expected by the later ingestion job.

The second-cut wiring also persists an intake record and runs the repository's document scanner before the raw file is saved.

## API and Callback Shapes

### Telegram message ingress

Existing endpoint:

`POST /api/sentry/telegram/message`

Important fields:

- `chat_id`
- `user_id`
- `has_photo`
- `photo_file_id`
- `has_document`
- `document_file_id`
- `message_id`

### Telegram callback data

Document intake callback format:

```text
docintake:{action}:{value}
```

Examples:

- `docintake:equipment:generator`
- `docintake:document:service_sheet`
- `docintake:notes:skip`
- `docintake:confirm:save`
- `docintake:confirm:cancel`

## Success Response

The save result returned to Sentry should contain at least:

```json
{
  "status": "saved",
  "concept_document_id": "concept_raw_123",
  "site_id": "site-002",
  "site_name": "Centre Court",
  "concept_path": "Centre Court/Generator/Service Sheet",
  "file_name": "CENTRE-COURT_GENERATOR_SERVICE-SHEET_2026-03-17.jpg"
}
```

## Non-Goals

Out of scope for this phase:

- immediate ingestion into SENTINEL search
- document Q and A
- document summarisation
- duplicate detection
- multi-photo merge
- OCR-based metadata suggestion on the upload request path

Those belong in later ingestion and optimization phases.
