---
title: "Developer Guide: Adding Module Integrations"
type: "guide"
status: "approved"
version: "1.0.0"
created: "2026-02-09"
updated: "2026-02-09"
author: "Sentinel Development Team"
tags: ["modules", "integration", "development", "guide"]
domain: "development"
audience: "developers"
complexity: "advanced"
estimated_read_time: 25
---

# Developer Guide: Adding Module Integrations

This guide shows how to add new cross-module integrations to the SENTINEL platform.

## Prerequisites

- Familiarity with [Module Connectivity & Cross-System Integration](../02-architecture/module-connectivity.md)
- Understanding of [Module System Architecture](../02-architecture/module-system.md)
- Python 3.11+ development environment set up
- Familiarity with FastAPI and async/await patterns

## Overview: What Are Module Integrations?

Module integrations are **automatic coordination links** between two modules. When both source and target modules are active, the system:

1. Automatically creates a `CrossModuleLink` object
2. Registers a handler in the target module's service
3. Invokes the handler when the trigger condition occurs
4. Performs coordinated actions across systems

**Example:** Energy module detects generator power active (trigger) → HVAC module raises setpoints +2°C (action).

---

## Step 1: Define the Integration Type

Add a new entry to `INTEGRATION_DEFINITIONS` in `/backend/app/models/module_registry.py`:

### File Location
```
/backend/app/models/module_registry.py (lines 385-451)
```

### Template

```python
"new_integration_id": {
    "name": "Human-Readable Integration Name",
    "description": "Clear description of what this integration does and why it matters",
    "source": ModuleType.SOURCE_MODULE,      # Module that detects the condition
    "target": ModuleType.TARGET_MODULE,      # Module that takes the action
    "trigger": "condition_description",      # When this integration activates
    "action": "action_performed",            # What action is taken
}
```

### Real Example: hvac_energy_loadshed

```python
"hvac_energy_loadshed": {
    "name": "HVAC Load Shedding",
    "description": "Reduce HVAC load when on generator power",
    "source": ModuleType.ENERGY,
    "target": ModuleType.HVAC,
    "trigger": "ats_position == 'generator'",
    "action": "increase_setpoints_by_2C",
}
```

### Naming Convention

- **Integration ID:** `{source}_{target}_{action}` in snake_case
  - Good: `energy_lighting_loadshed`, `security_hvac_occupancy`
  - Bad: `energyLightingLoadshed`, `energy_to_lighting_load_shed`

- **Name:** Clear, human-readable title
  - Good: "Occupancy-Based HVAC", "Solar Generation Contribution"
  - Bad: "Energy HVAC", "Sol Gen"

### Checklist for Step 1

- [ ] Chosen clear integration ID
- [ ] Written clear name and description
- [ ] Identified source and target modules
- [ ] Documented trigger condition
- [ ] Documented action performed
- [ ] Verified neither module is "custom"/"future"

---

## Step 2: Implement Integration Logic in Target Module

### File Location
```
/backend/app/services/{target_module}_service.py
```

### Handler Method Signature

```python
async def on_integration_{source}_{target}(
    self,
    trigger_data: Dict[str, Any]
) -> Optional[Dict[str, Any]]:
    """
    Handle {source} → {target} integration.
    
    Args:
        trigger_data: Context data from source module
        
    Returns:
        Result of integration action, or None if no action taken
        
    Raises:
        IntegrationError: If integration cannot be executed
    """
    # Implementation
    pass
```

### Real Example: HVAC Load Shedding Handler

```python
async def on_integration_energy_hvac(
    self,
    trigger_data: Dict[str, Any]
) -> Optional[Dict[str, Any]]:
    """
    Reduce HVAC load when on generator power.
    
    Raises setpoints +2°C to reduce cooling demand during expensive
    generator operation.
    """
    # Extract trigger data from energy module
    ats_position = trigger_data.get("ats_position")  # "grid" or "generator"
    load_shed_level = trigger_data.get("load_shed_level", 0)  # 0-6
    
    if ats_position != "generator":
        return None  # Not on generator, no action
    
    # Calculate setpoint adjustment
    # Load shedding stage 4-6 = aggressive reduction
    if load_shed_level >= 4:
        setpoint_offset = 2.0  # +2°C
    elif load_shed_level >= 2:
        setpoint_offset = 1.5  # +1.5°C
    else:
        setpoint_offset = 1.0  # +1°C
    
    # Apply to all zones
    result = await self.apply_load_shedding(
        setpoint_offset_c=setpoint_offset,
        reason="generator_power",
        duration_minutes=30
    )
    
    return {
        "action": "hvac_load_shedding",
        "setpoint_offset_c": setpoint_offset,
        "zones_affected": result.get("zones_affected", []),
        "estimated_load_reduction_kw": result.get("reduction_kw")
    }
```

