# LLM Judge Loop

## Status: INTERIM

This component is a **temporary production monitoring workaround**.
It will be replaced when the iDNa AI Testing Framework is provisioned.

## Replacement Trigger

**Replace** `LLMJudgeService` when:
1. iDNa AI Testing Framework endpoint is provisioned (URL/hostname available)
2. Endpoint is accessible from SENTINEL backend (network reachability confirmed)
3. `IDNA_TESTING_FRAMEWORK_URL` is set in environment

**Replacement action:** Update `LLMJudgeService.evaluate_recent()` to call
the iDNa endpoint instead of `ExplanationEvaluator.evaluate_explanation()`.
Deprecation date: log to this document when replacement is complete.

## What This Does

- Samples recent AI recommendations every 60 minutes
- Evaluates explanation quality (actionability, factuality, completeness, conciseness)
- Emits Prometheus gauge `sentinel_llm_judge_score` with labels: actionability, factuality, completeness, conciseness
- Logs evaluation scores at INFO level; logs error on failure

## Metrics

| Metric | Type | Labels | Description |
|--------|------|--------|-------------|
| `sentinel_llm_judge_score` | Gauge | `score_type` | 0-1 score per metric type |

## Files

- `backend/ml/explanations/evaluation.py` — `LLMJudgeService` class
- `backend/app/api/metrics.py` — `sentinel_llm_judge_score` gauge
- `backend/app/services/background_scheduler.py` — APScheduler job registration
- `backend/app/startup/events.py` — job initialization at startup
