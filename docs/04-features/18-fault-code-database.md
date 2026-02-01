---
status: implemented
version: 18
date: 2025-01-29
---

# Phase 18: Fault Code Database & Equipment Lookup

## Overview

Comprehensive fault code database with web scraping capabilities, SA parts supplier integration, and technical forum search. Enables instant offline fault code lookup with diagnosis, probable causes, recommended fixes, and parts sourcing for field technicians.

## Architecture

```
Technician Query (fault code, keyword, or natural language)
    ↓
┌─────────────────────────────────────────────────────────────────┐
│  EquipmentLookup Service                                        │
│  - Local fault code database (303 codes, 9 manufacturers)       │
│  - Case-insensitive fuzzy matching                              │
│  - Manufacturer/model detection from query                      │
└─────────────────────────────────────────────────────────────────┘
    ↓
┌─────────────────────────────────────────────────────────────────┐
│  Parts Supplier Search                                          │
│  - 11 SA suppliers (OEM + generic)                              │
│  - Generic equivalents mapping                                  │
│  - OEM part number lookup                                       │
└─────────────────────────────────────────────────────────────────┘
    ↓
┌─────────────────────────────────────────────────────────────────┐
│  Technical Forums                                               │
│  - HVAC-Talk, Eng-Tips, Reddit r/HVAC                          │
│  - Search URLs for real-world solutions                         │
└─────────────────────────────────────────────────────────────────┘
    ↓
Structured Response (fault info, parts, suppliers, forum links)
```

## Fault Code Database

**Location:** `backend/app/data/fault_codes.json`

### Coverage

| Manufacturer | Codes | Models |
|--------------|-------|--------|
| Carrier | 24 | 30XA, 30RB, 30HX, 39M, 38AR |
| Trane | 17 | RTAC, CGAM, CVHF, CLCP |
| Daikin | 119 | VRV (A/E/F/H/J/L/M/N/P/U/S/W/Y series) |
| ABB | 30 | ACS580, ACS880 drives |
| Danfoss | 40 | VLT AQ, FC series |
| York | 19 | YCAL, YK, YZ |
| Honeywell | 13 | Excel 5000, Hi-Spec, Enterprise Zone |
| Siemens | 17 | Apogee, Symphony, S7-1200 |
| Schneider | 24 | Altivar 61/71, M340, M580 |
| **Total** | **303** | |

### Fault Code Structure

```json
{
  "code": "E4",
  "name": "Low Oil Pressure",
  "severity": "critical",
  "description": "Compressor oil pressure has dropped below safe operating threshold.",
  "probable_causes": [
    {
      "cause": "Low oil level in compressor",
      "likelihood": "high",
      "check": "Check oil sight glass or level indicator"
    }
  ],
  "recommended_fix": {
    "immediate": [
      "Shut down compressor immediately to prevent catastrophic failure",
      "Verify oil pressure with mechanical gauge"
    ],
    "scenarios": {
      "low_oil": "Add compressor oil to proper level",
      "pump_failure": "Replace oil pump assembly"
    }
  }
}
```

### Severity Levels

| Level | Color | Description |
|-------|-------|-------------|
| `critical` | Red | Immediate shutdown required |
| `high` | Orange | Urgent attention needed |
| `medium` | Yellow | Schedule repair soon |
| `low` | Blue | Monitor and plan |
| `info` | Gray | Informational only |

## SA Parts Suppliers

**Location:** `backend/app/data/parts_suppliers.json`

### Supplier Database

| Supplier | Type | Coverage |
|----------|------|----------|
| Carrier SA | OEM | Carrier parts |
| Trane SA | OEM | Trane parts |
| Daikin SA | OEM | Daikin parts |
| Refrigeration Supplies | Generic + OEM | HVAC parts |
| Voltex | Component | Electrical, drives, motors |
| Mantech Electronics | Component | Controls, sensors |
| RS Components SA | Universal | Industrial parts |
| Festo SA | Pneumatics | Valves, actuators |
| SMC Pneumatics SA | Pneumatics | Cylinders, valves |
| Bearing Man | Mechanical | Bearings, seals, belts |
| BMG | Mechanical | Power transmission |

### Generic Equivalents

OEM to generic part mappings for cost savings:

| Component | OEM Part | Generic | Savings |
|-----------|----------|---------|---------|
| Contactors | Carrier 1452292 | Schneider LC1D40M7 | 50-70% |
| Pressure switches | Carrier OEM | Danfoss generic | 40-60% |
| Temperature sensors | Various OEM | Honeywell generic | 30-50% |
| VFD drives | OEM specific | ABB equivalent | 20-40% |
| IGBTs | Universal | Same power rating | 30-50% |

## Equipment Lookup Service

**Location:** `backend/app/services/equipment_lookup.py`

### Key Methods

```python
class EquipmentLookup:
    async def lookup_fault_code(
        self,
        manufacturer: str,
        fault_code: str,
        model: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Look up fault code and return comprehensive diagnosis.

        Returns:
            - fault: Fault details with causes and fixes
            - scraped_data: Web search results (if available)
            - parts: Relevant parts with suppliers
            - forum_solutions: Technical forum links
        """

    async def search_parts(
        self,
        part_number: Optional[str] = None,
        part_description: Optional[str] = None,
        manufacturer: Optional[str] = None
    ) -> List[Dict]:
        """Search SA suppliers for parts."""

    async def search_forums(
        self,
        query: str
    ) -> List[Dict]:
        """Get technical forum search links."""
```

