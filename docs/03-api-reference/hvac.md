---
title: "Hvac API"
type: "reference"
status: "draft"
version: "1.0.0"
created: "2026-03-31"
updated: "2026-03-31"
tags: ["sentinel", "documentation"]
related: []
domain: "hvac"
audience: "all"
complexity: "intermediate"
estimated_read_time: 10
---

# Hvac API

## Overview

HVAC Module API endpoints.

## Endpoints

- GET /overview/{site_id}
- GET /zones
- GET /zones/{zone_id}
- POST /zones/{zone_id}/setpoint
- GET /equipment
- GET /equipment/{equipment_id}
- GET /chillers
- POST /chillers/{chiller_id}/control
- POST /chillers/{chiller_id}/setpoint
- GET /chillers/{chiller_id}/setpoint

... and 2 more endpoints


## Implementation

For full details, see: `backend/app/api/hvac.py`
