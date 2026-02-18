# Stage 6: WhatsApp Integration — Quick Start (10 Minutes)

**Complete these 5 steps to enable WhatsApp in SENTRY bot**

---

## Step 1: Get WhatsApp Credentials (5 min)

### Choose Your Path:

**Option A: Twilio (Fastest - Recommended for Testing)**
```bash
# Sign up: https://www.twilio.com/try-twilio
# Get: Account SID, Auth Token, WhatsApp Number
# Get for FREE: $15 credit for testing

export WHATSAPP_PROVIDER=twilio
export TWILIO_ACCOUNT_SID=AC_____________
export TWILIO_AUTH_TOKEN=________________
export TWILIO_WHATSAPP_NUMBER=+14155552368
```

**Option B: Meta Cloud API (Recommended for Production)**
```bash
# 1. Create app: https://developers.facebook.com/
# 2. Add WhatsApp product
# 3. Get: Phone ID, API Token, Business ID

export WHATSAPP_PROVIDER=meta
export WHATSAPP_PHONE_ID=102348901234567
export WHATSAPP_API_TOKEN=EAA____________
export WHATSAPP_BUSINESS_ID=109876543210987
export WHATSAPP_WEBHOOK_TOKEN=sentry_webhook_2026
```

---

## Step 2: Create Python Files (3 min)

**Copy these 3 files into $SENTRY_HOME/**

### File 1: `integrations/whatsapp_service.py`
[160 lines - See STAGE_6_WHATSAPP_IMPLEMENTATION.md Part 2.1]

### File 2: `handlers/whatsapp_handler.py`
[80 lines - See STAGE_6_WHATSAPP_IMPLEMENTATION.md Part 2.2]

### File 3: `webhooks/whatsapp_webhook.py`
[70 lines - See STAGE_6_WHATSAPP_IMPLEMENTATION.md Part 2.3]

---

## Step 3: Add Configuration (2 min)

**Add to `$SENTRY_HOME/.env.local`:**
```bash
WHATSAPP_PROVIDER=twilio  # or meta
TWILIO_ACCOUNT_SID=AC_____________
TWILIO_AUTH_TOKEN=________________
TWILIO_WHATSAPP_NUMBER=+14155552368
WHATSAPP_WEBHOOK_TOKEN=sentry_webhook_2026
```

**Create `$SENTRY_HOME/config/technicians_whatsapp.json`:**
```json
{
  "technicians": [
    {
      "id": "tech-001",
      "name": "John Smith",
      "whatsapp_number": "+27721234567"
    }
  ]
}
```

---

## Step 4: Update Bot (1 min)

**In `$SENTRY_HOME/bot.py`, add imports:**
```python
from webhooks.whatsapp_webhook import router as whatsapp_router
from handlers.whatsapp_handler import get_whatsapp_handler
```

**Add to FastAPI app:**
```python
app.include_router(whatsapp_router)
```

---

## Step 5: Test (1 min)

```bash
# Start bot
cd $SENTRY_HOME
DEMO_MODE=true python3 bot.py

# In another terminal, test send:
python3 << 'EOF'
import asyncio
from integrations.whatsapp_service import get_whatsapp_service

async def test():
    service = get_whatsapp_service()
    result = await service.send_text_message(
        to_number="+27721234567",
        message="🧪 Test from SENTRY"
    )
    print("✅ Success!" if result["success"] else f"❌ Failed: {result}")

asyncio.run(test())
EOF
```

---

## ✅ Stage 6 Complete When:

- [ ] WhatsApp credentials obtained
- [ ] 3 Python files created in $SENTRY_HOME
- [ ] Configuration files added
- [ ] bot.py updated with webhook registration
- [ ] Test message sends successfully

---

**Next**: Stage 7 - Deploy to Jetson AGX Orin

See `STAGE_6_WHATSAPP_SETUP.md` for detailed documentation
