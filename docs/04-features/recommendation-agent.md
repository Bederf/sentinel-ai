---
title: "Recommendation Validation & Execution Agent"
type: "feature"
status: "complete"
version: "1.0.0"
created: "2026-02-19"
updated: "2026-02-19"
author: "SENTINEL Development Team"
tags: ["agent", "langgraph", "recommendations", "tier-routing", "approval", "whatsapp", "telegram"]
related: ["../08-ai-ml/ai-recommendation-system.md", "../03-api-reference/recommendations-api.md", "../06-safety-compliance/safety-interlocks-engine.md"]
domain: "optimization"
audience: "developers|operators|integrators"
complexity: "advanced"
estimated_read_time: 15
---

# Recommendation Validation & Execution Agent

A system-initiated (proactive) LangGraph agent that bridges ML recommendations to action. Takes pending recommendations through the complete lifecycle: validate relevance, assess impact, check maintenance schedule, route through tier engine, execute or request approval, and close the ML feedback loop.

## Key Facts

- **Framework:** LangGraph StateGraph with MemorySaver checkpointing
- **LLM usage:** Zero — all nodes are deterministic Python wrapping existing services
- **Nodes:** 13 (fetch, validate, assess, schedule, route, 3 tier handlers, approval handler, feedback, format, expire, defer)
- **Tests:** 72 (59 unit + 13 integration), all passing
- **Channels:** system, chat, WhatsApp, Telegram
- **Pattern:** Follows established desk complaint agent architecture

---

## Graph Architecture

```
                    ┌──────────────────────────────────────┐
                    │    Recommendation Agent (Proactive)   │
                    │                                       │
   START ──► fetch_pending                                  │
                │                                           │
                ├─ (no recs) → format_result → END          │
                │                                           │
                ▼                                           │
         validate_relevance                                 │
                │                                           │
                ├─ (stale) → mark_expired → END             │
                │                                           │
                ▼                                           │
          assess_impact                                     │
                │                                           │
                ▼                                           │
         check_schedule                                     │
                │                                           │
                ├─ (conflict) → defer → END                 │
                │                                           │
                ▼                                           │
          route_tier                                        │
                │                                           │
          ┌─────┼─────────┐                                │
          ▼     ▼         ▼                                │
     log_advisory  request_approval  auto_execute          │
     (Tier 1)      (Tier 2)          (Tier 3)             │
          │         │                  │                    │
          │    [needs_input=True]      │                    │
          │         │ (resume)         │                    │
          │    handle_approval_response│                    │
          │    ┌───┴───┐              │                    │
          │  approve  reject           │                    │
          │    │       │               │                    │
          └──► submit_feedback ◄───────┘                   │
                    │                                       │
                    ▼                                       │
              format_result → END                          │
                                                            │
                    └───────────────────────────────────────┘
```

---

## State Schema

```python
class RecommendationAgentState(TypedDict):
    messages: Annotated[list, add_messages]  # LangGraph message history
    # Input
    site_id: str                              # Building identifier
    channel: str                              # "system" | "whatsapp" | "telegram" | "chat"
    trigger: str                              # "scheduled" | "manual" | "health_alert"
    # Recommendation being processed
    recommendation_id: Optional[str]
    recommendation: Optional[dict]
    # Validation
    is_relevant: bool
    relevance_reason: str
    # Impact assessment
    impact: Optional[dict]                    # cost_zar, energy_kwh, comfort_delta, risk
    similar_faults: list                      # Cross-referenced similar past faults
    # Schedule check
    schedule_conflict: bool
    conflict_details: Optional[str]
    # Tier routing
    tier_result: Optional[dict]               # TierRoutingResult fields
    tier: Optional[str]                       # "tier1" | "tier2" | "tier3"
    # Execution
    execution_result: Optional[dict]          # ApprovalResult fields
    approval_status: Optional[str]            # "pending" | "approved" | "rejected"
    # Feedback
    feedback_submitted: bool
    # Output
    response: str                             # Final formatted result
    needs_input: bool                         # True = waiting for Tier 2 approval
    processing_complete: bool                 # True = all done
```

---

## Nodes

