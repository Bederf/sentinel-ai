/**
 * Equipment positioning algorithms for Digital Twin visualization
 *
 * Provides zone-grid-based distribution of equipment within building zones.
 * S002 equipment codes encode floor in the zone number:
 *   001-099 = L0 (Ground), 100-199 = L1, 200-299 = L2
 * Plant equipment has explicit floor markers: S002-CHILLER-B1-001
 */

import type { Equipment } from '@/lib/api/sites';
import { extractFloorFromCode } from '@/utils/floorExtraction';

export interface ZoneBounds {
  minX: number;
  maxX: number;
  minZ: number;
  maxZ: number;
  centerX: number;
  centerZ: number;
  width: number;
  depth: number;
}

export interface EquipmentPosition {
  x: number;
  y: number;
  z: number;
}

/**
 * Extract floor code from equipment code.
 * Delegates to floorExtraction.ts which handles:
 *   S002-VAV-204    → zone 204 → L2
 *   S002-CHILLER-B1-001 → B1
 *   S002-INV-R-002  → R
 */
export function extractFloor(code: string): string {
  return extractFloorFromCode(code) || 'L0';
}

/**
 * Extract the zone number from an S002 equipment code.
 * Returns the floor-relative zone index (0-based within that floor).
 *
 * Examples:
 *   S002-VAV-204       → zone 204, floor-relative = 4
 *   S002-LUM-101-08    → zone 101, floor-relative = 1
 *   S002-FCU-015       → zone 15,  floor-relative = 15
 *   S002-CHILLER-B1-001 → seq 1,   floor-relative = 1
 *   S002-DALI-001      → 1,        floor-relative = 1
 */
export function extractZoneNumber(code: string): number {
  if (!code) return 0;

  // S002-TYPE-ZONE or S002-TYPE-ZONE-FIXTURE
  // The zone number is always the 3rd segment for S002
  const parts = code.split('-');
  if (parts.length >= 3 && parts[0] === 'S002') {
    // Check if 3rd part is a number (zone-based equipment)
    const thirdPart = parseInt(parts[2], 10);
    if (!isNaN(thirdPart)) {
      // Floor-relative zone: strip the floor hundreds digit
      return thirdPart % 100;
    }

    // Plant equipment: S002-TYPE-FLOOR-SEQ (e.g., S002-CHILLER-B1-001)
    // Use the sequence number as zone
    if (parts.length >= 4) {
      const fourthPart = parseInt(parts[3], 10);
      if (!isNaN(fourthPart)) return fourthPart;
    }
  }

  // Fallback: last numeric segment
  const numMatch = code.match(/-(\d+)$/);
  if (numMatch) return parseInt(numMatch[1], 10) % 100;

  return 0;
}

/**
 * Build a zone key for grouping equipment.
 * Returns "Zone-{floor}-{zoneNum}" for zone-grid placement.
 */
export function buildZoneKey(code: string): string {
  const floor = extractFloor(code);
  const zoneNum = extractZoneNumber(code);
  return `Zone-${floor}-${zoneNum}`;
}

// Keep backward compat export
export const extractZoneLetter = (code: string): string => {
  const zoneNum = extractZoneNumber(code);
  return String(zoneNum);
};

/**
 * Clamp value to [min, max] range
 */
export function clamp(val: number, min: number, max: number): number {
  return Math.max(min, Math.min(max, val));
}

/**
 * Add seeded jitter based on zone number for deterministic placement.
 * Uses a simple hash so positions don't jump on re-render.
 */
export function addJitter(value: number, maxJitterPercent: number = 0.1, seed: number = 0): number {
  // Simple seeded pseudo-random
  const hash = Math.sin(seed * 9301 + 49297) * 49297;
  const rand = hash - Math.floor(hash); // 0..1
  const jitterAmount = Math.abs(value) * maxJitterPercent;
  return value + (rand - 0.5) * 2 * jitterAmount;
}

/**
 * Calculate zone bounds from desk coordinates
 */
export function calculateZoneBoundsFromCoords(xs: number[], zs: number[]): ZoneBounds | null {
  if (xs.length === 0 || zs.length === 0) return null;

  const minX = Math.min(...xs);
  const maxX = Math.max(...xs);
  const minZ = Math.min(...zs);
  const maxZ = Math.max(...zs);

  return {
    minX,
    maxX,
    minZ,
    maxZ,
    centerX: (minX + maxX) / 2,
    centerZ: (minZ + maxZ) / 2,
    width: maxX - minX || 2,
    depth: maxZ - minZ || 2,
  };
}

/**
 * Distribute equipment evenly within a zone using adaptive grid layout
 */
