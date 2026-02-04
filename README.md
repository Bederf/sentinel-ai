# SIMBIOT Concept Evolution Connector

> **The integration module that connects SENTINEL to MRI Evolution (Concept Evolution) via the FSI Public API.**

Part of the **SIMBIOT integration layer** — *"The connector that makes SENTINEL work with anything."*

---

## Architecture

```
SENTINEL AI Engine
       │
       │ Anomaly / Request
       ▼
┌─────────────────────────────────────────────────────────┐
│              SIMBIOT MODULE                               │
│                                                           │
│  ┌─────────────────────────────────────────────────────┐ │
│  │         concept_connector  ◄── THIS MODULE           │ │
│  │                                                       │ │
│  │  ┌──────────┐  ┌─────────────┐  ┌────────────────┐  │ │
│  │  │  Auth    │  │ Rate Limit  │  │ Circuit Break  │  │ │
│  │  │  (JWT)   │  │ (200/min)   │  │ (5→queue)      │  │ │
│  │  └────┬─────┘  └──────┬──────┘  └───────┬────────┘  │ │
│  │       └───────────────┼─────────────────┘            │ │
│  │                       ▼                               │ │
│  │              FSI Public API                           │ │
│  │         developer.fsiservices.com                     │ │
│  │                                                       │ │
│  │  POST /token          → JWT (7-day expiry)           │ │
│  │  POST /workorder/v1   → Create work order            │ │
│  │  GET  /workorder/v1/x → Poll status                  │ │
│  │  GET  /asset/v1       → Sync asset register          │ │
│  └─────────────────────────────────────────────────────┘ │
│                                                           │
│  Other SIMBIOT connectors:                               │
│  ├─ bms_connector (BACnet/Modbus/OPC-UA)                │
│  ├─ file_connector (CSV/Excel/JSON)                     │
│  └─ messenger_connector (WhatsApp/Telegram)             │
└─────────────────────────────────────────────────────────┘
       │
       │ Work Order (with SENTINEL diagnostics)
       ▼
┌─────────────────────────────────────────────────────────┐
│                 MRI EVOLUTION                             │
│                                                           │
│  Helpdesk → SLA Engine → FSI GO (iPad) → Technician    │
└─────────────────────────────────────────────────────────┘
```

## What It Does

| Flow | Description |
|------|-------------|
| **Anomaly → Work Order** | SENTINEL AI detects BMS anomaly → connector creates WO in MRI Evolution with full diagnostic report |
| **WhatsApp → Work Order** | Occupant messages via WhatsApp → SENTINEL NLP classifies → connector creates structured WO |
| **Status Polling** | Connector polls MRI Evolution for WO status changes → feeds resolution data back to SENTINEL ML |
| **Asset Sync** | Daily full sync + 4-hourly delta sync of MRI Evolution asset register into SENTINEL cache |

## Module Structure

```
simbiot_concept/
├── __init__.py                      # Package exports
├── connectors/
│   └── concept_connector.py         # Main ConceptConnector class
├── models/
│   ├── config.py                    # ConceptConfig (Pydantic)
│   ├── anomaly.py                   # SentinelAnomaly input model
│   └── work_order.py                # WorkOrder payload/response models
├── services/
│   └── auth.py                      # FSIAuthService (JWT management)
└── utils/
    ├── resilience.py                # RateLimiter, CircuitBreaker, Dedup
    └── audit.py                     # Structured API audit logging
```

## Quick Start

```python
from simbiot_concept import ConceptConnector, ConceptConfig, SentinelAnomaly
from simbiot_concept.models.anomaly import AnomalySource

# 1. Configure
config = ConceptConfig(
    api_base_url="https://developer.fsiservices.com",
    subscription_key="your-key",
    api_username="sentinel_api",
    api_password="your-password",
    customer_site_code="YOUR_SITE",
    segments=[...],
    severity_mapping=SeverityMapping(...),
    trade_mapping=TradeMapping(...),
)

# 2. Initialise
connector = ConceptConnector(config)
await connector.initialise()

# 3. Create work order from SENTINEL anomaly
anomaly = SentinelAnomaly(
    source=AnomalySource.BMS_ANOMALY,
    segment_id="SEG-FAIRLANDS-001",
    asset_type="chiller",
    severity_score=0.82,
    summary="Chiller compressor discharge temp rising abnormally",
    diagnostics="SENTINEL detected progressive increase in...",
)

result = await connector.create_work_order(anomaly)
print(f"Work order created: {result.work_order_id}")

# 4. Shutdown
await connector.shutdown()
```

## Prerequisites

- **FSI API Access** enabled in MRI Evolution contract
- **Subscription key** from FSI Developer Portal (developer.fsiservices.com)
- **Dedicated API user** in MRI Evolution (e.g. `sentinel_api`)
- **Segment IDs** for each facility/contract
- **Priority and Trade IDs** from MRI Evolution administrator
- Python 3.10+, `httpx`, `pydantic`

## Key Design Decisions

1. **Complement, don't replace.** Work orders appear in FSI GO exactly as manually-created ones. Zero technician retraining.
2. **Resilience first.** Rate limiter (200/min), circuit breaker (5-fail → local queue), exponential backoff, auto-retry.
3. **Zero disk persistence for secrets.** JWT tokens live in memory only. Credentials from Vault or env vars.
4. **Deduplication.** 30-minute cooldown per asset prevents alarm storms from flooding the helpdesk.
5. **Feedback loop.** Status polling captures technician resolution notes → feeds SENTINEL ML for continuous improvement.

---

*SIMBIOT: The integration layer that makes SENTINEL work with anything.*
