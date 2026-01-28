# Test Data Management Guide

## Overview

This guide explains how test data is managed in the BMS Intelligence testing system.

## Test Data Factories

### Frontend Factories

Located in `frontend/src/test-utils/factories.ts`:

- `createMockSite()` - Create test site data
- `createMockDevice()` - Create test device data
- `createMockAlert()` - Create test alert data
- `createMockPrediction()` - Create test prediction data
- `createMockEquipment()` - Create test equipment data
- `createMockAuditLog()` - Create test audit log entries

### Backend Factories

Located in `backend/tests/factories.py`:

- `DeviceFactory` - Create test device instances
- `SiteFactory` - Create test site instances
- `SafetyRuleFactory` - Create test safety rules
- `AuditLogFactory` - Create test audit entries

## Usage Examples

### Frontend

```typescript
import { createMockDevice, createMockSites } from '../../test-utils/factories';

// Single device
const device = createMockDevice({
  id: 'device-001',
  name: 'Test Chiller',
  device_type: 'HVAC_CHILLER',
});

// Multiple sites
const sites = createMockSites(5);
```

### Backend

```python
from tests.factories import DeviceFactory, SiteFactory

# Create device
device = DeviceFactory.create_chiller(
    device_id='device-001',
    name='Test Chiller'
)

# Create site
site = SiteFactory.create(
    site_id='site-001',
    name='Test Site'
)
```

## Mock Data Files

Backend mock data files are located in `backend/app/data/`:

- `mock_devices.json` - Device definitions
- `safety_rules.json` - Safety rule definitions
- `sites.json` - Site data
- `equipment.json` - Equipment data

## Test Data Strategy

1. **Use factories for unit tests** - Consistent, isolated data
2. **Use fixtures for integration tests** - Realistic data sets
3. **Use mock files for E2E tests** - Full data sets
4. **Reset data between tests** - Ensure test isolation

## Overriding Test Data

### Frontend

```typescript
const customDevice = createMockDevice({
  id: 'custom-id',
  name: 'Custom Name',
  // Override any property
  status: 'offline',
});
```

### Backend

```python
device = DeviceFactory.create(
    device_id='custom-id',
    name='Custom Name',
    status='offline'
)
```

## Best Practices

1. **Don't hardcode test data** - Use factories
2. **Keep data realistic** - Use values that match production
3. **Use deterministic data** - Same input = same output
4. **Clean up after tests** - Reset state between tests
5. **Document special cases** - Note any unusual test data
