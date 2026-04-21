---
title: "Document Placement Policy"
type: "guide"
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

# Document Placement Policy

This policy defines where markdown documents should be stored.

## Root (`/`)
Use root only for canonical project entry documents and approved top-level governance docs.

Examples:
- `README.md`
- `AGENTS.md`
- `CLAUDE*.md`
- `docs/02-architecture/NAMING_CONVENTIONS.md`
- `FEATURES.md`
- `TODO.md`, `TODOdone.md`

## Planning Artifacts (`.planning/`)
Use for execution artifacts and workflow outputs.

Examples:
- Phase plans and summaries
- Validation reports
- Debug snapshots
- Temporary rollout notes
- Historical implementation logs

Recommended locations:
- Active work: `.planning/phases/<phase>/`
- Historical records: `.planning/archive/`

## Product/Engineering Documentation (`docs/`)
Use for durable documentation that should remain discoverable long-term.

Examples:
- Architecture docs
- API references
- Feature specs
- Integration guides
- Security and operations runbooks
- Testing and development standards

## Decision Rule
If a document answers "what happened during this run/task," it belongs in `.planning/`.
If it answers "how the system works or should be used long-term," it belongs in `docs/`.
If uncertain, store in `.planning/archive/` and link from the relevant docs index.
