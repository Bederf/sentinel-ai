---
title: "Tool Use Best Practices"
type: "guide"
status: "approved"
version: "1.0.0"
created: "2026-01-30"
updated: "2026-01-30"
author: "Sentinel Development Team"
tags: ["development", "workflow", "best-practices"]
related: ["../01-getting-started/development-environment.md", "../11-testing/testing-strategy.md"]
domain: "general"
audience: "developers"
complexity: "intermediate"
estimated_read_time: 15
---

# Tool Use Best Practices

Best practices for using Claude Code and development tools effectively.

## Claude Code Workflow

### Nexus vs RAG decision precedence

Use a two-layer context model for agent work:

- **Nexus (Obsidian control context)**: current truth, active decisions, execution constraints.
- **RAG (`docs/` indexed knowledge)**: deep reference, implementation detail, historical context.

If Nexus and RAG disagree, **Nexus wins for current execution decisions**.

Promotion rule: move information from RAG into Nexus only when it changes runtime behavior,
active policy, safety gates, or current execution decisions.

### Reading Files

**GOOD: Read files before modifying**

```bash
# Always read first to understand context
Read /opt/bms-intelligence/backend/app/main.py
```

**BAD: Modifying without reading**

Never edit a file without reading it first. You risk breaking existing code, missing patterns, or introducing inconsistencies.

### Making Changes

**GOOD: Use Edit tool for targeted changes**

```python
# Edit specific sections
Edit(
    file_path="backend/app/services/device_abstraction.py",
    old_string="def read_point(self, point: str) -> float:",
    new_string="def read_point(self, point: str) -> Optional[float]:"
)
```

**BAD: Rewriting entire files**

Never rewrite entire files unless absolutely necessary (e.g., complete refactor). This breaks git blame and makes code review difficult.

### Running Tests

**GOOD: Run targeted tests**

```bash
# Run specific test file
pytest tests/api/test_devices.py

# Run tests matching pattern
pytest -k "device_control"

# Run unit tests only
pytest -m unit
```

**BAD: Running all tests constantly**

Running all tests (`pytest`) is slow. Run targeted tests during development, full test suite before committing.

### Code Patterns

**ANTI-PATTERN: Bypassing abstraction**

```python
# BAD: Direct protocol usage
if device.protocol == "bacnet":
    bacnet_client.write_property(device.address, point, value)
```

```python
# GOOD: Use abstraction layer
adapter = DeviceAdapter(device)
adapter.write_point(point, value)
```

**ANTI-PATTERN: Ignoring safety validation**

```python
# BAD: Write without safety check
device.write_point(point, value)
```

```python
# GOOD: Validate before writing
validation = safety_engine.validate(device, point, value)
if validation.is_safe:
    device.write_point(point, value)
```

**ANTI-PATTERN: Hardcoded values**

```python
# BAD: Magic numbers
if temperature > 28:
    trigger_alarm()
```

```python
# GOOD: Named constants
MAX_TEMPERATURE = 28  # Celsius
if temperature > MAX_TEMPERATURE:
    trigger_alarm()
```

## Git Workflow

### Commit Messages

**GOOD: Conventional commits**

```bash
git commit -m "feat(devices): add Modbus RTU protocol support"
git commit -m "fix(safety): correct temperature validation logic"
git commit -m "docs(api): update endpoint documentation"
```

**BAD: Vague commits**

```bash
git commit -m "update stuff"
git commit -m "fix bug"
git commit -m "wip"
```

### Branch Strategy

**GOOD: Feature branches**

```bash
git checkout -b feature/modbus-rtu-support
# Work on feature
git commit -m "feat(modbus): add RTU adapter"
git push origin feature/modbus-rtu-support
# Create PR
```

**BAD: Committing to main directly**

```bash
# NEVER do this
git checkout main
# Make changes
git commit -m "add feature"
```

### Code Review Checklist

Before submitting PR:

- [ ] All tests pass (`pytest` and `npm test`)
- [ ] No linting errors (`npm run lint`, `pylint app/`)
- [ ] Documentation updated (if needed)
- [ ] Follows naming conventions (see `NAMING_CONVENTIONS.md`)
- [ ] Safety validation included (for device control)
- [ ] Audit logging added (for state changes)
- [ ] Error handling present
- [ ] Code comments explain "why", not "what"

## Backend Development

### Pydantic Models

