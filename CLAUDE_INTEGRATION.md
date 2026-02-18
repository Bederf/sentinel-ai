# CLAUDE_INTEGRATION.md

External system integrations: Telegram, SIMBIOT, MCP server, webhooks.

## Telegram/Clawd Bot Integration

### Architecture

```
SENTINEL Alert/Work Order
    ↓
Clawd Bot (middleware)
    ↓
Telegram Chat (Technician's phone)
    ↓
Technician responses (WhatsApp/Telegram)
    ↓
Feedback collection
    ↓
Health score update
```

### Command Pattern

**Telegram commands must use letters/numbers/underscores only:**

```
✅ CORRECT                ❌ WRONG
S002_CHILLER_B1_001      S002-CHILLER-B1-001   (dashes not allowed)
S002_VAV_101             S002-VAV-101
FILTER_REPLACEMENT       Filter Replacement    (spaces not allowed)
```

**Conversion:**
```python
# Outgoing (SENTINEL → Telegram)
equipment_code = "S002-CHILLER-B1-001"
telegram_cmd = equipment_code.replace("-", "_")  # "S002_CHILLER_B1_001"

# Incoming (Telegram → SENTINEL)
telegram_cmd = "S002_CHILLER_B1_001"
equipment_code = telegram_cmd.replace("_", "-")  # "S002-CHILLER-B1-001"
```

### Message Flow

```
Alert triggered
    ↓
Service record created (status='notified')
    ↓
Background job every 30 seconds:
    1. Query pending service records
    2. For each: Get assigned technician
    3. Get technician's Telegram ID
    4. Format message with equipment code, issue, diagnostics
    5. Send via Sentry bot
    6. Mark service record as sent
    ↓
Technician receives on phone
    ↓
Technician types response (or shares photo)
    ↓
Sentry bot processes reply
    ↓
Service record marked 'data_collection'
    ↓
Feedback collection phase begins
```

### Clawd Bot Endpoints

**In `backend/app/api/clawd_webhooks.py`:**

```python
@router.post("/api/sentry/process-pending-notifications")
async def process_pending_notifications():
    """Process pending Telegram notifications"""
    # Get all service records with status='notified'
    # For each: send Telegram via Sentry bot
    # Mark as sent (status → 'data_collection')
    return {"success": count, "processed": processed_ids}

@router.post("/api/sentry/feedback")
async def handle_clawd_feedback(payload: ClaudFeedback):
    """Handle feedback submission from Clawd"""
    # Parse technician response
    # Update service record
    # Calculate health impact
    # Update equipment health_score
    return {"status": "received"}
```

### Service Templates

**From `ml_data_templates.json` (equipment-type specific):**

```json
{
  "CHILLER": {
    "questions": [
      "Filter condition?",
      "Compressor noise?",
      "Discharge temperature?",
      "Result after service?"
    ],
    "health_impact_options": ["positive", "neutral", "negative", "critical"]
  },
  "VAV": {
    "questions": [
      "Actuator response?",
      "Filter replacement?",
      "Damper test?",
      "Overall result?"
    ],
    "health_impact_options": ["positive", "neutral", "negative", "critical"]
  }
}
```

### Health Impact Scoring

```python
health_impact_map = {
    "positive": +2,    # Service fixed the issue completely
    "neutral": 0,      # Service performed but no improvement
    "negative": -3,    # Service made it worse
    "critical": -5     # Equipment now unsafe/unusable
}

# Example:
old_health = 45
impact = 2  # positive
new_health = max(0, min(100, old_health + impact))  # 47
```

---

## SIMBIOT Integration Layer

### Two-Level Architecture

**Level 1: MCP Server (embedded in FastAPI)**
```
Runs in FastAPI process
31+ tools for equipment queries, work orders, anomaly analysis
Reads equipment data, alerts, work orders from Supabase
Exposes tools via stdio protocol for Claude to use during chat
READ-ONLY for Supabase; use backend API for INSERT/UPDATE
```

