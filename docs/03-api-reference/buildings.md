# Buildings API

## Overview

Building Management API — CRUD for buildings, equipment, zones, desks, and building configuration.

## Endpoints

- GET /api/buildings — List all buildings
- GET /api/buildings/{site_id} — Get building details
- POST /api/buildings — Create building
- PUT /api/buildings/{site_id}/config — Update building configuration (Phase 157)
- POST /api/buildings/{site_id}/desks — Upload desk data
- POST /api/buildings/{site_id}/zones — Upload zone data
- POST /api/buildings/{site_id}/activate — Activate building
- POST /api/buildings/{site_id}/deactivate — Deactivate building
- DELETE /api/buildings/{site_id} — Delete building
- GET /api/buildings/{site_id}/desks — List desks
- GET /api/buildings/{site_id}/zones — List zones
- GET /api/buildings/{site_id}/equipment-summary — Equipment summary
- GET /api/buildings/{site_id}/equipment — Full equipment list
- GET /api/buildings/{site_id}/schedule — Get operating hours (Phase 158)
- PUT /api/buildings/{site_id}/schedule — Update operating hours (Phase 158)
- GET /api/buildings/{site_id}/holidays — List holidays (Phase 158)
- POST /api/buildings/{site_id}/holidays — Add custom holiday (Phase 158)
- DELETE /api/buildings/{site_id}/holidays/{id} — Remove custom holiday (Phase 158)

### PUT /api/buildings/{site_id}/config

Update building metadata, optimization profile, and contacts from the Settings UI. ADMIN role required. Emits `CONFIG_CHANGE` audit event.

**Request body** (all fields optional):

| Field | Type | Description |
|-------|------|-------------|
| name | string | Building name |
| display_name | string | Display name |
| address | string | Street address |
| building_type | string | `commercial_office`, `retail`, `industrial`, `mixed_use` |
| floors | string[] | Floor list (e.g. `["B1", "L1", "L2", "Roof"]`) |
| sqm | int | Gross floor area |
| occupancy_capacity | int | Max occupants |
| total_desks | int | Desk count |
| parking_bays | int | Parking bay count |
| optimization_profile | string | `cost_saving`, `comfort`, `balanced` |
| control_tier | string | `human_in_loop`, `supervised`, `automatic` |
| features | object | Feature flags (e.g. `{"hvac": true, "solar": true}`) |
| contacts | object | FM name, email, emergency phone |

### Operating Schedule (Phase 158)

`GET/PUT /api/buildings/{site_id}/schedule` manages per-day operating hours stored in `building.json`. The `SiteSchedule` service reads this config at runtime, falling back to hardcoded defaults if absent.

### Holiday Calendar (Phase 158)

`GET/POST/DELETE /api/buildings/{site_id}/holidays` manages SA public holidays (read-only, 12 pre-seeded) and custom holidays (add/delete). Stored in `building.json` under the `holidays` key.

## Implementation

For full details, see:
- `backend/app/api/buildings.py` — Building CRUD + config
- `backend/app/api/building_schedule.py` — Operating hours
- `backend/app/api/holiday_calendar.py` — Holiday calendar
