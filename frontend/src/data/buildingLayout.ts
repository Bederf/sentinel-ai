/**
 * BUILDING LAYOUT METADATA
 *
 * Defines physical structure for multi-floor pathfinding:
 * - Entrance/exit points for arrival/departure flows
 * - Vertical transport (elevators, stairs) with wait times
 * - Corridor connections between zones
 *
 * Phase 2: Multi-floor pathfinding foundation
 */

export interface Entrance {
  id: string;
  x: number;
  y: number;
  floor: number;
  capacity: number; // Max people entering simultaneously
}

export interface Exit {
  id: string;
  x: number;
  y: number;
  floor: number;
}

export interface VerticalTransport {
  id: string;
  type: 'elevator' | 'stairs';
  x: number;
  y: number;
  floors: number[]; // Which floors this connects
  waitTime: number; // Time in seconds to traverse (elevators only)
}

export interface CorridorSegment {
  id: string;
  floors: number[]; // Which floors this corridor spans
  zones: string[]; // Zone IDs connected by this corridor
}

export interface BuildingLayout {
  entrances: Entrance[];
  exits: Exit[];
  elevators: VerticalTransport[];
  stairs: VerticalTransport[];
  corridors: CorridorSegment[];
}

/**
 * Default building layout for site-002
 *
 * Physical layout:
 * - Ground floor (L0): Reception, Workspace, Common, Utility, Corridor
 * - Level 1 (L1): Meeting rooms, Kitchen, Server, Bathrooms
 * - Level 2 (L2): Meeting suites
 *
 * Vertical connections:
 * - Elevator 1 & 2: L0 → L1 → L2 (15 second wait)
 * - Stairs 1 & 2: All floors connected (no wait, ~2 sec per floor)
 * - Entrances: Main (reception) + Staff (corridor)
 * - Exits: Main (reception) + Emergency (per floor)
 */
export const BUILDING_LAYOUT: BuildingLayout = {
  // Building entry points for arrivals
  entrances: [
    {
      id: 'main-entrance',
      x: 0,
      y: -8, // South side of building
      floor: 0, // Ground floor
      capacity: 10, // Up to 10 people per arrival batch
    },
    {
      id: 'staff-entrance',
      x: -8,
      y: 0, // West side
      floor: 0,
      capacity: 5,
    },
  ],

  // Building exit points for departures
  exits: [
    {
      id: 'main-exit',
      x: 0,
      y: -8,
      floor: 0, // Must exit on ground floor
    },
    {
      id: 'emergency-exit-1',
      x: 8,
      y: 0,
      floor: 1, // Emergency exit per floor
    },
    {
      id: 'emergency-exit-2',
      x: 8,
      y: 0,
      floor: 2,
    },
  ],

  // Vertical transport: Elevators (with wait time)
  elevators: [
    {
      id: 'lift-1',
      type: 'elevator',
      x: -2,
      y: 2,
      floors: [0, 1, 2], // Connects all floors
      waitTime: 15, // 15 seconds elevator travel
    },
    {
      id: 'lift-2',
      type: 'elevator',
      x: 2,
      y: 2,
      floors: [0, 1, 2],
      waitTime: 15,
    },
  ],

  // Vertical transport: Stairs (no wait, faster)
  stairs: [
    {
      id: 'stairs-1',
      type: 'stairs',
      x: -6,
      y: 2,
      floors: [0, 1, 2],
      waitTime: 0, // Stairs are instant (no queue)
    },
    {
      id: 'stairs-2',
      type: 'stairs',
      x: 6,
      y: 2,
      floors: [0, 1, 2],
      waitTime: 0,
    },
  ],

  // Corridor segments connecting zones
  corridors: [
    {
      id: 'corridor-l0',
      floors: [0],
      zones: ['zone-1', 'zone-2', 'zone-4', 'zone-5'], // Ground floor zones
    },
    {
      id: 'corridor-l1',
      floors: [1],
      zones: ['zone-3'], // Level 1 zones (meeting, kitchen, server, bathroom)
    },
    {
      id: 'corridor-l2',
      floors: [2],
      zones: [], // Level 2 zones (for future expansion)
    },
  ],
};

/**
 * Find nearest entrance to spawn incoming person
 */
export function findNearestEntrance(preferredFloor: number = 0): Entrance {
  const entrances = BUILDING_LAYOUT.entrances.filter(e => e.floor === preferredFloor);
  if (entrances.length === 0) {
    // Fallback to any entrance
    return BUILDING_LAYOUT.entrances[0];
  }
  // Random from available entrances
  return entrances[Math.floor(Math.random() * entrances.length)];
}

/**
 * Find nearest exit to departure point
 */
export function findNearestExit(currentFloor: number): Exit {
  // Prefer exits on same floor, fallback to main exit
  const floorExits = BUILDING_LAYOUT.exits.filter(e => e.floor === currentFloor);
  if (floorExits.length > 0) {
    return floorExits[0];
  }
  // Must use main exit on ground floor
  return BUILDING_LAYOUT.exits.find(e => e.id === 'main-exit') || BUILDING_LAYOUT.exits[0];
}

/**
 * Find nearest vertical transport (elevator or stairs)
 */
export function findNearestVerticalTransport(
  fromFloor: number,
  toFloor: number,
  preferElevator: boolean = true
): VerticalTransport | null {
  const allTransport = [...BUILDING_LAYOUT.elevators, ...BUILDING_LAYOUT.stairs];

  // Filter to transport that connects both floors
  const viable = allTransport.filter(
    t => t.floors.includes(fromFloor) && t.floors.includes(toFloor)
  );

  if (viable.length === 0) return null;

  // Prefer elevators if requested
  if (preferElevator) {
    const elevators = viable.filter(t => t.type === 'elevator');
    if (elevators.length > 0) {
      return elevators[Math.floor(Math.random() * elevators.length)];
    }
  }

  // Fallback to first viable transport
  return viable[Math.floor(Math.random() * viable.length)];
}

/**
 * Get all zones on a specific floor
 */
export function getZonesOnFloor(floor: number): string[] {
  for (const corridor of BUILDING_LAYOUT.corridors) {
    if (corridor.floors.includes(floor)) {
      return corridor.zones;
    }
  }
  return [];
}

/**
 * Check if two zones are on same floor (direct connection possible)
 */
export function zonesOnSameFloor(zone1Floor: number, zone2Floor: number): boolean {
  return zone1Floor === zone2Floor;
}

/**
 * Get distance between two 2D points
 */
export function getDistance(x1: number, y1: number, x2: number, y2: number): number {
  const dx = x2 - x1;
  const dy = y2 - y1;
  return Math.sqrt(dx * dx + dy * dy);
}
