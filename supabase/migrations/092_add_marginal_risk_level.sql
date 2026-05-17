-- Migration: Add MARGINAL risk level to legionella_risk_assessment
-- Date: 2025-05-17
-- Purpose: Support 50-55°C transitional zone per SABS Legionella guidance
-- Frontend change: LegionellaPanel.tsx now displays 4 risk categories including Marginal
--
-- IMPORTANT: Run this BEFORE deploying the backend with MARGINAL RiskLevel enum
-- otherwise inserts will fail with constraint violations

-- ============================================================================
-- Update risk_level constraint to include 'marginal'
-- ============================================================================

-- Note: PostgreSQL requires dropping and recreating the constraint
-- since ALTER CONSTRAINT doesn't support adding values to CHECK constraints

ALTER TABLE legionella_risk_assessment
DROP CONSTRAINT IF EXISTS legionella_risk_assessment_risk_level_check;

ALTER TABLE legionella_risk_assessment
ADD CONSTRAINT legionella_risk_assessment_risk_level_check
CHECK (risk_level IN ('low', 'medium', 'marginal', 'high'));

-- ============================================================================
-- Add comment explaining the risk levels
-- ============================================================================

COMMENT ON COLUMN legionella_risk_assessment.risk_level IS
'Risk classification per SABS Legionella guidance:
low (<20°C or >55°C),
medium (20-45°C with recent treatment, or 45-50°C),
marginal (50-55°C transitional zone),
high (20-45°C + >30 days untreated)';

-- ============================================================================
-- Verify the constraint was updated
-- ============================================================================

-- Run this to verify:
-- SELECT conname, pg_get_constraintdef(oid)
-- FROM pg_constraint
-- WHERE conrelid = 'legionella_risk_assessment'::regclass
-- AND conname = 'legionella_risk_assessment_risk_level_check';