export function distributeEquipmentInZone(
  equipment: Equipment[],
  zoneBounds: ZoneBounds,
  floorY: number
): Map<string, EquipmentPosition> {
  const positions = new Map<string, EquipmentPosition>();
  const count = equipment.length;

  if (count === 0) return positions;

  // Single item → place at zone center
  if (count === 1) {
    positions.set(equipment[0].id, {
      x: zoneBounds.centerX,
      y: floorY,
      z: zoneBounds.centerZ,
    });
    return positions;
  }

  // Multiple items → adaptive grid
  const cols = Math.ceil(Math.sqrt(count));
  const rows = Math.ceil(count / cols);

  const usableWidth = zoneBounds.width * 0.7;
  const usableDepth = zoneBounds.depth * 0.7;

  const spacingX = usableWidth / (cols + 1);
  const spacingZ = usableDepth / (rows + 1);

  const marginX = (zoneBounds.width - usableWidth) / 2;
  const marginZ = (zoneBounds.depth - usableDepth) / 2;
  const startX = zoneBounds.minX + marginX + spacingX;
  const startZ = zoneBounds.minZ + marginZ + spacingZ;

  equipment.forEach((eq, idx) => {
    const col = idx % cols;
    const row = Math.floor(idx / cols);

    let x = startX + col * spacingX;
    let z = startZ + row * spacingZ;

    // Seeded jitter for deterministic placement
    x = addJitter(x, 0.08, idx * 7 + 1);
    z = addJitter(z, 0.08, idx * 13 + 3);

    x = clamp(x, -14, 14);
    z = clamp(z, -9, 9);

    positions.set(eq.id, { x, y: floorY, z });
  });

  return positions;
}

/**
 * Generate zone bounds for a floor using a grid layout.
 * Creates up to 25 zone cells (5 cols × 5 rows) across the building footprint.
 * Building footprint: X [-14..14] (28m), Z [-9..9] (18m)
 *
 * Zone numbers 0-24 map to grid positions:
 *   Row 0 (Z top):    zones 0-4
 *   Row 1:            zones 5-9
 *   Row 2 (center):   zones 10-14
 *   Row 3:            zones 15-19
 *   Row 4 (Z bottom): zones 20-24
 */
const GRID_COLS = 5;
const GRID_ROWS = 5;
const BUILDING_MIN_X = -14;
const BUILDING_MAX_X = 14;
const BUILDING_MIN_Z = -9;
const BUILDING_MAX_Z = 9;
const CELL_WIDTH = (BUILDING_MAX_X - BUILDING_MIN_X) / GRID_COLS;   // 5.6m
const CELL_DEPTH = (BUILDING_MAX_Z - BUILDING_MIN_Z) / GRID_ROWS;   // 3.6m

function makeZoneBounds(col: number, row: number): ZoneBounds {
  const minX = BUILDING_MIN_X + col * CELL_WIDTH;
  const maxX = minX + CELL_WIDTH;
  const minZ = BUILDING_MIN_Z + row * CELL_DEPTH;
  const maxZ = minZ + CELL_DEPTH;
  return {
    minX, maxX, minZ, maxZ,
    centerX: (minX + maxX) / 2,
    centerZ: (minZ + maxZ) / 2,
    width: CELL_WIDTH,
    depth: CELL_DEPTH,
  };
}

/**
 * Generate synthetic zone bounds for a floor.
 * Maps zone numbers (0-99) to grid cells across the building footprint.
 * Zone number → grid position: col = zoneNum % GRID_COLS, row = floor(zoneNum / GRID_COLS) % GRID_ROWS
 */
export function generateSyntheticZoneBounds(floorCode: string): Record<string, ZoneBounds> {
  const bounds: Record<string, ZoneBounds> = {};

  // Generate bounds for zones 0-24 (covering 5×5 grid)
  for (let zn = 0; zn < GRID_COLS * GRID_ROWS; zn++) {
    const col = zn % GRID_COLS;
    const row = Math.floor(zn / GRID_COLS) % GRID_ROWS;
    bounds[`Zone-${floorCode}-${zn}`] = makeZoneBounds(col, row);
  }

  // Also add some higher zone numbers that wrap around
  // (handles zones like 50, 60 etc. that exceed 25)
  for (let zn = 25; zn < 100; zn++) {
    const col = zn % GRID_COLS;
    const row = Math.floor(zn / GRID_COLS) % GRID_ROWS;
    bounds[`Zone-${floorCode}-${zn}`] = makeZoneBounds(col, row);
  }

  return bounds;
}

/**
 * Helper: convert equipment position map to array format
 */
export function positionsToArray(positions: Map<string, EquipmentPosition>): Array<[string, EquipmentPosition]> {
  return Array.from(positions);
}

/**
 * Helper: get position for single equipment, with fallback
 */
export function getEquipmentPositionWithFallback(
  equipment: Equipment,
  positions: Map<string, EquipmentPosition>,
  fallbackPosition: EquipmentPosition
): EquipmentPosition {
  return positions.get(equipment.id) || fallbackPosition;
}