| Node | Async | Service Called | What It Does |
|------|-------|---------------|--------------|
| `fetch_pending` | Yes | `RecommendationService` | Gets next PENDING recommendation |
| `validate_relevance` | Yes | `HealthSimulationService` | Checks freshness (30min max) + equipment health |
| `mark_expired` | Yes | `RecommendationRepository` | Marks stale rec as expired |
| `assess_impact` | Yes | `EnergyCostService` | Cost/energy/comfort impact calculation |
| `check_schedule` | Yes | `WorkOrderRepository` | Checks for open work orders |
| `defer` | Yes | — | Defers rec due to schedule conflict |
| `route_tier` | Yes | `TierRoutingEngine` | Routes through PARASITE tier engine |
| `log_advisory` | Yes | — | Formats Tier 1 advisory |
| `request_approval` | Yes | `WhatsAppService` | Sends Tier 2 approval request |
| `auto_execute` | Yes | `ApprovalService` | Executes with safety + COV + rollback |
| `handle_approval_response` | Yes | `ApprovalService` | Processes APPROVE/REJECT reply |
| `submit_feedback` | Yes | `MLFeedbackService` | Records outcome for ML learning |
| `format_result` | No | — | Sets `processing_complete=True` |

---

## Conditional Edges

| Edge | Condition | Routes To |
|------|-----------|-----------|
| `has_recommendation` | `recommendation` exists | `validate_relevance` / `format_result` |
| `check_relevance` | `is_relevant` | `assess_impact` / `mark_expired` |
| `check_schedule_conflict` | `schedule_conflict` | `defer` / `route_tier` |
| `tier_route` | `tier` value | `log_advisory` / `request_approval` / `auto_execute` |
| `check_needs_input` | `needs_input` | END / `submit_feedback` |

---

## Tool Functions

Thin async wrappers in `recommendation_tools.py` — no new business logic:

| Function | Wraps | Returns |
|----------|-------|---------|
| `get_pending_recommendations(site_id)` | `RecommendationService` | `list[dict]` |
| `check_equipment_health(code)` | `HealthSimulationService` | `{health_score, is_healthy}` |
| `check_maintenance_calendar(code)` | `WorkOrderRepository` | `{has_conflict, work_orders}` |
| `estimate_cost_impact(rec)` | `EnergyCostService` + rec data | `{cost_zar, energy_kwh, comfort_delta}` |
| `cross_reference_similar_faults(code, type)` | `RecommendationService.get_history()` | `list[dict]` |
| `route_through_tier_engine(rec)` | `TierRoutingEngine` | `TierRoutingResult` dict |
| `execute_tier3_auto(id, tier_result)` | `ApprovalService.auto_execute_recommendation()` | `ApprovalResult` dict |
| `execute_approved_recommendation(id, by, notes)` | `ApprovalService.execute_approval()` | `ApprovalResult` dict |
| `reject_recommendation(id, by, reason)` | `ApprovalService.reject_approval()` | `ApprovalResult` dict |
| `submit_feedback_to_model(id, equip, ...)` | `MLFeedbackService.record_module_outcome()` | `bool` |
| `check_recommendation_freshness(rec, max_age)` | Pure function (no service) | `{is_fresh, age_minutes}` |
| `update_recommendation_status(id, status)` | `RecommendationRepository` | `bool` |

---

## Channel Formatters

Formatters in `recommendation_formatters.py` produce output for each channel:

| Formatter | Channel | Output |
|-----------|---------|--------|
| `format_advisory_for_system()` | system | `[ADVISORY] equipment + action + impact` |
| `format_advisory_for_chat()` | chat/whatsapp | Markdown with bold labels, impact breakdown |
| `format_approval_request_whatsapp()` | whatsapp | Approval CTA with `APPROVE`/`REJECT` commands |
| `format_approval_request_telegram()` | telegram | Telegram-formatted approval request |
| `format_execution_result()` | all | Execution summary with COV status |
| `format_batch_summary()` | all | Summary of multiple processed recommendations |

---

## Integration Points

### 1. API Endpoint

```
POST /api/recommendations/{site_id}/process-pending
```

Triggers the agent for a site. Accepts `channel` and `trigger` in request body. Rate limited to 10/minute.

### 2. Chat Tool

Registered as `process_recommendation` in `chat_tools.py`:

```python
result = await process_recommendation(site_id="S002", channel="chat")
```

### 3. WhatsApp Approval Flow

In `whatsapp_webhooks.py`, `route_incoming_message()` detects `APPROVE`/`REJECT` prefixed messages and resumes the agent's checkpointed state:

```python
# Detect approval reply
content_upper = content.strip().upper()
if content_upper.startswith("APPROVE") or content_upper.startswith("REJECT"):
    agent = get_recommendation_graph()
    thread_id = f"rec_wa_{from_number}"
    config = {"configurable": {"thread_id": thread_id}}
    state = await agent.aget_state(config)
    if state.values and state.values.get("needs_input"):
        result = await agent.ainvoke(
            {"messages": [HumanMessage(content=content)]},
            config=config,
        )
```

