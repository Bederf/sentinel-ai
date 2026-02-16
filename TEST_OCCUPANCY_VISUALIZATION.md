# Occupancy Visualization Test Guide - Phase 1

## Quick Start

### Access the Frontend
- **URL:** http://localhost:9102 (or http://localhost:9096-9101 if 9102 is taken)
- **Backend:** http://localhost:9095 (API, should be running)
- **Expected:** Dashboard loads by default

### Navigate to Digital Twin
1. Click **"Digital Twin"** in the left sidebar
2. You should see the 3D building visualization by default

---

## Testing Occupancy Dots

### Test 1: Toggle Occupancy Display (2D View)

**Steps:**
1. In the Digital Twin header, click the **"2D"** button to switch to 2D floor plan view
2. You should see:
   - ✅ SVG floor plan with zones
   - ✅ Equipment markers (equipment-colored dots)
   - ✅ **Occupancy Toggle Button** in the top-right controls (person icon + "Occupancy" label)

3. Click the **"Occupancy"** toggle button
4. You should see:
   - ✅ Button turns **green** (active state)
   - ✅ **Animated colored dots** appear on the floor plan (overlaid on zones)
   - ✅ **Person counter** shows in the button: e.g., "Occupancy (12)"

**Expected Occupancy Dot Behaviors:**
- 🟦 **Cyan dots** = Workers (majority, moving smoothly)
- 🟪 **Purple dots** = Security (fewer, patrolling corridors)
- 🟩 **Green dots** = Cleaners (few, only after hours - currently should be none unless time is 6pm+)
- 🟧 **Orange dots** = Visitors (office hours only - currently should be few unless time is 10am-4pm)

### Test 2: Dot Movement Animation

**Steps:**
1. Keep the occupancy toggle **ON**
2. Watch the dots for **10-15 seconds**

**Expected Behavior:**
- ✅ Dots **move smoothly** within their zones (NOT teleporting, NOT static)
- ✅ Movement is **60fps smooth** (no jank or stuttering)
- ✅ Each dot picks a random destination within its zone
- ✅ When dot reaches destination, it pauses briefly, then picks a new target
- ✅ Some dots move more frequently than others (persona-based)
- ✅ Security (purple) should move more frequently than workers

### Test 3: Persona Colors & Count

**Steps:**
1. In the occupancy toggle, hover over the person count: e.g., "(15)"
2. Take mental note of dot colors

**Expected Distribution (Phase 1 - Random):**
- Majority should be cyan (workers) - ~70-80%
- Some purple (security) - ~10-20%
- Few green (cleaners) - ~5-10% (only after 6pm)
- Few orange (visitors) - ~5-10% (only 10am-4pm)

### Test 4: Floor Filtering

**Steps:**
1. On the left side of the 2D view, find the **Floor Selector** panel (shows floor buttons)
2. Click to select different floors

**Expected Behavior:**
- ✅ Floor ground/L0 should show dots in reception, workspace, common areas
- ✅ Floor L1 should show dots in meeting rooms, kitchens, servers
- ✅ Switching floors should **instantly update** the visible dots
- ✅ Dots don't appear on unselected floors

### Test 5: Occupancy Overlay on Equipment

**Steps:**
1. In 2D mode with occupancy enabled, rotate/pan the floor plan
2. Look at where occupancy dots are positioned

**Expected Behavior:**
- ✅ Dots should overlay on top of equipment markers (but not hide them)
- ✅ Dots have a **glow effect** (subtle drop shadow)
- ✅ Dots are semi-transparent when in "exiting" state (leaving building)

### Test 6: 3D View Occupancy (Phase 3 - Not Yet Implemented)

**Steps:**
1. Click the **"3D"** button to switch back to 3D
2. Click "Occupancy" toggle (should still be on)

**Expected Behavior (Phase 3):**
- Currently: No visible occupancy in 3D (dots are on 2D layer only)
- After Phase 3: Should see 3D cylinders (person meshes) moving through building

---

## Debugging Checklist

If dots don't appear:

### ✅ Check 1: Is Occupancy Enabled?
- Look for green "Occupancy" button with person count
- If button is gray, click to toggle it on

### ✅ Check 2: Are There Dots But They're Not Moving?
- Dots might be static in initial spawn zones
- Wait 10-15 seconds - movement should start
- Check browser DevTools Console (F12) for errors

### ✅ Check 3: Are Dots Visible But Very Small?
- They should be ~10px diameter circles
- If you see tiny specks, zoom in on the floor plan

### ✅ Check 4: Frontend Console Errors
- Press **F12** to open DevTools
- Click **"Console"** tab
- Look for red error messages
- Common issues:
  - ❌ `OccupancySimulation is not a constructor` → Import issue
  - ❌ `Cannot read property 'tick' of null` → Simulation not initialized
  - ❌ `Expected 5 arguments but got 4` → Type mismatch (check ZoneConfig)

