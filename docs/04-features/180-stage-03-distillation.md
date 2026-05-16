---
status: implemented
version: 1
date: 2026-05-16
---

# Stage 03 Distillation — FM Preference Extraction from Chat

## Overview

Extracts FM preferences from chat interactions and persists them across sessions. When an FM says "I prefer zone 3 at 20°C", Claude Sonnet answers the query while Claude Haiku (fire-and-forget, async) extracts the preference and stores it in the `user_preferences` Supabase table. On the next chat turn, active preferences are injected back into Claude's context, enabling cross-session learning without replaying full chat history.

**Models used:**
- Chat: Claude Sonnet (`task_class="chat_ai"`, existing)
- Extraction: Claude Haiku (`task_class="extraction"`, new)

---

## Architecture

```
User message → POST /api/chat
    ↓
Claude Sonnet generates response (SSE stream to client)
    ↓
Response fully streamed to client
    ↓
background_tasks.add_task(extract_preference_from_chat, ...)
    ↓
model_gateway.call(task_class="extraction")
    ├─ Primary:   anthropic / claude-haiku-4-20250507
    └─ Fallback:  minimax / MiniMax-M2.5
        ↓
Haiku extracts JSON: { preference_type, preference_value, confidence }
    ↓
    ├─ confidence > 0.75 → upsert to user_preferences table
    ├─ confidence 0.5-0.75 → logged at DEBUG, discarded
    └─ confidence < 0.5 → silently ignored
    ↓
Next chat turn:
    ├─ Fetch active preferences for user
    ├─ Inject as system message: "## FM Preferences (from previous sessions)"
    └─ Sonnet sees preferences in context
```

---

## Implementation

### Database: `user_preferences` table

```sql
CREATE TABLE user_preferences (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    site_id TEXT NOT NULL,
    user_id TEXT NOT NULL,
    preference_type TEXT NOT NULL CHECK (preference_type IN ('setpoint','priority','timing','equipment')),
    preference_value JSONB NOT NULL,
    source TEXT NOT NULL DEFAULT 'chat_explicit',
    confidence FLOAT NOT NULL DEFAULT 0.5 CHECK (confidence >= 0.0 AND confidence <= 1.0),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX idx_user_preferences_type ON user_preferences (site_id, user_id, preference_type);
CREATE INDEX idx_user_preferences_active ON user_preferences (site_id, user_id);
```

One active preference per type per user (upsert on conflict).

### Preference Types

| Type | Value Example | Description |
|------|--------------|-------------|
| `setpoint` | `{ "zone_id": "3", "min_temp": 20, "max_temp": 24 }` | Zone temperature targets |
| `priority` | `{ "priority": "comfort_over_energy" }` | Comfort vs energy trade-off |
| `timing` | `{ "start_time": "09:00", "end_time": "17:00" }` | Scheduling preferences |
| `equipment` | `{ "equipment_class": "hvac", "preference": "prefer_newer" }` | Equipment preferences |

### Routing: `task_class="extraction"`

Added to `backend/app/config/routing_profiles.py`:

- **api_prod/cloud_dev:** `anthropic/claude-haiku-4-20250507` → `minimax/MiniMax-M2.5` (fallback)
- **local_full:** `ollama/qwen2.5:7b-instruct`
- **idna:** `azure_openai/gpt-4o-mini`

### Key Files

| File | Purpose |
|------|---------|
| `backend/app/services/preference_extractor.py` | Haiku-based extraction service, fire-and-forget |
| `backend/app/repositories/preference_repository.py` | Supabase CRUD for user_preferences |
| `backend/app/models/preference.py` | PreferenceType enum, UserPreference model |
| `backend/app/api/chat.py` (lines 576-583) | Background task hook after response streamed |
| `backend/app/config/routing_profiles.py` | "extraction" task class definition |

---

## Data Flow

1. **Chat turn:** User sends message → `POST /api/chat`
2. **Response:** Claude Sonnet generates SSE stream → streamed to client
3. **Extraction:** After `[DONE]` sentinel, `background_tasks.add_task(extract_preference_from_chat, ...)` fires
4. **Haiku call:** `model_gateway.call(task_class="extraction", messages=[{prompt}], max_tokens=150, stream=False)`
5. **Storage:** If `confidence > 0.75` → `preference_repo.insert_preference(pref)` upserts to Supabase
6. **Injection:** Next chat turn → `preference_repo.fetch_active_by_user(site_id, user_id)` → rendered as system message `"## FM Preferences (from previous sessions):\n- Setpoint: Zone 3 minimum 20°C (confidence 92%, set 3 days ago)"`

---

## Confidence Tiers

| Range | Action | Logging |
|-------|--------|---------|
| > 0.75 | Store to DB | `logger.info("preference_extracted", ...)` |
| 0.5 - 0.75 | Discard | `logger.debug("preference_low_confidence", ...)` |
| < 0.5 | Silently ignore | none |

---

## Context Injection

Preferences are injected into Claude's message list as a `system` role message **before** conversation history but **after** the system prompt. This ensures:
- Preferences are visible to Claude but don't override the system prompt
- They persist across conversation turns
- They don't pollute token budget when no preferences exist (section omitted entirely)

---

## Edge Deployment Strategy

Extraction is routed through the model gateway via `task_class="extraction"`. When SENTINEL moves to Jetson Orin NX (local-only), swapping the extraction model requires only a change in `routing_profiles.py` — no extraction service code changes needed.

---

## Files

**Created:**
- `backend/supabase/migrations/20260516_001_user_preferences.sql`
- `backend/app/models/preference.py`
- `backend/app/services/preference_extractor.py`
- `backend/app/repositories/preference_repository.py`
- `backend/tests/test_preference_extractor.py`

**Modified:**
- `backend/app/config/routing_profiles.py` — added "extraction" task class
- `backend/app/api/chat.py` — background_tasks hook, preference injection, format helper
- `backend/app/repositories/chat_context_repository.py` — MAX_CHAT_HISTORY_PAIRS uncapped
