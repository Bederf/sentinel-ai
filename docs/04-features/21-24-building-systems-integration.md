---
title: "Building Systems Integration"
type: "feature"
status: "implemented"
version: "1.0.0"
created: "2026-02-03"
updated: "2026-02-03"
author: "SENTINEL Development Team"
tags: ["dali", "lighting", "hybrid-ai", "desk-hvac", "mcp", "simbiot"]
domain: "integration"
audience: "developers"
complexity: "advanced"
estimated_read_time: 15
phase: "21-24"
---

# Building Systems Integration

Cross-system intelligence connecting DALI lighting, HVAC, occupancy, and AI services through the SIMBIOT MCP server.

## Overview

Phases 21-24 implement SENTINEL's cross-system capabilities:
- **Phase 21**: Tridonic DALI-2 Lighting Integration
- **Phase 22**: Hybrid AI Architecture (Ollama + Claude)
- **Phase 23**: Desk-Level HVAC Intelligence
- **Phase 24**: SIMBIOT MCP Server

## Phase 21: DALI-2 Lighting Integration

### Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    DALI-2 Integration                       │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│   Tridonic Scenecom                                         │
│   ┌─────────────────┐                                       │
│   │ DALI-2 Gateway  │                                       │
│   │  • 1,315 PIR    │                                       │
│   │  • 619 Luminaires│                                      │
│   │  • 15 Zones     │                                       │
│   └────────┬────────┘                                       │
│            │                                                │
│            ▼                                                │
│   ┌─────────────────┐     ┌─────────────────┐              │
│   │  DALI Service   │────►│ Cross-System    │              │
│   │  (REST API)     │     │   Analyzer      │              │
│   └─────────────────┘     └─────────────────┘              │
│                                  │                          │
│                    ┌─────────────┼─────────────┐            │
│                    ▼             ▼             ▼            │
│              ┌──────────┐ ┌──────────┐ ┌──────────┐        │
│              │ Lighting │ │   HVAC   │ │ Occupancy│        │
│              │ Control  │ │ Setpoints│ │ Tracking │        │
│              └──────────┘ └──────────┘ └──────────┘        │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### API Endpoints

```bash
# Get zone status
GET /api/dali/zones/{zone_id}

Response:
{
  "zone_id": "L1-A",
  "zone_name": "Level 1 Zone A",
  "occupancy": {
    "occupied": true,
    "occupant_count": 12,
    "last_motion": "2026-02-03T14:55:00Z"
  },
  "lighting": {
    "brightness_percent": 85,
    "active_scene": "daylight-harvesting",
    "power_watts": 245
  },
  "daylight": {
    "current_lux": 450,
    "setpoint_lux": 500
  }
}

# Control zone
POST /api/dali/zones/{zone_id}/control
Content-Type: application/json

{
  "action": "set_scene",
  "scene": "presentation",
  "brightness_percent": 30
}
```

### Cross-System Features

- **Occupancy-based HVAC**: Unoccupied zones reduce cooling
- **Daylight harvesting**: Auto-dim when natural light sufficient
- **Comfort diagnosis**: Correlate lighting + HVAC for desk complaints

---

## Phase 22: Hybrid AI Architecture

### Routing Strategy

```
┌─────────────────────────────────────────────────────────────┐
│                    Hybrid AI Router                         │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│   User Query                                                │
│       │                                                     │
│       ▼                                                     │
│   ┌─────────────────┐                                       │
│   │ Task Classifier │                                       │
│   │  (Pattern Match)│                                       │
│   └────────┬────────┘                                       │
│            │                                                │
│     ┌──────┴──────┐                                        │
│     │             │                                        │
│     ▼             ▼                                        │
│ ┌────────┐   ┌────────┐                                    │
│ │ Tier 1 │   │ Tier 2 │                                    │
│ │ Ollama │   │ Claude │                                    │
│ │ (FREE) │   │ (PAID) │                                    │
│ └────────┘   └────────┘                                    │
│     │             │                                        │
│     ▼             ▼                                        │
│ Simple         Complex                                      │
│ Lookups        Reasoning                                    │
│ Data Queries   Control Actions                              │
│                Safety-Critical                              │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### Tier Classification

| Tier | Model | Use Cases | Cost |
|------|-------|-----------|------|
| 1 | Ollama (llama3.2:1b) | Simple lookups, data queries | FREE |
| 2 | Claude (Sonnet) | Complex reasoning, control actions | $0.0105/query |

### API

```bash
POST /api/hybrid-chat
Content-Type: application/json

{
  "message": "What is the temperature in zone L1-A?"
}

Response:
{
  "response": "The current temperature in Zone L1-A is 22.5°C...",
  "tier_used": 1,
  "model": "llama3.2:1b",
  "cost_usd": 0.0,
  "latency_ms": 450
}
```

### Cost Savings

- **40% reduction** vs all-Claude approach
- Simple queries: Ollama handles ~60% of traffic
- Complex queries: Claude for safety-critical actions

---

## Phase 23: Desk-Level HVAC Intelligence

### Complaint Handling Flow

```
┌─────────────────────────────────────────────────────────────┐
│                 Desk Complaint Diagnosis                    │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│   "User at desk 201 says it's too hot"                     │
│              │                                              │
│              ▼                                              │
│   ┌─────────────────┐                                       │
│   │  Desk Lookup    │  desk_id → zone → HVAC → DALI        │
│   │  (desks.json)   │                                       │
│   └────────┬────────┘                                       │
│            │                                                │
│            ▼                                                │
│   ┌─────────────────┐     ┌─────────────────┐              │
│   │ Context Flags   │────►│ CrossSystem     │              │
│   │ • near_window   │     │   Analyzer      │              │
│   │ • near_diffuser │     └────────┬────────┘              │
│   │ • near_printer  │              │                       │
│   └─────────────────┘              │                       │
│                           ┌────────┴────────┐              │
│                           ▼                 ▼              │
│                    ┌──────────┐      ┌──────────┐          │
│                    │   HVAC   │      │   DALI   │          │
│                    │ Readings │      │ Sensors  │          │
│                    └──────────┘      └──────────┘          │
│                           │                 │              │
│                           ▼                 ▼              │
│                    ┌────────────────────────────┐          │
│                    │     AI Diagnosis          │          │
│                    │  • Root cause             │          │
│                    │  • Confidence level       │          │
│                    │  • Suggested actions      │          │
│                    └────────────────────────────┘          │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### API

