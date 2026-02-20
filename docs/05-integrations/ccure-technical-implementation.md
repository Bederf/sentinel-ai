# C•CURE 9000 — Technical Implementation Guide

## Architecture Overview

The C•CURE integration is built on two parallel paths:

1. **Demo Mode (Phase 58.2)** — Uses pre-loaded JSON data for demonstrations
2. **Live Mode (Phase 58.3+)** — Integrates with victor Web Service API for production deployments

Both paths share the same intelligence layer, allowing seamless testing and production use.

---

## Component Architecture

### CCureAdapter (`backend/app/services/ccure/ccure_adapter.py`)

**Purpose:** Abstracted interface for C•CURE data access. Handles both demo and live modes.

**Key Methods:**

```python
class CCureAdapter:
    async def connect() → bool
        """Connect to C•CURE (loads demo data or authenticates to victor API)"""

    async def get_badge_events(since: datetime, limit: int) → List[Dict]
        """Fetch badge events since timestamp"""

    async def get_controllers() → List[CCureController]
        """Get all iSTAR controllers with health status"""

    async def get_door_status(door_id: str) → Dict
        """Get specific door/reader status"""

    async def get_occupancy(zone_id: str) → Dict
        """Get anti-passback zone occupancy"""

    async def get_personnel(badge_id: str) → Optional[CCurePersonnel]
        """Look up badge holder details"""
```

**Demo Mode Flow:**
```
CCureAdapter(demo_mode=True)
    ↓
await adapter.connect()
    ↓ Loads ccure_demo_data.json
self._demo_data = {
    "badge_events": [...],
    "controllers": [...],
    "zones": [...],
    "personnel": [...]
}
    ↓
await adapter.get_badge_events() → Returns demo events
```

**Live Mode Flow (Phase 58.3):**
```
CCureAdapter(
    api_url="https://ccure.example.com/api",
    license_guid="SENTINEL-CCURE-GUID-xxxxx",
    username="sentinel_operator",
    password="<secure>",
    demo_mode=False
)
    ↓
await adapter.connect()
    ↓ POST to victor API auth endpoint
    ↓ JWT token stored in self._token
    ↓
await adapter.get_badge_events()
    ↓ GET {api_url}/api/access-events?since=...&limit=...
    ↓ Authorization: Bearer {self._token}
```

---

### SecurityOccupancyService Intelligence Methods

**Location:** `backend/app/services/security_occupancy_service.py`

**New Methods (Phase 58.2):**

#### detect_after_hours_anomaly(site_id) → List[Dict]

Detects badge access outside business hours (18:00-06:00) with HVAC/lighting correlation.

**Algorithm:**
1. Get all badge events from last 24 hours
2. Filter events where `after_hours=True` OR timestamp hour ∈ [18-23, 0-5]
3. For each after-hours event:
   - Check if HVAC zone activated within 15 minutes
   - Check if lighting zone activated within 15 minutes
   - If either: create anomaly with correlation data
4. Estimate energy impact: HVAC (+3.5 kWh/hr) + Lighting (+0.75 kWh/hr)
5. Generate recommendation for operator

**Demo Mode:** Simulates HVAC/lighting activation (Phase 58.3+ will query actual systems)

#### detect_security_equipment_health_issues() → List[Dict]

Detects controller offline events and correlates with network/UPS infrastructure.

**Algorithm:**
1. Get all controllers from C•CURE
2. For each controller with status="offline":
   - Correlate with network switch port status
   - Correlate with UPS battery level
   - If network port down: "Check switch connection"
   - If network OK but controller offline: "Check power or firmware"
3. Create anomaly with network/UPS correlation

**Demo Mode:** Returns mock network/UPS status (Phase 58.3+ will query actual infrastructure)

---

## Data Models

### Extended security_badge_events

