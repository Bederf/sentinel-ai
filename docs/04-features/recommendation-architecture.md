# Recommendation Architecture: Two-Tier Pattern

## Overview

The system implements a **two-tier recommendation architecture** that separates strategic (business-level) recommendations from tactical (equipment-level) recommendations.

## Tier 1: Strategic Recommendations (AIRecommendationEngine - Phase A.5)

**Purpose**: Generate capital/operational investment recommendations with financial ROI analysis

**Characteristics**:
- **Scope**: Building-level, multi-month/year horizon
- **Examples**:
  - Install DALI lighting retrofit (R85,000 → R24,850/year savings)
  - HVAC maintenance (R15,000 → R42,025/year savings)
  - Water efficiency retrofit (R35,000 → R10,700/year savings)
- **Output**: Ranked list with ROI%, payback period, implementation timeline
- **API**: `/api/recommendations/ai`, `/api/recommendations/dashboard`
- **File**: `backend/app/services/ai_recommendation_engine.py`

### ROI Calculation Model

```python
Annual Savings = Baseline Cost - Optimized Cost
ROI % = (Annual Savings / Investment Cost) × 100
Payback Months = (Investment Cost / Annual Savings) × 12
Priority = Rank by ROI descending, confidence, difficulty
```

### Strategic Recommendation Example

```json
{
  "type": "lighting_optimization",
  "title": "Install DALI Lighting Control System",
  "investment_cost_r": 85000,
  "annual_savings_r": 24850,
  "roi_pct": 29.2,
  "payback_months": 41.5,
  "confidence": 0.92,
  "implementation_timeline_weeks": 4,
  "next_steps": [
    "Get lighting audit (2 weeks)",
    "Design DALI retrofit (1 week)",
    "Procurement (2 weeks)",
    "Installation & testing (4 weeks)"
  ]
}
```

---

## Tier 2: Tactical Recommendations (RecommendationService - Existing)

**Purpose**: Generate immediate equipment control actions for optimization and safety

**Characteristics**:
- **Scope**: Device-level, hourly/daily horizon
- **Examples**:
  - Setpoint adjustment: Chiller cooling setpoint 22°C → 24°C (low occupancy)
  - Lighting control: DALI brightness 80% → 40% (high daylight)
  - Load shedding: Disable non-critical loads during peak hours
- **Output**: Device-specific control action with approval tier
- **API**: `/api/recommendations` (POST/GET)
- **File**: `backend/app/services/recommendation_service.py`

### Tactical Recommendation Example

```json
{
  "action_type": "hvac_setpoint_change",
  "target_equipment": "S002-CHILLER-B1-001",
  "action": {
    "point": "cooling_setpoint",
    "value": 24.0
  },
  "reason": "Low occupancy (30%) - reduce active cooling",
  "expected_impact": {
    "energy_savings_percent": 8,
    "estimated_savings_r": 45
  },
  "risk_level": "low",
  "requires_approval": false,
  "status": "pending"
}
```

---

## Information Flow: Strategic → Tactical

The two tiers work together through **data flow**, not direct integration:

```
AIRecommendationEngine (Strategic)
    ↓ (informs)
Occupancy Analytics + Energy Models
    ↓ (triggers)
Lifecycle Orchestrator (Hourly)
    ↓ (generates)
RecommendationService (Tactical)
    ↓ (executes)
Device Control Service (BMS)
```

### Example: Lighting Retrofit → Immediate Dimming

1. **Strategic** (Phase A.5): "Install DALI system, save R24.8k/year"
   - Informs building operators of long-term financial opportunity
   - Drives capital planning and budget requests

2. **Tactical** (Lifecycle): "DALI is now installed"
   - Occupancy drops to 15% (8pm)
   - AI generates: "Reduce brightness to 25%" (from 100%)
   - Saves ~R5/night while providing security lighting

---

## Why Separate?

### Different Decision-Making Contexts

