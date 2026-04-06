---
title: "Simulation API"
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

# Simulation API

## Overview

Simulation API endpoints for BMS Intelligence

## Endpoints

- GET /status
- GET /equipment
- GET /equipment/{equipment_id}
- POST /fault/inject
- DELETE /fault/clear/{equipment_id}
- POST /control/speed
- POST /stop
- POST /start
- GET /stats
- POST /scenario/{scenario_name}

... and 20 more endpoints


## Implementation

For full details, see: `backend/app/api/simulation.py`
