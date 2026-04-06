---
title: "Sites"
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


## Province Requirement

`POST /api/sites` requires `region` (province). If omitted or blank, the API returns 400.

## Automatic Municipal Tariff Setup

When a site is created (Supabase enabled), the system auto-seeds:
- A default municipal tariff schedule based on `region`
- A municipal account for electricity billing

This ensures municipal billing is usable immediately after onboarding.
