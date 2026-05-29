---
title: Token Accounting Integration (Design)
---

Budget by Strategy
```
FIXED_WAVES:     base × 1.0 × 1.2
DYNAMIC_LIGHT:   base × 1.5 × 1.2
DYNAMIC_FULL:    base × 2.0 × 1.2
DYNAMIC_MASSIVE: base × 3.0 × 1.2
```

Tracking
- Allocate per-subagent budgets upfront
- Track tokens in real time if agent returns expose usage
- Soft limit (90%): warn; Hard limit (100%): halt and require user action

Resume
```
/gsd:master {phase} --tokens {newBudget} --resume
/gsd:master {phase} --resume-skip={planId}
```

Contract Section (draft)
```
token_budget_info:
  initial_budget: 270000
  tokens_used: 258000
  budget_utilization: 0.956
  budget_status: SOFT_LIMIT_WARNING

subagent_token_usage: [
  {plan_id, tokens_allocated, tokens_used, utilization}
]
```

Status
- MVP defers enforcement and detailed tracking to Phase 212+
