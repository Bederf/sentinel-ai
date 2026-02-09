# Phase 49: Municipal Billing Integration

## Overview

Municipal billing integrates electricity and water invoices into the platform, reconciles them against BMS meter data, detects billing anomalies, and generates dispute evidence packs. South African municipal invoices are frequently estimated or back‑billed, so BMS telemetry is treated as the primary truth and invoices are secondary validation.

## Key Capabilities

- **Invoice ingestion** via PDF upload (text extraction first, OCR fallback)
- **Reconciliation** of billed vs BMS consumption
- **Tariff validation** with NERSA‑aligned schedules
- **Maximum demand analysis** (peak demand windows + demand charge exposure)
- **Load staggering recommendations** to reduce demand peaks
- **Dispute evidence pack** for “pay then contest” workflows

## PDF Extraction Pipeline

1. **Text-based extraction (preferred)**
   - PyMuPDF → pdfplumber
   - Regex field extraction (account number, invoice number, totals, billing period)
2. **OCR fallback**
   - Triggered when text extraction is weak or confidence is low
   - Uses `MunicipalInvoiceOCRService` when available

Confidence rules:
- If core fields are missing or confidence < 0.6, OCR is attempted.

## Reconciliation Logic

- Compare billed consumption vs BMS-derived consumption
- Flag variance when deviation exceeds 5%
- Verify tariffs by recalculating expected charges from BMS consumption
- Mark invoice confidence when estimated/back‑billed

## Maximum Demand Analysis

- Uses InfluxDB `sensor_type` for power (default `power`)
- Computes peak demand and top peak windows
- Generates basic staggering guidance (delay non‑critical loads during peak windows)

## Data Flow

1. Upload invoice → PDF extraction → (optional OCR fallback)
2. Create municipal account/invoice record
3. Reconcile against BMS meters (energy + water)
4. Generate variance alerts + dispute evidence pack
5. Provide tariff and maximum demand insights

## Files

- API: `backend/app/api/municipal_billing.py`
- Services:
  - `backend/app/services/municipal_pdf_extraction_service.py`
  - `backend/app/services/municipal_reconciliation_service.py`
  - `backend/app/services/tariff_schedule_service.py`
- Repositories:
  - `backend/app/database/repositories/municipal_invoice_repository.py`
  - `backend/app/database/repositories/tariff_schedule_repository.py`
- Migration: `supabase/migrations/047_municipal_billing.sql`

## Notes

- Invoices can be inaccurate or estimated; BMS data remains the source of truth.
- Dispute packs support “pay under protest” workflows with evidence attachments.

## Demo Data Source (Supabase)

For demo mode, maximum demand is sourced from `municipal_demand_history` in Supabase. This table simulates daily peak demand and peak timestamps for each site/meter.

- Migration: `supabase/migrations/048_municipal_demand_history.sql`
- Repository: `backend/app/database/repositories/municipal_demand_repository.py`

## AI Recommendations Integration

Municipal billing insights are surfaced via the module registry as AI recommendations:

- **Maximum demand exposure** → Optimization recommendation (ENERGY module)
- **Tariff fit mismatch** → Optimization recommendation (CONTRACTS module)

Generated on invoice upload and reconciliation, using BMS aggregate data. These recommendations appear alongside other AI outputs in the unified module registry.

## MCP Tools (SIMBIOT Integration)

Municipal billing is accessible via SIMBIOT MCP server for AI-powered workflows and building onboarding:

### Tool: `process_municipal_bill`

Processes South African municipal utility bill PDFs and extracts invoice data.

**Parameters:**
- `building_id` (required): Building/site ID (e.g., "site-002")
- `pdf_file_path` (required): Absolute path to PDF file
- `municipality` (required): Municipality name (city_of_johannesburg, city_of_cape_town, ekurhuleni, ethekwini)
- `utility_type` (required): "electricity" or "water"
- `account_number` (required): Municipal account number
- `tariff_type` (optional): residential/commercial/industrial

**Returns:**
- Extracted invoice data (invoice number, billing period, consumption, amounts)
- Account and invoice IDs (created automatically)
- Confidence score (0.0-1.0)
- Status and error messages

**Example:**
```python
result = await server.call_tool(
    "process_municipal_bill",
    building_id="site-002",
    pdf_file_path="/path/to/bill.pdf",
    municipality="city_of_johannesburg",
    utility_type="electricity",
    account_number="4001234567"
)
```

### Tool: `get_utility_costs`

Retrieves utility cost analysis for a building from processed municipal bills.

**Parameters:**
- `building_id` (required): Building/site ID
- `period_start` (optional): Period start ISO date (defaults to current month start)
- `period_end` (optional): Period end ISO date (defaults to current month end)

**Returns:**
- Electricity and water costs (separate)
- Total cost for period
- Invoice counts and averages
- Period information

**Example:**
```python
result = await server.call_tool(
    "get_utility_costs",
    building_id="site-002",
    period_start="2026-01-01",
    period_end="2026-01-31"
)
```