```bash
POST /api/complaints/submit?desk_id=201&complaint_type=too_hot

Response:
{
  "desk_id": "201",
  "desk_location": "Level 2, Zone A, Near Window",
  "complaint_type": "too_hot",
  "diagnosis": {
    "root_cause": "Solar heat gain through west-facing window",
    "confidence": "high",
    "contributing_factors": [
      "Afternoon sun exposure (14:00-18:00)",
      "Window proximity (1.5m)",
      "Current zone temp: 24.2°C (setpoint: 22°C)"
    ]
  },
  "suggestions": [
    "Close blinds on west-facing windows",
    "Lower zone setpoint by 1°C",
    "Request facilities to check solar film"
  ],
  "auto_actions": [
    {"action": "Lowered L2-A setpoint to 21°C", "status": "executed"}
  ]
}
```

### Demo Desks

| Desk | Context | Typical Complaint |
|------|---------|-------------------|
| 201 | Near window (west) | Too hot (afternoon) |
| 202 | Near diffuser | Too cold (draft) |
| 203 | Near printer | Too warm |
| 204 | Interior | Stuffy |

---

## Phase 24: SIMBIOT MCP Server

### Overview

Model Context Protocol (MCP) server providing 21 tools for building management via Claude Desktop or cloud Claude.

### Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    SIMBIOT MCP Server                       │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│   Claude Desktop / Cloud Claude                             │
│              │                                              │
│              ▼                                              │
│   ┌─────────────────┐                                       │
│   │  MCP Transport  │                                       │
│   │  • stdio (local)│                                       │
│   │  • SSE (cloud)  │                                       │
│   └────────┬────────┘                                       │
│            │                                                │
│            ▼                                                │
│   ┌─────────────────────────────────────────┐              │
│   │           SIMBIOT MCP Server            │              │
│   │                                         │              │
│   │  Building Tools    Device Tools         │              │
│   │  • get_buildings   • get_devices        │              │
│   │  • get_assets      • read_device_point  │              │
│   │  • get_asset_detail• write_device_point │              │
│   │                                         │              │
│   │  Alarm Tools       Work Order Tools     │              │
│   │  • get_alarms      • get_work_orders    │              │
│   │  • search_alarms   • create_work_order  │              │
│   │                                         │              │
│   │  Trend Tools       Health Tools         │              │
│   │  • get_trends      • get_health_score   │              │
│   └─────────────────────────────────────────┘              │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### MCP Tools (21 total)

| Category | Tools |
|----------|-------|
| Building | get_buildings, get_assets, get_asset_detail |
| Device | get_devices, read_device_point, write_device_point |
| Alarm | get_alarms, search_alarms |
| Trend | get_trends, get_health_score |
| Work Order | get_work_orders, create_work_order |

### REST API

```bash
# List all tools
GET /api/mcp/simbiot/tools

# Execute tool
POST /api/mcp/simbiot/call
Content-Type: application/json

{
  "tool_name": "get_equipment_health",
  "arguments": {
    "site_code": "site-002"
  }
}

Response:
{
  "result": {
    "building": {"name": "Sandton City", "floors": 3},
    "health_summary": {"critical": 0, "warning": 2, "healthy": 154},
    "readings": {
      "temperature": {"average": 22.5, "min": 20.1, "max": 24.8},
      "occupancy": {"zones_occupied": 12, "total_occupants": 145}
    }
  }
}
```

### Claude Desktop Config

```json
{
  "mcpServers": {
    "simbiot": {
      "command": "python",
      "args": ["-m", "app.mcp.simbiot_stdio"],
      "cwd": "/opt/bms-intelligence/backend",
      "env": {"PYTHONPATH": "/opt/bms-intelligence/backend"}
    }
  }
}
```

## Implementation

**Phase 21 (DALI):**
- `backend/app/services/dali_service.py`
- `backend/app/api/dali.py`
- `backend/app/data/dali_mock_data.json`

**Phase 22 (Hybrid AI):**
- `backend/app/services/hybrid_ai_service.py`
- `backend/app/services/ollama_client.py`
- `backend/app/api/hybrid_chat.py`

**Phase 23 (Desk HVAC):**
- `backend/app/services/complaint_handler.py`
- `backend/app/services/cross_system_analyzer.py`
- `backend/app/api/complaints.py`
- `backend/app/data/desks.json`

**Phase 24 (SIMBIOT MCP):**
- `backend/app/mcp/simbiot_server.py`
- `backend/app/mcp/simbiot_stdio.py`
- `backend/app/api/mcp.py`
- `backend/app/api/mcp_sse.py`

## Related Documentation

- [DALI-HVAC Integration](../07-integrations/dali-hvac-integration.md)
- [Hybrid AI Router](../08-ai-ml/hybrid-ai-router.md)
- [MCP Tools Reference](../03-api-reference/mcp-tools-reference.md)