### ✅ Check 5: Network Issues
- Backend should be running (check http://localhost:9095/health)
- Frontend should be serving (check http://localhost:9102)

---

## Performance Testing

### Frame Rate Check
1. Press **F12** to open DevTools
2. Press **Ctrl+Shift+P** and type "Rendering"
3. Select **"Show rendering settings"**
4. Enable **"FPS meter"**
5. Watch occupancy dots move and check FPS counter

**Expected Performance:**
- ✅ **60 FPS** with 15 dots (Phase 1 scale)
- ✅ Smooth animation with no drops below 55 FPS
- ⚠️ May drop to 30-45 FPS if 100+ dots (will optimize in Phase 2)

---

## Data Flow Verification

### OccupancySimulation Engine Status
```
DigitalTwin.tsx
  ├── Initialize OccupancySimulation(defaultZones)
  ├── Spawn 15 initial people (random personas)
  ├── Start 60fps animation loop
  │   └── Each frame: simulation.tick(deltaTime)
  │       ├── Update person positions
  │       ├── Pick new destinations
  │       └── Return updated people array
  ├── Set people state (triggers re-render)
  └── Pass people to FloorPlan2D + DigitalTwinVisualization
      └── OccupancyMarkers2D renders SVG dots
```

### Files Involved
- ✅ `/frontend/src/lib/occupancySimulation.ts` - Core engine
- ✅ `/frontend/src/components/digital-twin/OccupancyMarkers2D.tsx` - 2D rendering
- ✅ `/frontend/src/components/digital-twin/DigitalTwin.tsx` - Integration
- ✅ `/frontend/src/components/digital-twin/FloorPlan2D.tsx` - 2D view with overlay
- ✅ `/frontend/src/lib/occupancyZones.ts` - Zone config (fallback data)

---

## Expected Results by View

### 2D Floor Plan (SVG)
```
┌─────────────────────────────────┐
│  Digital Twin       [3D] [2D] ★ │  ← Occupancy toggle (★ = active)
├─────────────────────────────────┤
│                                 │
│  Zone 1 (Reception)    Zone 2   │
│   🟦 🟦  (Reception)    🟦🟦🟦  │
│      🟨 (Equipment)              │
│                                 │
│  Zone 4 (Common)   Zone 5 (Util)│
│   🟪              🟩            │
│   🟦                            │
└─────────────────────────────────┘
Dots:
  🟦 = Cyan (Workers)
  🟪 = Purple (Security)
  🟩 = Green (Cleaners)
  🟧 = Orange (Visitors)
  🟨 = Equipment markers
```

### 3D Building (Currently No Occupancy - Phase 3)
- Equipment markers visible ✅
- Occupancy dots NOT visible yet (deferred to Phase 3)

---

## Phase 1 Limitations (by Design)

❌ **Not Yet Implemented:**
- Multi-floor vertical movement (coming Phase 2)
- Building entry/exit animations (coming Phase 2)
- Elevator transitions (coming Phase 2)
- 3D person meshes (coming Phase 3)
- Backend time sync (coming Phase 4)
- Time-based occupancy patterns (coming Phase 4)

✅ **Working in Phase 1:**
- Zone-level movement
- 4 persona types with different speeds
- Smooth 60fps animation
- Toggle on/off
- 2D visualization overlay
- Color coding by persona

---

## Success Criteria ✅

If you see **ALL** of these, Phase 1 is working correctly:

- [ ] Frontend loads on http://localhost:9102
- [ ] "Digital Twin" page accessible
- [ ] "2D" view shows floor plan with zones
- [ ] "Occupancy" button visible and toggleable
- [ ] Clicking Occupancy shows colored dots
- [ ] Dots move smoothly within zones
- [ ] Dots have correct colors (cyan/purple/green/orange)
- [ ] Person counter shows in button
- [ ] No console errors in DevTools
- [ ] FPS meter shows 55-60 FPS
- [ ] Switching floors updates visible dots
- [ ] Backend API responding (http://localhost:9095/health)

---

## Troubleshooting Quick Links

| Issue | Solution |
|-------|----------|
| No dots visible | Check DevTools Console for errors, ensure Occupancy toggle is ON |
| Dots not moving | Wait 10-15 seconds, check FPS meter for stuttering |
| Static dots forever | Check browser console - may be infinite loop, restart frontend |
| Wrong dot colors | Check PERSONAS config in occupancySimulation.ts (cyan/purple/green/orange) |
| Console errors | Read error carefully, check file names and import paths |
| Port already in use | Frontend will auto-increment port (9102, 9103, etc) |

---

## Next Testing Phase (Phase 2-4)

After Phase 1 is verified:
- [ ] Phase 2: Test multi-floor pathfinding (dots moving between floors)
- [ ] Phase 3: Test 3D person meshes in 3D view
- [ ] Phase 4: Test backend sync with Grant DALI scenario

---

**Last Updated:** 2026-02-16
**Version:** 1.0 (Phase 1 Complete)
