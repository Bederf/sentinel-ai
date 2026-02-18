# Stage 6: WhatsApp Channel Integration — Complete Setup Guide

**Phase**: SENTRY Rollout Stage 6/8
**Goal**: Add WhatsApp Business API channel to multi-channel SENTRY bot
**Duration**: 30-45 minutes
**Status**: Ready for Implementation

---

## Overview

This stage adds WhatsApp messaging capability to the SENTRY bot, enabling technicians and facilities managers to receive work orders, alerts, and safety notifications via WhatsApp in addition to Telegram.

### Multi-Channel Architecture

```
┌─────────────────┐
│  SENTINEL BMS   │
│   API Events    │
└────────┬────────┘
         │
         ▼
┌─────────────────────┐
│  SENTRY Bot         │
│ (Python/Telegram)   │
└────────┬────────────┘
         │
    ┌────┴────┐
    ▼         ▼
┌────────┐ ┌──────────┐
│Telegram│ │ WhatsApp │
│  Bot   │ │ Business │
└────────┘ └──────────┘
    ▲         ▲
    │         │
┌───┴─────────┴───┐
│   Technicians   │
│ Facilities Mgmt │
└─────────────────┘
```

### What Gets Delivered

✅ WhatsApp Business Account integration
✅ Webhook endpoint for incoming WhatsApp messages
✅ Message routing from SENTRY bot to WhatsApp
✅ Multi-channel notification support
✅ Configuration for both Telegram and WhatsApp
✅ Testing & validation scripts

---

## 1. WhatsApp Business Setup Options

### Quick Decision: Which Provider?

**For Production (South Africa)**: Use Meta Cloud API
**For Testing/MVP**: Use Twilio Sandbox
**For Development**: Use both (configure provider in env)

---

## Option A: Meta Cloud API (Recommended for Production)

### Pros
- Official Meta API, most stable and feature-complete
- No local infrastructure required
- Scales to 1000+ messages/day easily
- Built-in analytics and delivery reports
- Best for multi-country deployments
- Lowest per-message cost (~$0.01-0.03)

### Cons
- Requires WhatsApp Business Account verification
- API approval process (24-48 hours)
- Monthly message limits based on tier ($5-35/month)
- Phone number must be verified

### Setup Steps

#### 1.1 Create WhatsApp Business Account

```bash
# Visit: https://www.whatsapp.com/business/
# - Sign up with business email
# - Select: Cloud API (not Hosted API)
# - Verify business phone number (+27 for South Africa)
# - Complete KYC verification (2-4 hours)
```

#### 1.2 Register with Meta Business Platform

```bash
# 1. Create Facebook App
url: https://developers.facebook.com/
- Click "Create App"
- Select: Business
- App Type: "Business"
- App Name: "SENTRY BMS Bot"
- Business Purpose: "Facility Management Automation"

# 2. Add WhatsApp Product
- In App Dashboard → Products
- Find "WhatsApp" → Add to App
- Click "Set Up"
- Select: "Cloud API" option

# 3. Get Credentials
- Phone Number ID (in WhatsApp Setup → Senders)
- Business Account ID (Settings → Business Details)
- API Token (Settings → User Tokens → Generate)
```

#### 1.3 Generate API Credentials

```bash
# In Meta App Dashboard:

# Get Phone Number ID
Settings → WhatsApp Senders → Your Number → Phone Number ID
Example: 102348901234567

# Get Business Account ID
Settings → Business Details → Business Account ID
Example: 109876543210987

# Generate API Token
Settings → User Tokens → Generate Token
- Name: "SENTRY Bot"
- Permissions: whatsapp_business_messaging
- Token expires: Custom (1 year)
```

#### 1.4 Configure Webhook URL

```bash
# In Meta App Dashboard → WhatsApp → Configuration

# Webhook URL: https://your-domain.com/api/webhooks/whatsapp
# or for local: Use ngrok tunnel (see below)
# Verify Token: Generate random string (store in WHATSAPP_WEBHOOK_TOKEN)

# Example Verify Token: "sentry_webhook_secure_token_2026"
```

