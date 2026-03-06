# Digital Twin & Zones Architecture

**Unified Zone-Based Positioning System**

**See CLAUDE.md for quick reference. This document covers full architectural details.**

## Zone Structure (Supabase)

- **zones table**: 15 zone records with numeric IDs (001-005, 100-104, 200-204)
- **Desk distribution**: 100 desks/floor × 5 zones = 20 desks per zone
- **Zone centroids**: Auto-calculated from desk positions, exposed via `zone_centroids` view
- **Building structure (site-002):** Ground (L0), Level 1 (L1), Level 2 (L2) — NOT legacy L10/L11/L12

## Desk Positioning (Supabase)

- **desks table**: 300 desks with numeric IDs (Desk-001 to Desk-301)
- **Coordinates**: Each desk has `x_coord`, `z_coord` for 3D positioning
- **Zone reference**: Each desk references its zone via `zone_id` (e.g., Zone-001, Zone-101)
- **Naming encodes floor**: Desk-045 is L0, Desk-150 is L1, Desk-250 is L2

## Equipment Allocation

- **Equipment codes** reference zones numerically (e.g., S002-VAV-101 is in Zone-101)
- **Zone mapping**: Standardized via `dali_zone_mapping` table (legacy DALI zones → modern zones)
- **Equipment positioning**: Uses desk coordinates within zones for accurate 3D placement

## Digital Twin Components

### Main Orchestrator
- **Frontend:** `components/digital-twin/DigitalTwin.tsx`
  - Main container managing view state, floor filters, equipment selection
  - Toggles between 2D and 3D views with state synchronization
  - Handles all UI events and data refetching

### 2D Visualization
- **Frontend:** `components/digital-twin/FloorPlan2D.tsx`
  - SVG-based floor plan rendering
  - Draws desk layouts and zone boundaries
  - Equipment markers positioned on 2D plane (x, z coordinates)
  - Click handlers for equipment selection

### 3D Visualization
- **Frontend:** `components/digital-twin/EquipmentMarkers.tsx`
  - React Three Fiber component
  - 3D mesh renderings of equipment at calculated positions
  - Camera controls for navigation
  - Interactive selection via raycasting

### View Controls
- **Frontend:** `components/digital-twin/ViewToggle.tsx`
  - Button to switch between 2D/3D views
  - Preserves selection and filter state across view changes

### Supporting Utilities
- **Zone Bounds Hook:** `hooks/useZoneBounds.ts` (calculates zone boundaries from desk data)
- **Positioning Utils:** `utils/equipmentPositioning.ts` (adaptive grid distribution algorithm)

## Key Features

✓ Equipment distributed evenly within zones (adaptive grid layout)
✓ No clustering at zone centroids — items spaced ~20 desks per zone
✓ 2D and 3D views with identical filters and selection state
✓ Floor filtering, equipment type filtering, individual equipment selection
✓ Zone centroids calculated directly from desk positions (accurate)
✓ Equipment positioned at zone centroids + small type-specific offsets + jitter
✓ All floors auto-selected on load — all equipment visible immediately
✓ Clickable equipment labels in both 2D (text above circle) and 3D (Html overlay)
✓ Unified floor extraction via `@/utils/floorExtraction` (handles zone-based S002 codes)
✓ Larger canvas: `calc(100vh - 180px)` for more visualization space

## Database Schema

- Equipment codes directly reference zones: `S002-DALI-101` = Zone-101
- DALI zone mapping aligns legacy zones to modern zone numbering
- Desks reference zones: all Desk-122-141 are in Zone-101
- Zone table stores boundaries, occupancy, area for accurate visualization

## Positioning Algorithm

Equipment positioning uses adaptive grid distribution to avoid clustering:

```typescript
// Distribute equipment evenly within zone using grid
function calculateEquipmentPosition(
  zoneId: string,
  equipmentIndex: number,
  desksInZone: Desk[],
  equipmentType: string
) {
  // 1. Calculate zone centroid from desk positions
  const centroid = calculateZoneCentroid(desksInZone);

  // 2. Apply adaptive grid layout
  const gridPosition = gridLayout(equipmentIndex, Math.ceil(Math.sqrt(desksInZone.length)));

  // 3. Add type-specific offsets (visual separation)
  const typeOffset = getTypeOffset(equipmentType);

  // 4. Add small jitter for visual variety
  const jitter = randomJitter(0.5);

  return {
    x: centroid.x + gridPosition.x + typeOffset.x + jitter.x,
    z: centroid.z + gridPosition.z + typeOffset.z + jitter.z
  };
}
```

## Frontend Integration (React Query)

- **Hook:** `useEquipmentByZone(zoneId)` - Fetches equipment in specific zone
- **Hook:** `useAllEquipment()` - Fetches all equipment for site
- **Stale time:** 30s (equipment list rarely changes)
- **Error handling:** Graceful fallback to previous data on fetch failure

## Common Operations

### Selecting Equipment
```typescript
// When user clicks equipment in 2D/3D view
onEquipmentSelect(equipmentId) {
  setSelectedEquipment(equipmentId);
  // Trigger details panel, highlight in both views
}
```

### Filtering by Floor
```typescript
// User selects floor from dropdown
onFloorChange(floor) {
  setSelectedFloor(floor);
  // Refetch equipment for new floor
}
```

### Filtering by Type
```typescript
// User filters by equipment type
onTypeFilter(type) {
  setSelectedType(type);
  // Show only equipment of selected type
}
```

### View Switching
```typescript
// User toggles between 2D/3D
onViewToggle() {
  setView(view === '2d' ? '3d' : '2d');
  // Preserves selectedFloor, selectedType, selectedEquipment
}
```

## Troubleshooting

| Issue | Solution |
|-------|----------|
| Equipment markers not showing | Verify equipment has zone_id in database, check zone centroids calculated |
| Equipment clustering at zone center | Verify positioning algorithm using grid layout, check jitter is applied |
| 2D/3D view out of sync | Check state is shared between components, verify onViewToggle preserves filters |
| Zones not rendering correctly | Verify `dali_zone_mapping` table populated, check zone boundaries calculated from desks |
| Equipment position incorrect | Query zone centroid: `SELECT zone_id, centroid_x, centroid_z FROM zone_centroids` |

## Related Files

- **Backend Repositories:** `backend/app/database/repositories/zone_repository.py`, `desk_repository.py`, `equipment_repository.py`
- **Backend API:** `backend/app/api/zones.py`, `backend/app/api/desks.py`
- **Frontend API:** `frontend/src/lib/api/zones.ts`, `frontend/src/lib/api/desks.ts`
- **Frontend Hooks:** `frontend/src/hooks/useZones.ts`, `frontend/src/hooks/useEquipment.ts`, `frontend/src/hooks/useZoneBounds.ts`
- **Database Migrations:** `supabase/migrations/` (zones, desks, zone_centroids view)
