# Circular Import Analysis

**Date:** 2026-02-09
**Phase:** 67-02 Technical Debt Remediation

## Circular Import Chains Identified

### Chain 1: AI Services Circular Import

```
ai_optimizer.py
  └─> claude_service.claude_service
       └─> chat_tools.CHAT_TOOLS, chat_tools.execute_tool
            └─> ai_optimizer.ai_optimizer_service
                 └─> (CIRCULAR - back to ai_optimizer)
```

**Impact:** Module-level imports cause circular dependency

**Root Cause:**
- `ai_optimizer.py` (line 35): `from app.services.claude_service import claude_service`
- `claude_service.py` (line 12): `from app.services.chat_tools import CHAT_TOOLS, execute_tool`
- `chat_tools.py` (module-level): `from app.services.ai_optimizer import ai_optimizer_service`

**Why it doesn't fail immediately:**
Python's import caching allows this to work at runtime because:
1. `ai_optimizer` imports `claude_service` (which is cached)
2. `claude_service` imports `chat_tools` (which is cached)
3. `chat_tools` imports `ai_optimizer` (which is already cached from step 1)

However, this creates tight coupling and makes refactoring difficult.

---

### Chain 2: Device Abstraction Circular Import

```
device_abstraction.py
  └─> mock_devices.MockDeviceAdapter
  └─> bacnet_adapter.NiagaraBACnetAdapter
       └─> device_abstraction.DeviceAdapter
            └─> (CIRCULAR - back to device_abstraction)
```

**Impact:** Base class and implementations are tightly coupled

**Root Cause:**
- `device_abstraction.py` imports concrete implementations: `MockDeviceAdapter`, `NiagaraBACnetAdapter`
- `mock_devices.py` imports base class: `DeviceAdapter` from `device_abstraction`
- `bacnet_adapter.py` imports base class: `DeviceAdapter` from `device_abstraction`

**Why it doesn't fail immediately:**
Similar to above - Python's module cache prevents immediate failure, but the architecture violates dependency inversion principle.

---

## Solutions

### For Chain 1 (AI Services):
1. Extract shared interfaces to `app/services/ai_interfaces.py`
2. Use Protocol-based interfaces to decouple
3. Use lazy/runtime imports for concrete implementations
4. Restructure so tools don't need to import the optimizer directly

### For Chain 2 (Device Abstraction):
1. Extract base class `DeviceAdapter` to `app/services/device_base.py`
2. Update all modules to import from `device_base` instead of `device_abstraction`
3. Use factory pattern to avoid direct imports of concrete adapters

---

## Files to Modify

**Chain 1:**
- `backend/app/services/ai_optimizer.py`
- `backend/app/services/chat_tools.py`
- `backend/app/services/claude_service.py`
- `backend/app/services/ai_interfaces.py` (new)

**Chain 2:**
- `backend/app/services/device_abstraction.py`
- `backend/app/services/mock_devices.py`
- `backend/app/services/niagara/bacnet_adapter.py`
- `backend/app/services/device_base.py` (new)
