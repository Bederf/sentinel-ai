---
title: "44-02: Explainable AI for ML Predictions"
type: "spec"
status: "approved"
version: "1.0.0"
created: "2026-02-01"
updated: "2026-02-01"
author: "SENTINEL Development Team"
tags: ["phase-44", "explainable-ai", "predictive-maintenance"]
domain: "ai-ml"
audience: "product-managers"
complexity: "intermediate"
estimated_read_time: 12
---

# 44-02: Explainable AI for ML Predictions

## Feature Overview

**Phase:** 44 (Local LLM Integration)
**Plan:** 02 of 04
**Status:** ✅ COMPLETE
**Technical Lead:** SENTINEL AI Team

The Explainable AI (XAI) system transforms SENTINEL's ML predictions from black-box outputs into transparent, actionable explanations that maintenance technicians can understand and trust. This bridges the critical gap between AI predictions and human action.

## Problem Statement

**Before XAI:**
- ML predictions were numeric outputs without context
- Technicians received "chiller-001 has 85% failure probability" with no explanation
- No guidance on what actions to take or when
- Low trust in AI recommendations due to lack of transparency
- Maintenance decisions still required manual expert analysis

**After XAI:**
- "The chiller shows declining efficiency indicating refrigerant leak (85% confidence)"
- Clear root cause analysis with contributing factors
- Specific, prioritized maintenance actions
- Time and cost estimates for planning
- Risk assessment for informed decision-making
- Technician trust increases as they understand WHY predictions are made

## Business Value

### Cost Efficiency
- **70-80% cost reduction** using Ollama (local LLM) vs Claude API
- Estimated savings: **$50-100/month** at scale
- Free explanations for routine predictions
- Paid API only for complex edge cases

### Operational Impact
- **Faster decision-making** - Clear actions instead of manual analysis
- **Better prioritization** - Risk-based urgency classification (critical/high/medium/low)
- **Reduced downtime** - Proactive maintenance with specific guidance
- **Improved technician efficiency** - Actionable recommendations with time/cost estimates

### Trust & Adoption
- **Technicians understand WHY** predictions are made
- **Transparent reasoning** with contributing factors and evidence
- **Verifiable against knowledge base** through RAG integration
- **Continuous improvement** from feedback loop

## Feature Capabilities

### 1. Natural Language Explanations

**Input:** ML prediction with equipment data
**Output:** Human-readable explanation of root cause and implications

**Example:**
```
The chiller shows declining efficiency (from 0.92 to 0.84) over the past 30 days,
indicating refrigerant leak. Contributing factors:
- Age: 12 years (80% of expected lifespan)
- Vibration: 3.2g (elevated above 2.5g threshold)
- Pressure trend: Declining condenser pressure

This pattern matches 3 historical refrigerant leaks in similar equipment.
```

### 2. Structured Action Extraction

**Automatically extracts from explanations:**
- **Actions**: Specific maintenance tasks
- **Urgency**: Critical/High/Medium/Low priority
- **Time estimates**: Hours required for each action
- **Cost estimates**: Parts and labor costs
- **Required parts**: Bill of materials
- **Risk assessment**: Impact and probability

**Example Parsed Output:**
```json
{
  "actions": [
    {
      "description": "Inspect refrigerant lines and connections",
      "urgency": "high",
      "estimated_time_hours": 2.5,
      "estimated_cost": 3500.00,
      "parts_required": ["Leak detector", "Sealant", "Safety equipment"]
    }
  ],
  "risk_assessment": {
    "risk_level": "high",
    "impact": "Complete cooling failure",
    "probability": "85% within 7 days"
  }
}
```

### 3. Maintenance Recommender

**Combines multiple inputs for comprehensive recommendations:**
- ML predictions (LSTM, anomaly scores)
- Similar fault patterns from RAG knowledge base
- Historical maintenance effectiveness
- Equipment age and criticality
- Fleet experience from similar equipment

**Priority Classification:**

| Priority | Timeline | Criteria | Example Action |
|----------|----------|----------|----------------|
| **Critical** | 0-24 hours | Immediate failure risk | Emergency leak repair |
| **High** | 1-7 days | Failure likely soon | Schedule inspection |
| **Medium** | 7-30 days | Degradation detected | Plan maintenance |
| **Low** | Next PM cycle | Optimization opportunity | Bundle with routine PM |

### 4. Cost-Benefit Analysis

