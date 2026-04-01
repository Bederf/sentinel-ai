# Subsystem
Signal drill-down — block booking detail panel and notification routing.

# Pain point
The panel was a signal log with duplicate time markers, raw content always visible, and no clear actions for the concierge, while the block booking workflow lacked inline Resolve/Archive controls.

# Candidate
Replace the timeline view with a metadata-focused layout that shows room, organiser, booking dates, risk, and short reason, hide raw content behind a toggle, and add Resolve/Archive buttons wired to `conciergeApi.resolveSignal` so the concierge can remove a block alert from the UI while recording status metadata.

# Metric
Specs covered by `src/components/intelligence/__tests__/ConciergeMap.test.tsx` which now exercises block action buttons, validates metadata grid layout, and ensures non-block signals still show the detailed timeline.

# Verify command
`npm run test:run -- src/components/intelligence/__tests__/ConciergeMap.test.tsx`

# Guard command
Same as above to ensure the non-block SignalDrillDown experience and data fetching remain stable.

# Writable scope
- `frontend/src/components/intelligence/SignalDrillDown.tsx`
- `frontend/src/lib/api.ts`
- `frontend/src/components/intelligence/__tests__/ConciergeMap.test.tsx`

# Debt risk
Moderate-to-high if the new panel spreads into unrelated logic, so the change must stay confined to the block booking branch and rely on existing API calls (no new abstractions or config).

# Recommendation
Proceed, because the panel now exposes actionable controls and metadata with limited scope. Continue to monitor for unnecessary branching.

# Iteration log
1. Drafted block-booking detail layout that highlights organiser, meeting metadata, and guard badge with Resolve/Archive buttons.
2. Tucked raw signal content behind a toggle and reused `conciergeApi.resolveSignal` with an optional note parameter.
3. Added test coverage verifying the new workflow and ensured non-block signals still use the prior detail view.

# Outcome
Pending: tests added but note should be updated after a manual guard check confirms block notifications still only route via email (guard command run as part of the unit test suite).

# Keep or discard
keep (pending guard confirmation)
