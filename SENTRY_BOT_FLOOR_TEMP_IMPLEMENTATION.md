# Sentry Bot: Floor Temperature Query Implementation

## Overview
This document provides the complete implementation for adding floor temperature queries to the Sentry Telegram bot.

**Files to modify:** `$SENTRY_HOME/tools/sentry_ai_bridge.py`

**Existing functions to wire:** `get_zone_temperatures()` and `format_zone_temperatures()` from `$SENTRY_HOME/tools/bms_query.py`

---

## Implementation Steps

### Step 1: Add Detection Patterns and Helpers

Add these helper functions near the top of `sentry_ai_bridge.py`:

```python
import re

FLOOR_TEMP_PATTERNS = [
    r"temp(?:erature)?\s+(?:on\s+)?(?:floor|level)\s*[012L]?",
    r"(?:floor|level)\s*[012L]?\s+temp(?:erature)?",
    r"how\s+(?:hot|cold|warm)\s+is\s+(?:floor|level|the\s+building)",
    r"what(?:'s|is)?\s+the\s+temp(?:erature)?",
    r"zone\s+temp(?:erature)?s?",
    r"all\s+(?:floor|zone)\s+temps?",
]

def is_floor_temp_query(message: str) -> bool:
    """Detect if message is asking about floor temperatures."""
    msg = message.lower().strip()
    return any(re.search(p, msg) for p in FLOOR_TEMP_PATTERNS)


def extract_floor_from_message(message: str) -> str | None:
    """Extract floor level from message text.

    Returns:
        'L0', 'L1', 'L2', or None for all floors
    """
    msg = message.lower()
    if any(x in msg for x in ["floor 0", "level 0", "l0", "ground", "ground floor"]):
        return "L0"
    if any(x in msg for x in ["floor 1", "level 1", "l1", "first floor"]):
        return "L1"
    if any(x in msg for x in ["floor 2", "level 2", "l2", "second floor"]):
        return "L2"
    return None  # Return all floors
```

### Step 2: Add Handler Function

Add this handler function to `sentry_ai_bridge.py`:

```python
async def _handle_floor_temp_query(message: str, chat_id: int) -> str:
    """Handle floor temperature queries.

    Args:
        message: User's message text
        chat_id: Telegram chat ID

    Returns:
        Formatted response with zone temperatures
    """
    from tools.bms_query import get_zone_temperatures, format_zone_temperatures

    floor = extract_floor_from_message(message)

    # Query Supabase for zone temperatures
    data = get_zone_temperatures("STC")  # site-002 uses STC code

    # Filter by floor if specified
    if floor and "zones" in data:
        data["zones"] = [z for z in data["zones"] if z.get("floor") == floor]

    # Format and return response
    return format_zone_temperatures(data)
```

### Step 3: Integrate into detect_and_route()

Find the `detect_and_route()` function and add this check **before the general AI fallback**:

```python
async def detect_and_route(
    message_text: str,
    chat_id: int,
    user_name: str,
    # ... other parameters
) -> str:
    """Route user message to appropriate handler."""

    # ... existing routing logic ...

    # ADD THIS BLOCK (must be before general AI fallback)
    if is_floor_temp_query(message_text):
        return await _handle_floor_temp_query(message_text, chat_id)

    # ... continue with existing AI fallback logic ...
```

---

## Testing

### Test Cases

1. **Query specific floor:**
   - Message: `"what is the temperature on floor 1?"`
   - Expected: Returns L1 North (21.5°C) + L1 South (24.0°C ⚠️ fault)

2. **Query all temperatures:**
   - Message: `"show me all zone temperatures"`
   - Expected: Returns all 5 zones across 3 floors

3. **Query by floor number:**
   - Message: `"floor 2 temp"`
   - Expected: Returns L2 North (22.5°C) + L2 South (23.0°C)

4. **Ambiguous query (no floor):**
   - Message: `"what is the temperature?"`
   - Expected: Returns all zones (no floor filter)

5. **Alternative phrasing:**
   - Message: `"how hot is level 1?"`
   - Expected: Returns L1 zones

### Verification Commands

```bash
# After implementing changes, restart Sentry bot
systemctl restart sentry  # or your restart command

# Test via Telegram
# Send the test messages above to the bot
```

---

## Data Source

The bot will query Supabase using `get_zone_temperatures("STC")`:

```
STC Code → site-002 (Sandton City)
Available zones:
  - L0-North: 22.0°C (running)
  - L0-South: (check Supabase)
  - L1-North: 21.5°C (running)
  - L1-South: 24.0°C (fault)
  - L2-North: 22.5°C (running)
  - L2-South: 23.0°C (running)
```

If Supabase is unavailable, the formatter should fall back to cached/mock data.

---

## Integration Points

### Existing Functions (No Changes Needed)

These functions already exist and just need to be wired in:

- **`get_zone_temperatures(site_code)`** — Queries Supabase for zones
  - Location: `$SENTRY_HOME/tools/bms_query.py` (line ~242)
  - Returns dict with zones, timestamps, site info

- **`format_zone_temperatures(zones_data)`** — Formats response for Telegram
  - Location: `$SENTRY_HOME/tools/bms_query.py` (line ~300+)
  - Returns human-readable text or Markdown

### Modified Function

- **`detect_and_route()`** — Add floor temp check before AI fallback
  - Location: `$SENTRY_HOME/tools/sentry_ai_bridge.py`
  - Add 3 lines to integrate new handler

---

## Error Handling

The handler should gracefully handle:

1. **Supabase unavailable** → Return cached data or "Service temporarily unavailable"
2. **Zone not found** → Return "No zones found for that floor"
3. **Invalid floor** → Log error, proceed with all floors
4. **Network timeout** → Return "Unable to fetch temperature data, please try again"

---

## Fallback Behavior

If Supabase is down, the existing `format_zone_temperatures()` function should:
- Use `$SENTRY_HOME/data/hvac_zones.json` (if available)
- Or return mock data with latest known temperatures
- Always inform user of data freshness: "Last updated: HH:MM UTC"

---

## Code Snippet Summary

**What to add to `sentry_ai_bridge.py`:**

1. `FLOOR_TEMP_PATTERNS` (list)
2. `is_floor_temp_query()` (function)
3. `extract_floor_from_message()` (function)
4. `_handle_floor_temp_query()` (async function)
5. One line in `detect_and_route()`: `if is_floor_temp_query(...): return await _handle_floor_temp_query(...)`

**Total additions:** ~60 lines of code

---

## Deployment Checklist

- [ ] Copy/paste helper functions into `sentry_ai_bridge.py`
- [ ] Copy/paste handler function into `sentry_ai_bridge.py`
- [ ] Add routing check to `detect_and_route()`
- [ ] Verify Supabase connection works in test environment
- [ ] Test all 5 test cases above
- [ ] Restart Sentry bot service
- [ ] Monitor logs for errors (check `journalctl -u sentry` or bot logs)
- [ ] Confirm successful responses in Telegram

---

**Status:** Ready for implementation
**Related PR/Task:** Floor Temperature Query — Web Chat + Sentry Bot
**Web Chat Status:** ✅ COMPLETE (chat_tools.py modified)
**Sentry Bot Status:** ⏳ PENDING MANUAL IMPLEMENTATION
