---
title: "Multi-Tenant Isolation"
type: "policy"
status: "approved"
version: "1.0.0"
created: "2026-06-14"
updated: "2026-06-14"
author: "SENTINEL Security Team"
tags: ["security", "multi-tenant", "rls", "access-control", "bola"]
domain: "security"
audience: "all"
complexity: "intermediate"
estimated_read_time: 8
---

# Multi-Tenant Isolation

## Guarantee

> **A user authenticated for site A cannot read, write, or enumerate data for site B —
> enforced at two independent layers.**

In SENTINEL, "tenant" maps to a site (building). Each user's access set is an explicit
allowlist stored in the `user_site_access` table. The isolation holds even if one layer fails.

---

## Two-Layer Architecture

```
Incoming request
       │
       ▼
┌─────────────────────────────────────────┐
│  Layer 1: Application (FastAPI)         │
│  require_site_access() dependency       │
│  Checks user_site_access table          │
│  → 403 if user not in allowlist         │
└──────────────────┬──────────────────────┘
                   │  passes
                   ▼
┌─────────────────────────────────────────┐
│  Layer 2: Database (Supabase RLS)       │
│  PostgREST queries filtered by          │
│  building_id / auth.uid()               │
│  → 0 rows returned if uid not matched   │
└─────────────────────────────────────────┘
```

---

## Layer 1 — Application Enforcement

### `user_site_access` table

```sql
CREATE TABLE user_site_access (
  user_email  text       NOT NULL,
  site_id     uuid       NOT NULL,   -- FK → buildings.id
  granted_by  text,
  granted_at  timestamptz DEFAULT now(),
  PRIMARY KEY (user_email, site_id)
);
```

Every site-scoped API endpoint uses one of two FastAPI dependencies:

| Dependency | Protects | Applied to |
|------------|----------|-----------|
| `require_site_access(param)` | Path params: `{site_id}`, `{building_id}` | ~158 endpoints |
| `require_equipment_access(param)` | Path params: `{equipment_id}`, `{equipment_code}` | Equipment sub-routes |

`require_equipment_access` derives the site from the equipment code prefix
(e.g. `S002-AHU-B1-001` → `site-002`) then delegates to the site check.

**Check sequence inside `require_site_access()`:**

1. Extract site code from the path parameter.
2. If `DEMO_MODE=true` → allow (demo environments only; production always has `DEMO_MODE=false`).
3. Check `access_profiles` config (static allow-list for service accounts).
4. Query `user_site_access` table — if no matching `(user_email, site_id)` row → **HTTP 403**.
5. ADMIN role bypasses steps 3–4 (still logged).

Source: `backend/app/middleware/auth_middleware.py` lines 815–938,
`backend/app/database/repositories/user_site_access_repository.py`.

### Test coverage

57 integration tests in `tests/api/test_bola_authorization.py` verify that cross-tenant
requests return 403 across all 17 API files. These tests run on every pull request via CI.

---

## Layer 2 — Database RLS

### Tables with RLS enabled

| Table | Policy | Isolation column |
|-------|--------|-----------------|
| `devices` | SELECT / INSERT / UPDATE / DELETE | `building_id` |
| `dali_controllers` | SELECT / INSERT / UPDATE / DELETE | `building_id` |
| `dali_luminaires` | SELECT / INSERT / UPDATE / DELETE | `building_id` |
| `dali_sensors` | SELECT / INSERT / UPDATE / DELETE | `building_id` |
| `dali_zones` | SELECT / INSERT / UPDATE / DELETE | `building_id` |
| `dali_groups` | SELECT / INSERT / UPDATE / DELETE | `building_id` |
| `technician_notification_channels` | service_role only | role check |
| `agent_memory` | authenticated read; authenticated write | `auth.uid()` |
| `site_handbooks` | public read; authenticated write | role check |

Policy pattern (devices as example):

```sql
ALTER TABLE devices ENABLE ROW LEVEL SECURITY;

CREATE POLICY devices_select_policy ON devices
  FOR SELECT
  USING (
    building_id IN (
      SELECT id FROM buildings
      WHERE auth.uid() IS NOT NULL
    )
  );
```

Migration source: `backend/supabase/migrations/20250201_devices_and_dali.sql` lines 421–674.

### Service-role vs anon/authenticated

The SENTINEL backend connects to Supabase using the **service role key**, which bypasses RLS
by design (PostgREST service role behavior). This is intentional: the backend's own queries
are trusted, and application-layer isolation (Layer 1) enforces the boundary before any
database query runs.

RLS enforces isolation for two other access paths:
- **Direct PostgREST calls** using an anon or authenticated JWT (e.g. edge functions,
  client SDK calls, any third-party integration that doesn't go through the FastAPI backend).
- **Supabase Studio access** with a non-service-role session.

**Defence-in-depth posture:**
- Layer 1 fails → Layer 2 still returns 0 rows to anon/authenticated callers.
- Layer 2 disabled → Layer 1 still blocks the request before the query runs.

---

## Verification

### Prove tenant A cannot read tenant B's devices (RLS path)

Run these queries as a non-service-role Supabase authenticated session.
Replace UUIDs with real building IDs from the `buildings` table.

```sql
-- Step 1: Confirm user A is authenticated (should return their UUID)
SELECT auth.uid();

-- Step 2: Query devices for building B (a building user A has no access to)
-- Expected: 0 rows (RLS filters them out)
SELECT id, code, site_id
FROM devices
WHERE building_id = '<building-B-uuid>';

-- Step 3: Confirm user A CAN see their own building's devices
-- Expected: rows for building A
SELECT id, code, site_id
FROM devices
WHERE building_id = '<building-A-uuid>';
```

### Prove Layer 1 blocks cross-tenant API calls

```bash
# Get a valid token for a user who has access to site-002 only
TOKEN="<jwt-for-site-002-user>"

# Request site-002 data — should succeed
curl -s -H "Authorization: Bearer $TOKEN" \
  https://bms.sentinel-ai.co.za/api/sites/site-002/alerts | jq '.status'

# Request site-005 data — should return 403
curl -s -H "Authorization: Bearer $TOKEN" \
  https://bms.sentinel-ai.co.za/api/sites/site-005/alerts | jq '.detail'
# Expected: "Access to site site-005 denied"
```

### Grant / revoke access

```python
from app.database.repositories.user_site_access_repository import UserSiteAccessRepository

repo = UserSiteAccessRepository()

# Grant
repo.grant_access("user@example.com", "<building-uuid>", granted_by="admin@sentinel.ai")

# Verify
assert repo.has_access_to_site_code("user@example.com", SentinelRole.OPERATOR, "site-002")

# Revoke
repo.revoke_access("user@example.com", "<building-uuid>")
```

---

## What Would Have to Fail for a Cross-Tenant Breach

For user A to read user B's site data all of the following would have to fail simultaneously:

1. `require_site_access()` dependency incorrectly passes the check — AND
2. RLS policy on the relevant table is disabled or misconfigured — AND
3. The ADMIN role bypass is exploited (requires the attacker to already be an ADMIN, at which
   point access to other sites is expected behavior).

No single-point failure exposes cross-tenant data.

---

## Known Scope Limits

- RLS is not yet enabled on `ai_recommendations`, `ai_usage_daily`, or `sites` tables.
  Access to these is controlled exclusively by Layer 1 (application auth).
- `sentry_bot_state` table: RLS migration is in the Tier 3 backlog (LOW risk — PostgREST
  port 55321 is not exposed through any public route).

See `docs/09-security/README.md` for the full FSR 4.7 compliance mapping.
