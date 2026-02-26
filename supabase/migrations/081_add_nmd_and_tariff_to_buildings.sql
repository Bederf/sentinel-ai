-- Migration 081: Add NMD and Tariff Configuration to Buildings Table
-- Purpose: Store extracted NMD limits and demand charges from municipal bills
-- Date: 2026-02-12

-- Add columns to buildings table for NMD and tariff data
ALTER TABLE buildings ADD COLUMN IF NOT EXISTS nmd_limit_kva FLOAT;
ALTER TABLE buildings ADD COLUMN IF NOT EXISTS demand_charge_per_kva FLOAT;
ALTER TABLE buildings ADD COLUMN IF NOT EXISTS electricity_provider TEXT;
ALTER TABLE buildings ADD COLUMN IF NOT EXISTS billing_cycle_start_date DATE;
ALTER TABLE buildings ADD COLUMN IF NOT EXISTS billing_cycle_end_date DATE;
ALTER TABLE buildings ADD COLUMN IF NOT EXISTS bill_last_uploaded_at TIMESTAMPTZ;
ALTER TABLE buildings ADD COLUMN IF NOT EXISTS bill_document_path TEXT;
ALTER TABLE buildings ADD COLUMN IF NOT EXISTS nmd_extracted_from_bill BOOLEAN DEFAULT false;
ALTER TABLE buildings ADD COLUMN IF NOT EXISTS tariff_band TEXT;

-- Create indexes
CREATE INDEX IF NOT EXISTS idx_buildings_nmd_limit ON buildings(nmd_limit_kva) WHERE nmd_limit_kva IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_buildings_bill_uploaded ON buildings(bill_last_uploaded_at) WHERE bill_last_uploaded_at IS NOT NULL;

-- Add comments
COMMENT ON COLUMN buildings.nmd_limit_kva IS 'Notified Maximum Demand limit in kVA extracted from municipal electricity bill.';
COMMENT ON COLUMN buildings.demand_charge_per_kva IS 'Monthly demand charge rate (R/kVA) extracted from municipal tariff.';
COMMENT ON COLUMN buildings.nmd_extracted_from_bill IS 'True if NMD value was extracted from uploaded municipal bill; False if using default/manual value.';

-- Populate default NMD for existing buildings
UPDATE buildings
SET
  nmd_limit_kva = CASE
    WHEN code = 'S002' THEN 6000.0
    WHEN code = 'site-005' THEN 8000.0
    ELSE 5000.0
  END,
  demand_charge_per_kva = 155.50,
  electricity_provider = 'City Power',
  nmd_extracted_from_bill = false
WHERE nmd_limit_kva IS NULL;
