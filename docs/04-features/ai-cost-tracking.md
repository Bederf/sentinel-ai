# API & Service Cost Tracking Module

**Phase:** v48.0 Settings Panel + v58.0 Unified Service Cost Tracking (Phase 158)
**Status:** ✅ Complete
**Version:** 2.0
**Updated:** 2026-03-16

## Overview

The Cost Tracking module monitors spend across **all paid external services** used by SENTINEL — not just AI providers but also messaging (WhatsApp, BulkSMS, Telegram) and unit-based services (ElevenLabs TTS, EskomSePush). It captures every API call in real-time, calculates costs in both USD and ZAR, provides daily email reports, and sends Telegram alerts when daily spend exceeds a configurable threshold.

**Problem solved:** Running SENTINEL involves 7+ external services. Previously only AI token costs were tracked — roughly 40% of external API costs were invisible. Phase 158 extends the existing tracker to cover all paid services.

## Tracked Providers

### AI Providers (token-based)

| Provider | Models | Pricing Basis | Where Used |
|----------|--------|---------------|------------|
| **Anthropic** | Claude Sonnet 4, Haiku 4.5, Opus 4 | Per-token (input/output) | Chat, tool calling, AI recommendations |
| **OpenAI** | GPT-4.1-nano, GPT-4.1-mini, GPT-4o | Per-token (prompt/completion) | Fallback chat, hybrid AI routing |
| **ZhipuAI** | GLM-4.7-flash | Per-token | Alternative cloud provider (Z.ai) |
| **Ollama** | Local models | Free (tracked for audit) | Local-first inference |

### Messaging Providers (per-message)

| Provider | Key | Cost/Message (USD) | Where Used |
|----------|-----|-------------------|------------|
| **WhatsApp (Meta)** | `whatsapp_meta` | $0.005 | Plant alerts, WO assignments |
| **WhatsApp (Twilio)** | `whatsapp_twilio` | $0.005 | Plant alerts, WO assignments |
| **BulkSMS** | `bulksms` | $0.006 | SMS notifications |
| **Telegram** | `telegram` | $0.00 (free) | Sentry alerts, cost alerts |

### Unit-Based Services

| Provider | Key | Cost/Unit (USD) | Unit | Where Used |
|----------|-----|----------------|------|------------|
| **ElevenLabs** | `elevenlabs_chars` | $0.00003 | Character | Voice TTS synthesis |
| **EskomSePush** | `eskomsepush_call` | $0.00 (free tier) | API call | Load shedding status |

Each API call is tagged with a **source** label: `chat`, `tools`, `sentry`, `background`, `vision`, `tts`, `alert`, `energy`, `wo`.

## Architecture

```
┌─────────────────────┐    ┌─────────────────────┐    ┌─────────────────────┐
│  claude_service.py   │    │  openai_service.py   │    │  zai_service.py      │
│  stream_response()   │    │  stream_with_tools() │    │  stream_response()   │
└────────┬────────────┘    └────────┬────────────┘    └────────┬────────────┘
         │ response.usage           │ body.usage               │ body.usage
         ▼                          ▼                          ▼
┌──────────────────────────────────────────────────────────────────────────┐
│                       ai_usage_tracker.py                                │
│  ┌────────────────────────────────────────────────────────────────────┐  │
│  │  Thread-safe singleton                                             │  │
│  │  - record(provider, model, input_tokens, output, source, cache)   │  │
│  │  - record_message(provider, recipient_count, source)  ← Phase 158 │  │
│  │  - record_service(provider, units, unit_type, source) ← Phase 158 │  │
│  │  - get_summary(days) / get_today()                                │  │
│  │  - send_daily_report_email()                                      │  │
│  │  - _check_cost_alert()                        ← Phase 158         │  │
│  └────────────────────────────────────────────────────────────────────┘  │
│              │ flush every 10 calls                                      │
│              ▼                                                           │
│  ┌──────────────────────────────┐                                       │
│  │  ai_usage_log.json           │                                       │
│  │  { daily: { "2026-03-15":    │                                       │
│  │    { "anthropic/claude-...": { calls, tokens, cost },                │
│  │      "whatsapp_meta/message": { calls, cost },                       │
│  │      "elevenlabs/chars": { calls, cost }                             │
│  │    }                                                                 │
│  │  }}                                                                  │
│  └──────────────────────────────┘                                       │
└──────────────────────────────────────────────────────────────────────────┘
         │                    │                    ▲
         ▼                    ▼                    │
┌─────────────────┐  ┌────────────────────┐  ┌─────────────────────────┐
│  ai_usage.py    │  │  background_       │  │  Messaging & Services   │
│  REST API       │  │  scheduler.py      │  │  whatsapp_service.py    │
│  GET /summary   │  │  23:55 daily →     │  │  bulksms_provider.py    │
│  GET /today     │  │  email + alert     │  │  telegram_provider.py   │
│  PUT /rate      │  │                    │  │  tts_service.py         │
└─────────────────┘  └────────────────────┘  │  eskomsepush_service.py │
         │                                    └─────────────────────────┘
         ▼
┌─────────────────┐
│  Settings UI    │
│  AiCostTracker  │
│  .tsx           │
└─────────────────┘
```

