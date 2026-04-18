---
title: "Alert Escalation SOP"
---

# Alert Escalation SOP

## Overview

SENTINEL emits Prometheus alerts via Grafana. This document defines the
severity taxonomy, escalation chain, and on-call procedures.

## Severity Definitions

| Severity | Definition | Response SLA |
|----------|------------|-------------|
| **Critical** | Active safety violation, AEGIS engaged, ML inference completely blocked | 15 minutes |
| **Warning** | Data freshness violation, shadow mode degraded, prediction quality below threshold | 1 hour |
| **Info** | Routine operational events, mode transitions | Next business day |

## Escalation Chain

### Level 1 - Automated Response (0-15 min)

Automated systems act without human intervention:
- Safety violations -> AEGIS double-flag blocks all hardware writes
- ML inference blocked -> advisory mode activates, recommendations still generated

### Level 2 - On-Call Engineer (15 min - 2 hours)

Notified via Slack `#sentinel-alerts` and PagerDuty:

| Alert | On-Call Action |
|-------|----------------|
| `DataFreshnessViolation` | Check BMS connectivity; verify data pipeline; check Supabase `log_sources` |
| `ShadowModeDegraded` | Check SentinelDataSync heartbeat; verify integration_repository connectivity |
| `AegisModeEngaged` | Assess building state; prepare manual override if needed |
| `SafetyViolationAlert` | Identify equipment; engage facilities manager |

### Level 3 - Engineering Lead (2-4 hours)

If Level 2 unresolved:
- PagerDuty escalates to Engineering Lead
- Engineering Lead assesses scope and coordinates fix

### Level 4 - Head of Facilities + CTO (4+ hours)

Business impact:
- Building systems operating in degraded mode
- SENTINEL advisory only, no automated control
- Notify building management of status

## On-Call Rotation

On-call schedule managed in PagerDuty `sentinel-oncall` schedule.

Current rotation: See PagerDuty schedule.

## Alert Reference

| Alert Name | Source | Severity | SLO |
|------------|--------|----------|-----|
| `DataFreshnessViolation` | sentinel_data_sync | Warning | < 4h |
| `ShadowModeDegraded` | shadow_mode_polling | Warning | < 1h |
| `SafetyViolationAlert` | safety_interlocks | Critical | < 15m |
| `AegisModeEngaged` | aegis_service | Critical | < 15m |
| `LLMJudgeLowScore` | llm_judge_loop | Warning | < 4h |

## Grafana Dashboard

Alert status: https://grafana.internal/d/sentinel-alerts

## Contacts

| Role | Name | Contact |
|------|------|---------|
| On-Call Engineer | PagerDuty rotation | See PagerDuty |
| Engineering Lead | | |
| Facilities Manager | | |

## Grafana Contact Points

Alert routing configured in `infrastructure/grafana/provisioning/alerting/contact_points.yaml`:
- **Slack**: `#sentinel-alerts` via `sentinel-ops-slack`
- **PagerDuty**: `sentinel-ops-pagerduty` (auto-escalates)
- **Email**: `sentinel-ops-email` for audit trail

## Document History

| Date | Change | Author |
|------|--------|--------|
| 2026-04-18 | Initial version -- Phase 189 G8 | SENTINEL Architecture |
