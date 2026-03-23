# Phase 170-01: Frontend Supervised Execution Loop — BUILD COMPLETE

**Status**: ✅ COMPLETE  
**Date**: 2026-03-23  
**Compilation**: ✅ TypeScript + Vite successful  

## What Was Built

### 1. Decision Execution API Types (`src/lib/api/decision.ts`)

New API module for supervised control execution:

```typescript
// Types
- Decision: Frontend decision model
- ExecutionState: 'pending' | 'accepted' | 'verified' | 'timeout' | 'error'
- ExecutionProgress: Local state tracking for UI updates
- ExecutionEvent: SSE event from backend (COMMAND_ACCEPTED, COMMAND_VERIFIED, etc.)
- ApprovalExecutionRequest/Response: Request/response shape for POST /api/v1/approval/execute/{site_id}

// API Method
- decisionApi.executeDecision(siteId, decisionId, approvalOutcome)
  Returns ApprovalExecutionResponse with ACCEPTED status + correlation_id
```

### 2. useDecisionExecution Hook (`src/hooks/useDecisionExecution.ts`)

React Hook for managing decision execution state and async verification:

```typescript
const { execute, progress, isExecuting, isVerified, isTimeout, isError, error } =
  useDecisionExecution({
    siteId: "site-002",
    decisionId: "dec-1",
    onVerified: (details) => { /* telemetry matched */ },
    onTimeout: () => { /* 30s verification window closed */ },
    onError: (error) => { /* execution failed */ },
  })

// Dispatches decision via POST /api/v1/approval/execute/{site_id}
// Returns ACCEPTED immediately (does NOT block)
// Listens for async SSE events:
//   - COMMAND_ACCEPTED (initial dispatch confirmation)
//   - COMMAND_VERIFIED (telemetry confirmed change after 1-30s)
//   - COMMAND_TIMEOUT (no change detected after 30s)
//   - COMMAND_FAILED (device/safety error)
```

**Key Features**:
- Non-blocking execution (returns ACCEPTED immediately)
- 35-second timeout fallback (backend estimates 30s verification)
- SSE listener for async verification events
- Automatic cleanup on unmount
- Correlation ID threading for audit trail

### 3. ApproveButton Component (`src/components/ApproveButton.tsx`)

Hold-to-approve button with 3-second confirmation:

```typescript
<ApproveButton
  decision_id="dec-1"
  site_id="site-002"
  tier={3}  // CRITICAL (red), 2 (orange), 1 (green)
  device_id="S002-CHILLER-B1-001"
  point="enable"
  command_value={false}
  onApproved={() => { /* verified */ }}
  onFailed={(error) => { /* execution failed */ }}
  onTimeout={() => { /* 30s verification timeout */ }}
/>
```

**Features**:
- Tier-based color coding (red=CRITICAL, orange=HIGH, green=MEDIUM)
- 3-second hold requirement to prevent accidental execution
- Progress bar shows hold percentage
- Shows device/point/command details
- Transitions through states: pending → accepted → (verified|timeout|error)
- Haptic feedback on hold complete (if available)
- Touch-friendly (mouse + touch events)

### 4. DecisionMoment Component (`src/components/DecisionMoment.tsx`)

Display panel for pending decisions with approval UI:

```typescript
<DecisionMoment
  decision={{
    id: "dec-1",
    site_id: "site-002",
    device_id: "S002-CHILLER-B1-001",
    point: "enable",
    command_value: false,
    tier: 3,
    status: "pending",
  }}
  site_id="site-002"
  onApproved={() => { /* next step */ }}
  onRejected={() => { /* cleanup */ }}
  onFailed={(error) => { /* error handling */ }}
/>
```

**Features**:
- Shows device, control point, desired value, tier level
- Decision age (e.g., "47s ago")
- Audit trail info (decision_id, site_id)
- Integrated ApproveButton component
- Reject button for denying execution
- Info section explaining verification flow
- Responsive dark mode support

### 5. API Export Integration

Added decision API types and methods to `src/lib/api/index.ts`:
- `decisionApi.executeDecision()`
- `Decision` type
- `ExecutionState`, `ExecutionProgress`, `ExecutionEvent` types
- All properly exported for use throughout frontend

## Architecture

### State Flow