#### 1.5 Testing with ngrok (Local Development)

```bash
# For testing locally without deploying:

# 1. Install ngrok
curl https://ngrok-agent.s3.amazonaws.com/ngrok-v3-stable-linux-amd64.zip -o ngrok.zip
unzip ngrok.zip
sudo mv ngrok /usr/local/bin/

# 2. Start ngrok tunnel
ngrok http 8000  # Assuming bot runs on port 8000
# Output: https://abc123.ngrok.io

# 3. Register webhook with Meta
# Webhook URL: https://abc123.ngrok.io/api/webhooks/whatsapp
# Verify Token: sentry_webhook_secure_token_2026

# 4. Bot auto-receives messages from ngrok tunnel
```

---

## Option B: Twilio WhatsApp (Quick Testing)

### Pros
- Free testing environment (Twilio Sandbox)
- Works immediately, no approval wait
- Easy integration, well-documented
- Good for MVP/demo proof-of-concept
- Shared phone number for testing

### Cons
- Limited to 1 Twilio sandbox number
- Can only send to pre-approved phone numbers
- Not suitable for production
- Per-message costs for production (~$0.0075/msg)

### Quick Setup

```bash
# 1. Sign up for free Twilio account
url: https://www.twilio.com/try-twilio

# 2. Get Twilio Credentials
Account SID: AC0123456789...
Auth Token: (never commit to git!)

# 3. Set up WhatsApp Sandbox
Twilio Console → Messaging → Try WhatsApp
- Get Sandbox Number: +14155552368 (example)
- Add your phone number as participant
- Receive test number activation code

# 4. Get API credentials
Services → Messaging → WhatsApp
- Account SID (copy from console)
- Auth Token (copy from console)
- Twilio WhatsApp Number (+14155552368)
```

---

## 2. Implementation: Multi-Channel Message Handler

### File Structure

```
$SENTRY_HOME/
├── handlers/
│   ├── telegram_handler.py     (existing)
│   ├── whatsapp_handler.py     (NEW - Stage 6)
│   └── __init__.py
├── integrations/
│   ├── __init__.py
│   ├── telegram_service.py     (existing)
│   └── whatsapp_service.py     (NEW - Stage 6)
├── config/
│   ├── __init__.py
│   ├── channels.yaml           (NEW - multi-channel config)
│   └── technicians_whatsapp.json (NEW - phone mappings)
├── webhooks/
│   ├── __init__.py
│   ├── telegram_webhook.py     (existing)
│   └── whatsapp_webhook.py     (NEW - Stage 6)
└── bot.py                       (updated - Stage 6)
```

### Step 1: Create WhatsApp Service

**File**: `$SENTRY_HOME/integrations/whatsapp_service.py`

