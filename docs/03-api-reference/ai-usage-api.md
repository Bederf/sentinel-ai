# AI Usage & Cost Tracking API Reference

**Base URL:** `http://localhost:9095/api`
**Authentication:** Bearer token (JWT) — ADMIN or OPERATOR role
**Router prefix:** `/api/ai-usage`

---

## Endpoints

### GET /api/ai-usage/summary

Returns aggregated AI API costs over a configurable period. Breaks down by provider, model, and daily time series.

**Method:** `GET`
**Path:** `/api/ai-usage/summary`
**Authentication:** ADMIN or OPERATOR
**Query Parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `days` | int | 30 | Lookback period (1–365) |

#### Request

```bash
curl -X GET "http://localhost:9095/api/ai-usage/summary?days=30" \
  -H "Authorization: Bearer <token>"
```

#### Response (200 OK)

```json
{
  "period_days": 30,
  "usd_zar_rate": 18.5,
  "total_cost_usd": 12.4532,
  "total_cost_zar": 230.38,
  "total_tokens": 2847291,
  "by_provider": {
    "anthropic": {
      "calls": 342,
      "tokens": 2100000,
      "cost_usd": 10.23,
      "cost_zar": 189.26
    },
    "openai": {
      "calls": 85,
      "tokens": 747291,
      "cost_usd": 2.22,
      "cost_zar": 41.07
    }
  },
  "by_model": {
    "claude-sonnet-4-20250514": {
      "calls": 200,
      "tokens": 1500000,
      "cost_usd": 8.10,
      "cost_zar": 149.85
    },
    "claude-haiku-4-5-20251001": {
      "calls": 142,
      "tokens": 600000,
      "cost_usd": 2.13,
      "cost_zar": 39.41
    },
    "gpt-4.1-nano": {
      "calls": 85,
      "tokens": 747291,
      "cost_usd": 2.22,
      "cost_zar": 41.07
    }
  },
  "daily": [
    {
      "date": "2026-03-14",
      "cost_usd": 0.42,
      "cost_zar": 7.77,
      "tokens": 95000
    }
  ]
}
```

---

### GET /api/ai-usage/today

Returns real-time usage for the current day, broken down by model.

**Method:** `GET`
**Path:** `/api/ai-usage/today`
**Authentication:** ADMIN or OPERATOR

#### Request

```bash
curl -X GET http://localhost:9095/api/ai-usage/today \
  -H "Authorization: Bearer <token>"
```

#### Response (200 OK)

```json
{
  "date": "2026-03-14",
  "total_calls": 47,
  "total_tokens": 95200,
  "total_cost_usd": 0.4215,
  "total_cost_zar": 7.80,
  "models": {
    "anthropic/claude-sonnet-4-20250514": {
      "calls": 30,
      "input_tokens": 45000,
      "output_tokens": 22000,
      "cost_usd": 0.3650,
      "cost_zar": 6.75
    },
    "openai/gpt-4.1-nano": {
      "calls": 17,
      "input_tokens": 20000,
      "output_tokens": 8200,
      "cost_usd": 0.0565,
      "cost_zar": 1.05
    }
  }
}
```

---

### PUT /api/ai-usage/exchange-rate

Update the USD/ZAR exchange rate used for cost calculations.

**Method:** `PUT`
**Path:** `/api/ai-usage/exchange-rate`
**Authentication:** ADMIN only

#### Request

```bash
curl -X PUT http://localhost:9095/api/ai-usage/exchange-rate \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{"usd_zar": 18.75}'
```

#### Response (200 OK)

```json
{
  "status": "updated",
  "usd_zar": 18.75
}
```

---

### POST /api/ai-usage/flush

Force flush in-memory usage data to disk. Automatically called every 10 API calls and at daily rollover.

**Method:** `POST`
**Path:** `/api/ai-usage/flush`
**Authentication:** ADMIN only

---

## Pricing Model

Token costs are calculated using published API pricing (per 1M tokens, USD):

| Model | Input | Output | Provider |
|-------|-------|--------|----------|
| claude-sonnet-4-20250514 | $3.00 | $15.00 | Anthropic |
| claude-haiku-4-5-20251001 | $0.80 | $4.00 | Anthropic |
| claude-opus-4-20250514 | $15.00 | $75.00 | Anthropic |
| gpt-4.1-nano | $0.10 | $0.40 | OpenAI |
| gpt-4.1-mini | $0.40 | $1.60 | OpenAI |
| gpt-4o | $2.50 | $10.00 | OpenAI |
| glm-4.7-flash | $0.10 | $0.10 | ZhipuAI |
| ollama (local) | $0.00 | $0.00 | Local |

**Anthropic prompt caching:**
- Cache read tokens: 90% discount (10% of input price)
- Cache creation tokens: 25% surcharge (125% of input price)

**Currency:** All ZAR values use configurable USD/ZAR rate (default R18.50, editable via PUT endpoint).

## Daily Email Report

A daily summary email is sent at **23:55** to `info@sentinel-ai.co.za` via the background scheduler. The email includes:

- Today's total spend (ZAR + USD)
- API call count and token count
- Per-model breakdown
- 30-day running total by provider

Uses the `notification_smtp_*` settings from `.env`.

## Data Storage

Usage data is persisted to `backend/app/data/ai_usage_log.json` with daily rollup structure. Data is flushed to disk every 10 API calls and at day rollover.

## Source Files

| File | Purpose |
|------|---------|
| `backend/app/services/ai_usage_tracker.py` | Singleton tracker service, pricing, email report |
| `backend/app/api/ai_usage.py` | REST API endpoints |
| `backend/app/services/claude_service.py` | Anthropic token capture (lines 549, 437) |
| `backend/app/services/openai_service.py` | OpenAI token capture (lines 201, 275) |
| `backend/app/startup/events.py` | Daily email job registration |
| `frontend/src/components/settings/AiCostTracker.tsx` | Settings panel UI |
