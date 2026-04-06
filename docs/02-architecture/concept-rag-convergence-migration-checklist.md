---
title: "Concept Search to Canonical RAG Migration Checklist"
type: "architecture"
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

# Concept Search to Canonical RAG Migration Checklist

| Owner | Area | Target Date | Notes |
| --- | --- | --- | --- |
| Platform Engineering | Canonical retrieval/telemetry rollout | TBD | Update with confirmed sprint or release date |
| Product/Domain Owner | Validation & stakeholder sign-off | TBD | Record actual decision date once gating passes |

## Purpose

Provide an execution checklist for converging `Concept Search Service` onto `Canonical Document RAG` following ADR-005.

## Scope

- In scope: API compatibility, deprecation controls, telemetry gates, cutover criteria.
- Out of scope: model training changes or unrelated retrieval surfaces.

## 1) Deprecation Flags

- [ ] Add backend feature flags:
  - `CONCEPT_SEARCH_PROXY_MODE=true|false` (route Concept search calls through canonical retrieval path)
  - `CONCEPT_SEARCH_LEGACY_READ_ENABLED=true|false` (allow legacy Concept retrieval during compatibility window)
  - `CONCEPT_SEARCH_WRITE_TO_CANONICAL=true|false` (dual-write/single-write ingestion mode)
- [ ] Expose active flag states in health/config metadata for auditability.
- [ ] Add startup logs that emit flag values and checksum at boot.

## 2) API Compatibility Window

- [ ] Define compatibility window start/end dates (recommended: 60-90 days).
- [ ] Keep legacy endpoint response shape stable during window.
- [ ] Ensure legacy endpoint includes canonical `retrievalTelemetry` block.
- [ ] Add deprecation response header on legacy endpoints:
  - `Deprecation: true`
  - `Sunset: <RFC-1123 date>`
  - `Link: <migration doc URL>; rel="deprecation"`
- [ ] Publish migration notice in API docs and release notes.

## 3) Telemetry Gates (Go/No-Go)

- [ ] Dashboard panels live for both paths:
  - p95/p99 retrieval latency
  - hit rate / hits-per-second
  - fallback rate
  - error rate (5xx + tool failures)
- [ ] Gate thresholds agreed and documented:
  - `p95_latency_delta <= +20%` vs legacy baseline
  - `hit_count_non_regression >= 95%` of baseline median
  - `fallback_rate <= 2%` over rolling 24h
  - `error_rate <= 1%` over rolling 24h
- [ ] 14-day stability window passes all thresholds before final cutover.

## 4) Data/Metadata Parity

- [ ] Canonical chunk metadata contains Concept-required tags (building/site/vendor/domain facets).
- [ ] Citation grounding fields are preserved and visible in response payloads.
- [ ] OCR fallback path validated for low-text scanned Concept PDFs.
- [ ] Sampling audit: 30 representative queries show equivalent or improved relevance.

## 5) Cutover Criteria

- [ ] All telemetry gates pass for 14 consecutive days.
- [ ] No P1/P2 incidents attributable to canonical proxy mode during window.
- [ ] Backward-compatibility tests pass in CI for both legacy and canonical routes.
- [ ] Stakeholder sign-off received from:
  - Platform Engineering
  - Operations
  - Product/Domain owner
- [ ] Change window and rollback plan approved.

## 6) Cutover Execution

- [ ] Set:
  - `CONCEPT_SEARCH_PROXY_MODE=true`
  - `CONCEPT_SEARCH_WRITE_TO_CANONICAL=true`
  - `CONCEPT_SEARCH_LEGACY_READ_ENABLED=false`
- [ ] Deploy during approved window.
- [ ] Run smoke suite:
  - hybrid-context response contract
  - citation grounding in answers
  - telemetry emission and dashboard refresh
- [ ] Monitor for 24h with enhanced alerting.

## 7) Rollback Criteria

- [ ] Immediate rollback if:
  - p95 latency regression > 40% for 30m
  - fallback rate > 5% for 30m
  - error rate > 2% for 15m
  - critical relevance regression reported by operations
- [ ] Rollback action:
  - `CONCEPT_SEARCH_LEGACY_READ_ENABLED=true`
  - `CONCEPT_SEARCH_PROXY_MODE=false`
  - Keep canonical writes enabled only if data integrity is confirmed

## 8) Post-Cutover Cleanup

- [ ] Remove legacy Concept retrieval code paths.
- [ ] Remove temporary dual-write/proxy flags after one release cycle.
- [ ] Mark migration complete in ADR and architecture index.
- [ ] Archive final evidence pack (metrics snapshots + validation report + sign-offs).
