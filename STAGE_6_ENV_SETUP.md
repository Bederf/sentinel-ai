# Stage 6: WhatsApp Environment Configuration

## Quick Setup (Choose One)

### Option 1: Twilio Sandbox (Fastest - Recommended for Testing)

**Time**: 10 minutes | **Cost**: Free (use $15 credit)

```bash
# 1. Sign up at https://www.twilio.com/try-twilio
# 2. Get credentials from console:
#    - Account SID: ACxxxxxxxxxxxxxxxxx
#    - Auth Token: (copy to .env)
#    - WhatsApp Number: +14155552368 (sandbox number)

# 3. Add to backend/.env.local:

WHATSAPP_PROVIDER=twilio
TWILIO_ACCOUNT_SID=ACxxxxxxxxxxxxxxxxx
TWILIO_AUTH_TOKEN=your_auth_token_here
TWILIO_WHATSAPP_NUMBER=+14155552368
WHATSAPP_WEBHOOK_TOKEN=sentry_webhook_secure_2026

# 4. Add your phone to sandbox:
#    - Go to Twilio Console → Messaging → WhatsApp Sandbox
#    - Send: "join <code>" to sandbox number
#    - Receive: Confirmation message
```

### Option 2: Meta Cloud API (Recommended for Production)

**Time**: 30 minutes | **Cost**: $5-35/month | **Setup**: Requires API approval (24-48 hrs)

```bash
# 1. Create Facebook App: https://developers.facebook.com/
#    - App Type: Business
#    - App Name: SENTRY BMS
#    - Category: Business Management
#
# 2. Add WhatsApp Product:
#    - In App Dashboard → Add Product
#    - Select WhatsApp
#    - Choose "Cloud API"
#
# 3. Get Phone Number ID:
#    - Settings → WhatsApp Senders
#    - Your Business Number → Phone Number ID
#
# 4. Generate API Token:
#    - Settings → User Tokens
#    - Create Token with permissions:
#      - whatsapp_business_messaging
#      - whatsapp_business_management
#    - Copy token (don't share!)
#
# 5. Get Business Account ID:
#    - Settings → Business Details
#    - Business Account ID (109876543210987)
#
# 6. Register Webhook:
#    - Settings → Configuration
#    - Webhook URL: https://your-domain.com/api/whatsapp/webhooks
#    - Verify Token: sentry_webhook_secure_2026
#    - Subscribe to: messages, message_template_status_update

# 7. Add to backend/.env.local:

WHATSAPP_PROVIDER=meta
WHATSAPP_PHONE_ID=102348901234567
WHATSAPP_API_TOKEN=EAAxxxxxxxxxxxx
WHATSAPP_BUSINESS_ID=109876543210987
WHATSAPP_WEBHOOK_TOKEN=sentry_webhook_secure_2026
```

---

## Testing Without Actual WhatsApp

### Option 3: Mock Testing (No Credentials Needed)

For development without real API credentials:

```bash
# In backend/.env.local:
WHATSAPP_PROVIDER=mock
WHATSAPP_WEBHOOK_TOKEN=sentry_webhook_secure_2026

# This will:
# ✓ Accept webhook verification
# ✓ Log messages to console
# ✓ Skip actual API calls
# ✓ Return success without sending
```

---

## Environment File Template

**File**: `backend/.env.local`

```bash
# ============================================================================
# WhatsApp Configuration - Stage 6
# ============================================================================

# Provider: "meta" (production), "twilio" (testing), "mock" (development)
WHATSAPP_PROVIDER=twilio

# === Twilio Configuration (if WHATSAPP_PROVIDER=twilio) ===
TWILIO_ACCOUNT_SID=ACxxxxxxxxxxxxxxxxx
TWILIO_AUTH_TOKEN=your_auth_token_here
TWILIO_WHATSAPP_NUMBER=+14155552368

# === Meta Cloud API Configuration (if WHATSAPP_PROVIDER=meta) ===
WHATSAPP_PHONE_ID=102348901234567
WHATSAPP_API_TOKEN=EAAxxxxxxxxxxxx
WHATSAPP_BUSINESS_ID=109876543210987

# === Common Configuration ===
WHATSAPP_WEBHOOK_TOKEN=sentry_webhook_secure_2026

# ============================================================================
# End WhatsApp Configuration
# ============================================================================
```

---

## Verification Steps

### 1. Check Environment Loaded

