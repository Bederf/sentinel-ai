---
title: "Concept Evolution Connector API"
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

# Concept Evolution Connector API

Base prefix: `/api/concept`

## Purpose

Site-network handoff endpoint for document uploads destined for MRI Concept Evolution (or equivalent on-site network storage API).

## Endpoint

`POST /documents/upload`

Multipart form fields:

- `file` (required)
- `site_id` (required)
- `metadata_json` (optional, JSON object string; default `{}`)

## Auth

- Requires authenticated session (`AuthLevel.AUTHENTICATED`).
- `uploaded_by_user_id` is injected by backend from auth context.

## Behavior

- Backend forwards file + metadata to SIMBIOT-configured API URL:
  - `SIMBIOT_API_URL` + `/documents/upload`
- Credentials sourced from SIMBIOT env config.
- Returns remote connector response payload.

## Error Handling

- `400` invalid `metadata_json`
- `502` upstream site-network/Concept upload failure
