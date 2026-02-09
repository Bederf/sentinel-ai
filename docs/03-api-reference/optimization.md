# Optimization API

## Overview

Optimization API endpoints for HVAC load shedding and AI optimization.

## Endpoints

- GET /optimization/scenarios
- GET /optimization/eskom-status
- GET /optimization/eskom-status/{site_id}
- GET /optimization/eskomsepush/areas
- GET /optimization/eskomsepush/allowance
- GET /optimization/thermal-runway
- POST /optimization/analyze
- POST /optimization/analyze-load-shedding
- POST /optimization/approve
- GET /optimization/status/{site_id}

... and 4 more endpoints


## Implementation

For full details, see: `backend/app/api/optimization.py`
