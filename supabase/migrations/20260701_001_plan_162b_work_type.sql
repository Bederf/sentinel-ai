-- PLAN-162B: Add work_type column to work_orders table
-- Values: repair (default), replacement, retrofit, maintenance

ALTER TABLE work_orders ADD COLUMN IF NOT EXISTS work_type text NOT NULL DEFAULT 'repair';