## Cost Calculation

**Standard tokens:**
```
cost_usd = (input_tokens × input_price + output_tokens × output_price) / 1,000,000
```

**Anthropic prompt caching** (reduces costs significantly for repeated system prompts):
- Cache read tokens: charged at 10% of input price (90% saving)
- Cache creation tokens: charged at 125% of input price (25% surcharge)

**Currency conversion:**
```
cost_zar = cost_usd × usd_zar_rate
```
Default rate: R18.50 per USD. Configurable via `PUT /api/ai-usage/exchange-rate`.

## Daily Email Report

Sent automatically at **23:55** every day via the background scheduler to `info@sentinel-ai.co.za`.

**Sample email (Phase 158 format):**
```
SENTINEL AI Cost Report — 2026-03-15
==================================================

Today's Spend:   R 48.50  ($2.6216 USD)
API Calls:       155
Tokens Used:     1,247,000

--- By Model ---
  anthropic/claude-sonnet-4-20250514: 98 calls, 890,000+180,000 tokens, R 38.50
  openai/gpt-4.1-nano: 44 calls, 150,000+27,000 tokens, R 6.70

--- Messaging ---
  whatsapp_meta: 5 messages, R 0.46
  bulksms: 2 messages, R 0.22
  telegram: 12 messages, R 0.00

--- Services ---
  elevenlabs/chars: 3 calls, R 0.55
  eskomsepush/calls: 8 calls, R 0.00

--- 30-Day Running Total ---
  Total Spend:   R 920.40
  Total Tokens:  28,471,000
  anthropic: R 780.20 (2,800 calls)
  openai: R 112.20 (650 calls)
  whatsapp_meta: R 18.50 (200 messages)
  elevenlabs: R 9.50 (50 calls)

Exchange Rate:   1 USD = R 18.50

— SENTINEL AI Operations
```

**Sample email (snapshot with zero spend):**
```
SENTINEL AI Cost Report — 2026-03-16
==================================================

Today's Spend:   R 0.00  ($0.0000 USD)
API Calls:       0
Tokens Used:     0

--- By Model ---
  (no AI calls today)

--- 30-Day Running Total ---
  Total Spend:   R 0.18
  Total Tokens:  24,804
  openai: R 0.18 (11 calls)

Exchange Rate:   1 USD = R 18.50

— SENTINEL AI Operations
```

**SMTP:** Uses `notification_smtp_*` settings from backend `.env`.

## Cost Alert Threshold

When daily spend exceeds `COST_ALERT_DAILY_THRESHOLD_ZAR` (default: R100.00), a Telegram alert is sent to the configured chat. The alert fires once per day.

**Settings:**
- `cost_alert_daily_threshold_zar` — ZAR threshold (0 = disabled)
- `cost_alert_telegram_chat_id` — Telegram chat ID (falls back to `telegram_alert_chat_id`)

## Settings UI

The **API & Service Costs** panel appears in the Settings page and shows:

1. **Today's snapshot** — spend (ZAR/USD), call count, token count
2. **Period total** — selectable 7/30/90 days
3. **Daily bar chart** — visual spend trend with tooltips
4. **By provider** — percentage bars with per-provider colors (AI, messaging, services)
5. **By model** — table with calls, tokens, cost per model
6. **Exchange rate** — displayed at bottom

New providers (WhatsApp, BulkSMS, Telegram, ElevenLabs, EskomSePush) appear automatically in both "By Provider" and "By Model" sections when data exists.

## API Endpoints

| Endpoint | Method | Auth | Description |
|----------|--------|------|-------------|
| `/api/ai-usage/summary?days=30` | GET | ADMIN/OPERATOR | Period summary with breakdowns |
| `/api/ai-usage/today` | GET | ADMIN/OPERATOR | Real-time today's usage |
| `/api/ai-usage/exchange-rate` | PUT | ADMIN | Update USD/ZAR rate |
| `/api/ai-usage/flush` | POST | ADMIN | Force persist to disk |

