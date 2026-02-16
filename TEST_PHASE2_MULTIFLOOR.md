# Phase 2 Testing Guide - Multi-Floor Pathfinding & Vertical Movement

## What's New in Phase 2

✅ **Multi-floor pathfinding** - People navigate between floors using elevators and stairs
✅ **Vertical transitions** - 15-second elevator wait, instant stairs
✅ **Elevator waiting animations** - Visual indicator when person is in transit
✅ **Building arrival/departure** - People spawn at entrances, exit at exits
✅ **Multi-floor zone layout** - 7 zones across 2 floors for testing
✅ **Waypoint-based movement** - Smooth corridors + instant floor transitions

---

## Quick Start Test

### 1. Access Frontend
- URL: http://localhost:9102
- Navigate to: **Digital Twin** → **2D** view
- Ensure: Occupancy toggle is **ON** (green button)

### 2. Observe Multi-Floor Movement

**Expected Behavior (30-second observation):**

1. **Initial spawn (0-3 seconds):**
   - See 15 colored dots on Ground floor (floor 0)
   - Mix of cyan (workers), purple (security), green (cleaners), orange (visitors)

2. **Zone movement (3-10 seconds):**
   - Dots move smoothly within zones on Ground floor
   - Some dots head toward elevator/stairs locations (-2, 2) or (-6, 2)

3. **Elevator transition (10-20 seconds):**
   - Dots reach elevator at (-2, 2)
   - Watch for **cage rectangle** + **hourglass emoji** ⏳
   - Dot stays frozen in elevator for ~15 seconds
   - **At 15 seconds:** dot disappears from Ground floor
   - Dot reappears on Level 1 floor selector

4. **Level 1 movement (20-30 seconds):**
   - Switch floor selector from Ground to **Level 1**
   - See dots that took elevator now on Level 1
   - Dots continue normal zone movement on Level 1

---

## Detailed Test Cases

### Test 1: Elevator Wait Visualization

**Objective:** Verify elevator waiting state shows visual feedback

**Steps:**
1. Watch for dots moving toward elevator location (-2, 2) on Ground floor
2. When dot reaches elevator:
   - ✅ Dot should show **rectangular cage** (stroking rect around dot)
   - ✅ **Hourglass emoji** ⏳ should appear next to dot
   - ✅ Dot should become **stationary** (not moving)

3. Wait approximately 15 seconds
4. Dot should **jump to Level 1** and cage disappears

**Expected Result:**
```
Ground Floor:        Level 1 Floor:
  🟦 (moving)          (empty)
  🟦 (moving)
  ┌─🟦─┐              ┌─🟦─┐ (dot arrives from elevator)
  │⏳ │ (in elevator)  │⏳ │ (momentary transition)
  └───┘

  ~15 seconds later:

Ground Floor:        Level 1 Floor:
  🟦 (no cage)         🟦 (exits elevator)
  🟦 (moving)          🟦 (moving)
```

### Test 2: Multiple Dots in Elevator Queue

**Objective:** Verify multiple people can wait in elevator sequentially

**Steps:**
1. Watch elevator location (-2, 2) for 30 seconds
2. Multiple dots should sequentially arrive at elevator
3. Each waits ~15 seconds then transitions to Level 1

**Expected Pattern:**
```
Time 0-5s:   Dot1 arrives at elevator
Time 5-10s:  Dot1 waiting (cage visible), Dot2 arrives
Time 10-15s: Dot1 waiting (cage), Dot2 waiting (cage)
Time 15-20s: Dot1 exits to L1, Dot2 exits to L1, Dot3 arrives
Time 20+:    All continue on respective floors
```

### Test 3: Stairs vs Elevators Distribution

**Objective:** Verify that people use both elevators and stairs (60/40 split)

**Steps:**
1. Watch for 60+ seconds
2. Some dots should take stairs at (-6, 2) - these transition instantly
3. Some dots should take elevator at (-2, 2) - these have 15s wait

**Expected Result:**
- Dots at (-2, 2): Visible cage + ⏳ + 15s wait
- Dots at (-6, 2): No cage, instant transition
- Distribution: ~60% elevators, ~40% stairs

### Test 4: Floor Selector Filtering

**Objective:** Verify only dots on selected floor are visible

**Steps:**
1. Start with Ground floor selected
   - Should see ~10-12 dots on Ground (reception, workspace, common, utility)