**Integration Points:**
- **Building Onboarding**: Upload bills during SIMBIOT `create_building` workflow
- **Contract Management**: Compare municipal costs vs contract fees
- **Profitability Analysis**: Track utility costs in profitability dashboards
- **AI Queries**: Claude can analyze bills and suggest optimizations

**Implementation:**
- MCP Server: `backend/app/mcp/simbiot_server.py` (lines ~1710-1920)
- Tool definitions registered in `MCP_TOOLS` list
- Total MCP tools: 33 (increased from 31)

## Known Gaps

### 🔴 Gap 1: Tariff Parsing (HIGH Priority)

**Current State:**
- PDF ingestion stores raw PDF files and extracted text
- Structured `tariff_data` requires **manual parsing**
- TariffScheduleService exists but no automated extraction

**Impact:**
- ❌ Cannot auto-validate charges against tariff schedules
- ❌ Cannot detect tariff errors automatically
- ❌ Cannot calculate "expected bill" from BMS consumption
- ❌ Revenue protection and dispute support limited

**Root Cause:**
Municipal tariff PDFs have varying layouts:
- City Power: Multi-page tables with complex structures
- Cape Town: Separate annexures per tariff type
- eThekwini: Scanned documents (require OCR)
- Eskom: Standardized booklet format

**Proposed Solution:** Phase 49-09
- Parse tariff tables from PDF text using regex + ML fallback
- Map extracted fields to `tariff_data` structure
- Handle 5 municipality formats
- Add validation against NERSA guidelines
- **Effort:** 2-3 days | **Value:** HIGH (revenue protection)

---

### 🟡 Gap 2: Document Centre Links (LOW Priority)

**Current State:**
- `municipal_tariff_sources.json` has PDF URLs
- Some URLs work: COJ ✅, Eskom ✅, Cape Town ✅
- **eThekwini URL is a document centre landing page** ❌

**Impact:**
- ⚠️ Cannot auto-fetch latest tariff schedules
- ⚠️ Manual process to update tariff sources
- ⚠️ Risk of using outdated tariffs

**eThekwini Issue:**
```
URL: https://durban.gov.za/pages/government/documents?d=Service+Tariffs/...
→ This is a search/filter page, NOT a direct PDF
→ Requires manual navigation to download PDF
```

**Root Cause:**
Municipality document centres use JavaScript navigation, can't link directly to PDF files.

**Proposed Solution:** Phase 49-10
- Scrape eThekwini document centre for PDF links
- Implement generic municipal scraper
- Add to tariff ingestion service (monthly checks)
- Alert when new tariffs detected
- **Effort:** 1 day | **Value:** LOW (convenience)

---

### 🟠 Gap 3: BMS Aggregates / Maximum Demand (HIGH Priority)

**Current State:**
- **Maximum demand uses Supabase demo data** (`municipal_demand_history` table)
- **NOT using real sensor telemetry from InfluxDB**
- Demand analysis is not based on actual building data

**Impact:**
- ❌ Demand analysis is fake/demo only
- ❌ Cannot detect real demand spikes
- ❌ Staggering recommendations are generic
- ❌ No actual demand charge optimization

**Current Data Flow (BROKEN):**
```
MunicipalDemandRepository → Supabase → municipal_demand_history (DEMO DATA)
```

**Should Be:**
```
InfluxDB → Power sensors → Aggregate peak demand → Real analysis
```

**Existing Infrastructure:**
- ✅ InfluxDB service exists (`influxdb_service.py`)
- ✅ Timeseries API exists (`timeseries.py`)
- ✅ Power sensors writing to InfluxDB
- ✅ `MunicipalDemandRepository` has structure ready

**What's Missing:**
- ❌ InfluxDB query for peak demand (kW max over period)
- ❌ Peak window detection (when did peak occur?)
- ❌ Demand aggregation by meter/building
- ❌ Real-time demand monitoring integration

**Root Cause:**
Phase 49 focused on invoice ingestion/reconciliation. InfluxDB integration for demand was deferred. Used demo data for development.

**Proposed Solution:** Phase 49-11
- Add InfluxDB peak demand query method
- Implement demand aggregation by meter
- Calculate peak windows (top 10)
- Store real demand in `municipal_demand_history`
- Update reconciliation service to use real data
- Add real-time demand monitoring dashboard
- **Effort:** 2-3 days | **Value:** HIGH (actual cost optimization)

---

### 📊 Gap Priority Matrix

| Gap | Impact | Effort | Priority | Complexity |
|-----|--------|--------|----------|------------|
| Tariff Parsing | HIGH | 2-3 days | **HIGH** | Medium |
| Document Centre | MEDIUM | 1 day | LOW | Low |
| BMS Aggregates | HIGH | 2-3 days | **HIGH** | Medium |

**Recommended Order:**
1. **49-11: BMS Aggregates** (first - highest impact)
2. **49-09: Tariff Parsing** (second - revenue protection)
3. **49-10: Document Centre** (last - convenience)

---

### See Also

- **Phase 49-09**: Tariff Table Parser (planned)
- **Phase 49-10**: Municipal Document Centre Scraper (planned)
- **Phase 49-11**: Real-Time Demand Monitoring (planned)