```
1. Backend dispatches decision → Decision passed to DecisionMoment
2. User holds ApproveButton for 3 seconds
3. ApproveButton calls useDecisionExecution.execute()
4. POST /api/v1/approval/execute/{site_id} returns ACCEPTED immediately
5. useDecisionExecution opens SSE listener for correlation_id
6. Backend executes 14-step flow (steps 4-11 synchronous, 12-14 async)
7. Backend spawns background verification task (telemetry polling)
8. SSE stream sends COMMAND_VERIFIED/TIMEOUT/FAILED event
9. useDecisionExecution state updates → DecisionMoment shows result
10. UI transitions from "dispatching" → "verified"/"timeout"/"error"
```

### Async Verification Mechanism

**SSE Event Path** (Preferred):
- Backend subscribes frontend to `/api/events?correlation_id={correlationId}`
- Backend verification task emits events as it progresses
- Frontend receives real-time updates: ACCEPTED → VERIFIED/TIMEOUT/FAILED

**Polling Fallback** (If SSE unavailable):
- 35-second timeout triggers fallback polling interval
- Could query `/api/v1/approval/status/{decision_id}` periodically
- (Not implemented yet — SSE preferred approach in production)

## TypeScript Compliance

✅ All components use type-only imports (verbatimModuleSyntax enabled)
✅ Proper separation of value imports from type imports
✅ No circular dependencies
✅ Full type safety for ExecutionState transitions

## Testing Scope

The frontend components assume:
1. **Backend ready**: POST /api/v1/approval/execute/{site_id} works ✅ (verified in Phase 170-02)
2. **Auth working**: Bearer token with role validation ✅ (ENGINEER, OPERATOR, ADMIN roles)
3. **SSE stream available**: `/api/events?correlation_id=...` endpoint exists (NOT YET TESTED)
4. **Device writes work**: Backend can dispatch to BMS ✅ (uses device_manager.write_value)

## What's NOT Yet Done

### Missing for Full Integration:

1. **SSE Event Stream Endpoint**
   - Need `/api/events` endpoint that filters by correlation_id
   - Should emit ExecutionEvent when telemetry verifies change
   - (Phase 170-03 responsibility)

2. **Polling Fallback**
   - useDecisionExecution has skeleton for polling on SSE error
   - Should query `/api/v1/approval/status/{decision_id}` periodically
   - (Optional — SSE preferred, but fallback good for robustness)

3. **Integration with Existing UI**
   - DecisionMoment needs to be wired into a page/dashboard
   - Currently standalone component (not integrated into OptimizationPage, ControlDashboard, etc.)
   - Decision source needs to be identified (optimization recommendations? operator-initiated commands?)

4. **End-to-End Test**
   - Need to run supervised execution on S002 test equipment
   - Verify: hold button → dispatch → telemetry confirms → UI updates
   - (Planned after SSE wiring complete)

## What to Do Next

### Immediate Next Steps:

1. **Wire the SSE stream** (Phase 170-03)
   - Implement `/api/events` endpoint with correlation_id filtering
   - Make it emit COMMAND_ACCEPTED, COMMAND_VERIFIED, COMMAND_TIMEOUT, COMMAND_FAILED
   - Test with a mock event first

2. **Run end-to-end supervised execution test**
   - Pick a S002 device (e.g., chiller or FCU)
   - Create a decision manually or via API
   - Dispatch via frontend, verify telemetry changes
   - Confirm UI state transitions correctly

3. **Integrate DecisionMoment into a control page**
   - Could add to ControlDashboard as a modal/panel
   - Or create a "Pending Approvals" page
   - Show list of pending decisions for operator approval

## Files Summary

| File | Purpose | Status |
|------|---------|--------|
| `src/lib/api/decision.ts` | Decision execution API types | ✅ Complete |
| `src/hooks/useDecisionExecution.ts` | Execution state management + SSE | ✅ Complete |
| `src/components/ApproveButton.tsx` | Hold-to-confirm button | ✅ Complete |
| `src/components/DecisionMoment.tsx` | Decision display + approval UI | ✅ Complete |
| `src/lib/api/index.ts` | API exports | ✅ Updated |

## Compilation Results

```
✓ TypeScript compilation successful (0 errors)
✓ Vite build successful (4518 modules)
✓ No type safety issues
✓ Frontend ready for integration
```

---

**Next: Wire Phase 170-03 telemetry verification and SSE stream**
