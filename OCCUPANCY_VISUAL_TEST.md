# Occupancy Dots Visual Test - What You Should See

## Screen Layout

```
┌──────────────────────────────────────────────────────────────────┐
│  SENTINEL BMS Intelligence                          🔔 👤 ⚙️   │
├──────────────────────────────────────────────────────────────────┤
│ Digital Twin  📌                                                  │
├──────────────────────────────────────────────────────────────────┤
│ Building: [site-002 ▼]  ALL EQUIPMENT (23)  [3D] [2D] [Occupancy]│
│                                                                  ▼│
│                                                                  +│
├──────────────────────────────────────────────────────────────────┤
│                                                                   │
│   FLOOR SELECTOR (Left)         2D FLOOR PLAN (Center)           │
│   ┌─────────────┐              ┌─────────────────────┐          │
│   │ ☑ Ground(L0)│              │ RECEPTION           │          │
│   │ ☐ Level 1(L1)              │ 🟦 🟦 🟨            │          │
│   │ ☐ Level 2(L2)              │                     │          │
│   │ ☐ Roof(R)   │              │ WORKSPACE-A    L0   │          │
│   └─────────────┘              │ 🟪 🟦🟦 🟨 🟦      │          │
│                                 │                     │          │
│ Legend (SVG):                   │ COMMON      UTILITY  │          │
│ ● Green (60%+)                  │ 🟦         🟩     │          │
│ ● Yellow (30-60%)               │                     │          │
│ ● Red (<30%)                    │                     │          │
│                                 └─────────────────────┘          │
│                                    EQUIPMENT PANEL              │
│                                    (Right, minimized)            │
└──────────────────────────────────────────────────────────────────┘

Legend:
  🟦 = Cyan dot (Worker)
  🟪 = Purple dot (Security)
  🟩 = Green dot (Cleaner)
  🟧 = Orange dot (Visitor)
  🟨 = Yellow equipment marker
  ☑ = Floor selected
  ☐ = Floor not selected
```

## Occupancy Toggle Button

### INACTIVE (Before Clicking)
```
┌──────────────────────────────────────────┐
│ [3D] [2D] [👤 Occupancy]                 │
│                 ▲
│                 Gray button = OFF
│                 No person count shown
```

### ACTIVE (After Clicking)
```
┌──────────────────────────────────────────┐
│ [3D] [2D] [👤 Occupancy (15)]            │
│                 ▲
│                 Green button = ON
│                 Shows person count (15 = 15 dots visible)
```

## Dot Animation Sequence

### Second 0-2: Initial Spawn
```
Reception Zone:
  🟦 (spawned at center)
  🟦 (spawned at center)
  🟦 (spawned at center)

Workspace Zone:
  🟪 (patrol dot spawned)
  🟦 (worker spawned)
  🟦 (worker spawned)
```

### Second 3-5: Movement Starts
```
Reception Zone:
  🟦 ─→ (moving to target 1)
  🟦 ─→ (moving to target 2)
  🟦      (at rest)

Workspace Zone:
  🟪 ⟳ (patrolling)
  🟦 ─→ (moving)
  🟦 ─→ (moving)
```

### Second 6-10: Random Destination Changes
```
Reception Zone:
  🟦      (paused at target 1)
  🟦 ─→ (moving to new target)
  🟦      (at rest)

Workspace Zone:
  🟪 ─→ (continuous patrol)
  🟦 ─→ (moving)
  🟦      (paused)
```

### Continuous (Every 10-20 sec): Full Movement Cycle
```
Each dot cycles:
  1. Move to random point in zone (1-3 seconds)
  2. Pause briefly at destination (0.5-2 seconds)
  3. Pick new target and repeat

Security (🟪): Moves MORE FREQUENTLY (70% movement)
Worker (🟦):   Moves LESS FREQUENTLY (30% movement)
```

## State-Based Visual Changes

### IDLE State (Stationary Dot)
```
🟦 (Cyan dot, solid, at rest)
  No glow effect
  No dashed line to target
```

### MOVING State (Active Dot)
```
🟦─ - - -→ 🎯 (Cyan dot with dashed path line)
  ↑            ↑
  Current pos  Target position

Smooth CSS transition over 0.3 seconds
```

### ENTERING State (Arriving at Building)
```
    ◎ ◎ ◎          ← Outer glow circle
    ◎ 🟦 ◎          ← Main dot (cyan)
    ◎ ◎ ◎

Pulse animation: r = 7 → 10 → 7 (1.5 sec cycle)
Opacity: 0.4 → 0.1 → 0.4
```