**For each recommendation:**
```
Preventive Action Cost:    R 8,500
Failure Cost (if not done): R 65,000
  - Repair: R 45,000
  - Downtime: R 15,000
  - Secondary damage: R 5,000
ROI: 665% (R 56,500 savings)
```

### 5. Explanation Quality Metrics

**Automated quality assessment:**
- **Actionability**: Can actions be extracted and executed? (0-1)
- **Factuality**: Grounded in knowledge base? (0-1)
- **Completeness**: Covers root cause to recommendations? (0-1)
- **Conciseness**: Appropriate length? (0-1)

**Human evaluation criteria:**
- Usefulness (1-5): Helps make decisions?
- Clarity (1-5): Easy to understand?
- Trustworthiness (1-5): Seems well-grounded?
- Actionability (1-5): Clear next steps?

## User Stories

### Primary User Story

**As a maintenance technician,** I want to know WHY equipment is predicted to fail so I can determine appropriate actions.

**Acceptance Criteria:**
- Given an ML prediction for "chiller-001 has 85% failure probability"
- When I view the explanation
- Then I see:
  - Root cause: "Refrigerant leak in condenser circuit"
  - Contributing factors: Age, vibration, pressure trends
  - Matching historical patterns: "Similar to 3 previous refrigerant leaks"
  - Recommended actions with urgency levels
  - Time and cost estimates
  - Risk if action delayed

### Secondary User Stories

1. **Maintenance Planner**
   - As a maintenance planner, I want cost estimates for recommended actions so I can budget appropriately.

2. **Maintenance Supervisor**
   - As a supervisor, I want priority-based recommendations so I can allocate technician time effectively.

3. **FM Operations Manager**
   - As an operations manager, I want to understand the confidence and risk of predictions so I can make informed decisions about resource allocation.

## Technical Architecture

### System Components

```mermaid
graph TD
    A[ML Prediction Engine] --> B[Explanation Service]
    B --> C[Template Selector]
    B --> D[Vector DB Query]
    D --> G[RAG Context]
    C --> H[Prompt Builder]
    G --> H
    H --> I[LLM Router]
    I --> J[Ollama Local]
    I --> K[Claude API (Fallback)]
    J --> L[Explanation]
    K --> L
    L --> M[Parser]
    M --> N[Structured Output]
    B --> O[Maintenance Recommender]
    O --> P[Priority Rules]
    P --> Q[Action Recommendations]
    N --> R[Response Assembly]
    Q --> R
    R --> S[Technician UI]

    style J fill:#4ade80
    style K fill:#f87171
```

### Technology Stack

- **LLM Generation**: Ollama (local, free) + Claude (cloud, fallback)
- **Vector Database**: Supabase pgvector (semantic search)
- **Templates**: Python string templates with equipment-specific prompts
- **Parser**: Regex + NLP pattern matching for structure extraction
- **Cost**: Free for ~80% of explanations (Ollama), ~$0.002 per fallback (Claude)

### Data Flow

1. **ML Prediction Generated** (LSTM/Autoencoder)
2. **Explanation Service** queries RAG for relevant context
3. **Template** selected based on equipment type
4. **Prompt** constructed with prediction data + RAG context
5. **LLM** generates natural language explanation
6. **Parser** extracts structured actions, costs, risks
7. **Maintenance Recommender** prioritizes actions
8. **Response** includes explanation + recommendations + quality metrics

## API Specification

### Enhanced ML Prediction Endpoints

**GET /api/ml/predictions/lstm/{equipment_id}**

Query Parameters:
- `equipment_type` (required): chiller, generator, ahu, etc.
- `include_explanation` (optional): boolean, default false

**GET /api/ml/predictions/trend/{equipment_id}**

Query Parameters:
- `equipment_type` (required)
- `hours_history` (optional): default 168
- `include_explanation` (optional): boolean

**GET /api/ml/anomalies/equipment/{equipment_id}**

Query Parameters:
- `equipment_type` (required)
- `include_explanation` (optional): boolean

### New Maintenance Endpoints

**POST /api/ml/maintenance/recommendations**

Request Body:
```json
{
  "equipment_id": "string",
  "equipment_type": "string",
  "predictions": {"24h": 15.2},
  "confidence": 0.85,
  "include_historical": true,
  "urgency_filter": "critical"
}
```

**GET /api/ml/maintenance/priorities/{equipment_type}**

Returns priority decision framework for transparency.

**GET /api/ml/maintenance/history/{equipment_id}?days=30**

Returns historical maintenance actions and outcomes.

