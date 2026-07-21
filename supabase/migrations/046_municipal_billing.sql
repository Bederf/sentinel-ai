-- 047_municipal_billing.sql
-- Municipal billing integration tables

-- =============================================================================
-- Municipal Accounts
-- =============================================================================

CREATE TABLE IF NOT EXISTS municipal_accounts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    site_id TEXT NOT NULL,
    municipality TEXT NOT NULL,
    utility_type TEXT NOT NULL CHECK (utility_type IN ('electricity', 'water', 'gas', 'sewerage', 'refuse')),
    account_number TEXT NOT NULL,
    tariff_type TEXT,
    main_meter_id TEXT,
    active_from DATE NOT NULL DEFAULT CURRENT_DATE,
    active_until DATE,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    billing_email TEXT,
    payment_method TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(site_id, municipality, utility_type, account_number)
);

CREATE INDEX IF NOT EXISTS idx_municipal_accounts_site ON municipal_accounts(site_id);
CREATE INDEX IF NOT EXISTS idx_municipal_accounts_municipality ON municipal_accounts(municipality);

-- =============================================================================
-- Municipal Invoices
-- =============================================================================

CREATE TABLE IF NOT EXISTS municipal_invoices (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    municipal_account_id UUID NOT NULL REFERENCES municipal_accounts(id) ON DELETE CASCADE,
    site_id TEXT NOT NULL,
    municipality TEXT NOT NULL,
    utility_type TEXT NOT NULL CHECK (utility_type IN ('electricity', 'water', 'gas', 'sewerage', 'refuse')),

    -- Invoice identifiers
    invoice_number TEXT NOT NULL,
    invoice_date DATE DEFAULT CURRENT_DATE,
    due_date DATE,
    billing_period_start DATE,
    billing_period_end DATE,

    -- Consumption
    consumption_kwh DECIMAL(12, 2),
    previous_reading DECIMAL(12, 2),
    current_reading DECIMAL(12, 2),
    meter_number TEXT,

    -- Demand (commercial TOU only)
    demand_kva DECIMAL(10, 2),
    peak_demand_kw DECIMAL(10, 2),

    -- Cost breakdown
    energy_charge_zar DECIMAL(12, 2),
    network_charge_zar DECIMAL(10, 2),
    demand_charge_zar DECIMAL(10, 2),
    service_charge_zar DECIMAL(10, 2),
    vat_zar DECIMAL(12, 2),
    total_amount_zar DECIMAL(12, 2),

    -- TOU breakdown (if applicable)
    tou_breakdown JSONB,

    -- OCR metadata
    raw_pdf_path TEXT,
    ocr_confidence DECIMAL(4, 3),
    ocr_status TEXT CHECK (ocr_status IN ('pending', 'completed', 'needs_review', 'failed')) DEFAULT 'pending',

    -- Invoice confidence (estimated/back-billed flags)
    invoice_confidence_score DECIMAL(4, 3),
    invoice_confidence_flags JSONB,

    -- Reconciliation
    bms_consumption_kwh DECIMAL(12, 2),
    variance_pct DECIMAL(8, 2),
    reconciliation_status TEXT CHECK (reconciliation_status IN ('matched', 'variance_detected', 'disputed')),

    -- Dispute evidence pack
    dispute_pack JSONB,

    -- Approval
    approved_by TEXT,
    approved_at TIMESTAMPTZ,

    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),

    UNIQUE(municipal_account_id, invoice_number)
);

CREATE INDEX IF NOT EXISTS idx_municipal_invoices_account_period ON municipal_invoices(municipal_account_id, billing_period_start);
CREATE INDEX IF NOT EXISTS idx_municipal_invoices_site_period ON municipal_invoices(site_id, billing_period_start);
CREATE INDEX IF NOT EXISTS idx_municipal_invoices_reconciliation ON municipal_invoices(reconciliation_status) WHERE reconciliation_status IS NOT NULL AND reconciliation_status != 'matched';

-- =============================================================================
-- Tariff Schedules
-- =============================================================================

CREATE TABLE IF NOT EXISTS municipal_tariff_schedules (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    municipality TEXT NOT NULL,
    tariff_name TEXT NOT NULL,
    utility_type TEXT NOT NULL CHECK (utility_type IN ('electricity', 'water', 'gas')),
    effective_date DATE NOT NULL,
    expiry_date DATE,
    tariff_data JSONB NOT NULL,
    nersa_approved BOOLEAN DEFAULT FALSE,
    source_url TEXT,
    notes TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(municipality, tariff_name, effective_date)
);

CREATE INDEX IF NOT EXISTS idx_municipal_tariffs_effective ON municipal_tariff_schedules(effective_date DESC);
CREATE INDEX IF NOT EXISTS idx_municipal_tariffs_municipality ON municipal_tariff_schedules(municipality);

-- =============================================================================
-- Reconciliation Alerts
-- =============================================================================

CREATE TABLE IF NOT EXISTS municipal_reconciliation_alerts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    invoice_id UUID NOT NULL REFERENCES municipal_invoices(id) ON DELETE CASCADE,
    alert_type TEXT CHECK (alert_type IN ('consumption_variance', 'tariff_mismatch', 'meter_mismatch', 'vat_error')),
    severity TEXT CHECK (severity IN ('low', 'medium', 'high', 'critical')),
    expected_value DECIMAL(15, 2),
    actual_value DECIMAL(15, 2),
    variance_pct DECIMAL(8, 2),
    variance_amount_zar DECIMAL(12, 2),
    status TEXT CHECK (status IN ('open', 'under_investigation', 'resolved', 'disputed')) DEFAULT 'open',
    resolution_notes TEXT,
    resolved_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_municipal_alerts_open ON municipal_reconciliation_alerts(status) WHERE status = 'open';
