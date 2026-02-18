# Stage 6: Implementation Checklist & Execution Plan

**Status**: Ready to Execute
**Duration**: 45-60 minutes
**Complexity**: Moderate

---

## Part 1: Environment Setup (5 minutes)

### 1.1 Choose WhatsApp Provider

**Recommended for MVP/Testing**: Twilio Sandbox (immediate, free)
**Recommended for Production**: Meta Cloud API (official, scalable)

```bash
# Decide: Meta or Twilio?
# For this guide, we'll use: META (follow Part 2)
# For quick testing: TWILIO (follow Part 2B)
```

### 1.2 Get API Credentials

#### If Using Meta:

```bash
# 1. Go to: https://developers.facebook.com/
# 2. Create App → Business → name "SENTRY BMS"
# 3. Add Product → WhatsApp → Cloud API
# 4. Get credentials:

export WHATSAPP_PHONE_ID="102348901234567"          # Your phone ID
export WHATSAPP_API_TOKEN="EAAxxxxxxxxxxxx"         # Long token
export WHATSAPP_BUSINESS_ID="109876543210987"       # Business ID
export WHATSAPP_WEBHOOK_TOKEN="sentry_webhook_2026" # You generate this
export WHATSAPP_PROVIDER="meta"

# 5. For local testing, use ngrok:
ngrok http 8000
# Webhook URL: https://abc123.ngrok.io/api/webhooks/whatsapp
```

#### If Using Twilio (Quick Testing):

```bash
# 1. Go to: https://www.twilio.com/try-twilio
# 2. Get credentials from console

export TWILIO_ACCOUNT_SID="AC0123456789abcdef"
export TWILIO_AUTH_TOKEN="your_auth_token"
export TWILIO_WHATSAPP_NUMBER="+14155552368"
export WHATSAPP_PROVIDER="twilio"

# 3. Add your phone to sandbox:
# Twilio Console → Messaging → WhatsApp Sandbox → Join
# Send: join <code>
```

### 1.3 Add Environment Variables

```bash
# Edit $SENTRY_HOME/.env.local

WHATSAPP_PROVIDER=meta

# Meta credentials (if using Meta)
WHATSAPP_PHONE_ID=102348901234567
WHATSAPP_API_TOKEN=EAAxxxxxxxxxxxx
WHATSAPP_BUSINESS_ID=109876543210987
WHATSAPP_WEBHOOK_TOKEN=sentry_webhook_2026

# Twilio credentials (if using Twilio)
TWILIO_ACCOUNT_SID=AC0123456789abcdef
TWILIO_AUTH_TOKEN=your_auth_token
TWILIO_WHATSAPP_NUMBER=+14155552368

# Then reload:
source ~/.bashrc
```

---

## Part 2: Create Python Implementation Files

### 2.1 WhatsApp Service Layer

**File**: `$SENTRY_HOME/integrations/whatsapp_service.py`

[See STAGE_6_WHATSAPP_SETUP.md > Section 2 > Step 1]

**Quick Create**:
```bash
cat > $SENTRY_HOME/integrations/whatsapp_service.py << 'EOF'
import httpx
import os
from typing import Optional, Dict, Any
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

class WhatsAppService:
    def __init__(self, provider: str = "meta"):
        self.provider = provider
        if provider == "meta":
            self.phone_id = os.getenv("WHATSAPP_PHONE_ID", "")
            self.api_token = os.getenv("WHATSAPP_API_TOKEN", "")
            self.api_url = f"https://graph.instagram.com/v18.0/{self.phone_id}/messages"
        else:  # twilio
            self.account_sid = os.getenv("TWILIO_ACCOUNT_SID", "")
            self.auth_token = os.getenv("TWILIO_AUTH_TOKEN", "")
            self.twilio_whatsapp = os.getenv("TWILIO_WHATSAPP_NUMBER", "")
        self.webhook_token = os.getenv("WHATSAPP_WEBHOOK_TOKEN", "secret")

    async def send_text_message(self, to_number: str, message: str, context_id: Optional[str] = None) -> Dict[str, Any]:
        try:
            if self.provider == "meta":
                return await self._send_meta_text(to_number, message, context_id)
            else:
                return await self._send_twilio_text(to_number, message)
        except Exception as e:
            logger.error(f"Error sending: {e}")
            return {"success": False, "error": str(e)}

    async def _send_meta_text(self, to_number: str, message: str, context_id: Optional[str] = None) -> Dict[str, Any]:
        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": to_number,
            "type": "text",
            "text": {"preview_url": True, "body": message}
        }
        headers = {
            "Authorization": f"Bearer {self.api_token}",
            "Content-Type": "application/json"
        }
        async with httpx.AsyncClient() as client:
            response = await client.post(self.api_url, json=payload, headers=headers, timeout=10.0)
            response.raise_for_status()
            data = response.json()
            return {
                "success": True,
                "message_id": data.get("messages", [{}])[0].get("id"),
                "timestamp": datetime.utcnow().isoformat(),
                "provider": "meta"
            }

    async def _send_twilio_text(self, to_number: str, message: str) -> Dict[str, Any]:
        payload = {
            "From": self.twilio_whatsapp,
            "To": f"whatsapp:{to_number}",
            "Body": message
        }
        auth = (self.account_sid, self.auth_token)
        api_url = f"https://api.twilio.com/2010-04-01/Accounts/{self.account_sid}/Messages.json"
        async with httpx.AsyncClient() as client:
            response = await client.post(api_url, data=payload, auth=auth, timeout=10.0)
            response.raise_for_status()
            data = response.json()
            return {"success": True, "message_id": data.get("sid"), "timestamp": datetime.utcnow().isoformat(), "provider": "twilio"}

    def verify_webhook_token(self, token: str) -> bool:
        return token == self.webhook_token

_whatsapp_service: Optional[WhatsAppService] = None

def get_whatsapp_service(provider: str = "meta") -> WhatsAppService:
    global _whatsapp_service
    if _whatsapp_service is None:
        provider_env = os.getenv("WHATSAPP_PROVIDER", "meta")
        _whatsapp_service = WhatsAppService(provider_env)
    return _whatsapp_service
EOF
```