**POST /api/ml/maintenance/feedback**

Records actual outcomes for continuous improvement:
```json
{
  "equipment_id": "string",
  "recommendation_id": "string",
  "action_taken": "string",
  "outcome": "success|failed|partial",
  "actual_time_hours": 2.5,
  "actual_cost": 1500.00,
  "notes": "string"
}
```

## Integration with Existing Systems

### ML Model Pipeline

```
ML Training (Phase 43)
    ↓
ML Inference Service
    ↓
ML Prediction Output
    ↓
Explanation Service (NEW - Phase 44-02)
    ↓
    ├→ RAG Context from Phase 44-01
    ├→ LLM Generation (Ollama/Claude)
    ├→ Structured Parsing
    └→ Maintenance Recommender
    ↓
API Response with Explanation
    ↓
Frontend UI (Phase 44-03)
```

### RAG Knowledge Base

**Leverages Phase 44-01 RAG system:**
- Equipment manuals and documentation
- Historical fault patterns
- Maintenance procedures
- Parts catalogs
- Repair cost histories

**Enhancement Value:**
- Contextually relevant explanations
- Grounded in actual equipment data
- Fleet learning across sites
- Continuous improvement as knowledge base grows

## Success Metrics

### Technical Metrics

- **Cost per Explanation**: Target <$0.002 (80% reduction from $0.0105)
- **Generation Latency**: <6 seconds (3-5s Ollama, 5-8s Claude)
- **Parsing Accuracy**: >90% action extraction success rate
- **Explanation Quality**: Actionability >0.7, Factuality >0.6

### Business Metrics

- **Technician Adoption**: % of predictions viewed with explanations
- **Action Rate**: % of recommendations that result in maintenance actions
- **Cost Savings**: Actual maintenance cost reduction from proactive actions
- **Downtime Reduction**: Reduced equipment failures from preventive actions
- **Technician Satisfaction**: Survey scores on explanation usefulness

### Quality Metrics

Target scores from evaluation framework:
- **Actionability**: 0.75-0.90 (good to excellent)
- **Factuality**: 0.60-0.85 (acceptable to well-grounded)
- **Completeness**: 0.70-0.90 (good coverage)
- **Conciseness**: 0.80-0.95 (appropriate length)

## Test Coverage

**Automated Tests:** 56 test cases

```bash
# Unit Tests
tests/services/test_explanation_service.py (10 tests)
tests/services/test_maintenance_recommender.py (12 tests)
tests/ml/test_explanation_parser.py (14 tests)
tests/ml/test_explanation_evaluation.py (20 tests)
```

**Test Categories:**
- Template rendering for all equipment types
- LLM integration (Ollama primary, Claude fallback)
- RAG context enrichment
- Output parsing (various formats)
- Priority determination logic
- Cost estimation
- Feedback recording
- Evaluation metrics

## Example Use Cases

### Use Case 1: Refrigerant Leak Detection

**Scenario:** Chiller showing declining efficiency

**ML Prediction:**
- 24h: 15.2°C discharge temp (normal: 12-14°C)
- 48h: 15.8°C
- 72h: 16.1°C
- Anomaly score: 0.65

**Generated Explanation:**
```
Root Cause: Refrigerant leak in condenser circuit

Contributing Factors:
- Age: 12 years (80% of expected lifespan)
- Vibration: 3.2g (elevated above 2.5g threshold)
- Efficiency decline: 8% over 30 days

Historical Patterns: Matches 3 previous refrigerant leaks
in similar equipment (same age, similar vibration)

Recommended Actions:
1. Inspect refrigerant lines (URGENCY: HIGH)
   - Time: 2-3 hours
   - Cost: R 3,500-4,500
   - Parts: Leak detector, sealant

Risk if Delayed: 85% probability of complete cooling
failure within 7 days, estimated impact: R 67,000
```

**Cost-Benefit Analysis:**
- Preventive action: R 8,500
- Failure cost: R 67,000
- **Net savings: R 58,500 (689% ROI)**

### Use Case 2: Generator Load Forecast

**Scenario:** Generator approaching capacity during load shedding

**ML Prediction:**
- 24h load: 92% (threshold: 90%)
- Risk of overload during Eskom Stage 4

