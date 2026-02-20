# Tier 2 Approval Workflow (Supervised Device Control)

**Purpose:** Implements supervised control tier for equipment modifications. Operators approve AI recommendations before they're applied to Niagara devices, with safety validation at approval time and automatic rollback capability.

**See CLAUDE.md for quick reference. This document covers full implementation details.**

## Architecture

- **Service:** `backend/app/services/approval_service.py` (main business logic)
- **API:** `backend/app/api/approvals.py` (REST endpoints)
- **Models:** `backend/app/models/recommendation.py` (status enum, data classes)
- **Database:** `RecommendationRepository` stores all approval state and execution history
- **Tests:** `backend/tests/api/test_approvals.py` (12 integration tests), `frontend/src/components/Recommendations/__tests__/ApprovalWorkflow.test.tsx` (17 E2E tests)

## Workflow Stages (Recommendation Status)

```
PENDING      → Generated, awaiting operator action
  ├─ APPROVED → Operator approved (async transition)
  ├─ EXECUTED → Successfully written to device + COV verified
  ├─ REJECTED → Operator rejected with reason
  ├─ ROLLED_BACK → Previously executed approval was rolled back
  └─ FAILED → Execution failed (safety violation, device error, etc.)
```

## Safety Validation (Defense-in-Depth)

1. **First validation** (AI generation time): SafetyEngine.validate() blocks unsafe recommendations
2. **Second validation** (approval time): SafetyEngine.validate() re-checks before device write
   - Reason: Conditions may have changed between recommendation generation and approval
   - Example: Equipment health deteriorated, creating new safety constraints
   - If fails → Recommendation status = REJECTED with reason + audit log

## Device Write & COV Feedback

1. **Pre-write:** Call `device_manager.read_value()` to capture original value for rollback
2. **Write:** Call `device_manager.set_value()` to write target value to Niagara
3. **Verify COV:** Call `device_manager.read_value()` again to confirm device accepted change
   - COV (Change of Value) feedback verifies device hardware actually received/applied the value
   - Mismatch detected → Mark `cov_verified=false` but still mark execution as successful (operator sees warning)
   - Read failure → Mark `cov_verified=false` but continue (may be temporary network issue)

## Execution Result Storage

Stored in `recommendation.execution_result`:
```python
{
    "success": True,
    "device_write": {"success": True, ...},  # device_manager.set_value() result
    "cov_verified": True,                     # Did read-back match expected value?
    "original_value": 18.0,                   # Value BEFORE write (for rollback)
    "target_value": 20.0,                     # Value we tried to write
    "control_point": "setpoint",              # Point name
    "timestamp": "2026-02-12T10:15:30.123456" # When write executed
}
```

## Rollback Mechanism

- **Trigger:** Operator requests rollback via API after approval execution
- **Process:**
  1. Verify recommendation is EXECUTED (only executed can be rolled back)
  2. Extract `original_value` and `control_point` from `execution_result`
  3. Call `device_manager.set_value()` with original_value
  4. Verify COV feedback (confirm device restored to original value)
  5. Update status to ROLLED_BACK with rollback_reason and initiated_by
  6. Create audit log entry marking rollback
- **Result:** Equipment restored to pre-change state; preserves full change history for audit

## Audit Trail

Every approval/rejection/rollback creates audit log entry with:
- action_type: "equipment_approval", "equipment_rejection", "equipment_rollback"
- equipment_code: Target equipment identifier
- approved_by: User who took action
- approval_notes: Operator notes/reasoning
- change_description: What was changed (e.g., "setpoint = 20.0")
- execution_status: "success", "rejected", "failed"
- verified_by_cov: Boolean indicating COV verification result
- timestamp: When action occurred

## API Endpoints