```python
"""
WhatsApp Business API integration for SENTRY bot.
Supports both Meta Cloud API and Twilio.
"""

import httpx
import os
from typing import Optional, Dict, Any
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


class WhatsAppService:
    """WhatsApp Business API integration."""

    def __init__(self, provider: str = "meta"):
        """
        Initialize WhatsApp service.

        Args:
            provider: "meta" (Cloud API) or "twilio"
        """
        self.provider = provider

        if provider == "meta":
            self.phone_id = os.getenv("WHATSAPP_PHONE_ID", "")
            self.api_token = os.getenv("WHATSAPP_API_TOKEN", "")
            self.business_id = os.getenv("WHATSAPP_BUSINESS_ID", "")
            self.api_url = f"https://graph.instagram.com/v18.0/{self.phone_id}/messages"

        elif provider == "twilio":
            self.account_sid = os.getenv("TWILIO_ACCOUNT_SID", "")
            self.auth_token = os.getenv("TWILIO_AUTH_TOKEN", "")
            self.twilio_whatsapp = os.getenv("TWILIO_WHATSAPP_NUMBER", "")
            self.api_url = f"https://api.twilio.com/2010-04-01/Accounts/{self.account_sid}/Messages.json"

        self.webhook_token = os.getenv("WHATSAPP_WEBHOOK_TOKEN", "secret")

    async def send_text_message(
        self,
        to_number: str,
        message: str,
        context_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Send text message via WhatsApp.

        Args:
            to_number: Recipient phone (format: +27XXXXXXXXX for SA)
            message: Message text (max 1024 chars)
            context_id: Optional context message ID for threading

        Returns:
            Response with message ID and status
        """
        try:
            if self.provider == "meta":
                return await self._send_meta_text(to_number, message, context_id)
            else:
                return await self._send_twilio_text(to_number, message)
        except Exception as e:
            logger.error(f"Error sending WhatsApp message: {e}")
            return {"success": False, "error": str(e)}

    async def _send_meta_text(
        self,
        to_number: str,
        message: str,
        context_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Send via Meta Cloud API."""
        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": to_number,
            "type": "text",
            "text": {"preview_url": True, "body": message}
        }

        if context_id:
            payload["context"] = {"message_id": context_id}

        headers = {
            "Authorization": f"Bearer {self.api_token}",
            "Content-Type": "application/json"
        }

        async with httpx.AsyncClient() as client:
            response = await client.post(
                self.api_url,
                json=payload,
                headers=headers,
                timeout=10.0
            )
            response.raise_for_status()
            data = response.json()
            return {
                "success": True,
                "message_id": data.get("messages", [{}])[0].get("id"),
                "timestamp": datetime.utcnow().isoformat(),
                "provider": "meta"
            }

    async def _send_twilio_text(
        self,
        to_number: str,
        message: str
    ) -> Dict[str, Any]:
        """Send via Twilio."""
        payload = {
            "From": self.twilio_whatsapp,
            "To": f"whatsapp:{to_number}",
            "Body": message
        }

        auth = (self.account_sid, self.auth_token)

        async with httpx.AsyncClient() as client:
            response = await client.post(
                self.api_url,
                data=payload,
                auth=auth,
                timeout=10.0
            )
            response.raise_for_status()
            data = response.json()
            return {
                "success": True,
                "message_id": data.get("sid"),
                "timestamp": datetime.utcnow().isoformat(),
                "provider": "twilio"
            }

    def verify_webhook_token(self, token: str) -> bool:
        """Verify webhook token for security."""
        return token == self.webhook_token


# Singleton instance
_whatsapp_service: Optional[WhatsAppService] = None


def get_whatsapp_service(provider: str = "meta") -> WhatsAppService:
    """Get or create WhatsApp service singleton."""
    global _whatsapp_service
    if _whatsapp_service is None:
        provider_env = os.getenv("WHATSAPP_PROVIDER", "meta")
        _whatsapp_service = WhatsAppService(provider_env)
    return _whatsapp_service
```

### Step 2: Create WhatsApp Handler

**File**: `$SENTRY_HOME/handlers/whatsapp_handler.py`

