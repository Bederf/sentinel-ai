---
title: "Module Matrix Contract"
type: "architecture"
status: "approved"
version: "1.1.0"
created: "2026-02-20"
updated: "2026-02-20"
author: "Sentinel Development Team"
tags: ["modules", "contract", "alignment", "simbiot"]
domain: "general"
audience: "developers"
complexity: "intermediate"
estimated_read_time: 10
---

# Module Matrix Contract

This document is the canonical module contract used for planning and implementation alignment.

## Authoritative Sources

- Backend enum universe: `backend/app/models/module_registry.py` (`ModuleType`)
- Backend non-deactivatable rules: `backend/app/services/module_registry_service.py` (`NON_DEACTIVATABLE_MODULES`)
- Backend dependency rules: `backend/app/services/module_registry_service.py` (`MODULE_DEPENDENCIES`)
- API projection: `GET /api/modules/available` from `MODULE_DEFINITIONS`
- Frontend module type union: `frontend/src/lib/moduleRegistry.ts` (`ModuleType`)
- Frontend mandatory list: `frontend/src/lib/mandatoryModules.ts` (`MANDATORY_MODULES`)

## Official Module Matrix

| Module ID | Category | Backend Non-deactivatable | In `MODULE_DEFINITIONS` (`/available`) | Dependency |
|---|---|---:|---:|---|
| `kpi` | Core infrastructure | Yes | Yes | None |
| `ml` | Core infrastructure | Yes | Yes | None |
| `hvac` | Core infrastructure | Yes | Yes | None |
| `energy` | Core infrastructure | Yes | Yes | None |
| `assets` | Core infrastructure | Yes | Yes | None |
| `simbiot` | Core infrastructure | Yes | Yes | None |
| `integrations` | Core infrastructure | Yes | Yes | None |
| `notifications` | Core infrastructure | Yes | Yes | None |
| `control` | Paid add-on | No | Yes | None |
| `maintenance` | Paid add-on | No | Yes | None |
| `digital_twin` | Paid add-on | No | Yes | None |
| `lighting` | Building system add-on | No | Yes | Requires `control` |
| `fire` | Building system add-on | No | Yes | None |
| `access` | Building system add-on | No | Yes | None |
| `security` | Building system add-on | No | Yes | None |
| `solar` | Building system add-on | No | Yes | Requires `control` |
| `sustainability` | Building system add-on | No | Yes | None |
| `water` | Building system add-on | No | Yes | None |
| `contracts` | Building system add-on | No | Yes | None |

## Consistency Checks

### Check A: Backend Enum vs Frontend `ModuleType`
- Rule: sets must be exactly equal.
- Current status: `PASS`.

### Check B: Backend Non-deactivatable vs Frontend Mandatory
- Rule: frontend mandatory list must equal backend non-deactivatable set.
- Current status: `PASS`.
- Backend non-deactivatable: `kpi`, `ml`, `hvac`, `energy`, `assets`, `simbiot`, `integrations`, `notifications`.
- Frontend mandatory: `kpi`, `ml`, `hvac`, `energy`, `assets`, `simbiot`, `integrations`, `notifications`.
- Frontend mandatory aligned with backend.

### Check C: Enum Coverage in `MODULE_DEFINITIONS`
- Rule: all modules expected to be visible via `/api/modules/available` must exist in `MODULE_DEFINITIONS`.
- Current status: `PASS` — all 19 enum values have definitions.
- Fixed: `kpi`, `maintenance`, `digital_twin` definitions added (2026-02-20).

### Check D: Settings Feature Cards Coverage
- Rule: any user-toggleable module should have an explicit card or be intentionally omitted with rationale.
- Current status: `PASS`.
- Coverage: all module types are explicitly represented in `frontend/src/components/Settings.tsx` feature cards.

## Contracted Dependencies

- `solar` requires `control`.
- `lighting` requires `control`.
- Deactivating `control` cascades deactivation to dependent modules (`solar`, `lighting`).

## Acceptance Criteria for Alignment

A release is `PASS` only if all are true:

1. Backend enum and frontend `ModuleType` are equal sets.
2. Backend non-deactivatable and frontend mandatory sets are equal.
3. Every module intended for `/api/modules/available` has a `MODULE_DEFINITIONS` entry.
4. Settings UI has explicit treatment for each module: card or documented omission.
5. Dependency behavior is verified:
   - Activation blocked for `solar`/`lighting` when `control` inactive.
   - Cascade deactivation occurs when `control` is deactivated.

## Quick Verification Commands

```bash
cd /opt/bms-intelligence

python3 - <<'PY'
import re
from pathlib import Path

backend = Path('backend/app/models/module_registry.py').read_text()
frontend = Path('frontend/src/lib/moduleRegistry.ts').read_text()
mandatory = Path('frontend/src/lib/mandatoryModules.ts').read_text()

start = backend.index('class ModuleType')
end = backend.index('class ModuleStatus')
backend_enum = set(re.findall(r'^\s*[A-Z_]+\s*=\s*"([a-z_]+)"', backend[start:end], re.M))

u_start = frontend.index('export type ModuleType')
u_end = frontend.index('export type ModuleStatus')
frontend_enum = set(re.findall(r"'([a-z_]+)'", frontend[u_start:u_end]))

m_start = mandatory.index('MANDATORY_MODULES')
m_end = mandatory.index('];', m_start)
frontend_mandatory = set(re.findall(r"'([a-z_]+)'", mandatory[m_start:m_end]))

print('backend-only:', sorted(backend_enum - frontend_enum))
print('frontend-only:', sorted(frontend_enum - backend_enum))
print('mandatory-missing:', sorted(({'kpi','ml','hvac','energy','assets','simbiot','integrations','notifications'} - frontend_mandatory)))
PY
```
