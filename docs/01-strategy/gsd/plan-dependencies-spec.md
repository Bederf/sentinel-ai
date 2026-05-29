---
title: Plan Dependency Metadata Spec
---

Location
- Vault path: `sentinel-vault/00-GSD-Phases/Phase-{N}/plan-dependencies.json`

Schema (per plan)
```json
{
  "id": "cockpit-endpoint",
  "description": "...",
  "autonomy": "ralph" | "standard",
  "depends_on": ["upstream-plan-id"],
  "estimated_tokens": 50000,
  "estimated_duration_minutes": 45,
  "has_infra_changes": true | false,
  "requires_external_approval": true | false
}
```

Phase-Level Fields
- total_estimated_tokens
- total_estimated_duration_minutes (critical path)
- critical_path_plans
- external_approval_required

Examples
1) Linear: A → B → C
2) Diamond: A → {B, C} → D
3) Complex with approvals: gates block downstream until confirmed

Notes
- Missing file should not block MVP; infer independent nodes and warn
- Use to derive DAG and wave levels