```bash
# Verify backend can read config
cd backend
python3 -c "
from app.config.settings import settings
from app.integrations.whatsapp_service import get_whatsapp_service

service = get_whatsapp_service()
print(f'WhatsApp Service Status: {service.get_status()}')
"
```

Expected output:
```
WhatsApp Service Status: {
  'enabled': True,
  'provider': 'twilio',
  'phone_id': None,
  'twilio_number': '+14155552368'
}
```

### 2. Test Message Send

```bash
# Terminal 1: Start backend
cd backend
DEMO_MODE=true python -m uvicorn app.main:app --reload --port 9095

# Terminal 2: Test send
python3 << 'EOF'
import asyncio
from app.integrations.whatsapp_service import get_whatsapp_service

async def test():
    service = get_whatsapp_service()
    result = await service.send_text_message(
        to_number="+27721234567",
        message="🧪 Test message from SENTRY WhatsApp integration"
    )
    print(f"Result: {result}")

asyncio.run(test())
EOF
```

### 3. Webhook Verification Test

```bash
# If using ngrok:
ngrok http 8000  # Starts tunnel

# Register webhook with provider:
# Twilio: Console → WhatsApp Sandbox → Update URL
# Meta: App Dashboard → Settings → Configuration → Webhook URL

# Test verification (should return challenge):
curl -X GET \
  "http://localhost:9095/api/whatsapp/webhooks?hub.mode=subscribe&hub.verify_token=sentry_webhook_secure_2026&hub.challenge=1234567890"

# Expected response: 1234567890
```

---

## Technician Phone Configuration

**File**: `backend/app/data/technicians_whatsapp.json`

Update with real phone numbers:

```json
{
  "technicians": [
    {
      "id": "tech-001",
      "name": "John Smith",
      "specialty": "electrical",
      "whatsapp_number": "+27721234567",  # ← Your tech's WhatsApp number
      "active": true,
      "site_id": "S002"
    },
    {
      "id": "tech-002",
      "name": "Mike Johnson",
      "specialty": "hvac",
      "whatsapp_number": "+27721234568",  # ← Your tech's WhatsApp number
      "active": true,
      "site_id": "S002"
    }
  ]
}
```

---

## Troubleshooting

### Problem: "WhatsApp service not enabled"

**Cause**: Environment variables not set
**Solution**:
```bash
# Check what's loaded
echo "WHATSAPP_PROVIDER=$WHATSAPP_PROVIDER"
echo "TWILIO_ACCOUNT_SID=$TWILIO_ACCOUNT_SID"

# Make sure .env.local exists and sourced
ls -la backend/.env.local
source backend/.env.local  # If not auto-sourced
```

### Problem: 403 on Webhook Verification

**Cause**: Token mismatch
**Solution**:
```bash
# Verify token matches
# In Meta/Twilio: hub.verify_token=sentry_webhook_secure_2026
# In backend/.env.local: WHATSAPP_WEBHOOK_TOKEN=sentry_webhook_secure_2026
```

### Problem: "Invalid API Token"

**Cause**: Token expired or invalid
**Solution**:
```bash
# Generate new token from provider console:
# Twilio: Copy auth token again from console
# Meta: Settings → User Tokens → Generate new token
```

---

## Security Best Practices

⚠️ **NEVER commit secrets to git:**

```bash
# ✗ WRONG
git add backend/.env.local
git commit -m "Add env"

# ✓ RIGHT
echo "backend/.env.local" >> .gitignore
git add .gitignore
```

✅ **Store secrets safely:**

```bash
# Development: Local .env.local file
# Production: Use Kubernetes secrets or environment variables

# For Kubernetes:
kubectl create secret generic whatsapp-secrets \
  --from-literal=TWILIO_ACCOUNT_SID=... \
  --from-literal=TWILIO_AUTH_TOKEN=... \
  -n production
```

---

## Next Steps

1. ✅ **Choose provider** (Twilio for testing, Meta for production)
2. ✅ **Get credentials** from provider console
3. ✅ **Add to backend/.env.local**
4. ✅ **Update technician phone numbers** in JSON
5. ✅ **Test message send** with verification script
6. ✅ **Register webhook** with provider
7. ✅ **Verify webhook** receives test messages
8. ✅ **Monitor logs** for any errors

---

## Support

Having issues? Check:
1. `.env.local` file exists and readable
2. All credentials copied correctly (no spaces!)
3. Webhook URL registered with provider
4. Webhook token matches between provider and `.env.local`
5. Backend logs: `tail -f backend/logs/app.log`

---

**Version**: 1.0 | **Date**: 2026-02-18