| Aspect | Strategic (A.5) | Tactical (RecommendationService) |
|--------|-----------------|----------------------------------|
| **Decision Maker** | Facilities Manager, Finance | Building Operator, AI Optimization |
| **Timeline** | Months/Years | Minutes/Hours |
| **Investment** | R10k - R500k+ | R0 (uses existing equipment) |
| **Approval** | Board/Budget approval | Auto-execute (low risk) or Op approval |
| **Risk** | Business/Capital risk | Operational/Comfort risk |
| **Frequency** | Weekly/Monthly generation | Hourly execution |

### Architectural Benefits

1. **Separation of Concerns**: Each service has single responsibility
2. **Scalability**: Strategic engine optimized for offline batch processing; Tactical engine optimized for real-time control
3. **Auditability**: Clear financial models in strategic layer; Clear execution logs in tactical layer
4. **Extensibility**: New investment types don't affect control layer; new controls don't affect ROI calculations

---

## Integration Points

### 1. Dashboard Integration (Phase A.5 Complete)

**Strategic Data** displayed on `/api/recommendations/dashboard`:
```json
{
  "total_annual_savings_r": 101825,
  "total_investment_r": 180000,
  "average_payback_months": 21.2,
  "recommendations": [ {...}, {...} ]
}
```

**Tactical Data** displayed on `/api/recommendations` (sorted by priority):
```json
{
  "pending_count": 5,
  "approved_count": 2,
  "executed_count": 89,
  "recent": [ {...}, {...} ]
}
```

### 2. Validation Integration (Phase A.3-A.4 Complete)

Both recommendation types use validation engines to inform decision-making:

**Strategic** uses validation to justify recommendations:
- "HVAC COP degraded 2.9 → 2.5: Recommend R15k maintenance"
- "Cost variance +18%: Adjust tariffs, review model"

**Tactical** uses validation to qualify controls:
- "Power anomaly detected: Hold equipment changes until stable"
- "Cost spike during control window: Reduce aggressiveness"

### 3. Future: Adapter Pattern (Phase B+)

If direct tactical ↔ strategic integration needed:

```python
class RecommendationAdapter:
    """Convert strategic recommendations to tactical actions."""

    async def strategic_to_tactical(self, strategic_rec: Dict) -> List[Recommendation]:
        """
        Convert investment recommendation to control actions.
        Example: DALI retrofit → brightness control profiles
        """
        pass
```

---

## API Reference

### Strategic (AIRecommendationEngine)

```
POST /api/recommendations/ai
  - Generate AI recommendations
  - Params: site_id, metrics (lighting_kwh, water_liters, hvac_cop)
  - Returns: Ranked list with ROI analysis

GET /api/recommendations/dashboard
  - Dashboard summary of all recommendations
  - Returns: Totals, average payback, cost/benefit

GET /api/recommendations/by-type?type=lighting_optimization
  - Filter recommendations by type
  - Returns: Filtered list with implementation details
```

### Tactical (RecommendationService)

```
POST /api/recommendations
  - Create new equipment control recommendation
  - Params: target_equipment, action, reason, risk_level
  - Returns: Recommendation object with approval status

GET /api/recommendations?status=pending
  - List recommendations by status
  - Returns: Paginated list for operator review

PATCH /api/recommendations/{id}/approve
  - Operator approval for Tier 2 actions
  - Returns: Updated recommendation with execution status
```

---

## Conclusion

The two-tier architecture provides:

✅ **Strategic layer** for investment planning and financial analysis
✅ **Tactical layer** for real-time optimization and control
✅ **Clear separation** preventing scope creep and maintaining performance
✅ **Extensible foundation** for future ML models and decision engines

This pattern is intentional and reflects best practices in building automation:
- **Energy management systems** (EMS) typically have investment analysis separate from control
- **HVAC control systems** prioritize real-time response over long-term forecasting
- **Facility managers** need both operational dashboards and financial planning tools

---

**Last Updated**: 2026-02-18
**Applies to**: Phase A.5 (AIRecommendationEngine) and RecommendationService integration
**Status**: Architecture validated ✅