```python
"""
WhatsApp event handlers for SENTRY notifications.
Maps BMS events to WhatsApp messages for technicians.
"""

from typing import Dict, Any, Optional
from integrations.whatsapp_service import get_whatsapp_service
import json
import logging
from datetime import datetime

logger = logging.getLogger(__name__)


class WhatsAppHandler:
    """Handle WhatsApp messaging for SENTRY bot."""

    def __init__(self):
        self.service = get_whatsapp_service()
        self.technician_mapping = self._load_technician_mapping()

    def _load_technician_mapping(self) -> Dict[str, str]:
        """Load technician WhatsApp phone numbers."""
        try:
            with open("config/technicians_whatsapp.json", "r") as f:
                data = json.load(f)
                return {t["id"]: t["whatsapp_number"] for t in data.get("technicians", [])}
        except FileNotFoundError:
            logger.warning("technicians_whatsapp.json not found, using demo data")
            return {
                "tech-001": "+27721234567",
                "tech-002": "+27721234568",
                "tech-003": "+27721234569"
            }

    async def send_work_order_assignment(
        self,
        work_order: Dict[str, Any],
        technician_id: str
    ) -> bool:
        """
        Notify technician of work order assignment via WhatsApp.
        """
        phone = self.technician_mapping.get(technician_id)
        if not phone:
            logger.warning(f"No WhatsApp number for technician {technician_id}")
            return False

        message = f"""🔧 *Work Order Assigned*

*ID*: {work_order.get('id', 'N/A')}
*Priority*: {work_order.get('priority', 'NORMAL')}
*Equipment*: {work_order.get('equipment_code', 'N/A')}
*Location*: {work_order.get('location', 'N/A')}
*Description*: {work_order.get('description', 'No description')}"""

        try:
            result = await self.service.send_text_message(phone, message)
            return result.get("success", False)
        except Exception as e:
            logger.error(f"Error sending WhatsApp: {e}")
            return False

    async def send_critical_alert(
        self,
        alert: Dict[str, Any],
        recipient_ids: list
    ) -> int:
        """Send critical alert to multiple technicians."""
        count = 0
        message = f"""🚨 *CRITICAL ALERT*

*Type*: {alert.get('type', 'System')}
*Equipment*: {alert.get('equipment_code', 'Unknown')}
*Severity*: {alert.get('severity', 'High')}
*Details*: {alert.get('description', 'No details')}

⚠️ Immediate action required!"""

        for tech_id in recipient_ids:
            phone = self.technician_mapping.get(tech_id)
            if phone:
                try:
                    result = await self.service.send_text_message(phone, message)
                    if result.get("success"):
                        count += 1
                except Exception as e:
                    logger.error(f"Error sending to {phone}: {e}")

        return count


# Singleton
_handler: Optional[WhatsAppHandler] = None


def get_whatsapp_handler() -> WhatsAppHandler:
    """Get WhatsApp handler singleton."""
    global _handler
    if _handler is None:
        _handler = WhatsAppHandler()
    return _handler
```

### Step 3: Create Webhook Endpoint

**File**: `$SENTRY_HOME/webhooks/whatsapp_webhook.py`

```python
"""
WhatsApp webhook endpoint for receiving incoming messages.
Integrates with FastAPI in bot.py
"""

from fastapi import APIRouter, Request, HTTPException
from integrations.whatsapp_service import get_whatsapp_service
import logging

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/webhooks", tags=["whatsapp"])


@router.get("/whatsapp")
async def verify_whatsapp_webhook(request: Request):
    """
    WhatsApp webhook verification (GET).
    Meta sends: hub.mode, hub.verify_token, hub.challenge
    """
    mode = request.query_params.get("hub.mode")
    token = request.query_params.get("hub.verify_token")
    challenge = request.query_params.get("hub.challenge")

    if mode != "subscribe":
        raise HTTPException(status_code=403, detail="Invalid mode")

    service = get_whatsapp_service()
    if not service.verify_webhook_token(token):
        raise HTTPException(status_code=403, detail="Invalid token")

    logger.info(f"WhatsApp webhook verified with token: {token[:10]}...")
    return int(challenge)


@router.post("/whatsapp")
async def handle_whatsapp_message(request: Request):
    """
    Handle incoming WhatsApp messages (POST).
    """
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
        message_type = message.get("type", "text")
        content = message.get("text", {}).get("body", "") if message_type == "text" else ""

        logger.info(f"Incoming WhatsApp from {from_number}: {content}")

        # Route message to handler
        await route_incoming_message(from_number, content)

        return {"status": "ok"}

    except Exception as e:
        logger.error(f"Error handling WhatsApp message: {e}")
        return {"status": "error", "message": str(e)}


async def route_incoming_message(from_number: str, content: str) -> None:
    """Route incoming WhatsApp message to appropriate handler."""
    service = get_whatsapp_service()

    if content.startswith("WO-"):
        msg = f"Work order lookup: {content} - Coming soon"
        await service.send_text_message(from_number, msg)
    elif content.lower() in ["status", "summary"]:
        msg = "📊 Status: All systems operational"
        await service.send_text_message(from_number, msg)
    elif content.lower() in ["help", "?"]:
        msg = """*SENTRY Bot Commands*
*WO-XXX* - Lookup work order
*Status* - Show facility status
*Help* - Show this message"""
        await service.send_text_message(from_number, msg)
    else:
        msg = "Type *Help* for available commands"
        await service.send_text_message(from_number, msg)
```

