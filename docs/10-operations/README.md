# Operations Documentation

SENTINEL BMS Intelligence operations runbooks, procedures, and references.

## Runbooks

| Document | Description |
|----------|-------------|
| `aegis-enablement-runbook.md` | AEGIS safety mode enablement procedures |
| `aegis-phase0-daily-ops.md` | Phase 0 daily operations checklist |
| `deployment-runbook.md` | Deployment and rollback procedures |
| `jetson-edge-deployment.md` | Jetson edge device deployment guide |
| `logging-observability.md` | Logging and observability setup |
| `ml-model-health.md` | ML model health monitoring and recovery |
| `monitoring-stack.md` | Monitoring stack (Grafana/Prometheus/Loki) |
| `sprint0-hardware-test-protocol.md` | Hardware test protocol for Sprint 0 |
| `supabase-performance-runbook.md` | Supabase performance tuning |
| `alert-escalation-sop.md` | Alert escalation procedures and on-call rotation |
| `https-ssl-setup.md` | HTTPS/SSL setup for SENTINEL endpoints |

## Operations Notes

Additional operational notes in `operations-notes/` directory.

## Alerting

Grafana alerting rules: `infrastructure/grafana/provisioning/alerting/security-alerts.yaml`

Contact points: `infrastructure/grafana/provisioning/alerting/contact_points.yaml`

## Dashboard References

- Security Operations: `dashboards/sentinel-security-operations.json`
- AI Governance: `dashboards/sentinel-ai-governance.json`
- DB Performance: `dashboards/sentinel-db-performance.json`