**GOOD: Use Pydantic for validation**

```python
from pydantic import BaseModel, Field, validator

class DeviceControlRequest(BaseModel):
    device_id: str = Field(..., min_length=1)
    point: str = Field(..., min_length=1)
    value: float = Field(..., ge=-100, le=100)

    @validator('device_id')
    def validate_device_id(cls, v):
        if not re.match(r'^\d{3}-[a-z]{3}-[a-z]+-\d{3}$', v):
            raise ValueError('Invalid device ID format')
        return v
```

**BAD: Manual validation**

```python
# DON'T do this
def control_device(device_id, point, value):
    if not device_id:
        return {"error": "Missing device_id"}
    # Manual validation error-prone
```

### Error Handling

**GOOD: Specific exceptions**

```python
from fastapi import HTTPException
from app.services.safety_interlocks import SafetyViolation

try:
    device.write_point(point, value)
except SafetyViolation as e:
    raise HTTPException(status_code=403, detail=str(e))
except DeviceNotFoundError as e:
    raise HTTPException(status_code=404, detail=str(e))
except Exception as e:
    logger.error(f"Unexpected error: {e}", exc_info=True)
    raise HTTPException(status_code=500, detail="Internal server error")
```

**BAD: Generic catch-all**

```python
# DON'T do this
try:
    device.write_point(point, value)
except:
    return {"error": "Failed"}
```

### Logging

**GOOD: Structured logging**

```python
import logging

logger = logging.getLogger(__name__)

logger.info(
    "Device control action",
    extra={
        "device_id": device_id,
        "point": point,
        "value": value,
        "user": user,
    }
)
```

**BAD: Print statements**

```python
# DON'T do this
print(f"Writing {value} to {point}")
```

### Async/Await

**GOOD: Use async for I/O operations**

```python
@router.get("/api/devices/{device_id}")
async def get_device(device_id: str):
    # Async database call
    device = await repo.get_device(device_id)
    # Async external API call
    telemetry = await fetch_telemetry(device_id)
    return device
```

**BAD: Blocking operations in async handlers**

```python
# DON'T do this
@router.get("/api/devices/{device_id}")
async def get_device(device_id: str):
    # Synchronous call blocks event loop
    device = repo.get_device(device_id)  # BAD
    return device
```

## Frontend Development

### TypeScript Types

**GOOD: Strict types**

```typescript
interface Device {
  id: string;
  name: string;
  type: DeviceType;
  points: Record<string, PointValue>;
}

type DeviceType = 'chiller' | 'ahu' | 'fcu' | 'vav';

interface PointValue {
  value: number;
  unit: string;
  timestamp: Date;
}
```

**BAD: Any types**

```typescript
// DON'T do this
const device: any = await fetchDevice();
device.points.anything = 'whatever';  // No type safety
```

### Error Handling

**GOOD: User-friendly errors**

```typescript
try {
  await controlDevice({ deviceId, point, value });
  toast.success('Device controlled successfully');
} catch (error) {
  if (error instanceof SafetyViolation) {
    toast.error(`Safety violation: ${error.message}`);
  } else {
    toast.error('Failed to control device. Please try again.');
    logger.error('Control failed:', error);
  }
}
```

**BAD: Silent failures**

```typescript
// DON'T do this
try {
  await controlDevice({ deviceId, point, value });
} catch (error) {
  // Ignore error
}
```

### React Hooks

**GOOD: Custom hooks for logic**

```typescript
export function useDeviceControl(deviceId: string) {
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<Error | null>(null);

  const control = async (point: string, value: number) => {
    setIsLoading(true);
    setError(null);
    try {
      await api.controlDevice(deviceId, point, value);
    } catch (err) {
      setError(err as Error);
      throw err;
    } finally {
      setIsLoading(false);
    }
  };

  return { control, isLoading, error };
}
```

**BAD: Logic in components**

```typescript
// DON'T do this
const DeviceComponent = () => {
  const [isLoading, setIsLoading] = useState(false);
  // 50 lines of control logic mixed with UI
};
```

### API Calls

**GOOD: Centralized API client**

```typescript
// lib/api.ts
export async function controlDevice(
  deviceId: string,
  point: string,
  value: number
): Promise<void> {
  const response = await fetch(`${API_URL}/api/devices/${deviceId}/control`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ point, value }),
  });

  if (!response.ok) {
    throw new Error(await response.text());
  }
}
```

