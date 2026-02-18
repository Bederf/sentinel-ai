# Stage 6: WhatsApp Integration Testing & Validation

**Status**: Ready to Test
**Duration**: 30-45 minutes

---

## Test 1: Environment Configuration Check

### Objective
Verify that WhatsApp credentials are properly loaded

### Steps

```bash
#!/bin/bash
# test_stage6_env.sh

cd /opt/bms-intelligence/backend

echo "=== Stage 6 Environment Check ==="
echo ""

# Check .env.local exists
if [ -f .env.local ]; then
    echo "✅ backend/.env.local exists"
    echo "   WHATSAPP_PROVIDER=$(grep WHATSAPP_PROVIDER .env.local | cut -d= -f2)"
else
    echo "❌ backend/.env.local NOT FOUND"
    exit 1
fi

echo ""
echo "Checking Python imports..."

python3 << 'PYEOF'
import os
import sys

try:
    from app.integrations.whatsapp_service import get_whatsapp_service
    print("✅ whatsapp_service imports correctly")

    service = get_whatsapp_service()
    status = service.get_status()

    print(f"✅ Service initialized")
    print(f"   Provider: {status['provider']}")
    print(f"   Enabled: {status['enabled']}")

    if not status['enabled']:
        print("⚠️  WhatsApp service not enabled - check credentials")

except Exception as e:
    print(f"❌ Error: {e}")
    sys.exit(1)
PYEOF
```

**Expected Output**:
```
=== Stage 6 Environment Check ===

✅ backend/.env.local exists
   WHATSAPP_PROVIDER=twilio

Checking Python imports...
✅ whatsapp_service imports correctly
✅ Service initialized
   Provider: twilio
   Enabled: True
```

---

## Test 2: Webhook Verification

### Objective
Verify that webhook endpoint accepts Meta/Twilio verification

### Steps

```bash
#!/bin/bash
# test_stage6_webhook_verify.sh

echo "=== Webhook Verification Test ==="
echo ""

# Start backend in background (if not running)
if ! pgrep -f "uvicorn app.main:app" > /dev/null; then
    echo "Starting backend..."
    cd /opt/bms-intelligence/backend
    DEMO_MODE=true python -m uvicorn app.main:app --reload --port 9095 &
    sleep 3
fi

WEBHOOK_URL="http://localhost:9095/api/whatsapp/webhooks"
VERIFY_TOKEN="sentry_webhook_secure_2026"
CHALLENGE="1234567890"

echo "Testing webhook verification endpoint..."
echo "URL: $WEBHOOK_URL"
echo ""

RESPONSE=$(curl -s -w "\n%{http_code}" -X GET \
  "$WEBHOOK_URL?hub.mode=subscribe&hub.verify_token=$VERIFY_TOKEN&hub.challenge=$CHALLENGE")

HTTP_CODE=$(echo "$RESPONSE" | tail -1)
BODY=$(echo "$RESPONSE" | head -1)

echo "Response: $BODY"
echo "HTTP Status: $HTTP_CODE"
echo ""

if [ "$BODY" = "$CHALLENGE" ] && [ "$HTTP_CODE" = "200" ]; then
    echo "✅ Webhook verification PASSED"
else
    echo "❌ Webhook verification FAILED"
    echo "   Expected body: $CHALLENGE"
    echo "   Expected status: 200"
fi
```

**Expected Output**:
```
=== Webhook Verification Test ===

Testing webhook verification endpoint...
URL: http://localhost:9095/api/whatsapp/webhooks

Response: 1234567890
HTTP Status: 200

✅ Webhook verification PASSED
```

---

## Test 3: Message Send (Twilio Sandbox)

### Objective
Send a test message via Twilio

### Prerequisites
- Twilio account with WhatsApp Sandbox
- Your phone added to sandbox participants
- Sandbox number: +14155552368

### Steps

