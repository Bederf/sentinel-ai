---
title: "Local Chat API Reference"
type: "api-reference"
status: "approved"
version: "1.0.0"
created: "2026-02-06"
updated: "2026-02-06"
author: "SENTINEL Development Team"
tags: ["api", "local-chat", "phase-44", "ollama"]
domain: "ai-ml"
audience: "developers"
complexity: "beginner"
estimated_read_time: 5
---

# Local Chat API Reference

Phase 44-03 endpoints for natural language queries over ML predictions and equipment data using local Ollama LLM.

## POST /api/chat/local

Query equipment data and ML predictions using natural language.

**Request Body:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `message` | string | Yes | Natural language query |
| `site_id` | string | No | Building/site context |

**Response:**

| Field | Type | Description |
|-------|------|-------------|
| `response` | string | Generated natural language response |
| `intent` | string | Classified intent (see Intent Types below) |
| `confidence` | float | Classification confidence (0.0-1.0) |
| `equipment_ids` | string[] | Extracted equipment IDs (v2.0 format) |
| `equipment_type` | string? | Extracted equipment type |
| `model_used` | string? | Ollama model used (null if offline) |
| `llm_available` | bool | Whether Ollama was available |

**Example:**

```bash
curl -X POST http://localhost:9095/api/chat/local \
  -H "Content-Type: application/json" \
  -d '{"message": "What is the status of S002-CHILLER-B1-001?"}'
```

```json
{
  "response": "S002-CHILLER-B1-001 (chiller): Health 72%, Status: running. 1 active alert: elevated vibration.",
  "intent": "equipment_status",
  "confidence": 0.95,
  "equipment_ids": ["S002-CHILLER-B1-001"],
  "equipment_type": "chiller",
  "model_used": "phi3:mini",
  "llm_available": true
}
```

## POST /api/chat/local/stream

SSE streaming version of `/api/chat/local`. Returns Server-Sent Events.

**Request Body:** Same as `/api/chat/local`.

**SSE Events:**

```
data: {"type": "metadata", "intent": "equipment_status", "confidence": 0.95, "equipment_ids": ["S002-CHILLER-B1-001"], "model_used": "phi3:mini"}

data: {"type": "content", "text": "The chiller health is at 72% with "}
data: {"type": "content", "text": "elevated vibration readings..."}

data: [DONE]
```

**Event Types:**

| Type | Description |
|------|-------------|
| `metadata` | Intent classification and context (sent first) |
| `content` | Response text chunk (~50 characters) |
| `error` | Error message if processing fails |
| `[DONE]` | Stream complete sentinel |

## GET /api/chat/local/intents

List all supported query intents with descriptions and examples.

**Response:**

```json
{
  "intents": [
    {
      "intent": "why_prediction",
      "description": "Explain why a prediction was made",
      "examples": [
        "Why is S002-CHILLER-B1-001 predicted to fail?",
        "What caused the health score drop on the AHU?"
      ]
    }
  ]
}
```

## Intent Types

| Intent | Trigger Patterns | Confidence |
|--------|-----------------|------------|
| `why_prediction` | "why is/does/will", "root cause", "what caused" | 0.85-0.95 |
| `maintenance_due` | "maintenance due/schedule", "remaining life", "spare parts" | 0.85-0.95 |
| `compare_equipment` | "compare", "versus/vs", "which is better" | 0.85-0.95 |
| `show_trends` | "show/display trends", "over the last N days" | 0.80-0.90 |
| `explain_anomaly` | "anomaly", "unusual reading", "spike in" | 0.85-0.95 |
| `equipment_status` | "status of", "health score", "how is X doing" | 0.75-0.85 |
| `general_query` | Fallback for unmatched queries | 0.50 |

## Entity Extraction

The classifier extracts entities from queries automatically:

- **Equipment IDs**: Regex `S\d{3}-[A-Z]+-[A-Z0-9]+-[A-Z0-9]+` (case-insensitive)
- **Equipment types**: "chiller", "ahu", "air handling", "generator", "pump", "dali", etc.
- **Time ranges**: "last 7 days", "past month", "this week"

## Offline Behavior

When Ollama is unavailable, the API returns structured data responses from repositories:

- **equipment_status**: Health score, status, and alert count
- **maintenance_due**: RUL days and health percentage
- **Other intents**: Classification metadata with note to start Ollama