**BAD: Fetch calls in components**

```typescript
// DON'T do this
const handleControl = async () => {
  const response = await fetch(`http://localhost:9095/api/devices/${deviceId}/control`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ point, value }),
  });
  // Duplicated across components
};
```

## Testing

### Unit Tests

**GOOD: Test behavior, not implementation**

```python
def test_temperature_validation():
    """Test that temperature validation works correctly."""
    rule = TemperatureRangeRule(min_temp=16, max_temp=28)

    # Safe temperature
    result = rule.validate("temperature", 20)
    assert result.is_safe is True

    # Unsafe temperature
    result = rule.validate("temperature", 30)
    assert result.is_safe is False
    assert result.severity == Severity.BLOCK
```

**BAD: Testing implementation details**

```python
# DON'T do this
def test_temperature_validation():
    rule = TemperatureRangeRule(min_temp=16, max_temp=28)
    # Testing private methods
    assert rule._check_range(20) is True  # Fragile
```

### Integration Tests

**GOOD: Test API endpoints**

```python
def test_control_device_success(client):
    """Test device control endpoint."""
    response = client.post(
        "/api/devices/S001-CHILLER-B1-001/control",
        json={"point": "chw_supply_temp_setpoint", "value": 7.0}
    )

    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
```

### Frontend Tests

**GOOD: Test component behavior**

```typescript
describe('DeviceControl', () => {
  it('shows loading state while controlling', async () => {
    const { getByText } = render(<DeviceControl deviceId="S001-CHILLER-B1-001" />);
    const button = getByText('Control');

    fireEvent.click(button);

    expect(getByText('Controlling...')).toBeInTheDocument();
  });
});
```

## Debugging

### Backend Debugging

**GOOD: Use Python debugger**

```python
import pdb; pdb.set_trace()

# Or use ipdb (better)
import ipdb; ipdb.set_trace()
```

**VS Code Breakpoints:**
1. Open file in VS Code
2. Click left of line number to set breakpoint
3. Press F5 to start debugging
4. Select "Python: Current File"

### Frontend Debugging

**GOOD: Use browser DevTools**

```typescript
// Add breakpoint
debugger;

// Or use console.log
console.log('Current state:', state);
console.table(devices);
```

**React DevTools:**
- Install React DevTools browser extension
- Inspect component props and state
- View component hierarchy

### Logging

**Backend:**
```python
import logging
logger = logging.getLogger(__name__)

logger.setLevel(logging.DEBUG)
logger.debug("Detailed debug info")
logger.info("General info")
logger.warning("Warning message")
logger.error("Error occurred", exc_info=True)
```

**Frontend:**
```typescript
console.log('Info:', data);
console.warn('Warning:', warning);
console.error('Error:', error);
console.table(devices);
```

## Performance

### Backend Optimization

**GOOD: Use database indexes**

```sql
CREATE INDEX idx_devices_site ON devices(site_id);
CREATE INDEX idx_audit_logs_device ON audit_logs(device_id);
```

**GOOD: Use pagination**

```python
@router.get("/api/devices")
async def list_devices(page: int = 1, page_size: int = 50):
    offset = (page - 1) * page_size
    devices = await repo.list_devices(offset, page_size)
    return devices
```

### Frontend Optimization

**GOOD: Memoize expensive computations**

```typescript
const sortedDevices = useMemo(
  () => devices.sort((a, b) => a.name.localeCompare(b.name)),
  [devices]
);
```

**GOOD: Lazy load routes**

```typescript
const OptimizationPage = lazy(() => import('./pages/OptimizationPage'));
```

## Security

### NEVER Do This

- Hardcode API keys in code
- Commit credentials to git
- Disable safety validation
- Bypass audit logging
- Expose internal errors to users
- Use `eval()` or similar
- Trust user input without validation

### ALWAYS Do This

- Validate all input (use Pydantic)
- Use environment variables for secrets
- Log all control actions
- Validate against safety rules
- Sanitize error messages
- Use parameterized queries
- Implement rate limiting

## Related Documentation

- [Development Environment Setup](../01-getting-started/development-environment.md)
- [Testing Strategy](../11-testing/testing-strategy.md)
- [System Architecture](../02-architecture/system-overview.md)
- [Safety Interlocks Engine](../06-safety-compliance/safety-interlocks-engine.md)
