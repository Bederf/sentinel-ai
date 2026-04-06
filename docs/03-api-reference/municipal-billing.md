---
title: "Municipal Billing API"
type: "reference"
status: "draft"
version: "1.0.0"
created: "2026-03-31"
updated: "2026-03-31"
tags: ["sentinel", "documentation"]
related: []
domain: "bms"
audience: "all"
complexity: "intermediate"
estimated_read_time: 10
---

# Municipal Billing API

Base prefix: `/api/municipal-billing`

## Invoice Upload

`POST /invoices/upload`

Form fields:
- `file` (PDF)
- `site_id`
- `municipality`
- `utility_type` (electricity | water | gas | sewerage | refuse)
- `account_number`
- `tariff_type` (optional)
- `meter_number` (optional)

Returns:
- `invoice`
- `reconciliation` (if parsed data available)
- `pdf_path`

`POST /invoices/upload-batch`

Form fields:
- `files[]`
- `site_id`
- `municipality`
- `utility_type`
- `account_number`
- `tariff_type` (optional)

## Invoice Management

`GET /invoices`

Query params:
- `site_id`
- `municipality`
- `utility_type`
- `billing_period`
- `reconciliation_status`
- `limit` (default 50)
- `offset` (default 0)

`GET /invoices/{invoice_id}`

`GET /invoices/{invoice_id}/pdf`

`POST /invoices/{invoice_id}/approve`

Form fields:
- `approved_by`

`POST /invoices/{invoice_id}/dispute`

Form fields:
- `dispute_reason`
- `disputed_by`

`GET /invoices/{invoice_id}/dispute-pack`

Returns a structured evidence payload for municipal disputes.

## Tariffs

`GET /tariffs`

Query params:
- `municipality`
- `utility_type`
- `active_date` (YYYY-MM-DD)

`POST /tariffs`

Form fields:
- `municipality`
- `tariff_name`
- `utility_type`
- `effective_date` (YYYY-MM-DD)
- `tariff_data` (JSON string)

`GET /tariffs/{municipality}/{tariff_name}/calculate`

Query params:
- `site_id`
- `month`
- `year`

`POST /tariffs/ingest`

Triggers ingestion of official tariff PDFs based on the source registry.

## Reconciliation

`GET /reconciliation/portfolio`

Query params:
- `billing_period` (YYYY-MM)

`GET /reconciliation/{site_id}/load-profile`

Query params:
- `period_start` (YYYY-MM-DD)
- `period_end` (YYYY-MM-DD)

`GET /reconciliation/{site_id}/maximum-demand`

Query params:
- `period_start` (YYYY-MM-DD)
- `period_end` (YYYY-MM-DD)
- `meter_id` (optional)
- `sensor_type` (optional, default: `power`)

---

## NMD (Notified Maximum Demand) Extraction (Phase 081)

When electricity invoices are uploaded, SIMBIOT automatically extracts the NMD value from the bill and updates the building's NMD limit in the database.

### Automatic NMD Persistence

**Flow:**
1. Upload invoice: `POST /invoices/upload`
2. SIMBIOT processes invoice PDF
3. AI extracts NMD value from bill (e.g., "Notified Maximum Demand: 6,000 kVA")
4. Automatic database update:
   - `buildings.nmd_limit_kva` = extracted value
   - `buildings.demand_charge_per_kva` = extracted rate
   - `buildings.electricity_provider` = municipality
   - `buildings.nmd_extracted_from_bill` = true
   - `buildings.bill_last_uploaded_at` = timestamp
   - `buildings.billing_cycle_start_date` = invoice period start
   - `buildings.billing_cycle_end_date` = invoice period end

### Usage in Peak Demand Management

The extracted NMD value is immediately used by the Demand-Aware Coordinator for real-time peak monitoring:

```json
GET /api/peak-demand/S002/status
Response:
{
  "nmd_limit_kva": 6000,
  "last_nmd_extraction": "2026-02-10T09:15:00Z",
  "nmd_source": "municipal_bill"
}
```

**Benefits:**
- Real-time peak demand monitoring against actual contractual limit
- Cost-benefit analysis for peak shaving based on actual demand charges
- Automatic cost calculation: (Headroom - Safety Margin) × Demand Charge Rate

### Fallback When No Bill Uploaded

If no bill has been uploaded:
- Database query returns NULL
- Coordinator falls back to seeded defaults:
  - S002: 6,000 kVA
  - site-005: 8,000 kVA
- Status shows: `"nmd_source": "fallback"`

### Example: Bill Upload with NMD Extraction

**Request:**
```bash
POST /invoices/upload
Form data:
  - file: City_Power_Invoice_202601.pdf
  - site_id: S002
  - municipality: City Power Johannesburg
  - utility_type: electricity
  - account_number: 123456789
```

**Response:**
```json
{
  "invoice": {
    "id": "inv-20260210-001",
    "site_id": "S002",
    "municipality": "City Power Johannesburg",
    "utility_type": "electricity",
    "created_at": "2026-02-10T09:15:00Z",
    "pdf_path": "/invoices/city_power_202601.pdf"
  },
  "reconciliation": {
    "nmd_limit_kva": 6000,
    "demand_charge_per_kva": 155.50,
    "billing_start_date": "2026-01-01",
    "billing_end_date": "2026-01-31",
    "total_demand_charges_zar": 930000
  }
}
```

**Database Update (Automatic):**
```sql
UPDATE buildings SET
  nmd_limit_kva = 6000,
  demand_charge_per_kva = 155.50,
  nmd_extracted_from_bill = true,
  bill_last_uploaded_at = '2026-02-10T09:15:00Z',
  electricity_provider = 'City Power Johannesburg',
  billing_cycle_start_date = '2026-01-01',
  billing_cycle_end_date = '2026-01-31'
WHERE code = 'S002';
```

### Peak Demand Integration

After NMD is extracted, the Peak Demand API immediately uses it for real-time monitoring:

1. **Immediate:** Dashboard shows current demand vs new NMD limit
2. **5-minute cycle:** Coordinator evaluates headroom and generates recommendations if < 15%
3. **Example:** If current demand = 5,500 kW and NMD = 6,000 kVA:
   - Headroom = 500 kW (8.3%)
   - Status: **CRITICAL** (< 5% safety margin)
   - Recommendations: BESS discharge + HVAC setpoint increase

**See also:** [Peak Demand API](peak-demand-api.md) - Real-time demand monitoring