### 2.2 WhatsApp Handler

**File**: `$SENTRY_HOME/handlers/whatsapp_handler.py`

```bash
cat > $SENTRY_HOME/handlers/whatsapp_handler.py << 'EOF'
from typing import Dict, Any, Optional
from integrations.whatsapp_service import get_whatsapp_service
import json
import logging

logger = logging.getLogger(__name__)

class WhatsAppHandler:
    def __init__(self):
        self.service = get_whatsapp_service()
        self.technician_mapping = self._load_technician_mapping()

    def _load_technician_mapping(self) -> Dict[str, str]:
        try:
            with open("config/technicians_whatsapp.json", "r") as f:
                data = json.load(f)
                return {t["id"]: t["whatsapp_number"] for t in data.get("technicians", [])}
        except FileNotFoundError:
            logger.warning("technicians_whatsapp.json not found")
            return {}

    async def send_work_order_assignment(self, work_order: Dict[str, Any], technician_id: str) -> bool:
        phone = self.technician_mapping.get(technician_id)
        if not phone:
            logger.warning(f"No WhatsApp for tech {technician_id}")
            return False

        message = f"🔧 Work Order: {work_order.get('id')}\n{work_order.get('description')}"
        result = await self.service.send_text_message(phone, message)
        return result.get("success", False)

    async def send_critical_alert(self, alert: Dict[str, Any], recipient_ids: list) -> int:
        count = 0
        message = f"🚨 ALERT: {alert.get('type')} - {alert.get('description')}"
        for tech_id in recipient_ids:
            phone = self.technician_mapping.get(tech_id)
            if phone:
                result = await self.service.send_text_message(phone, message)
                if result.get("success"):
                    count += 1
        return count

_handler: Optional[WhatsAppHandler] = None

def get_whatsapp_handler() -> WhatsAppHandler:
    global _handler
    if _handler is None:
        _handler = WhatsAppHandler()
    return _handler
EOF
```

### 2.3 WhatsApp Webhook

**File**: `$SENTRY_HOME/webhooks/whatsapp_webhook.py`

```bash
cat > $SENTRY_HOME/webhooks/whatsapp_webhook.py << 'EOF'
from fastapi import APIRouter, Request, HTTPException
from integrations.whatsapp_service import get_whatsapp_service
import logging

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/webhooks", tags=["whatsapp"])

@router.get("/whatsapp")
async def verify_whatsapp_webhook(request: Request):
    mode = request.query_params.get("hub.mode")
    token = request.query_params.get("hub.verify_token")
    challenge = request.query_params.get("hub.challenge")

    if mode != "subscribe":
        raise HTTPException(status_code=403, detail="Invalid mode")

    service = get_whatsapp_service()
    if not service.verify_webhook_token(token):
        raise HTTPException(status_code=403, detail="Invalid token")

    logger.info("WhatsApp webhook verified")
    return int(challenge)

@router.post("/whatsapp")
async def handle_whatsapp_message(request: Request):
    try:
        body = await request.json()
        entry = body.get("entry", [{}])[0]
        changes = entry.get("changes", [{}])[0]
        value = changes.get("value", {})
        messages = value.get("messages", [])

        if not messages:
            return {"status": "ok"}

        message = messages[0]
        from_number = message.get("from")
        content = message.get("text", {}).get("body", "")

        logger.info(f"WhatsApp: {from_number}: {content}")
        return {"status": "ok"}
    except Exception as e:
        logger.error(f"Error: {e}")
        return {"status": "error"}
EOF
```

---

## Part 3: Configuration Files

### 3.1 Technician Phone Mapping

```bash
mkdir -p $SENTRY_HOME/config

cat > $SENTRY_HOME/config/technicians_whatsapp.json << 'EOF'
{
  "technicians": [
    {
      "id": "tech-001",
      "name": "John Smith",
      "specialty": "electrical",
      "whatsapp_number": "+27721234567",
      "active": true
    },
    {
      "id": "tech-002",
      "name": "Mike Johnson",
      "specialty": "hvac",
      "whatsapp_number": "+27721234568",
      "active": true
    },
    {
      "id": "tech-003",
      "name": "Sarah Lee",
      "specialty": "plumbing",
      "whatsapp_number": "+27721234569",
      "active": true
    }
  ]
}
EOF
```