### 4. Telegram Approval Flow

In `work_order_notifier.py`, `handle_telegram_recommendation_approval()` handles `/approve`, `/reject`, `APPROVE`, `REJECT` commands:

```python
result = await handle_telegram_recommendation_approval(
    telegram_user_id="user123",
    text="/approve rec-abc123"
)
```

Thread ID pattern: `f"rec_tg_{telegram_user_id}"`

---

## Multi-Turn Example (Tier 2 via WhatsApp)

```
[System] New pending recommendation: REC-abc123
  → fetch_pending: recommendation for S002-FCU-201 setpoint 20°C → 18°C
  → validate_relevance: equipment health 45% (below threshold), rec age 2min ✓
  → assess_impact: R12/hour savings, 0.8°C comfort delta, LOW risk
  → check_schedule: no open WOs on FCU-201 ✓
  → route_tier: confidence 0.72 → Tier 2 (approval required)
  → request_approval: send WhatsApp to Mike Johnson (HVAC tech)

    "🔧 *Approval Required*
     Equipment: S002-FCU-201 (Level 2, Zone A)
     Action: Lower setpoint from 20°C → 18°C
     Confidence: 72% | Risk: LOW
     💰 Estimated saving: R12/hour
     Reply: APPROVE rec-abc1 or REJECT rec-abc1 <reason>"

  → needs_input=True, state checkpointed

[WhatsApp] Mike replies: "APPROVE rec-abc1"
  → Resume agent thread
  → ApprovalService.execute_approval() → SafetyEngine ✓ → Device write ✓ → COV ✓
  → submit_feedback: record success → MLFeedbackService
  → "✅ FCU-201 setpoint lowered to 18°C. COV confirmed."
```

---

## Files

| File | Lines | Purpose |
|------|-------|---------|
| `backend/app/agents/recommendation_graph.py` | ~400 | LangGraph StateGraph definition |
| `backend/app/agents/recommendation_tools.py` | ~330 | Async service wrappers |
| `backend/app/agents/recommendation_formatters.py` | ~280 | Channel-specific formatters |
| `backend/app/agents/__init__.py` | — | Exports `get_recommendation_graph()` |
| `backend/app/services/chat_tools.py` | — | Registers `process_recommendation` tool |
| `backend/app/api/whatsapp_webhooks.py` | — | WhatsApp approval reply routing |
| `backend/app/api/recommendations.py` | — | `process-pending` API endpoint |
| `backend/app/services/sentry_integration/work_order_notifier.py` | — | Telegram approval handler |
| `backend/tests/agents/test_recommendation_graph.py` | ~700 | 59 unit tests |
| `backend/tests/agents/test_recommendation_routing.py` | ~550 | 13 integration tests |

---

## Existing Services Reused (NOT Modified)

| Service | Reused As |
|---------|-----------|
| `TierRoutingEngine` | `route_recommendation()` — confidence → tier routing |
| `ApprovalService` | `auto_execute_recommendation()`, `execute_approval()`, `reject_approval()` |
| `RecommendationService` | `get_pending_recommendations()`, `get_history()` |
| `RecommendationRepository` | `get()`, `update()` |
| `MLFeedbackService` | `record_module_outcome()` |
| `EnergyCostService` | TOU tariff rates for cost impact calc |
| `HealthSimulationService` | Equipment health check |
| `WorkOrderRepository` | Open work order check |
| `SafetyEngine` | Called by ApprovalService (defense-in-depth) |
| `WhatsAppService` | Outbound approval messages |

---

## Verification

```bash
# Run all agent tests (72 recommendation + 73 desk complaint = 145)
cd /opt/bms-intelligence/backend
DEMO_MODE=true python3 -m pytest tests/agents/ -v --noconftest

# Run recommendation tests only
DEMO_MODE=true python3 -m pytest tests/agents/test_recommendation_graph.py tests/agents/test_recommendation_routing.py -v --noconftest
```

---

## Related Documents

- [AI Recommendation System](../08-ai-ml/ai-recommendation-system.md) — Full recommendation pipeline
- [Recommendations API Reference](../03-api-reference/recommendations-api.md) — API endpoints
- [Safety Interlocks Engine](../06-safety-compliance/safety-interlocks-engine.md) — Safety validation
- [Approval Workflow](../../APPROVAL_WORKFLOW.md) — Approval service patterns

---

## Changelog

| Version | Date | Changes |
|---------|------|---------|
| 1.0.0 | 2026-02-19 | Initial release — 13-node StateGraph, 3-tier routing, WhatsApp/Telegram approval, ML feedback loop, 72 tests |
