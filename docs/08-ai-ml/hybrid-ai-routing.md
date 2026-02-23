---
title: "Hybrid AI Routing"
type: "architecture"
status: "approved"
version: "1.1.0"
created: "2026-01-30"
updated: "2026-02-23"
author: "Sentinel Development Team"
tags: ["ai", "ollama", "anthropic", "zai", "routing", "popia", "cross-border"]
related: ["../02-architecture/system-overview.md", "../03-api-reference/mcp-tools-reference.md", "../03-api-reference/privacy-api.md"]
domain: "ai-ml"
audience: "developers"
complexity: "intermediate"
estimated_read_time: 12
---

# Hybrid AI Routing

SENTINEL routes AI requests between local Ollama models and a configured cloud provider.

The routing layer now enforces POPIA cross-border controls:

- Cloud routing is blocked when `cross_border_transfer` consent is missing.
- Requests fall back to local models when cloud is blocked/unavailable.
- Tool/control operations are cloud-only and are disabled in forced-local mode.

## Runtime flow

```mermaid
graph TD
  U[User request] --> C[Classify task]
  C --> P{Cloud allowed?}
  P -->|No| L[Local Ollama]
  P -->|Yes| T{Tool/control requested?}
  T -->|Yes| CL[Cloud provider with tools]
  T -->|No| R{Tier 1 or Tier 2}
  R -->|Tier 1| L
  R -->|Tier 2| CP[Cloud provider]
  CP --> F{Cloud failure?}
  F -->|Yes| L
  F -->|No| O[Response]
  L --> O
  CL --> O
```

## Providers and models

### Local (default fallback)

| Model | Purpose |
|---|---|
| `llama3.2:1b` | Fast lookups |
| `phi3:mini` | Balanced local reasoning |

### Cloud (configurable)

| Provider | Model setting |
|---|---|
| Anthropic | `claude_model` |
| Z.ai | `zai_model` |

Active provider is selected with `ai_cloud_provider` (`anthropic` or `zai`).

## POPIA cross-border gate

Cloud processing requires explicit consent when `popia_require_cross_border_consent=true`.

Gate implementation:

- Consent check helper: `backend/app/services/popia_consent_guard.py`
- Chat routing enforcement: `backend/app/api/chat.py`, `backend/app/api/hybrid_chat.py`
- Core router enforcement: `backend/app/services/hybrid_ai_service.py`

Behavior:

- If consent exists: normal hybrid routing.
- If consent is missing/withdrawn: local-only execution.
- If cloud is selected but blocked: no cloud escalation is attempted.

## Safety and tool-calling behavior

Tool/control execution is treated as safety-critical and remains cloud-path only.

If routing is forced local (consent block, local-only mode, or no cloud credentials):

- `use_tools` is disabled.
- Query still executes locally for advisory text responses.
- Control/tool actions are not attempted.

## Configuration

Set in `backend/app/config/settings.py` and environment:

```bash
# Routing
AI_CLOUD_PROVIDER=anthropic      # anthropic | zai
LOCAL_AI_ONLY=false              # true forces full local mode

# Anthropic
ANTHROPIC_API_KEY=...
CLAUDE_MODEL=claude-3-5-haiku-latest

# Z.ai
ZAI_API_KEY=...
ZAI_MODEL=GLM-4.5-Air

# POPIA
POPIA_REQUIRE_CROSS_BORDER_CONSENT=true
```

## API touchpoints

- `POST /api/chat`
- `POST /api/hybrid-chat`
- `POST /api/chat/local` (local endpoint)
- Related privacy controls: `docs/03-api-reference/privacy-api.md`

## Observability

Track these signals for routing governance:

- Local vs cloud route counts
- Consent-blocked cloud attempts
- Tool-request blocked due to local-only mode
- Cloud failure fallback count
- Per-provider error rates (Anthropic, Z.ai)

## Operational notes

1. For GPU SBC deployments, run `LOCAL_AI_ONLY=true` to match production topology.
2. In hybrid dev mode, keep consent gating enabled to test POPIA behavior early.
3. Validate both paths in CI: cloud-enabled and consent-blocked local-only.

## Related documents

- `docs/03-api-reference/privacy-api.md`
- `docs/compliance/popia-compliance-register.md`
- `docs/09-security/consent-and-privacy.md`
