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

The bridge supports **global** and **per-site** tokens via environment variables:

| Env Var | Purpose |
|---------|---------|
| `BRIDGE_API_TOKEN` | Global token — used for bridge-level auth |
| `BRIDGE_API_TOKEN_SITE002` | Site-002 specific token (per-site override) |

The bridge validates site-specific endpoints against the per-site token.
Global `BRIDGE_API_TOKEN` alone will **not** authenticate site-specific requests.

### Current Tokens

Do not store literal bridge tokens in documentation. Check the configured secret stores directly when rotating or debugging credentials.

### Storage

Tokens live in two places:

1. **Bridge VPS**: `/etc/sentinel-bridge/env` — bridge's own environment
2. **Supabase**: `site_adapter_config.connection_config.token` — SENTINEL's source of truth

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
2. Wizard discovers 1006+ points via bridge API
3. Bridge adapter config saved with `enabled: false` (disabled by default)
4. User toggles bridge ON in Settings → SIMBIOT Bridge
5. Site starts at `commissioning` phase → 10% poll sampling
6. Phase auto-promotes to `shadow_live` when quality gates pass (≥24h, ≥50 polls, quality ≥ 0.7)
7. User can optionally generate a **building twin** via Step 5 of the wizard

Site-005 (Example Hospital Private Hospital, Umhlanga) is configured on the bridge (Niagara/Tridium, oBIX protocol) but not yet in `site_adapter_config`.
