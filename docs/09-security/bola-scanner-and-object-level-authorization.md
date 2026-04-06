---
title: "BOLA Scanner & Object-Level Authorization"
type: "policy"
status: "draft"
version: "1.0.0"
created: "2026-03-31"
updated: "2026-03-31"
tags: ["sentinel", "documentation"]
related: []
domain: "security"
audience: "all"
complexity: "intermediate"
estimated_read_time: 10
---

# BOLA Scanner & Object-Level Authorization

**Version:** 3.0 | **Date:** 2026-03-11 | **Status:** Complete — 158 endpoints protected, 57 integration tests

## Overview

BOLA (Broken Object Level Authorization) is OWASP API Security Top 10 #1. It occurs when an API uses a user-supplied object ID and fails to enforce object-level authorization on it.

SENTINEL's API has 614 parameterized endpoints — each one is a potential BOLA attack surface.

## Initial Scan Results

| Metric | Count | Percentage |
|--------|-------|------------|
| Total parameterized endpoints | 614 | 100% |
| **FAIL (BOLA vulnerability)** | **180** | **29%** |
| PASS (correctly blocked) | 235 | 38% |
| INCONCLUSIVE (404/500) | 199 | 32% |

## Root Cause

No `require_site_access()` dependency existed. Many endpoints had:
- Zero authentication (`buildings.py`, `equipment.py`, `device_controls.py`, `energy_centre.py`)
- Authentication but no object-level authorization check
- No verification that the requesting user has access to the referenced site/equipment

## Fix: Object-Level Authorization Dependencies

Two new FastAPI dependencies added to `backend/app/middleware/auth_middleware.py`:

### `require_site_access(site_param, auth_level)`

Protects endpoints with `{site_id}` or `{building_id}` path parameters.

```python
@router.get("/api/sites/{site_id}")
async def get_site(
    site_id: str,
    auth: AuthContext = Depends(require_site_access("site_id")),
):
    ...
```

**Authorization flow:**
1. Authenticate (JWT/API key) — 401 if missing
2. Check auth level (AUTHENTICATED/OPERATOR/ADMIN) — 403 if insufficient
3. ADMIN role bypasses all site checks
4. Demo config check: if user has `allowedSites`, verify site is in list
5. Database check: query `user_site_access` table for (email, site_code)
6. Default deny on mismatch

### `require_equipment_access(equipment_param, auth_level)`

Protects endpoints with `{equipment_id}` or `{equipment_code}` path parameters.

Derives site from equipment code format: `S002-AHU-B1-001` → `site-002`, then applies the same site access check.

```python
@router.get("/api/equipment/{equipment_id}/controls")
async def get_controls(
    equipment_id: str,
    auth: AuthContext = Depends(require_equipment_access("equipment_id")),
):
    ...
```

### `_equipment_code_to_site(equipment_code)`

Helper function: `S002-AHU-B1-001` → `site-002`

Pattern: Equipment codes start with `S{NNN}` where NNN is the site number.

## Files Fixed

### Phase 1 (Initial)

| File | Endpoints Fixed | Previous Auth |
|------|----------------|---------------|
| `buildings.py` | 10 | None (public) |
| `device_controls.py` | 6 | None on reads, OPERATOR on execute |
| `energy_centre.py` | 12 | None (public) |
| `equipment.py` | 3 | None (public) |
| `sites.py` | 3 | Auth-only (no site scope) |
| `security.py` | ~10 | Mixed |

### Phase 2 (52 additional endpoints)

| File | Endpoints Fixed | Guard Type |
|------|----------------|------------|
| `desks.py` | 5 | `require_site_access` |
| `dispatch_optimizer.py` | 3 | `require_site_access` |
| `load_forecast.py` | 3 | `require_site_access` |
| `peak_demand.py` | 5 | `require_site_access` |
| `recommendations.py` | 3 | `require_site_access` |
| `sites_3d.py` | 6 | `require_site_access` |
| `solar_annual.py` | 3 | `require_site_access` |
| `sustainability.py` | 18 | `require_site_access` |
| `zone_ingestion.py` | 5 | `require_site_access` |
| `baseline.py` | 15 | `require_equipment_access` + `get_current_user` |
| `baselines.py` | 7 | `require_equipment_access` |

**Total protected endpoints: ~85 (Phase 1) + 73 (Phase 2) = ~158 endpoints**

## Verified Behavior

| Test | Result |
|------|--------|
| Unauthenticated → any endpoint | 401 Authentication required |
| bederf (site-002 only) → site-002 | 200 OK (allowed) |
| bederf (site-002 only) → site-003 | 403 No access to site |
| bederf → S002 equipment | 200 OK (allowed) |
| bederf → S003 equipment | 403 No access to equipment |
| admin → any site | 200 OK (ADMIN bypass) |

## BOLA Scanner Tool

Location: `security/bola-scanner/`

### Usage

```bash
cd security/bola-scanner

# Scan high-risk endpoints
python3 -m app --high-risk --report all

# Full scan (all 614 endpoints)
python3 -m app --report all

# Scan specific tags
python3 -m app --tags devices,sites --report json

# Scan with ZAP proxy
python3 -m app --proxy http://localhost:8080 --report all
```