**New Columns (Migration 060):**
```sql
event_type TEXT                -- C•CURE event type (access_granted, forced_door, etc.)
clearance_level TEXT           -- Badge holder's access level (IT-ADMIN, FINANCE-STANDARD)
department TEXT                -- Badge holder's department (IT Operations, Finance)
after_hours BOOLEAN DEFAULT FALSE  -- Whether access was outside business hours (18:00-06:00)
```

### New Tables

#### security_anomalies
Tracks all detected security anomalies with cross-system correlations.

```python
@dataclass
class SecurityAnomaly:
    anomaly_id: Optional[UUID]
    anomaly_type: str            # after_hours_access, controller_offline, forced_door
    severity: str                # warning, critical, info
    badge_event_id: Optional[str]
    zone_id: Optional[str]
    description: str             # Human-readable anomaly description
    hvac_correlation: Optional[Dict]      # {zone_id, activation_time, setpoint_change}
    lighting_correlation: Optional[Dict]  # {zone_id, activation_time, brightness_change}
    energy_impact: Optional[str]          # "Estimated 4.25 kWh excess per hour"
    resolved: bool = False
    detected_at: datetime
    resolved_at: Optional[datetime]
    notes: Optional[str]
```

#### ccure_controllers
Tracks iSTAR controller health and connectivity.

```python
@dataclass
class CCureController:
    controller_id: str
    name: str                    # e.g., "iSTAR Ultra - Ground Floor"
    model: str                   # iSTAR Ultra, iSTAR Edge, iSTAR Standard
    firmware: str                # e.g., "5.10.2"
    encryption_mode: str         # FIPS 197 AES-256
    tamper_status: str           # normal, enclosure_open, back_tamper
    last_seen: datetime
    ip_address: str
    reader_count: int
    status: str                  # online, offline, degraded
```

---

## API Integration Flow

### Demo Mode (Current - Phase 58.2)

```python
# Endpoint: GET /api/security/events/anomalies
@router.get("/events/anomalies")
async def get_security_anomalies(since: str = "24h", anomaly_type: Optional[str] = None):
    occ_svc = get_security_occupancy_service()

    # 1. Get after-hours anomalies
    after_hours = occ_svc.detect_after_hours_anomaly(site_id="site-002")

    # 2. Get equipment health issues
    equipment_health = occ_svc.detect_security_equipment_health_issues()

    # 3. Combine and filter
    all_anomalies = after_hours + equipment_health
    if anomaly_type:
        all_anomalies = [a for a in all_anomalies if a["type"] == anomaly_type]

    return {
        "anomalies": all_anomalies,
        "count": len(all_anomalies),
        "summary": {
            "after_hours_count": len(after_hours),
            "equipment_health_count": len(equipment_health)
        }
    }
```

**Demo Data Flow:**
```
CCureAdapter(demo_mode=True)
    ↓ ccure_demo_data.json
{
  "badge_events": [
    {"person_name": "Johan", "timestamp": "21:30", "after_hours": true, ...},
    {"person_name": "Sarah", "timestamp": "14:15", "after_hours": false, ...}
  ],
  "controllers": [
    {"controller_id": "CTL-001", "status": "online"},
    {"controller_id": "CTL-003", "status": "offline"}
  ]
}
    ↓ detect_after_hours_anomaly() filters events with after_hours=true
    ↓ detect_security_equipment_health_issues() checks for offline controllers
    ↓ Simulates HVAC/network/UPS correlation
    ↓ Returns anomalies with full context
```

### Live Mode (Phase 58.3+)

```python
# Same endpoint, different data source
@router.get("/events/anomalies")
async def get_security_anomalies(since: str = "24h", ...):
    occ_svc = get_security_occupancy_service()

    # Intelligence methods use CCureAdapter internally
    # In live mode:
    # 1. CCureAdapter.connect() authenticates to victor API
    # 2. get_badge_events() queries victor API for real events
    # 3. Correlations use actual HVAC/network/UPS data

    after_hours = occ_svc.detect_after_hours_anomaly(site_id="site-002")
    # Same flow, but with real data
```

