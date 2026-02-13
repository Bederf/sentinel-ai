# CLAUDE.md Reduction Plan

**Target:** Reduce from 75.4k chars to ~20k chars by extracting large sections into focused docs

## Sections to Extract (with estimated char counts)

| Section | Current Chars | New File | Keep in CLAUDE.md |
|---------|--------------|----------|------------------|
| Approval Workflow (Tier 2) | ~7,500 | `docs/APPROVAL_WORKFLOW.md` | ✓ 300-word summary + link |
| Peak Demand Management | ~6,800 | `docs/PEAK_DEMAND_COORDINATION.md` | ✓ 200-word summary + link |
| Equipment Baseline Diagnostic | ~8,200 | `docs/EQUIPMENT_BASELINE_WORKFLOW.md` | ✓ 300-word summary + link |
| Naming Conventions (Two-Tier) | ~5,500 | `docs/EQUIPMENT_NAMING.md` | ✓ Quick reference only |
| Digital Twin & Zones | ~3,200 | `docs/DIGITAL_TWIN_ARCHITECTURE.md` | ✓ 200-word summary + link |
| Patterns & Constraints | ~4,100 | `docs/DEVELOPMENT_PATTERNS.md` | ✓ Keep essentials (Async, TypeScript, DB) |
| Debugging Scenarios | ~2,400 | `docs/DEBUGGING_GUIDE.md` | ✓ Link to full guide |

## New CLAUDE.md Structure (target: ~20k chars)

1. **Project Overview** (unchanged) - 300 chars
2. **Quick Reference** (unchanged) - 1,500 chars
3. **Setup** (keep concise) - 1,200 chars
4. **Architecture** (overview only) - 1,500 chars
5. **Key Design Patterns** (summaries + links):
   - Device Abstraction Layer - 200 chars
   - Safety System - 200 chars
   - Approval Workflow - 300 chars + `→ See docs/APPROVAL_WORKFLOW.md`
   - Peak Demand Management - 200 chars + `→ See docs/PEAK_DEMAND_COORDINATION.md`
   - AI Recommendations System - 300 chars
   - React Query - 200 chars
6. **Configuration** (keep) - 1,200 chars
7. **Key Services & Files** (keep) - 800 chars
8. **Frontend TypeScript** (keep essentials) - 600 chars
9. **Naming Conventions** (quick ref only) - 600 chars
10. **Important Patterns** (essentials only) - 1,200 chars
11. **Code Organization Rules** (keep) - 500 chars
12. **When You Get Stuck** (restructured):
    - API & Backend issues - 300 chars
    - Frontend & TypeScript - 300 chars
    - Database & Supabase - 300 chars
    - Quick Links to Detailed Docs - 500 chars

## Action Items

1. ✅ Create `docs/APPROVAL_WORKFLOW.md` - Move full Tier 2 details
2. ✅ Create `docs/PEAK_DEMAND_COORDINATION.md` - Move full coordination details
3. ✅ Create `docs/EQUIPMENT_BASELINE_WORKFLOW.md` - Move Gen Set 5 full workflow
4. ✅ Create `docs/EQUIPMENT_NAMING.md` - Move Two-Tier system
5. ✅ Create `docs/DIGITAL_TWIN_ARCHITECTURE.md` - Move zone positioning
6. ✅ Create `docs/DEVELOPMENT_PATTERNS.md` - Move async/TypeScript/DB patterns
7. ✅ Create `docs/DEBUGGING_GUIDE.md` - Move debugging scenarios
8. ✅ Rewrite CLAUDE.md with links to new docs
9. ✅ Update memory about restructuring

## Files Created
- docs/APPROVAL_WORKFLOW.md ✓
- docs/PEAK_DEMAND_COORDINATION.md ✓
- docs/EQUIPMENT_BASELINE_WORKFLOW.md ✓
- docs/EQUIPMENT_NAMING.md ✓
- docs/DIGITAL_TWIN_ARCHITECTURE.md ✓
- docs/DEVELOPMENT_PATTERNS.md ✓
- docs/DEBUGGING_GUIDE.md ✓