### 3.2 Environment Variables

```bash
# Add to $SENTRY_HOME/.env.local

cat >> $SENTRY_HOME/.env.local << 'EOF'

# WhatsApp Configuration
WHATSAPP_PROVIDER=meta
WHATSAPP_PHONE_ID=YOUR_PHONE_ID
WHATSAPP_API_TOKEN=YOUR_API_TOKEN
WHATSAPP_BUSINESS_ID=YOUR_BUSINESS_ID
WHATSAPP_WEBHOOK_TOKEN=sentry_webhook_2026
EOF

# Verify
cat $SENTRY_HOME/.env.local | grep WHATSAPP
```

---

## Part 4: Integration with Bot

### 4.1 Update bot.py

Add to imports:
```python
from webhooks.whatsapp_webhook import router as whatsapp_router
from handlers.whatsapp_handler import get_whatsapp_handler
```

Add to FastAPI setup (after existing routers):
```python
# Register WhatsApp webhook
app.include_router(whatsapp_router)
```

---

## Part 5: Testing

### 5.1 Test Message Send

```bash
#!/bin/bash
# test_whatsapp.sh

cd $SENTRY_HOME

python3 << 'TESTEOF'
import asyncio
import os
from integrations.whatsapp_service import get_whatsapp_service

async def test_send():
    print("Testing WhatsApp message send...")
    service = get_whatsapp_service()

    result = await service.send_text_message(
        to_number="+27721234567",  # Replace with test number
        message="🧪 Test message from SENTRY WhatsApp integration"
    )

    if result["success"]:
        print(f"✅ Success! Message ID: {result['message_id']}")
    else:
        print(f"❌ Failed: {result.get('error')}")

asyncio.run(test_send())
TESTEOF
```

### 5.2 Test Webhook Verification

```bash
# If using ngrok
WEBHOOK_URL="https://abc123.ngrok.io/webhooks/whatsapp"

# Test verification
curl -X GET \
  "$WEBHOOK_URL?hub.mode=subscribe&hub.verify_token=sentry_webhook_2026&hub.challenge=1234567890"

# Expected response: 1234567890
```

### 5.3 Test Incoming Message

```bash
# Simulate incoming message
curl -X POST \
  -H "Content-Type: application/json" \
  -d '{
    "object": "whatsapp_business_account",
    "entry": [{
      "changes": [{
        "value": {
          "messages": [{
            "from": "27721234567",
            "id": "wamid.123",
            "timestamp": "1234567890",
            "type": "text",
            "text": {"body": "Help"}
          }]
        }
      }]
    }]
  }' \
  http://localhost:8000/webhooks/whatsapp
```

---

## Part 6: Validation Checklist

Run this to verify Stage 6 completion:

```bash
#!/bin/bash
# validate_stage6.sh

echo "=== Stage 6 Validation ==="

# 1. Check files exist
echo ""
echo "1. Python files:"
for f in integrations/whatsapp_service.py handlers/whatsapp_handler.py webhooks/whatsapp_webhook.py; do
  [ -f "$SENTRY_HOME/$f" ] && echo "  ✓ $f" || echo "  ✗ MISSING: $f"
done

# 2. Check config files
echo ""
echo "2. Config files:"
[ -f "$SENTRY_HOME/config/technicians_whatsapp.json" ] && echo "  ✓ technicians_whatsapp.json" || echo "  ✗ MISSING"

# 3. Check environment
echo ""
echo "3. Environment variables:"
grep -q "WHATSAPP_PROVIDER" "$SENTRY_HOME/.env.local" && echo "  ✓ WHATSAPP_PROVIDER set" || echo "  ✗ NOT SET"
grep -q "WHATSAPP_WEBHOOK_TOKEN" "$SENTRY_HOME/.env.local" && echo "  ✓ WHATSAPP_WEBHOOK_TOKEN set" || echo "  ✗ NOT SET"

# 4. Check bot.py integration
echo ""
echo "4. bot.py integration:"
grep -q "whatsapp_router" "$SENTRY_HOME/bot.py" && echo "  ✓ WhatsApp router imported" || echo "  ✗ Router not imported"

echo ""
echo "=== Validation Complete ==="
```

---

## Part 7: Troubleshooting

If tests fail, check:

```bash
# 1. Environment loaded
echo $WHATSAPP_API_TOKEN

# 2. Files readable
ls -la $SENTRY_HOME/integrations/whatsapp_service.py
ls -la $SENTRY_HOME/config/technicians_whatsapp.json

# 3. Python syntax
python3 -m py_compile $SENTRY_HOME/integrations/whatsapp_service.py

# 4. Logs
tail -f $SENTRY_HOME/logs/sentry.log
```

---

## Next: Stage 7

After Stage 6 validation completes:

**Stage 7**: Deploy to Jetson AGX Orin with `SENTRY_HOME=/opt/sentry`

---

**Version**: 1.0 | **Status**: Ready for Execution