### EXITING State (Leaving Building)
```
🟦 (Semi-transparent, 50% opacity)

Dashed path line visible to exit point
After reaching exit: dot disappears entirely
```

## Tooltip on Hover

Position mouse over any dot:
```
┌──────────────────┐
│ WORKER           │ ← Persona type (uppercase)
│ Zone: zone-2     │ ← Current zone assignment
└──────────────────┘
```

## Performance Metrics

### FPS Counter (DevTools)
With 15 dots on Ground Floor:
```
┌──────────┐
│ ⚡ 60 FPS │ ← Smooth green indicator
│ (or 59)  │   Usually stays 55-60 FPS
└──────────┘
```

## Floor Switching Behavior

### Switching FROM Ground to Level 1
```
BEFORE: Dots visible in Reception, Workspace, Common, Utility
↓ (click Ground checkbox to deselect)
AFTER:  Dots immediately disappear from 2D view
↓ (click Level 1 checkbox to select)
NEW:    Dots appear in Meeting rooms, Server, Kitchen zones

NOTE: Transition is instant (no animation)
```

## Occupancy Counter Update

### Manual Count Verification
```
Button shows:   [👤 Occupancy (15)]
Your count:     Count dots on screen = 15
Match:          ✅ YES = Working correctly
                ❌ NO = Check for spawning/despawning logic
```

## Common Visual Issues & Fixes

### Issue: Dots appear as TINY SPECKS
```
Solution: Zoom into floor plan using browser zoom (Ctrl++)
Result: Dots should be ~5-10mm diameter circles
```

### Issue: Dots DON'T MOVE (frozen in place)
```
Possible causes:
1. occupancyEnabled toggle is OFF (button is gray)
   → Solution: Click to turn on (button turns green)

2. JavaScript error in console
   → Solution: Check F12 Console tab, fix error

3. Animation loop not running
   → Solution: Check that tick() is called in useEffect
```

### Issue: Dots BLINK/DISAPPEAR randomly
```
Possible causes:
1. Floor selector has no floors selected
   → Solution: Click "Ground" floor to select it

2. Dots are transitioning between floors (Phase 2 not yet ready)
   → Solution: This is normal in Phase 1, only zone-level movement
```

### Issue: All dots are SAME COLOR
```
Expected: Mix of cyan (70%), purple (15%), green/orange (15%)
If all cyan: Check PERSONAS config in occupancySimulation.ts
Verify: spawnPersonInZone() selects random persona types
```

### Issue: Too many or too FEW dots
```
Expected:    ~15 dots total in Phase 1 (5 zones × 3 per zone average)
If 0 dots:   Occupancy toggle is OFF
If 5 dots:   Check spawnPerson() loop count in DigitalTwin.tsx (line 168)
If 50+ dots: Check that reconciliation isn't creating duplicates
```

## Successful Test Checklist ✅

After 30 seconds of observation, you should see:

```
Dots Visible:
  ✅ Mix of cyan, purple, green, orange dots
  ✅ All dots have glow effect (drop shadow)
  ✅ Dot count matches button label

Movement:
  ✅ Dots moving smoothly (no jerky teleports)
  ✅ Different speeds (security faster than workers)
  ✅ Each dot pauses briefly at destinations
  ✅ Dashed path lines showing movement direction

Interaction:
  ✅ Toggle button works (on/off)
  ✅ Person count updates correctly
  ✅ Floor selector filters dots
  ✅ Hovering shows tooltip

Performance:
  ✅ FPS meter shows 55-60 FPS
  ✅ No stuttering or lag
  ✅ Smooth animations throughout
```

## Before Reporting Issues

1. ✅ Frontend dev server is running (http://localhost:9102)
2. ✅ Backend is running (http://localhost:9095)
3. ✅ You clicked the Occupancy toggle (button is GREEN)
4. ✅ You selected at least one floor in Floor Selector
5. ✅ You waited 5 seconds for dots to initialize and start moving
6. ✅ You opened DevTools Console (F12) and checked for errors
7. ✅ You tried on a different floor (if dots not visible)

---

**Phase 1 Complete!** 🎉

Dots should be animated and moving smoothly within their zones.
Multi-floor movement and 3D visualization coming in Phases 2-3.

---

**Last Updated:** 2026-02-16
**Version:** Phase 1 (Core Engine Complete)
