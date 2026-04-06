---
title: "DALI Intelligence Dashboard - Implementation Checklist"
type: "spec"
status: "draft"
version: "1.0.0"
created: "2026-03-31"
updated: "2026-03-31"
tags: ["sentinel", "documentation"]
related: []
domain: "lighting"
audience: "all"
complexity: "intermediate"
estimated_read_time: 10
---

# DALI Intelligence Dashboard - Implementation Checklist

## Status: 90% Complete ✅

### ✅ COMPLETED (Ready to Use)

#### Backend Implementation
- [x] **Simulation Engine** (`backend/app/api/dali.py`)
  - 365-day physics-based simulation
  - 3 scenarios: Baseline, With DALI, With SENTINEL AI
  - ML learning curve (60% → 95%)
  - Solar geometry, weather patterns, occupancy models
  - API endpoint: `GET /api/dali/simulation?site_id={site_id}`

- [x] **Router Registration** (`backend/app/api/registrars/building.py`)
  - Router configured with `/api/dali` prefix
  - Endpoint accessible at: `/api/dali/simulation`

#### Frontend Components
- [x] **DALI Panel Component** (`frontend/src/components/DaliIntelligencePanel.tsx`)
  - Hero metrics cards (3 metrics with color coding)
  - Cumulative savings area chart (Recharts)
  - Monthly comparison bar chart (12 months seasonal variation)
  - Breakdown cards (occupancy + daylight savings)
  - Educational callout
  - Loading spinner with graceful error handling
  - Responsive design (mobile/tablet/desktop)

- [x] **Card Definition** (`frontend/src/lib/cardDefinitions.tsx`)
  - Card registered in SECTION_CARDS as `lighting-intelligence`
  - Lightbulb icon imported and configured
  - defaultVisible: true (shows by default)
  - Category: 'section' (dashboard section, not KPI)

- [x] **Building Overview Integration** (`frontend/src/components/SiteDetail.tsx`)
  - LightingIntelligencePanel rendered as card #8 in overview
  - Gated by `isModuleActive('lighting')` and `visibleSections.includes('lighting-intelligence')`
  - Toggleable via inline CardLibrary

### ⏳ REMAINING (Manual Step)

#### Dashboard Integration
- [ ] **Update DashboardSectionId Type** (line ~80)
  ```typescript
  Add:  | 'dali-intelligence'
  After:  | 'site-protection'
  ```

- [ ] **Add Render Function** (before renderRiskPredictions)
  ```typescript
  const renderDaliIntelligence = () => (
    <DashboardSection id="dali-intelligence">
      <div className="mt-6">
        <DaliIntelligencePanel siteId="site-002" />
      </div>
    </DashboardSection>
  );
  ```

- [ ] **Update sectionRenderers Map** (line ~1650)
  ```typescript
  Add:  'dali-intelligence': renderDaliIntelligence,
  After:  'site-protection': renderSiteProtection,
  ```

- [ ] **Update Default sectionOrder** (line ~130)
  ```typescript
  Add:  'dali-intelligence',
  After:  'site-protection',
  ```

---

## Quick Start (If using VS Code with Serena)

### Option 1: Let Serena Complete the Integration
```
Ask Claude: "Complete the DALI dashboard integration in Dashboard.tsx -
update the DashboardSectionId type, add the renderDaliIntelligence
function, and register it in sectionRenderers and sectionOrder."
```

### Option 2: Manual Integration (5 minutes)

1. **Open:** `frontend/src/components/Dashboard.tsx`

2. **Find Line ~80:** `type DashboardSectionId =`
   - Add `| 'dali-intelligence'` after `| 'site-protection'`

3. **Find Line ~1000:** `const renderEnergyComparison = () =>`
   - Add new function AFTER this:
   ```typescript
   const renderDaliIntelligence = () => (
     <DashboardSection id="dali-intelligence">
       <div className="mt-6">
         <DaliIntelligencePanel siteId="site-002" />
       </div>
     </DashboardSection>
   );
   ```