**Generated Explanation:**
```
Situation: Generator load approaching maximum capacity

Contributing Factors:
- Building occupancy: 95% (higher than usual)
- External temperature: 35°C (increased cooling demand)
- Load shedding: Stage 4 active (12:00-14:30)

Predicted Impact: Generator overload likely at 13:45
if load shed procedure not activated

Recommended Actions:
1. Activate HVAC load shed (URGENCY: CRITICAL)
   - Time: 5 minutes
   - Impact: Reduce load by 15%

2. Notify building occupants (URGENCY: HIGH)
   - Time: 10 minutes
   - Impact: Manage expectations

Risk if Delayed: Generator overload (100% probability),
automatic shutdown, building blackout
```

### Use Case 3: AHU Filter Optimization

**Scenario:** Pressure drop across AHU filters increasing

**ML Prediction:**
- Pressure drop trend: +15% over 7 days
- Predicted blockage: 75% within 14 days

**Generated Explanation:**
```
Observation: AHU filter pressure drop increasing

Contributing Factors:
- Runtime: 18 hours/day (high usage)
- Outdoor air quality: Poor (construction nearby)
- Filter age: 75 days (rated for 90 days)

Predicted Timeline: Filter will be 90% blocked in 12 days
"""

Recommended Actions:
1. Inspect filters visually (URGENCY: MEDIUM)
   - Time: 15 minutes
   - Cost: R 0 (visual only)

2. Schedule filter replacement (URGENCY: MEDIUM)
   - Time: 45 minutes
   - Cost: R 800 (4 filters)
   - Timeline: Within 2 weeks

Benefit: 15% energy savings from clean filters = R 2,100/year
ROI: 262% annual return
```

## Deployment

### Prerequisites

- Ollama service running (http://127.0.0.1:11434)
- Supabase with pgvector extension enabled
- RAG knowledge base populated (Phase 44-01)
- ML models trained and deployed (Phase 43)

### Configuration

**Environment Variables:**

```bash
# Ollama Configuration
OLLAMA_BASE_URL=http://127.0.0.1:11434
OLLAMA_MODEL=qwen:7b

# Claude Configuration (for fallback)
ANTHROPIC_API_KEY=<your-key>
CLAUDE_MODEL=claude-sonnet-4-20250514

# Explanation Settings
ENABLE_EXPLANATIONS=true
DEFAULT_CONFIDENCE_THRESHOLD=0.6
PARSE_STRUCTURED_OUTPUT=true
```

**Feature Flags:**

```python
# Enable in settings.json
{
  "features": {
    "explanations": true,
    "maintenance_recommendations": true,
    "cost_estimates": true,
    "risk_assessment": true
  }
}
```

## Future Enhancements

### Phase 44-03: Frontend Integration
- Equipment detail modal with explanation display
- Maintenance recommendations panel
- Visual confidence indicators and risk meters
- Technician feedback workflow UI

### Phase 44-04: Alert Routing
- Automatic Telegram escalation for critical explanations
- Email notifications for high-priority recommendations
- Work order generation integration
- Mobile push notifications for urgent actions

### Phase 44-05: Continuous Learning
- A/B testing framework for prompt templates
- Automated quality monitoring dashboard
- Active learning from technician corrections
- Feedback loop reinforcement learning

### Future Considerations
- Multi-language explanation support
- Voice interface for technicians
- AR overlay explanations for equipment
- Integration with CMMS work orders
- Predictive parts inventory based on recommendations

## Related Documentation

- **Phase 44-01:** [RAG Integration](../08-ai-ml/rag-integration-overview.md)
- **Phase 43:** [ML Model Development](43-ml-model-development.md)
- **Phase 44-03:** [Frontend Integration (TODO)](../08-ai-ml/frontend-integration.md)

## Development Notes

**Key Decisions:**
1. Ollama primary (FREE) + Claude fallback (PAID) for cost efficiency
2. Structured output parsing for programmatic action extraction
3. RAG integration for context-aware explanations
4. Priority-based action classification
5. Evaluation framework for quality monitoring
6. Non-breaking API changes (explanations opt-in)

**Technical Debt:**
- Template coverage limited to 7 equipment types (expand as needed)
- Cost estimates based on historical averages (refine with vendor integrations)
- RAG quality depends on knowledge base completeness (ongoing ingestion)
- Evaluation requires reference explanations for semantic similarity (log expert explanations)

## Changelog

**2026-02-01:** Phase 44-02 Implementation Complete
- Equipment-specific templates (271 lines)
- Explanation service with Ollama/Claude routing
- Structured output parser (482 lines)
- Maintenance recommender (463 lines)
- Evaluation framework (482 lines)
- API integration (enhanced prediction endpoints)
- 56 automated tests
- No breaking changes