**Level 2: Concept Connector (standalone)**
```
Location: /opt/bms-intelligence/simbiot_concept/
Bridges SENTINEL ↔ MRI Evolution (Concept) via FSI Public API
Handles work order creation, status polling, asset sync, JWT auth
Used by background jobs for external CAFM integration
Can be installed: pip install -e simbiot_concept/
```

### MCP Server Tools (31+)

**In `backend/app/mcp/simbiot_server.py`:**

```python
# Tool categories:
# - Equipment queries (30 tools)
#   list_equipment, get_equipment_by_code, get_health_trends, etc.
# - Work order management (15 tools)
#   list_work_orders, get_work_order_details, create_work_order, etc.
# - Anomaly analysis (10 tools)
#   analyze_equipment_fault, predict_failure, get_alerts, etc.
# - Recommendations (8 tools)
#   get_pending_recommendations, evaluate_recommendation, etc.
```

**Usage in Claude conversation:**
```
User: "What equipment needs attention?"
Claude (with MCP):
1. Calls tool: list_equipment(health_lt=80)
2. Gets: [{"code": "S002-CHILLER-B1-001", "health": 45}, ...]
3. Responds: "Your CHILLER has health score 45% and needs service..."
```

### Concept Connector Pattern

```python
from simbiot_concept import ConceptConnector, ConceptConfig, SentinelAnomaly

# 1. Configure
config = ConceptConfig(
    api_base_url="https://developer.fsiservices.com",
    subscription_key="...",
    api_username="sentinel_api",
    api_password="...",
    customer_site_code="YOUR_SITE",
    segments=[...],
)

# 2. Initialize
connector = ConceptConnector(config)
await connector.initialise()

# 3. Create work order from anomaly
anomaly = SentinelAnomaly(
    source=AnomalySource.BMS_ANOMALY,
    segment_id="SEG-001",
    asset_type="chiller",
    severity_score=0.82,
    summary="Compressor discharge temp rising",
    diagnostics="Progressive increase over 2 hours..."
)

result = await connector.create_work_order(anomaly)
print(f"WO created: {result.work_order_id}")

# 4. Shutdown
await connector.shutdown()
```

### Key Features

- **JWT Auth:** 7-day token expiry, auto-refresh
- **Rate Limiting:** 200 requests/minute (exponential backoff)
- **Circuit Breaker:** 5 failures → queue locally, retry later
- **Deduplication:** 30-minute cooldown per asset (prevent alarm storms)
- **Feedback Loop:** Status polling captures technician notes

### When to Use

- **MCP Server:** When Claude needs to query equipment during conversation
- **Concept Connector:** When SENTINEL alerts need to create external work orders

---

## Webhook Integration

### Outbound Webhooks (SENTINEL → External)

**Example: Notify external system of alert**

```python
# In background job or alert handler
import httpx

@router.post("/api/alerts")
async def create_alert(...):
    alert = await alert_service.create(...)

    # Trigger outbound webhook
    if settings.WEBHOOK_URL:
        async with httpx.AsyncClient() as client:
            await client.post(
                settings.WEBHOOK_URL,
                json={
                    "event": "alert.created",
                    "equipment_code": alert.equipment_code,
                    "severity": alert.severity,
                    "timestamp": alert.created_at.isoformat(),
                },
                timeout=10,
            )

    return alert
```

### Inbound Webhooks (External → SENTINEL)

**Example: Receive work order updates from external system**

```python
@router.post("/api/webhooks/external/work-order-update")
async def receive_work_order_update(payload: dict):
    """Receive work order status update from external system"""

    # Verify webhook signature (SENTRY_WEBHOOK_SECRET)
    signature = request.headers.get("X-Signature")
    if not verify_signature(payload, signature):
        raise HTTPException(status_code=403, detail="Invalid signature")

    # Update work order
    work_order = await work_order_service.update_from_external(
        external_id=payload["id"],
        status=payload["status"],
        notes=payload["notes"],
    )

    return {"status": "received", "work_order_id": work_order.id}
```