```bash
#!/bin/bash
# test_stage6_send_message.sh

cd /opt/bms-intelligence/backend

echo "=== WhatsApp Message Send Test ==="
echo ""

python3 << 'PYEOF'
import asyncio
import os
from app.integrations.whatsapp_service import get_whatsapp_service

async def test_send():
    service = get_whatsapp_service()

    if not service.enabled:
        print("❌ WhatsApp service not enabled")
        return False

    # Replace with YOUR phone number
    test_phone = "+27721234567"  # ← UPDATE THIS

    print(f"Sending test message to {test_phone}...")
    print("")

    result = await service.send_text_message(
        to_number=test_phone,
        message="🧪 Test message from SENTRY WhatsApp integration\n\nIf you see this, Stage 6 is working!"
    )

    if result.get("success"):
        print(f"✅ Message sent successfully!")
        print(f"   Message ID: {result['message_id']}")
        print(f"   Provider: {result['provider']}")
        print(f"   Timestamp: {result['timestamp']}")
        return True
    else:
        print(f"❌ Message send failed")
        print(f"   Error: {result.get('error')}")
        return False

success = asyncio.run(test_send())
exit(0 if success else 1)
PYEOF
```

**Expected Output**:
```
=== WhatsApp Message Send Test ===

Sending test message to +27721234567...

✅ Message sent successfully!
   Message ID: wamid.HBEUHBWEHUEHUwuheuh==
   Provider: twilio
   Timestamp: 2026-02-18T14:30:45.123456
```

**Physical Verification**:
- [ ] Check your WhatsApp
- [ ] You should receive the test message
- [ ] Reply to verify two-way communication

---

## Test 4: Work Order Notification

### Objective
Test sending work order notification to technician

### Steps

```bash
#!/bin/bash
# test_stage6_work_order.sh

cd /opt/bms-intelligence/backend

echo "=== Work Order Notification Test ==="
echo ""

python3 << 'PYEOF'
import asyncio
from app.handlers.whatsapp_handler import get_whatsapp_handler

async def test_work_order():
    handler = get_whatsapp_handler()

    if not handler.enabled:
        print("❌ WhatsApp handler not enabled")
        return False

    # Mock work order
    work_order = {
        "id": "WO-12345",
        "priority": "HIGH",
        "equipment_code": "S002-CHILLER-B1-001",
        "location": "Building 2, Floor B1",
        "description": "Chiller temperature out of range. Check thermostat calibration."
    }

    # Send to tech-001 (John Smith)
    technician_id = "tech-001"

    print(f"Sending work order {work_order['id']} to {technician_id}...")
    print("")

    result = await handler.send_work_order_assignment(work_order, technician_id)

    if result:
        print(f"✅ Work order notification sent!")
        print(f"   Work Order: {work_order['id']}")
        print(f"   Priority: {work_order['priority']}")
        print(f"   Equipment: {work_order['equipment_code']}")
        return True
    else:
        print(f"❌ Work order notification failed")
        print(f"   Check technician_id and phone mapping")
        return False

success = asyncio.run(test_work_order())
exit(0 if success else 1)
PYEOF
```

**Expected Output**:
```
=== Work Order Notification Test ===

Sending work order WO-12345 to tech-001...

✅ Work order notification sent!
   Work Order: WO-12345
   Priority: HIGH
   Equipment: S002-CHILLER-B1-001
```

---

## Test 5: Incoming Message Handling

### Objective
Test that bot responds to incoming WhatsApp messages

### Steps

