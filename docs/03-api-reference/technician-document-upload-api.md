---
title: "Technician Document Upload API"
type: "reference"
status: "draft"
version: "1.0.0"
created: "2026-03-31"
updated: "2026-03-31"
tags: ["sentinel", "documentation"]
related: []
domain: "bms"
audience: "all"
complexity: "intermediate"
estimated_read_time: 10
---

# Technician Document Upload API

Base prefix: `/api/documents`

## Purpose

Technician-specific upload endpoint for equipment/compliance documentation with strict metadata validation and login-derived site/user binding.

## Endpoint

`POST /technician/upload`

Multipart form fields:

- `file` (required)
- `equipment_id` (required)
- `document_name` (required, controlled allowlist)
- `document_sub_class` (required, controlled allowlist)
- `category_discipline` (required, controlled allowlist)
- `document_creation_date` (required, `YYYY-MM-DD`)
- `trigger_date` (required, `YYYY-MM-DD`)
- `title` (optional)
- `site_id` (optional; only used for admin/multi-site cases)

## Identity & Site Binding Rules

- `uploaded_by_user_id` is always derived from authenticated session.
- For non-admin users, `site_id` is derived from user-site allocation.
- Client-side site override is not accepted for single-site technician users.
- If no site allocation exists, upload is rejected.

## Validation Rules

- Controlled values required for `document_name`, `document_sub_class`, `category_discipline`.
- Date format must be `YYYY-MM-DD`.
- `trigger_date` cannot be before `document_creation_date`.
- Upload security scan is applied before storage/indexing.
- Duplicate detection:
  - hard duplicate: same file hash + same site
  - soft duplicate: same `document_name` + `document_creation_date` + `equipment_id` on same site

## Per-Site Storage Routing

- Storage is resolved per site by policy in `backend/app/data/site_document_storage_policies.json`.
- Supported modes:
  - `local` (default): local/cloud ingestion pipeline with indexing
  - `cloud`: currently same ingestion path as `local`
  - `site_network`: forwards upload to site-network connector endpoint
- Optional policy flags:
  - `dual_write`: write both local pipeline and site-network target
  - `fallback_to_local`: if site-network upload fails, fallback to local pipeline

## Expiry & Retention (Phase 2 scaffold)

- Backend now derives `retention_rule_key` from document type mapping.
- `expiry_date` is calculated from `trigger_date + retention_rule_days`.
- `is_expired` is evaluated at upload time.
- `alert_offsets_days` is returned as policy guidance (`[90, 30, 7]`).
- Full scheduled alert dispatch is a later phase.

## Response

Returns standard document upload payload plus technician metadata:

- `document_id`
- `title`
- `chunk_count`
- `indexing_status`
- `storage_path`
- `site_id`
- `uploaded_by_user_id`
- `document_name`
- `document_sub_class`
- `category_discipline`
- `document_creation_date`
- `trigger_date`
- `retention_rule_key`
- `expiry_date`
- `is_expired`
- `alert_offsets_days`
- `storage_mode`
