-- PLAN-162B: Add reset_reason column to review_queue for operator visibility

ALTER TABLE review_queue ADD COLUMN IF NOT EXISTS reset_reason text;
