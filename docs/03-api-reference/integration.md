# Integration API

## Overview

API endpoints for integration setup and log ingestion.

## Endpoints

- GET /sources
- GET /sources/{source_id}
- POST /sources
- PATCH /sources/{source_id}
- DELETE /sources/{source_id}
- POST /sources/{source_id}/activate
- POST /sources/{source_id}/deactivate
- POST /detect-format
- GET /sources/{source_id}/mappings
- POST /sources/{source_id}/mappings

... and 21 more endpoints


## Implementation

For full details, see: `backend/app/api/integration.py`