See [AI Usage API Reference](../03-api-reference/ai-usage-api.md) for full request/response examples.

## Adding New Providers

### AI Providers (token-based)

```python
from app.services.ai_usage_tracker import usage_tracker

usage_tracker.record(
    provider="new_provider",
    model="model-name",
    input_tokens=1500,
    output_tokens=800,
    source="chat",
)
```

Add pricing to `PRICING_USD_PER_1M` dict in `ai_usage_tracker.py`.

### Messaging Providers (per-message)

```python
from app.services.ai_usage_tracker import usage_tracker

usage_tracker.record_message("new_provider", recipient_count=1, source="alert")
```

Add pricing to `MESSAGE_PRICING_USD` dict in `ai_usage_tracker.py`.

### Unit-Based Services

```python
from app.services.ai_usage_tracker import usage_tracker

usage_tracker.record_service("new_provider", units=500, unit_type="chars", source="tts")
```

Add pricing to `SERVICE_PRICING_USD` dict using key format `{provider}_{unit_type}`.

## Source Files

| File | Purpose |
|------|---------|
| `backend/app/services/ai_usage_tracker.py` | Core tracker singleton + pricing + email + alert |
| `backend/app/api/ai_usage.py` | REST endpoints |
| `backend/app/services/claude_service.py` | Anthropic capture hooks |
| `backend/app/services/openai_service.py` | OpenAI capture hooks |
| `backend/app/services/zai_service.py` | ZhipuAI capture hooks (Phase 158) |
| `backend/app/integrations/whatsapp_service.py` | WhatsApp Meta/Twilio tracking (Phase 158) |
| `backend/app/services/notification_providers/bulksms_provider.py` | BulkSMS tracking (Phase 158) |
| `backend/app/services/notification_providers/telegram_provider.py` | Telegram tracking (Phase 158) |
| `backend/app/services/tts_service.py` | ElevenLabs TTS tracking (Phase 158) |
| `backend/app/services/eskomsepush_service.py` | EskomSePush tracking (Phase 158) |
| `backend/app/config/settings.py` | Cost alert threshold settings |
| `backend/app/startup/events.py` | Scheduler job registration |
| `backend/app/data/ai_usage_log.json` | Persistent daily data |
| `frontend/src/components/settings/AiCostTracker.tsx` | UI component |
| `backend/tests/services/test_service_cost_tracking.py` | 16 tests (Phase 158) |
| `backend/app/services/vision_service.py` | `usage_tracker.record()` after LLM call (2026-03-21) |
| `backend/app/services/ocr_service.py` | `usage_tracker.record()` after LLM call (2026-03-21) |
| `backend/app/services/job_card_processing_service.py` | `usage_tracker.record()` at both call sites (2026-03-21) |
| `backend/app/services/email_intake_agent.py` | `usage_tracker.record()` + Claude-primary/OpenAI-fallback order (2026-03-21) |
| `backend/app/services/phyphox_analyzer.py` | `usage_tracker.record()` after LLM call (2026-03-21) |

## Cost control fixes (2026-03-21)

### Previously untracked call sites

Seven LLM call sites were not writing to `ai_usage_log.json`, making daily cost reports
understated. The following services now call `usage_tracker.record()` immediately after every
LLM response:

| Service | Model used | Source label |
|---------|-----------|-------------|
| `vision_service.py` | Claude (vision) | `vision` |
| `ocr_service.py` | Claude (OCR) | `vision` |
| `job_card_processing_service.py` (×2) | Claude | `wo` |
| `email_intake_agent.py` | Claude / OpenAI (fallback) | `background` |
| `phyphox_analyzer.py` | Claude | `background` |

### Provider order correction — email intake agent

`email_intake_agent.py` previously hardcoded OpenAI as the primary provider. It now uses
Claude (Anthropic) as primary with OpenAI as fallback, consistent with the rest of SENTINEL's
hybrid AI routing policy. This also means email intake token costs now appear under
`anthropic/*` in the daily report rather than `openai/*`.

### Prompt caching — second Claude streaming path

`claude_service.py` exposes two streaming functions:

- `stream_response_with_tools()` — had prompt caching enabled (pre-existing)
- `stream_response()` — did not have prompt caching

`cache_control: ephemeral` is now applied to system prompts in `stream_response()`, matching
the existing pattern in `stream_response_with_tools()`. For workloads with large repeated system
prompts, this can reduce Anthropic input token costs by up to 90% on cache hits.

### Impact

After these fixes, the 23:55 daily cost report via `background_scheduler` captures **all**
LLM spend rather than roughly 60%. No schema or API changes were required; the fixes are
purely additive `record()` calls at each call site.
