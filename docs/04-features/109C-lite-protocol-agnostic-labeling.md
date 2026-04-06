---
title: "Phase 109C-lite: Protocol-Agnostic Labeling"
type: "spec"
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

# Phase 109C-lite: Protocol-Agnostic Labeling

## Purpose
Reduce protocol lock-in in user-facing language without changing optimization or control behavior.

## Scope
- UI label updates only (cards and panel text)
- Additive metadata field in live occupancy payloads
- No threshold, safety, routing, or write-path changes

## Terminology
- Prefer **occupancy signals** over protocol-specific wording
- Prefer **lighting/occupancy source** over protocol-specific source names

## Backward Compatibility
- Existing endpoints and fields remain intact
- New field is additive: `source_type` (example: `lighting_protocol`)
- Existing clients continue to work without changes

## Explicit Non-Goals
- No control logic changes
- No module activation changes
- No ingestion enforcement changes