```python
# Approve a pending recommendation
POST /api/approvals/recommendations/{rec_id}/approve
  Request: {"approved_by": "tech@site-002", "approval_notes": "Peak demand response"}
  Response: ApprovalResponse with execution_result and cov_verified

# Reject a pending recommendation
POST /api/approvals/recommendations/{rec_id}/reject
  Request: {"rejected_by": "supervisor@site", "reason": "Conflicting with scheduled maintenance"}
  Response: ApprovalResponse with rejection confirmation

# Get approval status
GET /api/approvals/recommendations/{rec_id}/status
  Response: ApprovalStatus with current state, timestamps, rejection_reason

# Rollback an executed approval
POST /api/approvals/recommendations/{rec_id}/rollback
  Query params: rollback_reason (optional), initiated_by (from auth context)
  Response: ApprovalResponse with rollback confirmation
```

## Testing Patterns

**Backend (pytest, `test_approvals.py`):**
- Mock `device_manager` with `set_value()` and `read_value()` methods
- Mock `SafetyEngine.validate()` to return `{"is_safe": True/False, "reason": "..."}`
- Mock `recommendations_repo` and `audit_repo` with AsyncMock
- Use side_effect for COV verification: `[{"success": True, "value": 18.0}, {"success": True, "value": 20.0}]`
- Test paths:
  - ✓ Approval succeeds with COV verified
  - ✓ Approval fails when SafetyEngine rejects
  - ✓ Approval fails when device write fails
  - ✓ Approval succeeds with COV mismatch (warning)
  - ✓ Rollback succeeds with original value restoration
  - ✓ Rollback fails when not in EXECUTED state
  - ✓ Rejection succeeds with reason recorded
  - ✓ Validation rejects already-executed recommendations

**Frontend (vitest, `ApprovalWorkflow.test.tsx`):**
- Mock `approvalsApi` with QueryClient provider
- Use `screen.getByRole()` for accessible element queries
- Test flows:
  - ✓ Recommendation list displays pending items
  - ✓ Dialog opens and closes correctly
  - ✓ Form validation before submission
  - ✓ API call on approve button click
  - ✓ Success/error messages displayed
  - ✓ Loading states during submission
  - ✓ Rejection workflow (alt path)

## Common Patterns

```python
# ✅ CORRECT: Execute approval with all safety checks
result = await approval_service.execute_approval(
    recommendation_id="rec-123",
    approved_by="technician@site",
    approval_notes="Urgent peak demand"
)
if result.success:
    print(f"Device updated, COV verified: {result.cov_verified}")

# ✅ CORRECT: Rollback an executed change
rollback = await approval_service.rollback_approval(
    recommendation_id="rec-123",
    rollback_reason="Error detected post-execution",
    initiated_by="supervisor@site"
)

# ❌ WRONG: Bypassing approval workflow
await device_manager.set_value(equipment_id, point, value)  # No safety check!

# ❌ WRONG: Assuming COV verified always means perfect match
# Use: if result.cov_verified is False, device may have accepted partial value
```

## Troubleshooting

| Issue | Solution |
|-------|----------|
| Approval fails with "Safety constraint violation" | Check SafetyEngine rules in `data/safety_rules.json`, verify equipment health/constraints |
| COV verification fails but approval marked success | Device write succeeded but read confirmation delayed/failed; check device connectivity |
| Rollback fails with "missing original state" | Original value not captured during approval; check `execution_result.original_value` is populated |
| Recommendation never transitions from PENDING | Check `recommendations_repo` implementation; verify database persistence |

## Related Files

- **Backend Services:** `backend/app/services/approval_service.py`, `backend/app/services/safety_interlocks.py`
- **Backend API:** `backend/app/api/approvals.py`, `backend/app/api/audit_log.py`
- **Frontend Components:** `frontend/src/components/Recommendations/ApprovalDialog.tsx`, `frontend/src/components/Recommendations/RecommendationsList.tsx`
- **Frontend API:** `frontend/src/lib/api/approvals.ts`
- **Tests:** `backend/tests/api/test_approvals.py`, `frontend/src/components/Recommendations/__tests__/`
