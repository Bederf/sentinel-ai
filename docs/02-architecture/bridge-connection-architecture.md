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
| POST | `/api/telemetry/read` | Bearer token |
| POST | `/api/telemetry/write` | Bearer token |

## Authentication: Per-Site Tokens

The bridge supports **global** and **per-site** tokens via environment variables:

| Env Var | Purpose |
|---------|---------|
| `BRIDGE_API_TOKEN` | Global token — used for bridge-level auth |
| `BRIDGE_API_TOKEN_SITE002` | Site-002 specific token (per-site override) |

The bridge validates site-specific endpoints against the per-site token.
Global `BRIDGE_API_TOKEN` alone will **not** authenticate site-specific requests.

### Current Tokens (site-002)

- Global: `GDGKc5HuaKDvm9CXb9nsOx50TvCrNqfazRgATrnlC2TKiK2cJHYWudISBnII_VYh`
- Site-002: `ScUAjUet7i2vvcE0fuzn6dsF3C+YRMWbf8yMWwdoYbw=`

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
# From bridge VPS:
systemctl status sentinel-bridge
journalctl -u sentinel-bridge -f
```

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

## Multi-Site Pattern

Each site can use a different bridge or protocol, configured entirely in DB:

```json
S002 (bridge):  { "base_url": "http://10.99.0.1:8080", "token": "..." }
S005 (bridge):  { "base_url": "http://10.99.0.5:8080", "token": "..." }
S00X (direct):  { "host": "192.168.10.50", "device_instance": 1234, "port": 47808 }
```

No code changes needed — `MultiSitePollingCoordinator` selects the adapter dynamically based on protocol and config.

## Connection Configs in Database

Configured sites as of 2026-05-03:

| Site | Protocol | Bridge URL | Status |
|------|----------|------------|--------|
| site-001 | bridge | http://10.99.0.1:8080 | Disabled (future) |
| site-002 | bridge | http://10.99.0.1:8080 | Active, telemetry flowing |
| site-005 | bridge | (configured on bridge) | Not tracked in SENTINEL DB yet |

Site-005 (Busamed Gateway Private Hospital, Umhlanga) is configured on the bridge (Niagara/Tridium, oBIX protocol) but not yet in `site_adapter_config`.