---

## Demo Data Structure

**File:** `backend/app/data/ccure_demo_data.json`

### Badge Events
```json
{
  "badge_events": [
    {
      "event_id": "CCURE-EVT-001",
      "event_type": "access_granted",
      "door_id": "CCURE-DR-L1-001",
      "zone_id": "CCURE-ZN-L1-EXEC",
      "badge_id": "FAC-001-12345",
      "person_name": "Johan van der Merwe",
      "department": "IT Operations",
      "clearance_level": "IT-ADMIN",
      "direction": "entry",
      "timestamp": "2026-02-10T21:30:00Z",
      "granted": true,
      "after_hours": true,
      "reason": "Valid access"
    }
  ]
}
```

**Event Types Represented:**
- ✅ `access_granted` — Normal badge entry
- ✅ `forced_door` — Door opened without credential
- ✅ `door_held_open` — Door held open >threshold
- ✅ `anti_passback` — Anti-passback violation
- ✅ `controller_offline` — iSTAR controller lost connection

### Controllers
```json
{
  "controllers": [
    {
      "controller_id": "CCURE-CTL-001",
      "name": "iSTAR Ultra - Ground Floor",
      "model": "iSTAR Ultra",
      "firmware": "5.10.2",
      "encryption_mode": "FIPS 197 AES-256",
      "tamper_status": "normal",
      "last_seen": "2026-02-10T23:00:00Z",
      "ip_address": "10.1.1.60",
      "reader_count": 8,
      "status": "online"
    },
    {
      "controller_id": "CCURE-CTL-003",
      "name": "iSTAR Edge - Level 3",
      "status": "offline"  // Represents offline scenario
    }
  ]
}
```

---

## Testing Strategy

### Unit Tests

**File:** `backend/tests/services/ccure/test_ccure_adapter.py`

```python
@pytest.mark.asyncio
async def test_ccure_adapter_demo_mode():
    """Test adapter loads demo data correctly"""
    adapter = CCureAdapter(demo_mode=True)
    connected = await adapter.connect()

    assert connected
    events = await adapter.get_badge_events(limit=5)
    assert len(events) == 5
    assert events[0]["person_name"] == "Johan van der Merwe"

@pytest.mark.asyncio
async def test_after_hours_anomaly_detection():
    """Test anomaly detection with demo data"""
    occ_svc = get_security_occupancy_service()
    anomalies = occ_svc.detect_after_hours_anomaly()

    assert len(anomalies) > 0
    assert anomalies[0]["type"] == "after_hours_access"
    assert "energy_impact" in anomalies[0]

@pytest.mark.asyncio
async def test_equipment_health_monitoring():
    """Test controller offline detection"""
    occ_svc = get_security_occupancy_service()
    issues = occ_svc.detect_security_equipment_health_issues()

    assert len(issues) > 0
    assert any(i["type"] == "controller_offline" for i in issues)
```

### Integration Tests

```python
@pytest.mark.asyncio
async def test_security_api_endpoints(client):
    """Test API endpoints with demo data"""

    # Test C•CURE status
    response = client.get("/api/security/ccure/status")
    assert response.status_code == 200
    assert response.json()["mode"] == "demo"

    # Test anomalies endpoint
    response = client.get("/api/security/events/anomalies?since=24h")
    assert response.status_code == 200
    data = response.json()
    assert "anomalies" in data
    assert data["count"] > 0
```

---

## Phase 58.3: Live Integration Implementation

### victor Web Service API Authentication

**Endpoint:** `POST {api_url}/auth/token`

```python
async def _authenticate(self):
    """Obtain JWT token from victor Web Service API"""
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{self.api_url}/auth/token",
            json={
                "license_guid": self.license_guid,
                "username": self.username,
                "password": self.password
            },
            verify=True  # Verify SSL certificate (self-signed OK with cert pinning)
        )
        data = response.json()
        self._token = data["token"]
        self._token_expires = data.get("expires_in", 3600)
```