### Architecture

```
bola-scanner/
├── app/
│   ├── main.py          # CLI entry point
│   ├── scanner.py       # Core BOLA probe logic
│   ├── auth.py          # SENTINEL auth helpers
│   ├── openapi_graph.py # OpenAPI spec parser
│   ├── models.py        # Data models
│   └── reporters.py     # Terminal/JSON/HTML reports
├── specs/
│   └── openapi.json     # Cached OpenAPI spec
├── reports/             # Generated scan reports
├── docker-compose.yml   # Scanner + ZAP stack
└── Dockerfile
```

### How It Works

1. Parse OpenAPI spec → extract parameterized endpoints
2. Authenticate as owner (admin) and attacker (operator)
3. Discover real resource IDs from list endpoints
4. For each endpoint: call as attacker with owner's resource ID
5. Classify response: 200 = FAIL, 401/403 = PASS, 404/500 = INCONCLUSIVE
6. Generate report with evidence

## Integration Tests

Location: `backend/tests/api/test_bola_authorization.py` — **57 tests**, all marked `@pytest.mark.security`.

### Test Strategy

- **Owner**: admin role, `allowedSites: ["site-002"]`
- **Attacker**: operator role, `allowedSites: ["site-003"]` (NO site-002 access)
- **Anon**: no auth context
- Patches `TESTING` env var to `"false"` and replaces `_authenticate_request` to inject controlled AuthContext
- Injects test demo configs via `monkeypatch` on `USER_DEMO_CONFIGS`

### Test Classes

| Class | Tests | What It Verifies |
|-------|-------|-----------------|
| `TestSiteEndpointBola` | 30 | Cross-site access blocked for buildings, desks, sustainability, peak-demand, load-forecast, dispatch, recommendations, solar, 3D config, zone-ingestion |
| `TestEquipmentEndpointBola` | 7 | Cross-site equipment access blocked (equipment code → site derivation) |
| `TestMutatingEndpointBola` | 11 | POST/PATCH/DELETE operations blocked (highest risk) |
| `TestCrossSiteAllowed` | 1 | Attacker CAN access their own site (no over-blocking) |
| `TestUnauthenticatedAccess` | 6 | No token → 401 |
| `TestAdminBypass` | 2 | Admin role correctly bypasses site restrictions |

### Coverage Distribution

| Resource Domain | Tests | Endpoints Covered | Methods |
|-----------------|-------|-------------------|---------|
| Buildings (detail, equipment, zones) | 3 | 3 | GET |
| Desks (list, stats, centroids) | 3 | 3 | GET |
| Sustainability (summary, emissions, efficiency, config, ESG, certs) | 7 | 7 | GET |
| Peak Demand (status, forecast, summary, approve) | 4 | 4 | GET, POST |
| Load Forecast (forecast, accuracy, retrain) | 4 | 3 | GET, POST |
| Dispatch Optimizer (schedule, compare, solve) | 3 | 3 | GET, POST |
| Recommendations (list, history, process) | 3 | 3 | GET, POST |
| Solar Annual (summary, simulate) | 2 | 2 | GET, POST |
| 3D Config (config, viewer-data, positions, create, delete) | 5 | 5 | GET, POST, PATCH, DELETE |
| Zone Ingestion (centroids, validate, zones POST, desks POST) | 4 | 4 | GET, POST |
| Device Controls (validate, recommend, execute) | 3 | 3 | POST |
| Baselines (active, report, summary, history, capture) | 5 | 5 | GET, POST |
| Unauthenticated access (no-token) | 6 | 6 | GET, POST |
| Cross-site allowed (own site) | 1 | 1 | GET |
| Admin bypass (own site, other site) | 2 | 2 | GET |
| Owner allowed (equipment, forecast) | 2 | 2 | GET |
| **Total** | **57** | **56 unique** | |

### Running

```bash
# BOLA tests only
pytest tests/api/test_bola_authorization.py -v

# All security tests (includes BOLA)
pytest -m security tests/api/ -v
```

## Remaining Work

- Remaining unprotected endpoints are primarily non-site-scoped (global endpoints, health checks, auth, chat)
- Cloudflare API Shield discovery running (check after 48hrs from 2026-03-11 for learned schema)

## Cloudflare API Shield

Enabled on zone `bms.aimthelaw.co.za`:
- **API Discovery**: Auto-maps endpoints from live traffic (24-48hrs)
- **BOLA Scanner**: Flags enumeration + pollution attacks
- **Schema Validation**: Can enforce learned schema on high-risk endpoints
- Dashboard: Security → API Shield → Endpoint Management

## Related

- OWASP API Security Top 10: API1:2023 Broken Object Level Authorization
- `backend/app/middleware/auth_middleware.py` — Authorization dependencies
- `backend/app/database/repositories/user_site_access_repository.py` — Site access DB
- `backend/app/config/demo_configs.py` — Demo user site restrictions