---

## REST API Integration

### Common Patterns

**Batch Operations (Prevent N+1):**

```bash
# ❌ WRONG - 30 separate calls
for device_id in devices:
    curl http://localhost:9095/api/devices/$device_id/status

# ✅ CORRECT - 1 batch call
curl -X POST http://localhost:9095/api/devices/batch/status \
  -H "Content-Type: application/json" \
  -d '{"device_ids": ["d1", "d2", ..., "d30"]}'
```

**Error Handling:**

```bash
# Check for error response
curl http://localhost:9095/api/devices/invalid
# Returns: {"detail": "Device not found", "status_code": 404}

# Set up retry logic for 500 errors
max_retries=3
for i in {1..3}; do
  response=$(curl -w "%{http_code}" http://localhost:9095/api/devices)
  if [[ "$response" =~ ^2[0-9]{2}$ ]]; then
    break
  fi
  sleep $((2 ** i))  # Exponential backoff
done
```

### Authentication

**All requests require Authorization header:**

```bash
# Get token (DEMO_MODE: instant access)
TOKEN=$(curl -s -X POST http://localhost:9095/api/login \
  -H "Content-Type: application/json" \
  -d '{"email":"user@example.com"}' | jq -r '.access_token')

# Use token in requests
curl http://localhost:9095/api/devices \
  -H "Authorization: Bearer $TOKEN"
```

### Rate Limiting

**Backend enforces limits:**

| Endpoint Type | Limit | Strategy |
|---------------|-------|----------|
| Individual | 60/min | Discourage N+1 |
| Batch | 300/min | Encourage efficient usage |
| Webhook | 200/min | For external integrations |

**Response headers:**
```
X-RateLimit-Limit: 60
X-RateLimit-Remaining: 45
X-RateLimit-Reset: 1708095600
```

---

## Performance & Resilience

### Connection Pooling

```python
# ✅ CORRECT - Reuse client connection
async with httpx.AsyncClient() as client:
    for i in range(100):
        await client.get("https://...")  # Reuses connection

# ❌ WRONG - New connection per request
for i in range(100):
    async with httpx.AsyncClient() as client:
        await client.get("https://...")  # 100 connections!
```

### Timeout Handling

```python
# ✅ CORRECT - Set reasonable timeout
async with httpx.AsyncClient(timeout=10.0) as client:
    try:
        response = await client.get("https://...", timeout=5)
    except httpx.TimeoutException:
        logger.error("Request timed out")
        raise HTTPException(status_code=504, detail="Service timeout")
```

### Circuit Breaker Pattern

```python
# Example: Concept Connector circuit breaker
if failed_requests > 5:
    # Switch to local queue mode
    queue_request_locally()
    retry_later()  # Exponential backoff
else:
    send_to_external_service()
```

---

## Testing Integrations

### Mock External Endpoints

```python
from unittest.mock import patch, AsyncMock

@pytest.mark.asyncio
async def test_work_order_notification():
    with patch('httpx.AsyncClient.post') as mock_post:
        mock_post.return_value = AsyncMock(status_code=200)

        alert = await alert_service.create(equipment_id="eq-123")

        # Verify webhook was called
        mock_post.assert_called_once()
        call_args = mock_post.call_args
        assert call_args.kwargs["json"]["event"] == "alert.created"
```

### E2E Integration Testing

```bash
# Test full flow with real integrations
pytest -m integration tests/

# Use DEMO_MODE=false to test with real external systems
# Set WEBHOOK_URL and CONCEPT_API_KEY in .env
```

---

See related docs:
- `CLAUDE_ARCHITECTURE.md` - System design
- `CLAUDE_WORKFLOWS.md` - Telegram notification flow
- `CLAUDE_QUICK_START.md` - Common commands