### Badge Event Polling

**Endpoint:** `GET {api_url}/api/access-events`

```python
async def get_badge_events(self, since: datetime, limit: int) -> List[Dict]:
    """Fetch badge events from live victor API"""
    if not self._connected:
        raise RuntimeError("Not connected to C•CURE. Call connect() first.")

    async with httpx.AsyncClient() as client:
        response = await client.get(
            f"{self.api_url}/api/access-events",
            headers={"Authorization": f"Bearer {self._token}"},
            params={
                "since": since.isoformat(),
                "limit": limit
            }
        )
        return response.json()
```

### Polling Strategy

**Default (Phase 58.3):** 60-second polling interval
```python
# In SecurityOccupancyService
async def poll_badge_events_loop():
    adapter = CCureAdapter(live_mode=True, ...)
    await adapter.connect()

    while True:
        try:
            events = await adapter.get_badge_events(
                since=datetime.now() - timedelta(minutes=1)
            )
            for event in events:
                process_badge_event(event)
        except Exception as e:
            logger.error(f"Polling error: {e}")

        await asyncio.sleep(60)  # Poll every 60 seconds
```

**Future (Phase 58.3+):** WebSocket real-time events
```python
# TODO Phase 58.4: Replace polling with WebSocket
# Endpoint: WSS {api_url}/ws/access-events
# Latency: <1 second vs 60 seconds with polling
# Bandwidth: Reduced (event-driven vs periodic)
```

---

## Error Handling

### Resilience Patterns

**Rate Limiting:**
```python
from app.utils.resilience import RateLimiter

rate_limiter = RateLimiter(calls=1000, period=3600)

async def get_badge_events(self, ...):
    await rate_limiter.acquire()
    # Make API call
```

**Circuit Breaker:**
```python
from app.utils.resilience import CircuitBreaker

async with CircuitBreaker(failure_threshold=5, timeout_seconds=60):
    events = await adapter.get_badge_events()
```

**Exponential Backoff:**
```python
@retry(wait=wait_exponential(multiplier=1, min=2, max=30))
async def get_badge_events(self, ...):
    # API call with automatic retry on 429/503
```

### Logging

```python
logger.info("CCureAdapter: Connecting to victor API")
logger.info("CCureAdapter: Using DEMO MODE - Partner license required")
logger.warning("CCureAdapter: Live mode not implemented - requires license")
logger.error("CCureAdapter: Authentication failed - check credentials")
```

---

## Security Considerations

### Credential Storage

**Production (Phase 58.3+):**
```python
# NEVER store credentials in code or environment
# Use Supabase Vault or AWS Secrets Manager

CCURE_API_URL = os.getenv("CCURE_API_URL")
CCURE_LICENSE_GUID = os.getenv("CCURE_LICENSE_GUID")
CCURE_USERNAME = os.getenv("CCURE_USERNAME")

# Password stored in Vault:
ccure_password = get_secret("ccure-operator-password")
```

### Token Management

```python
# Token rotation every hour
if datetime.now() > self._token_expires:
    await self._authenticate()  # Get new token

# NEVER log tokens
logger.info(f"Authenticated to victor API")  # ✓ Safe
logger.info(f"Token: {self._token}")  # ✗ NEVER
```

### SSL/TLS

```python
# Verify victor API certificate
# For self-signed certs in development:
async with httpx.AsyncClient(verify=False) as client:  # ✗ DEV ONLY
    ...

# Production: Use certificate pinning
async with httpx.AsyncClient(verify="/path/to/ca.pem") as client:  # ✓ PROD
    ...
```

---

## References

- **victor Web Service API:** https://softwarehouse.com/developers/api-reference/
- **C•CURE 9000 v2.90:** https://softwarehouse.com/products/ccure-9000/
- **Software House Partner Program:** https://softwarehouse.com/partner-network/
- **SENTINEL Security Module:** See `docs/04-features/58-security-module.md`
