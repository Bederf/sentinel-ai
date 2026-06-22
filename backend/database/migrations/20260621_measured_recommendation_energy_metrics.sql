-- Measured recommendation energy feedback metrics
-- Stores auditable before/after kWh and Rand impact from real telemetry.

ALTER TABLE recommendations ADD COLUMN IF NOT EXISTS baseline_energy_kwh FLOAT;
ALTER TABLE recommendations ADD COLUMN IF NOT EXISTS actual_energy_kwh FLOAT;
ALTER TABLE recommendations ADD COLUMN IF NOT EXISTS actual_saving_kwh FLOAT;
