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