### Key Implementation Patterns

**1. Always Check Trigger Data Validity:**
```python
if trigger_data.get("condition") is None:
    logger.warning("Integration triggered with invalid data")
    return None
```

**2. Make Actions Idempotent (safe to call multiple times):**
```python
# BAD: Setpoint changes accumulate
current = await self.get_zone_setpoint("zone_1")
await self.set_zone_setpoint("zone_1", current + 2.0)  # Wrong!

# GOOD: Set to absolute value
await self.set_zone_setpoint("zone_1", 24.0, reason="load_shedding")
```

**3. Return Structured Result:**
```python
return {
    "action": "integration_name",
    "success": True,
    "affected_devices": ["zone_1", "zone_2"],
    "estimated_impact_kw": 5.2,
    "duration_minutes": 30
}
```

**4. Handle Integration Errors Gracefully:**
```python
try:
    await self.apply_action()
except IntegrationError as e:
    logger.error(f"Integration failed: {e}")
    # Don't raise - log and return empty result
    return {"success": False, "reason": str(e)}
```

### Async/Await Requirements

**Important:** All integration handlers must be async:

```python
# CORRECT - async handler
async def on_integration_energy_hvac(self, trigger_data):
    result = await self.apply_load_shedding()  # await required!
    return result

# WRONG - not async
def on_integration_energy_hvac(self, trigger_data):  # Missing async!
    result = self.apply_load_shedding()  # Can't await!
    return result
```

### Checklist for Step 2

