# Bridge Connection Architecture

## Network Topology

SENTINEL backend connects to BMS sites through a **bridge service** — a REST API proxy running on a separate VPS. No direct BMS connections.

```
SENTINEL VPS                      Bridge VPS                     Site N BMS
(144.91.122.235)                  (separate server)              (local network)
┌──────────────────┐             ┌──────────────┐              ┌──────────────┐
│  FastAPI Backend  │  WireGuard  │  Bridge API  │  BACnet/     │  Desigo CC   │
│  Port 9095        ├────────────→│  Port 8080   ├─────────────→│  Niagara     │
│                   │  Encrypted  │  10.99.0.1   │  oBIX/REST   │  etc.        │
└──────────────────┘  Tunnel     └──────────────┘              └──────────────┘
```

## Why a Bridge

**FNB network policy** prohibits external internet from the BMS network. The bridge:
- Runs on a separate VPS inside a WireGuard VPN
- Exposes a REST API over the VPN tunnel
- Translates REST calls → BMS protocol (BACnet, Modbus, oBIX, Desigo REST)
- Returns telemetry as JSON

SENTINEL never touches BMS devices directly.

## WireGuard Tunnel

- Interface: `wg0`
- Bridge VPN IP: `10.99.0.1`
- SENTINEL VPN IP: dynamically assigned
- Allowed IPs: `10.99.0.0/24`

Check tunnel status:
```bash
wg show
# Expected: recent handshake (< 2 min), increasing transfer counters
```

## Bridge API Endpoints

| Method | Path | Auth |
|--------|------|------|
| GET | `/health` | No |
| GET | `/sites` | No |
| GET | `/sites/{site_id}/config` | No |
| GET | `/api/sites/{site_id}/health` | Bearer token |
| GET | `/api/sites/{site_id}/telemetry` | Bearer token |
| GET | `/api/sites/{site_id}/points` | Bearer token |
| GET | `/api/sites/{site_id}/devices` | Bearer token |
| GET | `/api/sites/{site_id}/objects` | Bearer token |
| POST | `/api/telemetry/read` | Bearer token |
| POST | `/api/telemetry/write` | Bearer token |

## Discovery Session Attestation

Every discovery run through `GET /api/simbiot/sites/{site_id}/capabilities` is now **persisted** with a unique `discovery_id`:

```json
{
  "site_id": "site-005",
  "discovery_id": "550e8400-e29b-41d4-a716-446655440000",
  "discovered_at": "2026-07-06T14:30:00Z",
  "adapter_type": "bridge",
  "summary": { "devices": 1, "points": 1078, "writable_points": 45 },
  "devices": [ ... ]
}
```

The `discovery_id` is a **permit** that:
- Proves the data came from a real scan (not fabricated)
- Expires after **10 minutes** (prevents stale commits)
- Can only be used **once** (marked `committed` after use)
- Must match the **site_id** (prevents cross-site replay)

This replaces the old "trust whatever JSON the frontend sends" model with cryptographic-like attestation without the crypto.

## Point Discovery and Writeability

For bridge-connected sites, the bridge object catalog is the source of truth for point existence and writeability.

`GET /api/sites/{site_id}/objects` returns the BACnet/object catalog with fields such as:

- `object_id` — exact bridge point ID, for example `S002-AHU-B1-001.DAMPER_POSITION`
- `equipment_id` — raw site equipment ID from the bridge/site
- `object_type` and `instance` — BACnet object metadata
- `point_type` — semantic role when provided, for example `command` or `setpoint`
- `writable` — whether the bridge reports that the point can be written

Sentinel must preserve `writable=true` when importing bridge objects into `point_asset_mappings`. The bridge write endpoint also enforces its site-side writable-point allowlist, so the bridge must keep that guard synced to the same object catalog. When the bridge guard is synced, a known-equipment bridge object with `writable=true` is a verified writable mapping for Sentinel readiness and approval prechecks.

Analog Value, Binary Value, and Multi-State Value points are not assumed writable from object type alone. They are candidates for control only when the bridge catalog marks the specific point as `writable=true`, and actual writes still require the bridge write guard to allow the exact `object_id`.

## Authentication: Per-Site Tokens

The bridge supports **global** and **per-site** tokens via environment variables. SENTINEL must use site-scoped tokens for site-specific bridge endpoints.

| Env Var | Purpose |
|---------|---------|
| `BRIDGE_API_TOKEN` | Legacy/global fallback only |
| `BRIDGE_API_TOKEN_SITE_002` | Site-002 bridge token |
| `BRIDGE_API_TOKEN_SITE_005` | Site-005 bridge token |
| `SIMBIOT_API_KEY_SITE_###` | Accepted site-scoped alias |

The bridge validates site-specific endpoints against the per-site token.
Global `BRIDGE_API_TOKEN` alone will **not** authenticate site-specific requests.

### Current Tokens

Do not store literal bridge tokens in documentation. Check the configured secret stores directly when rotating or debugging credentials.

### Storage

Tokens live in two places:

1. **Bridge VPS**: `/etc/sentinel-bridge/env` — bridge's own environment
2. **SENTINEL backend**: `/etc/sentinel/secrets.env` — `BRIDGE_API_TOKEN_SITE_###`
3. **Supabase**: `site_adapter_config.connection_config.token_env` — name of the env secret, not the token value

Do not store new literal bridge tokens in `site_adapter_config.connection_config.token`. Existing DB tokens are legacy fallback only and should be migrated to `token_env`.

