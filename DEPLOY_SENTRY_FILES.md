# Deploy to Sentry Bot - Phase 41 Integration Files

## Files to Copy

### Step 1: Notification Tool (Converts work orders to Telegram notifications)
```bash
# Source
/opt/bms-intelligence/backend/app/services/sentry_integration/wo_notifier_tool.py

# Destination (copy to)
$SENTRY_HOME/tools/wo_notifier.py

# Make executable
chmod +x $SENTRY_HOME/tools/wo_notifier.py
```

**Purpose:** Sends work order notifications to technicians via Telegram

**Usage:**
```bash
cd $SENTRY_HOME
python tools/wo_notifier.py notify --help
python tools/wo_notifier.py status SR-2026-XXX
```

---

### Step 2: Conversation Handler (Manages "done" reply flow)
```bash
# Source
/opt/bms-intelligence/backend/app/services/sentry_integration/conversation_handler.py

# Destination (create directory if needed)
mkdir -p $SENTRY_HOME/handlers/
$SENTRY_HOME/handlers/wo_conversation_handler.py
```

**Purpose:** Handles the back-and-forth conversation after technician replies "done"

**Key Methods:**
- `handle_initial_done()` - Gets first prompt after "done"
- `handle_file_reply()` - Processes uploaded files/photos/audio
- `format_status_message()` - Shows what's still needed

---

### Step 3: AI Bridge Integration Snippets (Update existing file)
```bash
# View integration guide
/opt/bms-intelligence/backend/app/services/sentry_integration/sentry_ai_bridge_integration.py

# Edit existing file
$SENTRY_HOME/tools/sentry_ai_bridge.py
```

**Add these code blocks to sentry_ai_bridge.py:**

**A. Add import:**
```python
from handlers.wo_conversation_handler import WOConversationHandler
```

**B. Add pattern detection function:**
```python
def is_work_order_message(message: str) -> tuple[bool, Optional[str], Optional[str]]:
    # Detects "done", service record codes, status requests
```

**C. Add handlers:**
```python
def handle_work_order_initial(service_record_code: str, telegram_user_id: str) -> str:
    # Handles "done" reply - starts data collection

def handle_wo_file_upload(service_record_code: str, telegram_user_id: str,
                         file_info: Dict[str, Any], message_type: str) -> str:
    # Handles photo/audio/file uploads

def handle_wo_status(service_record_code: str, telegram_user_id: str) -> str:
    # Shows collection progress
```

**D. Update message routing:**
```python
def detect_and_route(message: str, user_id: str, ...):
    # Add work order detection before existing routing
    is_wo, sr_code, action = is_work_order_message(message)
    if is_wo and sr_code:
        # Route to appropriate handler
```

**E. Update file upload handling:**
```python
def handle_incoming_file(user_id: str, file_info: dict):
    # Check if during active work order collection
    # Route to handle_wo_file_upload if yes
```

Reference: Full code in `sentry_ai_bridge_integration.py`

---

### Step 4: Bot Message Handlers (Update existing file)
```bash
# Edit existing file
$SENTRY_HOME/bot.py
```

**Add these handlers:**

**A. Text message handler for "done":**
```python
@bot.message_handler(content_types=['text'])
def handle_message(message):
    user_id = message.from_user.username or str(message.from_user.id)
    # Route through sentry_ai_bridge.detect_and_route()
```

**B. File upload handler:**
```python
@bot.message_handler(content_types=['photo', 'audio', 'document'])
def handle_file(message):
    user_id = message.from_user.username or str(message.from_user.id)
    # Check if during WO collection
    # Download and process file
```

Reference: Full code in `CLAUDE_INTEGRATION_GUIDE.md`

---

## Verification Steps

### Step 1: Test BMS Backend
```bash
cd /opt/bms-intelligence/backend
source venv/bin/activate
uvicorn app.main:app --reload --port 9095
```

