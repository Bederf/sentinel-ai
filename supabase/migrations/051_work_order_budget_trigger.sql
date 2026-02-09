-- =====================================================
-- Migration 051: Work Order → Budget Actuals Trigger
-- =====================================================

-- Helper function to upsert budget row and apply deltas
CREATE OR REPLACE FUNCTION apply_budget_actuals_delta(
  p_contract_id UUID,
  p_year INTEGER,
  p_month INTEGER,
  p_labor_delta DECIMAL,
  p_parts_delta DECIMAL
) RETURNS VOID AS $$
DECLARE
  v_budget_id UUID;
BEGIN
  IF p_contract_id IS NULL THEN
    RETURN;
  END IF;

  SELECT id INTO v_budget_id
  FROM budgets
  WHERE contract_id = p_contract_id
    AND budget_year = p_year
    AND budget_month = p_month
    AND equipment_type IS NULL
  LIMIT 1;

  IF v_budget_id IS NULL THEN
    INSERT INTO budgets (
      code,
      contract_id,
      equipment_type,
      budget_year,
      budget_month,
      labor_budget_zar,
      parts_budget_zar,
      consumables_budget_zar,
      subcontractor_budget_zar,
      callout_budget_zar,
      labor_actual_zar,
      parts_actual_zar,
      consumables_actual_zar,
      subcontractor_actual_zar,
      callout_actual_zar,
      status,
      notes
    ) VALUES (
      'BUD-' || LEFT(p_contract_id::TEXT, 8) || '-' || p_year::TEXT || '-' || LPAD(p_month::TEXT, 2, '0'),
      p_contract_id,
      NULL,
      p_year,
      p_month,
      0, 0, 0, 0, 0,
      GREATEST(p_labor_delta, 0),
      GREATEST(p_parts_delta, 0),
      0, 0, 0,
      'draft',
      'Auto-created by work_order budget trigger'
    ) RETURNING id INTO v_budget_id;
  ELSE
    UPDATE budgets
    SET
      labor_actual_zar = COALESCE(labor_actual_zar, 0) + p_labor_delta,
      parts_actual_zar = COALESCE(parts_actual_zar, 0) + p_parts_delta
    WHERE id = v_budget_id;
  END IF;
END;
$$ LANGUAGE plpgsql;

-- Main trigger function
CREATE OR REPLACE FUNCTION update_budget_actuals_from_work_order()
RETURNS TRIGGER AS $$
DECLARE
  new_year INTEGER;
  new_month INTEGER;
  old_year INTEGER;
  old_month INTEGER;
  new_labor DECIMAL := COALESCE(NEW.labor_cost_zar, 0);
  new_parts DECIMAL := COALESCE(NEW.parts_cost_zar, 0);
  old_labor DECIMAL := COALESCE(OLD.labor_cost_zar, 0);
  old_parts DECIMAL := COALESCE(OLD.parts_cost_zar, 0);
  new_total DECIMAL := COALESCE(NEW.total_cost_zar, 0);
  old_total DECIMAL := COALESCE(OLD.total_cost_zar, 0);
BEGIN
  -- Only process when contract_id is set
  IF NEW.contract_id IS NULL THEN
    RETURN NEW;
  END IF;

  -- Normalize costs: if total present but labor+parts empty, assign to labor
  IF new_total > 0 AND new_labor = 0 AND new_parts = 0 THEN
    new_labor := new_total;
  END IF;
  IF old_total > 0 AND old_labor = 0 AND old_parts = 0 THEN
    old_labor := old_total;
  END IF;

  -- Determine periods
  new_year := EXTRACT(YEAR FROM COALESCE(NEW.completed_at, NEW.created_at, NOW()));
  new_month := EXTRACT(MONTH FROM COALESCE(NEW.completed_at, NEW.created_at, NOW()));
  old_year := EXTRACT(YEAR FROM COALESCE(OLD.completed_at, OLD.created_at, NOW()));
  old_month := EXTRACT(MONTH FROM COALESCE(OLD.completed_at, OLD.created_at, NOW()));

  -- Case 1: status becomes completed
  IF (OLD.status IS DISTINCT FROM 'completed') AND NEW.status = 'completed' THEN
    PERFORM apply_budget_actuals_delta(NEW.contract_id, new_year, new_month, new_labor, new_parts);
    RETURN NEW;
  END IF;

  -- Case 2: status removed from completed
  IF OLD.status = 'completed' AND NEW.status IS DISTINCT FROM 'completed' THEN
    PERFORM apply_budget_actuals_delta(NEW.contract_id, old_year, old_month, -old_labor, -old_parts);
    RETURN NEW;
  END IF;

  -- Case 3: status completed and costs changed
  IF OLD.status = 'completed' AND NEW.status = 'completed' THEN
    IF new_year = old_year AND new_month = old_month THEN
      PERFORM apply_budget_actuals_delta(
        NEW.contract_id,
        new_year,
        new_month,
        new_labor - old_labor,
        new_parts - old_parts
      );
    ELSE
      -- Period changed: subtract old, add new
      PERFORM apply_budget_actuals_delta(NEW.contract_id, old_year, old_month, -old_labor, -old_parts);
      PERFORM apply_budget_actuals_delta(NEW.contract_id, new_year, new_month, new_labor, new_parts);
    END IF;
  END IF;

  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trigger_update_budget_actuals_from_work_order ON work_orders;
CREATE TRIGGER trigger_update_budget_actuals_from_work_order
AFTER INSERT OR UPDATE OF status, labor_cost_zar, parts_cost_zar, total_cost_zar, contract_id, completed_at
ON work_orders
FOR EACH ROW
EXECUTE FUNCTION update_budget_actuals_from_work_order();