### Features

- **Case-insensitive matching**: "e4" → "E4", "fault 004" → "FAULT_004"
- **Fuzzy manufacturer matching**: "carrier", "Carrier", "CARRIER" all work
- **Model-specific codes**: Some faults are model-specific (e.g., 30XA vs 30RB)
- **Async web scraping**: Non-blocking HTTP requests with 10s timeout

## REST API

**Base URL:** `/api/equipment-lookup`

### Endpoints

```bash
# Fault code lookup
GET /api/equipment-lookup/fault-code?manufacturer=Carrier&fault_code=E4&model=30XA

# Parts search
GET /api/equipment-lookup/parts?part_description=oil+filter&manufacturer=Carrier

# Natural language search
POST /api/equipment-lookup/search?query=carrier+chiller+making+noise
```

### Response Example

```json
{
  "fault": {
    "code": "E4",
    "name": "Low Oil Pressure",
    "severity": "critical",
    "description": "Compressor oil pressure has dropped below safe threshold.",
    "probable_causes": [...],
    "recommended_fix": {...}
  },
  "manufacturer": "carrier",
  "model": "30XA",
  "parts": [
    {
      "name": "Compressor Oil Filter",
      "part_number": "30XA-OILF-001",
      "suppliers": [
        {"name": "Carrier SA", "phone": "+27 11 207 2000"}
      ],
      "generic_alternative": {
        "part_number": "UNIV-OILF-30",
        "manufacturer": "Universal",
        "suppliers": ["rs-components", "refrigeration-supplies"]
      }
    }
  ],
  "forum_solutions": [
    {
      "source": "HVAC-Talk",
      "search_url": "https://hvac-talk.com/search?q=carrier+30xa+e4",
      "description": "Professional HVAC technician forum"
    }
  ]
}
```

## MCP Server Integration

**Location:** `backend/app/mcp/equipment_server.py`

### MCP Tools

| Tool | Description |
|------|-------------|
| `lookup_fault_code` | Fault diagnosis with parts and fixes |
| `lookup_parts` | SA supplier search |
| `search_equipment_issue` | Natural language search |

### Usage in AI Chat

```
User: "Carrier chiller showing E4 fault"

SENTINEL: 🔴 CRITICAL: E4 - Low Oil Pressure

The compressor oil pressure has dropped below safe operating threshold.

**Probable Causes:**
1. Low oil level (high likelihood) - Check sight glass
2. Oil pump failure (medium) - Test pump pressure

**Immediate Actions:**
• Shut down compressor immediately
• Verify oil pressure with mechanical gauge

**Parts Needed:**
• Oil filter: Carrier 30XA-OILF-001
  - Carrier SA: +27 11 207 2000
  - Generic: UNIV-OILF-30 (RS Components)

**Community Resources:**
• HVAC-Talk: [Search results]
• Eng-Tips: [Search results]
```

## Technical Forums

| Forum | URL | Coverage |
|-------|-----|----------|
| HVAC-Talk | hvac-talk.com | Professional technicians |
| Eng-Tips | eng-tips.com | Engineering discussions |
| Reddit r/HVAC | reddit.com/r/HVAC | Community experiences |
| Refrigeration Engineer | refrigeration-engineer.com | Technical articles |

## Files Reference

### Created
- `backend/app/data/fault_codes.json` - 303 fault codes
- `backend/app/data/parts_suppliers.json` - 11 suppliers + mappings
- `backend/app/services/equipment_lookup.py` - Core service (820+ lines)
- `backend/app/api/equipment_lookup.py` - REST API (457 lines)
- `backend/app/mcp/equipment_server.py` - MCP tools (315 lines)

### Dependencies
- `aiohttp>=3.9.0` - Async HTTP
- `beautifulsoup4>=4.12.0` - HTML parsing
- `lxml>=5.0.0` - XML parser

## Usage Examples

### Python

```python
from app.services.equipment_lookup import EquipmentLookup

lookup = EquipmentLookup()

# Fault code lookup
result = await lookup.lookup_fault_code("Carrier", "E4", "30XA")
print(f"Severity: {result['fault']['severity']}")
print(f"Causes: {result['fault']['probable_causes']}")

# Parts search
parts = await lookup.search_parts(part_description="oil filter", manufacturer="Carrier")
for part in parts:
    print(f"{part['name']}: {part['suppliers']}")
```

### cURL

```bash
# Fault lookup
curl "http://localhost:9095/api/equipment-lookup/fault-code?manufacturer=Carrier&fault_code=E4"

# Parts search
curl "http://localhost:9095/api/equipment-lookup/parts?part_description=contactor"

# Natural language
curl -X POST "http://localhost:9095/api/equipment-lookup/search?query=daikin+vrv+communication+error"
```

## Status

✅ **IMPLEMENTED** - Phase 18 complete

- 18-01: Fault code database (303 codes)
- 18-02: SA parts suppliers (11 suppliers)
- 18-03: REST API and MCP server
