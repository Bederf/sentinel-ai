# Subsystem
Concierge intelligence map – secondary category circle layout plus block signal drag behavior.

# Pain point
Secondary circles currently showed mix of numbers and labels, overlapped parent nodes when rooms moved, and block signals could not be dismissed without a custom API call. The UI lacked a mechanical metric to ensure the behavior was bounded.

# Candidate
Ensure primary room circles display room names/optional counts, secondary circles only ever show the labels Ghost/Info/Block, secondary nodes expand outward away from the parent, and dragging a Block circle onto its parent resolves that signal with the POST `/api/concierge/rooms/{site}/{room}/signals/{signal}/resolve` call.

# Metric
`src/components/intelligence/__tests__/ConciergeMap.test.tsx` passes, covering the new label-only rendering, outward expansion, and block-drag resolution (the test also verifies the SignalDrillDown block actions).

# Verify command
`npm run test:run -- src/components/intelligence/__tests__/ConciergeMap.test.tsx`

# Guard command
Same `npm run test:run ...` to guard against regressions in block routing (keeps the email/resolution path intact) and to ensure SignalDrillDown/Beacon detail still renders for non-block signals.

# Writable scope
- `frontend/src/components/intelligence/ConciergeMap.tsx`
- `frontend/src/components/intelligence/SignalDrillDown.tsx`
- `frontend/src/lib/api.ts`
- `frontend/src/components/intelligence/__tests__/ConciergeMap.test.tsx`

# Debt risk
Moderate: added extra layout math, label sizing helpers, and custom drag-to-remove state, which increases complexity if it drifts beyond this isolated change.

# Recommendation
Keep and measure via the `ConciergeMap` unit test, since the UI change is narrowly scoped and the additional logic is contained inside the same component.

# Iteration log
1. Reworked `buildRoomNodes`/`buildChildElements` to compute label sizes, enforce Ghost/Info/Block labels, and position children outward without overlapping the parent circle.
2. Added API helper edit plus new drag-to-parent logic for block signals, supporting visual confirmation before removal.
3. Updated the block detail panel/output in `SignalDrillDown` along with tests so the change has automated verification.

# Outcome
Metric satisfied (tests pass); block drag-to-parent now resolves single signal cleanly and secondary nodes only render the allowed labels. Keep.

# Keep or discard
keep
