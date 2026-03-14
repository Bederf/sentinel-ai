# AI Cost Tracking Module

**Phase:** v48.0 Settings Panel
**Status:** ✅ Complete
**Version:** 1.0

## Overview

The AI Cost Tracking module monitors token consumption and spend across all AI providers used by SENTINEL. It captures every API call in real-time, calculates costs in both USD and ZAR, and provides daily email reports to `info@sentinel-ai.co.za`.

**Problem solved:** Running SENTINEL involves multiple AI providers (Claude for chat/tools, OpenAI for fallback, Sentry gateway for Telegram, Ollama for local inference). Without tracking, costs are invisible until the monthly invoice arrives.

## Tracked Providers

| Provider | Models | Pricing Basis | Where Used |
|----------|--------|---------------|------------|
| **Anthropic** | Claude Sonnet 4, Haiku 4.5, Opus 4 | Per-token (input/output) | Chat, tool calling, AI recommendations |
| **OpenAI** | GPT-4.1-nano, GPT-4.1-mini, GPT-4o | Per-token (prompt/completion) | Fallback chat, hybrid AI routing |
| **ZhipuAI** | GLM-4.7-flash | Per-token | Alternative cloud provider |
| **Ollama** | Local models | Free (tracked for audit) | Local-first inference |

Each API call is tagged with a **source** label: `chat`, `tools`, `sentry`, `background`, `vision`, `tts`.

## Architecture

```
┌─────────────────────┐    ┌─────────────────────┐
│  claude_service.py   │    │  openai_service.py   │
│  stream_response()   │    │  stream_with_tools() │
│  stream_with_tools() │    │  stream_response()   │
└────────┬────────────┘    └────────┬────────────┘
         │ response.usage           │ body.usage
         ▼                          ▼
┌──────────────────────────────────────────────┐
│          ai_usage_tracker.py                  │
│  ┌──────────────────────────────┐            │
│  │  Thread-safe singleton       │            │
│  │  - record(provider, model,   │            │
│  │    input_tokens, output,     │            │
│  │    source, cache_tokens)     │            │
│  │  - get_summary(days)         │            │
│  │  - get_today()               │            │
│  │  - send_daily_report_email() │            │
│  └──────────────────────────────┘            │
│              │ flush every 10 calls          │
│              ▼                               │
│  ┌──────────────────────────────┐            │
│  │  ai_usage_log.json           │            │
│  │  { daily: { "2026-03-14":    │            │
│  │    { "anthropic/claude-...": │            │
│  │      { calls, tokens, cost } │            │
│  │    }                         │            │
│  │  }}                          │            │
│  └──────────────────────────────┘            │
└──────────────────────────────────────────────┘
         │                    │
         ▼                    ▼
┌─────────────────┐  ┌────────────────────┐
│  ai_usage.py    │  │  background_       │
│  REST API       │  │  scheduler.py      │
│  GET /summary   │  │  23:55 daily →     │
│  GET /today     │  │  email to          │
│  PUT /rate      │  │  info@sentinel-    │
└─────────────────┘  │  ai.co.za          │
         │           └────────────────────┘
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

**Sample email:**
```
SENTINEL AI Cost Report — 2026-03-14
==================================================

Today's Spend:   R 45.20  ($2.4432 USD)
API Calls:       142
Tokens Used:     1,247,000

--- By Model ---
  anthropic/claude-sonnet-4-20250514: 98 calls, 890,000+180,000 tokens, R 38.50
  openai/gpt-4.1-nano: 44 calls, 150,000+27,000 tokens, R 6.70

--- 30-Day Running Total ---
  Total Spend:   R 892.40
  Total Tokens:  28,471,000
  anthropic: R 780.20 (2,800 calls)
  openai: R 112.20 (650 calls)

Exchange Rate:   1 USD = R 18.50

— SENTINEL AI Operations
```

**SMTP:** Uses `notification_smtp_*` settings from backend `.env`.

## Settings UI

The **AI API Costs** panel appears in the Settings page and shows:

1. **Today's snapshot** — spend (ZAR/USD), call count, token count
2. **Period total** — selectable 7/30/90 days
3. **Daily bar chart** — visual spend trend with tooltips
4. **By provider** — percentage bars (Anthropic vs OpenAI vs Ollama)
5. **By model** — table with calls, tokens, cost per model
6. **Exchange rate** — displayed at bottom

## API Endpoints

| Endpoint | Method | Auth | Description |
|----------|--------|------|-------------|
| `/api/ai-usage/summary?days=30` | GET | ADMIN/OPERATOR | Period summary with breakdowns |
| `/api/ai-usage/today` | GET | ADMIN/OPERATOR | Real-time today's usage |
| `/api/ai-usage/exchange-rate` | PUT | ADMIN | Update USD/ZAR rate |
| `/api/ai-usage/flush` | POST | ADMIN | Force persist to disk |

See [AI Usage API Reference](../03-api-reference/ai-usage-api.md) for full request/response examples.

## Adding New Providers

To track a new AI provider, call the tracker from the service code:

```python
from app.services.ai_usage_tracker import usage_tracker

usage_tracker.record(
    provider="new_provider",
    model="model-name",
    input_tokens=1500,
    output_tokens=800,
    source="chat",  # or "tools", "sentry", "background"
)
```

Add pricing to `PRICING_USD_PER_1M` dict in `ai_usage_tracker.py`.

## Source Files

| File | Purpose |
|------|---------|
| `backend/app/services/ai_usage_tracker.py` | Core tracker singleton + pricing + email |
| `backend/app/api/ai_usage.py` | REST endpoints |
| `backend/app/services/claude_service.py` | Anthropic capture hooks |
| `backend/app/services/openai_service.py` | OpenAI capture hooks |
| `backend/app/startup/events.py` | Scheduler job registration |
| `backend/app/data/ai_usage_log.json` | Persistent daily data |
| `frontend/src/components/settings/AiCostTracker.tsx` | UI component |
