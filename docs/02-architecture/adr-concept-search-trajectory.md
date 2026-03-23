---
title: "ADR-005 — Canonical Document RAG vs Concept Search Service"
status: "accepted"
date: 2026-03-25
authors: ["Sentinel Platform Team"]
---

# Decision Record: Concept search trajectory

## Context

- Canonical Document RAG is now the telemetry-rich retrieval backbone for all core documents (hugely improved grounding, citations, OCR fallback, Prometheus metrics, `retrievalTelemetry` API exposure).
- The existing Concept Search Service remains a separate ingestion + query surface for Concept documents. Clients and tooling sometimes treat it as “Concept-specific RAG,” which introduces duplication and inconsistent instrumentation.
- We must decide whether to keep Concept Search Service separate, converge it into the Canonical RAG, or live somewhere in between; whichever path we choose should be recorded formally so downstream teams know the target architecture.

## Options

1. **Keep Concept Search Service separate**
   * Pros: Domain-specific freedom, lower immediate risk, can continue Concept-only experiments.
   * Cons: Doubles ingestion paths, citation logic, metrics; increases long-term maintenance burden.

2. **Converge Concept Search onto the Canonical Document RAG**
   * Pros: Shared telemetry/citation instrumentation, single API surface, unified governance.
   * Cons: Requires migrating Concept doc ingestion, possibly rewriting Concept-specific tooling.

3. **Hybrid: maintain service but sync into canonical RAG**
   * Pros: Keeps existing Concept tooling in place while still surfacing canonical metrics.
   * Cons: Adds synchronization complexity between two stores, still leaves clients confused.

## Decision

- We **converge Concept Search Service into the Canonical Document RAG**.
- Rationale:
  * The telemetry/citation/instrumentation work now lives in Canonical RAG, so staying separate would require duplicating all of it; convergence avoids that duplication and ensures consistent metrics.
  * Clients already rely on the canonical `/api/technical/hybrid-context` telemetry/metrics, and a single RAG endpoint keeps the contract stable.
  * Concept-specific metadata can still be encoded during ingestion (tags, vendor labels) and surfaced via canonical chunk metadata; there’s no architectural need for a second retrieval path anymore.

## Consequences

- Create a migration plan: ingest Concept documents through the canonical chunk/metadata pipeline and retire the old Concept-specific fetch endpoint.
- Update documentation (this ADR, `docs/02-architecture/document-retrieval-canonical-note.md`, monitoring guides) to state that Concept content flows through Canonical Document RAG.
- Remove Concept-specific telemetry from service once canonical metrics prove reliable; rely on the new `retrievalTelemetry` signal instead.
- Communicate to downstream clients that `/api/technical/hybrid-context` is the canonical retrieval contract, and the Concept Search tool now wraps or proxies that canonical path.