Check endpoints:
```bash
curl http://localhost:9095/api/health
curl -H "X-Sentry-Secret: sentry-bms-phase-41" \
  http://localhost:9095/api/sentry/work-order/status/SR-2026-TEST123
```

### Step 2: Test Sentry Tools

```bash
cd $SENTRY_HOME

# Install required packages if needed
pip install requests

# Test WO notification tool
python tools/wo_notifier.py status SR-2026-TEST123

# Test conversation handler
python -c "
from handlers.wo_conversation_handler import WOConversationHandler
h = WOConversationHandler('SR-2026-TEST123', '@test')
print(h.format_status_message())
"
```

### Step 3: End-to-End Test

1. Send WO notification
2. Check Telegram message received
3. Reply "done"
4. Upload test files
5. Verify completion in BMS

---

## Quick Deployment Script

Create `$SENTRY_HOME/update_phase41.sh`:

```bash
#!/bin/bash
set -e

echo "Deploying Phase 41 Integration to Sentry Bot..."

# Copy notification tool
echo "1. Copying WO notifier..."
cp /opt/bms-intelligence/backend/app/services/sentry_integration/wo_notifier_tool.py tools/wo_notifier.py
chmod +x tools/wo_notifier.py

# Copy conversation handler
echo "2. Copying conversation handler..."
mkdir -p handlers
cp /opt/bms-intelligence/backend/app/services/sentry_integration/conversation_handler.py handlers/wo_conversation_handler.py

# Update sentry_ai_bridge.py (manual step)
echo "3.
⚠️  MANUAL STEP REQUIRED:"
echo "   Edit tools/sentry_ai_bridge.py and add:"
echo "   - Import: from handlers.wo_conversation_handler import WOConversationHandler"
echo "   - Pattern detection function"
echo "   - Work order handlers"
echo "   - Routing logic"
echo ""
echo "   Reference: /opt/bms-intelligence/backend/app/services/sentry_integration/sentry_ai_bridge_integration.py"

# Update bot.py (manual step)
echo "4. ⚠️  MANUAL STEP REQUIRED:"
echo "   Edit bot.py and add message/file handlers"
echo "   Reference: CLAUDE_INTEGRATION_GUIDE.md"

echo ""
echo "✅ Files copied successfully!"
echo "📚 Next: Follow manual integration steps above"
echo "🧪 Test with: python tools/wo_notifier.py status SR-2026-TEST123"
```

Make executable:
```bash
chmod +x $SENTRY_HOME/update_phase41.sh
```

Run:
```bash
cd $SENTRY_HOME
./update_phase41.sh
```

---

## Documentation Files

- **Detailed Guide:** `/opt/bms-intelligence/CLAUDE_INTEGRATION_GUIDE.md`
- **Quick Instructions:** `/opt/bms-intelligence/CLAUDE_BOT_UPDATE.md`
- **Feature Details:** `/opt/bms-intelligence/docs/04-features/41-ml-knowledge-capture-01.md`

---

## Testing Checklist

- [ ] WO notifier tool copied and executable
- [ ] Conversation handler in handlers/ directory
- [ ] Sentry AI bridge updated with work order detection
- [ ] Message routing includes work order routes
- [ ] File upload handler checks for active WO collection
- [ ] Telegram bot restarted with new handlers
- [ ] BMS backend running on port 9095
- [ ] Test WO notification sends successfully
- [ ] Test "done" reply triggers first prompt
- [ ] Test file upload sends next prompt
- [ ] Test status check shows progress
- [ ] Test completion marks record complete

---

## Support

If issues:
1. Check `/opt/bms-intelligence/CLAUDE_INTEGRATION_GUIDE.md` troubleshooting section
2. Verify BMS endpoints: `curl http://localhost:9095/api/health`
3. Check Sentry logs for errors
4. Verify X-Sentry-Secret header matches in both systems

**Status:** All integration files created and ready for deployment