### Updating Token in Database

For new sites or token rotation:

```sql
UPDATE site_adapter_config
SET connection_config = jsonb_set(
  connection_config,
  '{token}',
  '"NEW_TOKEN_HERE"'
)
WHERE site_id = 'site-002'
AND protocol = 'bridge';
```

## SENTINEL Side: Token Resolution

`MultiSitePollingCoordinator` reads `connection_config` from `site_adapter_config`:

1. Queries `site_adapter_config` for enabled bridge adapters
2. Extracts `connection_config.token` and `connection_config.base_url`
3. Passes to `ShadowModePollingService(site_id, bridge_url, bridge_token)`
4. Service creates HTTP client with bearer auth header

## Debugging

### Tunnel Down
```bash
wg show                    # Check handshake age
ping 10.99.0.1             # Test WireGuard connectivity
systemctl restart wg-quick@wg0
```

### Bridge Offline
```bash
curl http://10.99.0.1:8080/health    # Unauthenticated health check
```

Operational access from the Sentinel host is through the WireGuard bridge API. Do not assume SSH access or host-level service control from Sentinel.

### Token Mismatch
```bash
# Test with token from DB:
curl http://10.99.0.1:8080/api/sites/site-002/health \
  -H "Authorization: Bearer $(TOKEN)"

# 200 = auth OK, 401 = token mismatch, 403 = no token sent
```

### BMS Devices Offline (behind bridge)
```json
{"status":"ok","site_id":"site-002","site_available":false}
```
Bridge is reachable but cannot reach BMS — site-side issue.

## Ingestion Quality Gate

The bridge polling rate is automatically controlled by the site's onboarding phase:

| Phase | Poll Sampling | Purpose |
|-------|:------------:|---------|
| `commissioning` | 10% | New sites start here — protects baselines from startup noise |
| `shadow_live` | 50% | Building baselines, monitoring data quality |
| `advisory+` | 100% | Full trust, all data flows |

The gate is enforced in `ShadowModePollingService.poll()` by reading the site's `onboarding_phase` from Supabase and skipping poll cycles proportionally. See the policy gate system docs for promotion criteria.

## Multi-Site Pattern

Each site can use a different bridge or protocol, configured entirely in DB:

```json
S002 (bridge):  { "base_url": "http://10.99.0.1:8080", "token": "..." }
S003 (bridge):  { "base_url": "http://10.99.0.1:8080", "token": "..." }
S00X (direct):  { "host": "192.168.10.50", "device_instance": 1234, "port": 47808 }
```

Per-site adapter configs are saved via the SIMBIOT Connection Wizard into `site_adapter_config` with the correct protocol and connection details. No code changes needed — the coordinator selects the adapter dynamically.

## Connection Configs in Database

Configured sites as of 2026-05-28:

| Site | Protocol | Bridge URL | Status |
|------|----------|------------|--------|
| site-001 | bridge | http://10.99.0.1:8080 | Disabled (future) |
| site-002 | bridge | http://10.99.0.1:8080 | Active, telemetry flowing |
| site-003 | bridge | http://10.99.0.1:8080 | Active, commissioning phase (10% sampling) |

### New site onboarding flow

1. SIMBIOT Connection Wizard creates the site (Supabase + disk)
2. Wizard discovers points via bridge API → receives `discovery_id`
3. **Atomic commit** via `POST /api/onboarding/bridge-review/{site_id}/commit`
   - Includes `discovery_id` for attestation
   - Postgres RPC performs all upserts in one transaction
   - Equipment + mappings + modules + bridge status + state transition
   - **All-or-nothing**: if any step fails, nothing is committed
4. Bridge adapter config saved with `enabled: false` (disabled by default)
5. User toggles bridge ON in Settings → SIMBIOT Bridge
6. Site starts at `commissioning` phase → 10% poll sampling
7. Phase auto-promotes to `shadow_live` when quality gates pass (≥24h, ≥50 polls, quality ≥ 0.7)
8. User can optionally generate a **building twin** via Step 5 of the wizard

### Onboarding State Machine

The `site_onboarding_state` table tracks where a site is in the pipeline:

| State | Meaning |
|-------|---------|
| `created` | Site exists, nothing discovered yet |
| `discovered` | Points enumerated, awaiting review |
| `synced` | Capability sync completed |
| `canonical` | Equipment + mappings committed atomically |
| `live` | Modules active, data collection started |

A site can only be in one state at a time. The atomic commit transitions `discovered` → `canonical` in one transaction. If the commit fails, the site stays in `discovered` and the operator can retry.

### Atomic Commit (Postgres RPC)

The `commit_bridge_review()` function performs 11 steps in a single transaction:

1. Validate `discovery_id` (exists, matches site, active, <10 min old)
2. Upsert all `equipment` rows
3. Upsert all `point_asset_mappings` rows
4. Update `sites.equipment_count`
5. Upsert `site_module_configs`
6. Upsert `site_modules` (with `phase_override='shadow'`)
7. Mark `bridge_discovered_equipment` as `onboarded`
8. Mark discovery session `committed`
9. Transition `site_onboarding_state` → `canonical`
10. Return summary JSONB

If any step fails, **Postgres rolls back everything**. No more half-finished sites with orphaned equipment or missing mappings.

Site-005 (Busamed Gateway Private Hospital, Umhlanga) is configured on the bridge (Niagara/Tridium, oBIX protocol) and now uses the atomic commit path.