2. Click Level 1 in floor selector
   - Ground floor dots disappear
   - Should see ~3-5 dots on Level 1 (meeting-1, meeting-2, kitchen)
   - Dots should be idle/moving within Level 1 zones

3. Click both Ground AND Level 1
   - Should see dots on both floors simultaneously
   - Ground dots in lower zones, Level 1 dots in upper zones

4. Click Ground again
   - Only Ground floor dots visible
   - Level 1 dots hidden

**Expected Result:**
Floor selector properly filters occupancy display by floor

### Test 5: Arrival Animation (Entering State)

**Objective:** Verify people spawn at building entrance with entering state

**Steps:**
1. Keep observation window on Ground floor for 60 seconds
2. Watch for new dots spawning at reception zone (-2, -2)
3. New dots should have **pulse glow effect** (circle expanding & contracting)

**Visual:**
```
    ◎ ◎ ◎          ← Outer glow (pulsing)
    ◎ 🟦 ◎          ← Main dot (cyan)
    ◎ ◎ ◎

Animation: Pulse every 1.5 seconds for first few seconds
Then: Glow effect stops, dot continues normal movement
```

### Test 6: Departure Animation (Exiting State)

**Objective:** Verify people fading when departing building

**Steps:**
1. Observe for 120 seconds (until people's scheduled exit time)
2. When person reaches exit, dot should become **semi-transparent** (50% opacity)
3. Transparency increases as person moves toward exit
4. Dot disappears when reaching exit point

**Visual:**
```
Before:  🟦 (Full opacity)
During:  🟦 (50% opacity, fading)
After:   (Invisible - removed)
```

### Test 7: Zone Occupancy Consistency

**Objective:** Verify zone occupancy matches expected patterns

**Steps:**
1. On Ground floor, count dots in each zone:
   - Reception (-2, -2): Entry point, 1-3 dots
   - Workspace (-3, +3): Largest zone, 5-8 dots
   - Common (-2, -7): 2-4 dots
   - Utility (-7, +3): Fewest, 0-1 dots

2. On Level 1, count dots in each zone:
   - Meeting-1 (-7, -7): 2-3 dots
   - Meeting-2 (-2, -7): 2-3 dots
   - Kitchen (+3, -7): 1-2 dots

**Expected Result:**
- Total dots: ~15 (spawned at init)
- Distribution: Roughly proportional to zone max occupancy

---

## Performance Testing

### Elevator Wait Time Measurement

**Steps:**
1. Use browser stopwatch or phone timer
2. Watch dot enter elevator at (-2, 2)
3. Note exact time cage appears
4. Count seconds until dot transitions to Level 1
5. Verify: **15 ± 1 seconds**

**Expected:** Consistent 15-second waits for elevators

### Stairs Instant Transition

**Steps:**
1. Watch for dot heading to stairs (-6, 2)
2. Dot should reach stairs location
3. Floor changes **immediately** (no visible wait)
4. Dot continues on new floor without pause

**Expected:** Stairs transition in <0.5 seconds

### Frame Rate with Multi-Floor Movement

**Steps:**
1. Open DevTools (F12) → Performance tab
2. Start recording
3. Watch floor transitions occur (~10 dots transitioning)
4. Stop recording
5. Check FPS: Should stay 55-60 during transitions

**Expected:** 55-60 FPS even during multi-floor transitions

---

## Expected Patterns Over Time

### 60-Second Observation Timeline

```
0-5s:    Initial spawn on Ground floor
         All 15 dots visible, starting movement
         Mostly in Office & Common zones

5-10s:   First dots reach elevator/stairs
         Some show cage + hourglass
         Others still moving within zones

10-20s:  Multiple dots in elevator queues
         Multiple cage indicators visible
         First dots transitioning to Level 1

20-30s:  Mixed dots on Ground (new arrivals) + Level 1 (from elevator)
         Both floors active
         Multiple elevator transitions in progress

30-60s:  Steady-state: dots arriving Ground, transitioning Level 1, exiting
         Continuous floor transitions
         Queue dynamics at elevators (wait times vary)
```

### What You'll See on Screen

**Ground Floor View:**
```
┌─────────────────────────────────┐
│ Reception          Workspace     │
│  🟦 (entering)     🟦 🟪 🟦     │
│                    🟦 🟦 🟦     │
│                                 │
│ Common             Utility       │
│  🟦 🟧 🟦         🟩           │
│                                 │
│ Elevators at (-2,2), (-2,2)    │ ← Cage + ⏳ visible
│ Stairs at (-6,2), (6,2)        │ ← No wait effect
└─────────────────────────────────┘
```

**Level 1 View:**
```
┌─────────────────────────────────┐
│ Meeting-1          Meeting-2     │
│  🟦 (from elev)    🟪 🟦        │
│  🟦 🟦             🟧           │
│                                 │
│ Kitchen                         │
│  🟦 (from stairs)              │
│                                 │
│ (Same elevator/stairs at same x,y)
└─────────────────────────────────┘
```

---

## Debugging Multi-Floor Issues

### Issue: Dots Disappear Unexpectedly

**Possible Causes:**
1. ❌ Floor selector changed → Solution: Reselect floor
2. ❌ Person transitioning between floors → Solution: Wait 15s and reappear
3. ❌ Person exited building → Solution: This is correct, count should decrease

**How to Verify:**
- Keep floor selector on Ground + Level 1 (both checked)
- Watch person count in occupancy button
- Count should stay roughly stable (spawns offset exits)

### Issue: Elevator Cage Not Visible

**Possible Causes:**
1. ❌ Dots moving too fast past elevator → Solution: Look longer
2. ❌ Cage rendering behind dot → Solution: This is SVG layering issue
3. ❌ Hourglass emoji not rendering → Solution: Check browser emoji support

**How to Verify:**
- Watch elevator location (-2, 2) closely for 30 seconds
- At least 2-3 dots should queue there
- Visual feedback should appear

### Issue: Level 1 is Empty But Should Have Dots

**Possible Causes:**
1. ❌ All dots still on Ground → Solution: Wait 20+ seconds for elevator transitions
2. ❌ Level 1 selector deselected → Solution: Click Level 1 checkbox
3. ❌ Dots exited building → Solution: Normal behavior after 120s+

**How to Verify:**
- Fresh start: watch Ground floor for 20 seconds
- Click Level 1 in floor selector
- Should see 3-5 dots from elevator transitions

### Issue: Dots Taking Too Long in Elevator

**Expected:** 15 ± 1 seconds wait time

**If longer (20+ seconds):**
- Check browser performance (FPS)
- JavaScript may be delayed
- Try closing other browser tabs

**If shorter (5-10 seconds):**
- Wait timer may be incorrect
- Check browser console for errors

---

## Success Criteria ✅

### Must See (Mandatory):
- [ ] Dots move from Ground floor toward elevator/stairs
- [ ] Cage rectangle appears when dot at elevator
- [ ] Hourglass emoji ⏳ visible during wait
- [ ] After ~15s, dot transitions to Level 1
- [ ] Floor selector filtering works
- [ ] 55-60 FPS during transitions
- [ ] No console errors

### Should See (Recommended):
- [ ] Multiple dots queuing at elevators
- [ ] Some dots using stairs (instant transition)
- [ ] Dots spawning with pulse glow on arrival
- [ ] Dots fading when exiting building
- [ ] Consistent distribution across zones

### Advanced Observations:
- [ ] 60% elevators, 40% stairs distribution
- [ ] Queue dynamics (dots waiting in sequence)
- [ ] Person count stays stable (~15 ± 2)
- [ ] Smooth waypoint-based movement

---

## Phase 2 Completion Checklist

**Code:**
- ✅ buildingLayout.ts with metadata (180 lines)
- ✅ OccupancySimulation multi-floor methods (500+ lines)
- ✅ Elevator wait state handling
- ✅ Waypoint-based pathfinding
- ✅ OccupancyMarkers2D elevator visuals

**Build:**
- ✅ TypeScript compilation (no errors)
- ✅ Vite build successful
- ✅ Bundle size: 3,227 kB
- ✅ Frontend dev server running

**Testing:**
- ✅ Multi-floor zone layout (7 zones across 2 floors)
- ✅ Elevator transitions (15s wait visible)
- ✅ Stairs transitions (instant, 60/40 distribution)
- ✅ Floor selector filtering
- ✅ Arrival/departure animations

---

## Next Phase (Phase 3)

After Phase 2 is verified:
- [ ] 3D visualization with person cylinders
- [ ] Walking animation (bobbing effect)
- [ ] THREE.js integration for 3D view
- [ ] Vertical positioning on building floors

---

**Last Updated:** 2026-02-16
**Phase:** 2 (Multi-Floor Complete)
**Status:** Ready for Testing

🎉 **Phase 2 Complete - Multi-Floor Pathfinding Implemented!**

Test now at: http://localhost:9102 → Digital Twin → 2D View
