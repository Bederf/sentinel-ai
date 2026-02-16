/**
 * Equipment positioning algorithms for Digital Twin visualization
 *
 * Provides adaptive grid-based distribution of equipment within zones
 * to avoid clustering at zone centroids.
 */

import type { Equipment } from '@/lib/api/sites';

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
 * Extract floor code from equipment ID
 * Example: S002-CHILLER-B1-001 → "B1"
 */
export function extractFloor(code: string): string {
  const match = code.match(/-(B\d|G|L\d+|R)-/i);
  return match ? match[1].toUpperCase() : 'L0';
}

/**
 * Desk zones use compass directions: N, S, E, W, C
 * Equipment zones use numeric IDs mapped to 5 groups.
 * This maps the 5 equipment zone groups to compass directions
 * matching the desk zone_id convention (Zone-L1-N, Zone-L1-S, etc.)
 */
const ZONE_INDEX_TO_COMPASS = ['N', 'E', 'S', 'W', 'C'] as const;

/**
 * Extract zone direction from equipment code
 * Maps to compass directions (N/E/S/W/C) to match desk zone_id format.
 *
 * Example: S002-VAV-101 → zone index (101-1)%5=0 → "N"
 * Example: S002-CHILLER-B1-A → "N" (A→N, B→E, C→S, D→W, E→C)
 */
export function extractZoneLetter(code: string): string {
  // Letter suffix (A-E) → compass
  const letterMatch = code.match(/-([A-E])$/i);
  if (letterMatch) {
    const idx = letterMatch[1].toUpperCase().charCodeAt(0) - 65; // A=0, B=1, ...
    return ZONE_INDEX_TO_COMPASS[idx] || 'C';
  }

  // Numeric suffix → compass via modulo 5
  const numMatch = code.match(/-(\d+)$/);
  if (numMatch) {
    const idx = (parseInt(numMatch[1], 10) - 1) % 5;
    return ZONE_INDEX_TO_COMPASS[idx] || 'C';
  }

  return 'C'; // default: center zone
}

/**
 * Clamp value to [min, max] range
 */
export function clamp(val: number, min: number, max: number): number {
  return Math.max(min, Math.min(max, val));
}

/**
 * Add random jitter to a value
 * @param value Base value
 * @param maxJitterPercent Jitter as percentage of magnitude (0-1)
 * @returns Jittered value
 */
export function addJitter(value: number, maxJitterPercent: number = 0.1): number {
  const jitterAmount = Math.abs(value) * maxJitterPercent;
  return value + (Math.random() - 0.5) * 2 * jitterAmount;
}

/**
 * Calculate zone bounds from desk coordinates
 * @param xs Array of X coordinates
 * @param zs Array of Z coordinates
 * @returns Zone bounds with min/max/center/dimensions
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
    width: maxX - minX || 2, // Minimum width to avoid division by zero
    depth: maxZ - minZ || 2, // Minimum depth
  };
}

/**
 * Distribute equipment evenly within a zone using adaptive grid layout
 *
 * Algorithm:
 * 1. For single item: place at zone center
 * 2. For multiple items: calculate grid dimensions (cols = sqrt(N))
 * 3. Calculate grid spacing (60% of zone dimensions with margins)
 * 4. Place equipment in grid pattern with ±10% jitter for natural look
 * 5. Clamp to building bounds to prevent escaping
 *
 * @param equipment Array of equipment items to distribute
 * @param zoneBounds Zone boundaries calculated from desk positions
 * @param floorY Y-position for the equipment (floor height)
 * @returns Map of equipment.id → EquipmentPosition
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
  // Calculate grid dimensions: cols = ceil(sqrt(N)), rows = ceil(N/cols)
  const cols = Math.ceil(Math.sqrt(count));
  const rows = Math.ceil(count / cols);

  // Calculate spacing: use 60% of zone dimensions to leave margins
  const usableWidth = zoneBounds.width * 0.6;
  const usableDepth = zoneBounds.depth * 0.6;

  const spacingX = usableWidth / (cols + 1);
  const spacingZ = usableDepth / (rows + 1);

  // Starting position (center the grid within zone)
  const marginX = (zoneBounds.width - usableWidth) / 2;
  const marginZ = (zoneBounds.depth - usableDepth) / 2;
  const startX = zoneBounds.minX + marginX + spacingX;
  const startZ = zoneBounds.minZ + marginZ + spacingZ;

  // Distribute equipment
  equipment.forEach((eq, idx) => {
    const col = idx % cols;
    const row = Math.floor(idx / cols);

    let x = startX + col * spacingX;
    let z = startZ + row * spacingZ;

    // Add jitter (±10% of spacing) for natural look
    x = addJitter(x, 0.1);
    z = addJitter(z, 0.1);

    // Clamp to building bounds (-14..14 for X, -9..9 for Z)
    x = clamp(x, -14, 14);
    z = clamp(z, -9, 9);

    positions.set(eq.id, { x, y: floorY, z });
  });

  return positions;
}

/**
 * Generate synthetic zone bounds for floors without desk data (e.g., B1, R).
 * Creates 5 compass zones (N/E/S/W/C) evenly distributed across the building footprint.
 * Building footprint: X [-14..14], Z [-9..9]
 */
export function generateSyntheticZoneBounds(floorCode: string): Record<string, ZoneBounds> {
  const bounds: Record<string, ZoneBounds> = {};

  // 5 zones: N (top), S (bottom), E (right), W (left), C (center)
  const zones: Record<string, { minX: number; maxX: number; minZ: number; maxZ: number }> = {
    N: { minX: -8, maxX: 8, minZ: -9, maxZ: -3 },
    S: { minX: -8, maxX: 8, minZ: 3, maxZ: 9 },
    E: { minX: 4, maxX: 14, minZ: -4, maxZ: 4 },
    W: { minX: -14, maxX: -4, minZ: -4, maxZ: 4 },
    C: { minX: -5, maxX: 5, minZ: -4, maxZ: 4 },
  };

  for (const [dir, rect] of Object.entries(zones)) {
    bounds[`Zone-${floorCode}-${dir}`] = {
      minX: rect.minX,
      maxX: rect.maxX,
      minZ: rect.minZ,
      maxZ: rect.maxZ,
      centerX: (rect.minX + rect.maxX) / 2,
      centerZ: (rect.minZ + rect.maxZ) / 2,
      width: rect.maxX - rect.minX,
      depth: rect.maxZ - rect.minZ,
    };
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