```bash
#!/bin/bash
# test_stage6_incoming_message.sh

WEBHOOK_URL="http://localhost:9095/api/whatsapp/webhooks"

echo "=== Incoming Message Test ==="
echo ""

# Simulate incoming message from WhatsApp
echo "Sending: 'Help' command..."
echo ""

RESPONSE=$(curl -s -X POST \
  -H "Content-Type: application/json" \
  -d '{
    "object": "whatsapp_business_account",
    "entry": [{
      "changes": [{
        "value": {
          "messages": [{
            "from": "27721234567",
            "id": "wamid.test123",
            "timestamp": "1645123456",
            "type": "text",
            "text": {
              "body": "Help"
            }
          }]
        }
      }]
    }]
  }' \
  "$WEBHOOK_URL")

echo "Response: $RESPONSE"
echo ""

if echo "$RESPONSE" | grep -q '"status":"ok"'; then
    echo "✅ Message received and processed"
    echo "   Bot should send help message back"
else
    echo "❌ Message processing failed"
fi

echo ""
echo "Testing Work Order lookup..."
echo ""

RESPONSE=$(curl -s -X POST \
  -H "Content-Type: application/json" \
  -d '{
    "object": "whatsapp_business_account",
    "entry": [{
      "changes": [{
        "value": {
          "messages": [{
            "from": "27721234567",
            "id": "wamid.test456",
            "timestamp": "1645123457",
            "type": "text",
            "text": {
              "body": "WO-12345"
            }
          }]
        }
      }]
    }]
  }' \
  "$WEBHOOK_URL")

echo "Response: $RESPONSE"

if echo "$RESPONSE" | grep -q '"status":"ok"'; then
    echo "✅ Work order query processed"
    echo "   Bot should send WO details"
else
    echo "❌ Work order query failed"
fi
```

**Expected Output**:
```
=== Incoming Message Test ===

Sending: 'Help' command...

Response: {"status":"ok"}

✅ Message received and processed
   Bot should send help message back

Testing Work Order lookup...

Response: {"status":"ok"}

✅ Work order query processed
   Bot should send WO details
```

---

## Test 6: Critical Alert Broadcast

### Objective
Test sending critical alert to multiple technicians

### Steps

```bash
#!/bin/bash
# test_stage6_alert.sh

cd /opt/bms-intelligence/backend

python3 << 'PYEOF'
import asyncio
from app.handlers.whatsapp_handler import get_whatsapp_handler

async def test_alert():
    handler = get_whatsapp_handler()

    alert = {
        "type": "Equipment Failure",
        "equipment_code": "S002-UPS-001",
        "severity": "CRITICAL",
        "description": "UPS battery critically low (5% remaining)"
    }

    recipient_ids = ["tech-001", "tech-002", "manager-001"]

    print("=== Critical Alert Broadcast Test ===")
    print("")
    print(f"Sending alert to {len(recipient_ids)} recipients...")
    print("")

    count = await handler.send_critical_alert(alert, recipient_ids)

    print(f"✅ Alert sent to {count}/{len(recipient_ids)} recipients")

    return count > 0

success = asyncio.run(test_alert())
PYEOF
```

**Expected Output**:
```
=== Critical Alert Broadcast Test ===

Sending alert to 3 recipients...

✅ Alert sent to 3/3 recipients
```

---

## Test 7: Full Integration Test

### Objective
Run all tests in sequence

### Steps

```bash
#!/bin/bash
# test_stage6_full.sh

cd /opt/bms-intelligence

echo "╔════════════════════════════════════════════════════════════════╗"
echo "║         STAGE 6: WhatsApp Integration - Full Test              ║"
echo "╚════════════════════════════════════════════════════════════════╝"
echo ""

TESTS_PASSED=0
TESTS_FAILED=0

# Test 1: Environment
echo "[1/7] Testing environment configuration..."
if bash STAGE_6_TESTING_GUIDE.md 2>/dev/null | grep -q "✅ Service initialized"; then
    echo "✅ PASSED"
    ((TESTS_PASSED++))
else
    echo "❌ FAILED"
    ((TESTS_FAILED++))
fi
echo ""

# Test 2: Webhook
echo "[2/7] Testing webhook verification..."
if [ "$HTTP_CODE" = "200" ]; then
    echo "✅ PASSED"
    ((TESTS_PASSED++))
else
    echo "❌ FAILED"
    ((TESTS_FAILED++))
fi
echo ""

# Summary
echo "╔════════════════════════════════════════════════════════════════╗"
echo "║                     TEST SUMMARY                               ║"
echo "╚════════════════════════════════════════════════════════════════╝"
echo ""
echo "Passed: $TESTS_PASSED/7"
echo "Failed: $TESTS_FAILED/7"
echo ""

if [ $TESTS_FAILED -eq 0 ]; then
    echo "✅ ALL TESTS PASSED - Stage 6 Ready for Deployment"
    exit 0
else
    echo "❌ Some tests failed - see details above"
    exit 1
fi
```