4. **Find Line ~1650:** `const sectionRenderers: Record<Dashboard...`
   - Add `'dali-intelligence': renderDaliIntelligence,` after `'site-protection': renderSiteProtection,`

5. **Find Line ~130:** `const [sectionOrder, setSectionOrder]`
   - Add `'dali-intelligence',` after `'site-protection',`

6. **Save & Test:**
   ```bash
   npm run build
   npm run dev
   ```

---

## Testing

### Backend Verification
```bash
# Test the API endpoint
curl http://localhost:9095/api/dali/simulation?site_id=site-002

# Expected: JSON with 3 keys
# - summary: annual costs, savings, metrics
# - daily_data: 122 entries (every 3rd day)
# - monthly_data: 12 entries (monthly breakdown)
```

### Frontend Verification
1. Start services:
   ```bash
   # Terminal 1
   cd backend && DEMO_MODE=true python -m uvicorn app.main:app --reload --port 9095

   # Terminal 2
   cd frontend && npm run dev
   ```

2. Open http://localhost:9096
3. Scroll dashboard - DALI card should appear after "Site Protection Status"
4. Card should show:
   - Loading spinner (1-2 seconds)
   - Then 3 hero metrics
   - Area chart with 3 diverging lines
   - Bar chart with 12 months
   - 2 breakdown cards

5. Click "Customize" button (top right):
   - Find "DALI Intelligence: Tridonic"
   - Toggle on/off
   - Verify it appears/disappears on dashboard

---

## Files Summary

### New Files (2)
| File | Size | Purpose |
|------|------|---------|
| `backend/app/api/dali.py` | 550 lines | Simulation engine + endpoint |
| `frontend/src/components/DaliIntelligencePanel.tsx` | 400 lines | Dashboard card component |

### Modified Files (4)
| File | Changes | Impact |
|------|---------|--------|
| `backend/app/api/registrars/building.py` | +1 line | Register router |
| `frontend/src/components/Dashboard.tsx` | +1 line import | Import component |
| `frontend/src/lib/cardDefinitions.tsx` | +1 icon, +8 lines | Register card definition |
| (Dashboard.tsx manual) | +4 edits | Type, function, map, order |

### Documentation (2)
| File | Purpose |
|------|---------|
| `docs/DALI_INTELLIGENCE_IMPLEMENTATION.md` | Complete technical doc |
| `DALI_IMPLEMENTATION_CHECKLIST.md` | This checklist |

---

## Success Criteria

- [ ] Backend API returns data in <2 seconds
- [ ] Frontend component loads with spinner
- [ ] Hero metrics display: R80k saved, 44% reduction, 92% accuracy
- [ ] Area chart shows 3 diverging lines (365 days)
- [ ] Bar chart shows 12 months with seasonal variation
- [ ] Breakdown cards show occupancy + daylight savings
- [ ] Card toggles on/off via Card Library
- [ ] No console errors
- [ ] Responsive on mobile (tested at 375px width)
- [ ] Grant can demonstrate to customers

---

## Rollback Plan

If something breaks:
1. Remove `dali-intelligence` from `sectionOrder`
2. Comment out `renderDaliIntelligence` function
3. Remove from `sectionRenderers` map
4. Remove from `DashboardSectionId` type
5. Remove import line (or leave it - no harm)
6. Restart frontend

Dashboard will work normally without DALI card.

---

## Support

For issues:
1. Check `docs/DALI_INTELLIGENCE_IMPLEMENTATION.md` for technical details
2. Verify backend is running: `curl http://localhost:9095/api/dali/simulation`
3. Check browser console (F12) for errors
4. Check terminal logs for backend errors

---

**Status:** ✅ 90% Complete - Ready for Final Integration
**Estimated Time to Complete:** 5 minutes (manual) or instant (Serena)
**Owner:** Grant Demo
**Target Completion:** Today