---

## 3. Configuration Files

### `.env.local`

```bash
# WhatsApp Provider (meta or twilio)
WHATSAPP_PROVIDER=meta

# Meta Cloud API
WHATSAPP_PHONE_ID=102348901234567
WHATSAPP_API_TOKEN=your_long_api_token_here
WHATSAPP_BUSINESS_ID=109876543210987
WHATSAPP_WEBHOOK_TOKEN=sentry_webhook_secure_token_2026

# Alternative: Twilio
TWILIO_ACCOUNT_SID=AC0123456789abcdef
TWILIO_AUTH_TOKEN=your_twilio_auth_token
TWILIO_WHATSAPP_NUMBER=+14155552368
```

### `config/technicians_whatsapp.json`

```json
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
    }
  ]
}
```

---

## 4. Integration & Testing

### Update bot.py

Add to imports:
```python
from webhooks.whatsapp_webhook import router as whatsapp_router
from handlers.whatsapp_handler import get_whatsapp_handler
```

Add to FastAPI setup:
```python
# Register WhatsApp webhook
app.include_router(whatsapp_router)
```

### Testing Script

```bash
#!/bin/bash
# test_whatsapp_stage6.sh

SENTRY_HOME="/home/bederf/.sentry"
cd $SENTRY_HOME

echo "🧪 Stage 6: WhatsApp Integration Tests"
echo ""

# Test 1: Send message
echo "Test 1: Send WhatsApp message..."
python3 << 'EOF'
import asyncio
from integrations.whatsapp_service import get_whatsapp_service

async def test():
    service = get_whatsapp_service()
    result = await service.send_text_message(
        to_number="+27721234567",
        message="🧪 Test message from SENTRY"
    )
    print(f"✓ Success" if result["success"] else f"✗ Failed: {result}")

asyncio.run(test())
EOF

echo ""
echo "Tests complete!"
```

---

## 5. Deployment Checklist

### Pre-Deployment
- [ ] WhatsApp Business Account created
- [ ] API credentials obtained (Phone ID, Token, Business ID)
- [ ] Webhook token generated and configured
- [ ] Technician phone numbers in config/technicians_whatsapp.json
- [ ] Environment variables in .env.local
- [ ] Test message sends successfully

### Deployment
- [ ] Start bot: `cd $SENTRY_HOME && python3 bot.py`
- [ ] Verify webhook listening
- [ ] Test work order notification
- [ ] Test incoming message handling
- [ ] Monitor logs for errors

### Post-Deployment
- [ ] Document Meta API settings
- [ ] Set up webhook logs monitoring
- [ ] Configure message retry logic
- [ ] Create technician update procedure

---

## 6. Success Criteria

✅ **Stage 6 Complete** when:

1. **Meta/Twilio Account**: WhatsApp Business Account active with API credentials
2. **Webhook Registered**: `/api/webhooks/whatsapp` receiving events from Meta
3. **Outbound Messages**: SENTRY bot sends test message to technician WhatsApp
4. **Inbound Messages**: Technician can send WO lookup, receives response
5. **Fallback Working**: If Telegram fails, messages go to WhatsApp
6. **No Hardcoding**: All phone numbers in config files, none in code
7. **Error Handling**: Network failures don't crash bot
8. **Logging**: All events logged for troubleshooting

---

## 7. Troubleshooting

| Issue | Solution |
|-------|----------|
| 403 on webhook verification | Check `hub.verify_token` matches `WHATSAPP_WEBHOOK_TOKEN` |
| Messages not sent | Verify phone format: `+27XXXXXXXXX`, credentials in .env |
| Webhook not called | Confirm URL registered in Meta/Twilio settings |
| AsyncClient timeout | Check internet connection, try 15s timeout |
| ModuleNotFoundError | `pip install httpx` |

---

## Next Stages

**Stage 7**: Deploy to Jetson AGX Orin (`SENTRY_HOME=/opt/sentry`)
**Stage 8**: Multi-site configuration rollout

---

**Version**: 1.0 | **Date**: 2026-02-18 | **Status**: Ready for Implementation