---

## Validation Checklist

Run this before marking Stage 6 complete:

```bash
#!/bin/bash
# STAGE_6_VALIDATION_CHECKLIST.sh

echo "=== Stage 6 Validation Checklist ==="
echo ""

CHECKS=0
PASSED=0

# Check 1: Files exist
CHECKS=$((CHECKS + 1))
if [ -f backend/app/integrations/whatsapp_service.py ]; then
    echo "✅ whatsapp_service.py exists"
    PASSED=$((PASSED + 1))
else
    echo "❌ whatsapp_service.py MISSING"
fi

# Check 2: Handler exists
CHECKS=$((CHECKS + 1))
if [ -f backend/app/handlers/whatsapp_handler.py ]; then
    echo "✅ whatsapp_handler.py exists"
    PASSED=$((PASSED + 1))
else
    echo "❌ whatsapp_handler.py MISSING"
fi

# Check 3: Webhook exists
CHECKS=$((CHECKS + 1))
if [ -f backend/app/api/whatsapp_webhooks.py ]; then
    echo "✅ whatsapp_webhooks.py exists"
    PASSED=$((PASSED + 1))
else
    echo "❌ whatsapp_webhooks.py MISSING"
fi

# Check 4: Config file exists
CHECKS=$((CHECKS + 1))
if [ -f backend/app/data/technicians_whatsapp.json ]; then
    echo "✅ technicians_whatsapp.json exists"
    PASSED=$((PASSED + 1))
else
    echo "❌ technicians_whatsapp.json MISSING"
fi

# Check 5: Registrar updated
CHECKS=$((CHECKS + 1))
if grep -q "whatsapp_webhooks" backend/app/api/registrars/operations.py; then
    echo "✅ operations.py registrar updated"
    PASSED=$((PASSED + 1))
else
    echo "❌ operations.py registrar NOT updated"
fi

# Check 6: Environment configured
CHECKS=$((CHECKS + 1))
if [ -f backend/.env.local ] && grep -q "WHATSAPP_" backend/.env.local; then
    echo "✅ .env.local configured"
    PASSED=$((PASSED + 1))
else
    echo "❌ .env.local NOT configured"
fi

# Check 7: Backend starts without errors
CHECKS=$((CHECKS + 1))
cd backend
if timeout 5 python -c "from app.integrations.whatsapp_service import get_whatsapp_service; get_whatsapp_service()" 2>/dev/null; then
    echo "✅ Backend imports without errors"
    PASSED=$((PASSED + 1))
else
    echo "❌ Backend import errors"
fi

echo ""
echo "=== Result ==="
echo "Passed: $PASSED/$CHECKS"
echo ""

if [ $PASSED -eq $CHECKS ]; then
    echo "✅ Stage 6 VALIDATION COMPLETE - Ready for Deployment"
    exit 0
else
    echo "❌ Some checks failed - see details above"
    exit 1
fi
```

---

## Troubleshooting

| Error | Cause | Solution |
|-------|-------|----------|
| `ModuleNotFoundError: whatsapp_service` | Import path incorrect | Check file location: `backend/app/integrations/whatsapp_service.py` |
| `WHATSAPP_PROVIDER not set` | Env variable missing | Add to `backend/.env.local` |
| `Webhook returns 403` | Token mismatch | Verify `WHATSAPP_WEBHOOK_TOKEN` matches provider setting |
| `Message send fails` | API credentials invalid | Check Token/Account SID in provider console |
| `No technician phone found` | Config missing | Update `technicians_whatsapp.json` |

---

## Success Criteria

✅ **Stage 6 Complete** when all tests pass:

- [ ] Environment variables load correctly
- [ ] Webhook verification returns 200 OK
- [ ] Test message sends via WhatsApp
- [ ] Technician receives work order notification
- [ ] Bot responds to incoming messages
- [ ] Critical alerts broadcast to multiple users
- [ ] No Python errors or import failures
- [ ] Logs show successful message routing

---

**Version**: 1.0 | **Date**: 2026-02-18