- [ ] Created handler method in target module service
- [ ] Signature matches template
- [ ] Validates trigger_data input
- [ ] Returns structured result dict
- [ ] All I/O operations are async (with await)
- [ ] Handles errors gracefully (doesn't raise)
- [ ] Action is idempotent (safe to call multiple times)
- [ ] Includes docstring with purpose and behavior

---

## Step 3: Register Handler with Integration Manager

### In Target Module's Service `__init__`

```python
# backend/app/services/{target_module}_service.py

class {TargetModule}Service:
    def __init__(self):
        # ... existing initialization ...
        
        # Register integration handlers
        self.integration_handlers = {
            "energy_lighting_loadshed": self.on_integration_energy_lighting,
            "new_integration_id": self.on_integration_source_target,  # Add this
        }
```

### Integration Manager Lookup

The system automatically discovers handlers:

```python
# backend/app/services/module_integration_manager.py

async def trigger_integration(
    self,
    integration_id: str,
    trigger_data: Dict
) -> Optional[Dict]:
    """
    Trigger an integration by ID.
    
    1. Looks up target module service
    2. Finds handler in service.integration_handlers
    3. Invokes handler with trigger_data
    4. Returns result
    """
    target_service = self.services[integration.target_module]
    handler = target_service.integration_handlers.get(integration_id)
    
    if handler is None:
        raise IntegrationError(f"Handler not found for {integration_id}")
    
    result = await handler(trigger_data)
    return result
```

### Checklist for Step 3

- [ ] Added handler to `integration_handlers` dict in target service
- [ ] Integration ID matches INTEGRATION_DEFINITIONS key
- [ ] Handler method exists and is callable

---

## Step 4: Create Integration Trigger Points

Integration handlers are invoked when conditions are detected. Add trigger points in source module.

### Pattern: Timer-Based Triggers

```python
# backend/app/services/{source_module}_service.py

async def _monitor_integration_triggers(self):
    """Monitor conditions that should trigger integrations."""
    while True:
        try:
            # Check trigger conditions
            ats_position = await self.get_ats_position()
            load_shed_level = await self.get_load_shed_level()
            
            trigger_data = {
                "ats_position": ats_position,
                "load_shed_level": load_shed_level,
                "timestamp": datetime.utcnow()
            }
            
            # Trigger all active integrations from this module
            await self.integration_manager.trigger_from_source(
                source_module="energy",
                trigger_data=trigger_data
            )
            
        except Exception as e:
            logger.error(f"Integration trigger error: {e}")
        
        # Check every 30 seconds
        await asyncio.sleep(30)
```

### Pattern: Event-Based Triggers

```python
# When something happens, trigger integrations immediately

async def on_occupancy_change(self, zone_id: str, occupancy: int):
    """Security module detected occupancy change."""
    trigger_data = {
        "zone_id": zone_id,
        "occupancy": occupancy,
        "timestamp": datetime.utcnow()
    }
    
    # Trigger HVAC and Lighting integrations
    await self.integration_manager.trigger_from_source(
        source_module="security",
        trigger_data=trigger_data
    )
```

### Integration Manager API

```python
class IntegrationManager:
    async def trigger_from_source(
        self,
        source_module: str,
        trigger_data: Dict
    ) -> Dict[str, Any]:
        """
        Trigger all integrations where source_module is active.
        
        Returns dict mapping integration_id → result
        """
        results = {}
        integrations = self.get_active_integrations(source=source_module)
        
        for integration in integrations:
            try:
                result = await self.trigger_integration(
                    integration.id,
                    trigger_data
                )
                results[integration.id] = result
            except Exception as e:
                logger.error(f"Integration {integration.id} failed: {e}")
                results[integration.id] = {"error": str(e)}
        
        return results
```

### Checklist for Step 4

- [ ] Added trigger point(s) in source module
- [ ] Trigger point calls `integration_manager.trigger_from_source()`
- [ ] Passes appropriate `trigger_data` dict
- [ ] Handles integration errors gracefully

---

## Step 5: Write Integration Tests

### File Location
```
/backend/tests/integration/test_module_coordination.py
```

### Test Template

```python
import pytest
from unittest.mock import AsyncMock, patch
from app.services.hvac_service import HVACService
from app.services.energy_service import EnergyService
from app.models.module_registry import INTEGRATION_DEFINITIONS

@pytest.mark.integration
class TestNewIntegration:
    """Test {source} → {target} integration."""
    
    @pytest.fixture
    async def services(self):
        """Initialize services."""
        hvac_service = HVACService()
        energy_service = EnergyService()
        
        # Register with integration manager
        integration_manager.register_service("hvac", hvac_service)
        integration_manager.register_service("energy", energy_service)
        
        return {
            "hvac": hvac_service,
            "energy": energy_service,
            "manager": integration_manager
        }
    
    async def test_integration_triggers_when_condition_met(self, services):
        """Test integration fires when source module detects condition."""
        hvac_service = services["hvac"]
        energy_service = services["energy"]
        manager = services["manager"]
        
        # Setup: Mock zone setpoint getter/setter
        hvac_service.get_zone_setpoint = AsyncMock(return_value=22.0)
        hvac_service.set_zone_setpoint = AsyncMock()
        
        # Trigger: Send data that matches integration condition
        trigger_data = {
            "ats_position": "generator",
            "load_shed_level": 4
        }
        
        # Act: Trigger integration
        results = await manager.trigger_from_source(
            source_module="energy",
            trigger_data=trigger_data
        )
        
        # Assert: Verify HVAC action taken
        assert "hvac_energy_loadshed" in results
        result = results["hvac_energy_loadshed"]
        assert result["success"] is True
        assert result["setpoint_offset_c"] == 2.0
        
        # Verify setpoint was actually changed
        hvac_service.set_zone_setpoint.assert_called()
    
    async def test_integration_idempotent(self, services):
        """Test calling integration multiple times is safe."""
        hvac_service = services["hvac"]
        manager = services["manager"]
        
        hvac_service.set_zone_setpoint = AsyncMock()
        
        trigger_data = {"ats_position": "generator", "load_shed_level": 4}
        
        # Call integration twice
        result1 = await manager.trigger_from_source("energy", trigger_data)
        result2 = await manager.trigger_from_source("energy", trigger_data)
        
        # Both should succeed
        assert result1["hvac_energy_loadshed"]["success"]
        assert result2["hvac_energy_loadshed"]["success"]
        
        # Setpoint should be 24°C both times (idempotent)
        # not 26°C (which would happen if changes accumulated)
        assert hvac_service.set_zone_setpoint.call_count == 2
        calls = hvac_service.set_zone_setpoint.call_args_list
        assert calls[0][1]["setpoint"] == 24.0
        assert calls[1][1]["setpoint"] == 24.0
    
    async def test_integration_handles_errors_gracefully(self, services):
        """Test integration doesn't crash on unexpected data."""
        hvac_service = services["hvac"]
        manager = services["manager"]
        
        # Trigger with missing data
        trigger_data = {"ats_position": None}  # Missing critical field
        
        # Should not raise - should return error in result
        results = await manager.trigger_from_source("energy", trigger_data)
        
        assert "hvac_energy_loadshed" in results
        assert results["hvac_energy_loadshed"]["success"] is False

    async def test_integration_definition_complete(self):
        """Verify integration exists in INTEGRATION_DEFINITIONS."""
        integration_id = "hvac_energy_loadshed"
        
        assert integration_id in INTEGRATION_DEFINITIONS
        definition = INTEGRATION_DEFINITIONS[integration_id]
        
        # Verify all required fields
        assert definition["name"]
        assert definition["description"]
        assert definition["source"]
        assert definition["target"]
        assert definition["trigger"]
        assert definition["action"]
```

### Test Checklist

- [ ] Test fires when trigger condition met
- [ ] Test doesn't fire when trigger condition not met
- [ ] Test idempotent (can call multiple times safely)
- [ ] Test handles bad trigger_data gracefully
- [ ] Test returns structured result dict
- [ ] Test integration defined in INTEGRATION_DEFINITIONS
- [ ] Test end-to-end with actual services (not mocks)

### Running Tests

```bash
cd backend
source venv/bin/activate

# Run just your new integration tests
pytest tests/integration/test_module_coordination.py::TestNewIntegration -v

# Run all integration tests
pytest tests/integration/ -m integration -v

# With coverage
pytest tests/integration/ --cov=app.services -v
```

---

## Step 6: Update Documentation

### 1. Update Module Connectivity Documentation

**File:** `/docs/02-architecture/module-connectivity.md`

Add to "Integration Catalog" section:

```markdown
| **new_integration_id** | Source → Target | Trigger condition | Action | Example |
|---|---|---|---|---|
| **new_integration_id** | Source Module → Target Module | When condition X | Does action Y | "Example scenario showing value" |
```

### 2. Update Integration API Reference

**File:** `/docs/03-api-reference/module-integration-api.md`

The endpoint documentation automatically includes all integrations defined in `INTEGRATION_DEFINITIONS`, so no changes needed here.

### 3. Create/Update Scenario Section

Add example scenario showing the integration in action:

```markdown
## Scenario: When New Integration Matters

**Scenario:** [Concrete real-world situation]

**System Behavior:**
1. Source module detects trigger
2. Integration activates
3. Target module performs action
4. Result: [tangible business value]

**Example:** "Specific example with numbers/timeline"
```

### 4. Update Module Connectivity Diagram (if needed)

**File:** `/docs/02-architecture/diagrams/module-connectivity.mmd`

Add new arrow if integration creates new cross-module connection:

```mermaid
source_module -->|integration_id| target_module
```

---

## Step 7: Integration Testing in Production

### Pre-Deployment Checklist

- [ ] All unit tests passing: `pytest tests/unit/ -v`
- [ ] All integration tests passing: `pytest tests/integration/ -v`
- [ ] No debug code left in (`pdb`, `breakpoint()`, `console.log`)
- [ ] Error messages are user-friendly
- [ ] Integration handler is idempotent
- [ ] No new security vulnerabilities (pre-commit hooks pass)
- [ ] Documentation updated with examples
- [ ] Linting passes: `ruff check backend/app/ --fix`

### Testing in Staging

```bash
# Start backend with test data
DEMO_MODE=false python -m uvicorn app.main:app --reload --port 9095

# Test integration via API
curl -X GET http://localhost:9095/api/modules/site/site-002/integrations

# Manually trigger scenario to verify integration fires
# (e.g., change ATS position to test energy→hvac integration)

# Monitor logs for integration trigger events
tail -f backend/logs/integration.log
```

### Testing with Live Systems

1. **Enable only in staging first**
   - Set `auto_integration: false` in `site_modules.json`
   - Manually enable test integration: `POST /api/modules/site/{site}/integration/{link_id}/toggle?enabled=true`

2. **Monitor integration telemetry**
   - `GET /api/modules/site/{site_id}/integration/{link_id}/telemetry`
   - Check success rates, latency, error logs

3. **Gradual rollout to production**
   - Test at one site first
   - Monitor for 24 hours
   - If successful, enable at other sites
   - Keep `auto_integration: false` initially (manual control)
   - Only enable `auto_integration: true` after confidence gained

---

## Common Pitfalls & Solutions

### Pitfall 1: Integration Handler Blocks Event Loop

**Problem:**
```python
# BAD - blocks event loop
def on_integration_energy_hvac(self, trigger_data):
    result = requests.get("http://api.example.com")  # Sync blocking call!
    return result
```

**Solution:**
```python
# GOOD - non-blocking
async def on_integration_energy_hvac(self, trigger_data):
    async with httpx.AsyncClient() as client:
        result = await client.get("http://api.example.com")
    return result
```

### Pitfall 2: Integration Changes Accumulate

**Problem:**
```python
# BAD - accumulates changes
current = await self.get_setpoint("zone_1")
await self.set_setpoint("zone_1", current + 2.0)
await self.set_setpoint("zone_1", current + 2.0)  # Called twice → 24°C instead of 22°C
```

**Solution:**
```python
# GOOD - idempotent
await self.set_setpoint("zone_1", 24.0, reason="load_shedding")  # Always 24°C
await self.set_setpoint("zone_1", 24.0, reason="load_shedding")  # Still 24°C
```

### Pitfall 3: Integration Not Registered

**Problem:**
```python
# Created handler but forgot to register
class HVACService:
    async def on_integration_energy_hvac(self, trigger_data):
        pass
    
    # Missing from __init__!
    # self.integration_handlers = {"energy_hvac": self.on_integration_energy_hvac}
```

**Solution:**
```python
class HVACService:
    def __init__(self):
        self.integration_handlers = {
            "hvac_energy_loadshed": self.on_integration_energy_hvac,  # Register!
        }
    
    async def on_integration_energy_hvac(self, trigger_data):
        pass
```

### Pitfall 4: Trigger Data Not Validated

**Problem:**
```python
# BAD - assumes trigger_data is always valid
def on_integration_energy_hvac(self, trigger_data):
    ats_pos = trigger_data["ats_position"]  # KeyError if missing!
    load_shed = trigger_data["load_shed_level"]
```

**Solution:**
```python
# GOOD - validates data
async def on_integration_energy_hvac(self, trigger_data):
    ats_pos = trigger_data.get("ats_position")
    if ats_pos is None:
        logger.warning("Integration triggered without ats_position")
        return {"success": False, "reason": "missing_ats_position"}
    
    load_shed = trigger_data.get("load_shed_level", 0)
    # ... rest of implementation
```

---

## Integration Lifecycle Examples

### Example: Full Lifecycle of energy_lighting_loadshed

**Step 1: Define (in module_registry.py)**
```python
"energy_lighting_loadshed": {
    "name": "Lighting Load Shedding",
    "description": "Reduce lighting when on generator",
    "source": ModuleType.ENERGY,
    "target": ModuleType.LIGHTING,
    "trigger": "ats_position == 'generator'",
    "action": "reduce_lighting_50_percent",
}
```

**Step 2: Implement (in lighting_service.py)**
```python
async def on_integration_energy_lighting(self, trigger_data):
    ats_position = trigger_data.get("ats_position")
    if ats_position != "generator":
        return None
    
    # Dim all zones to 50%
    zones = await self.get_all_zones()
    for zone in zones:
        await self.set_zone_level(zone.id, level=50)
    
    return {
        "action": "lighting_load_shedding",
        "zones_affected": [z.id for z in zones],
        "new_level_percent": 50
    }
```

**Step 3: Register (in lighting_service.py __init__)**
```python
self.integration_handlers = {
    "energy_lighting_loadshed": self.on_integration_energy_lighting,
}
```

**Step 4: Trigger (in energy_service.py monitor)**
```python
async def _monitor_integration_triggers(self):
    while True:
        ats_pos = await self.get_ats_position()
        trigger_data = {"ats_position": ats_pos}
        await self.integration_manager.trigger_from_source("energy", trigger_data)
        await asyncio.sleep(30)
```

**Step 5: Test**
```python
async def test_energy_lighting_loadshed():
    trigger_data = {"ats_position": "generator"}
    results = await manager.trigger_from_source("energy", trigger_data)
    
    assert results["energy_lighting_loadshed"]["success"]
    assert lighting_service.set_zone_level.called
```

**Step 6: Document**
Add to module-connectivity.md and API reference.

**Step 7: Deploy**
- Test in staging
- Monitor telemetry
- Roll out to production

---

## See Also

- [Module Connectivity & Cross-System Integration](../02-architecture/module-connectivity.md) - Business view
- [Module System](../02-architecture/module-system.md) - Architecture
- [Module Integration API Reference](../03-api-reference/module-integration-api.md) - API details
- [Tool Use Best Practices](tool-use-best-practices.md) - Development workflow

---

**Document Control**

| Revision | Date | Change | Author |
|----------|------|--------|--------|
| 1.0 | 2026-02-09 | Initial publication | Sentinel Team |
