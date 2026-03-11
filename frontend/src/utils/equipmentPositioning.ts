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

const BUILDING_MIN_X = -14;
const BUILDING_MAX_X = 14;
const BUILDING_MIN_Z = -9;
const BUILDING_MAX_Z = 9;
const ZONE_COUNT_PER_FLOOR = 5;
const ZONE_STRIP_WIDTH = (BUILDING_MAX_X - BUILDING_MIN_X) / ZONE_COUNT_PER_FLOOR;
const PLANT_ZONE_SUFFIX = 'plant';

function normalizeFloorCode(floor: string): string {
  return floor === 'G' ? 'L0' : floor;
}

export function isPlantFloor(floor: string): boolean {
  const normalized = normalizeFloorCode(floor).toUpperCase();
  return normalized === 'R' || /^B\d+$/.test(normalized);
}

function fullFloorBounds(): ZoneBounds {
  return {
    minX: BUILDING_MIN_X,
    maxX: BUILDING_MAX_X,
    minZ: BUILDING_MIN_Z,
    maxZ: BUILDING_MAX_Z,
    centerX: (BUILDING_MIN_X + BUILDING_MAX_X) / 2,
    centerZ: (BUILDING_MIN_Z + BUILDING_MAX_Z) / 2,
    width: BUILDING_MAX_X - BUILDING_MIN_X,
    depth: BUILDING_MAX_Z - BUILDING_MIN_Z,
  };
}

function normalizeZoneIndex(rawZone: number): number {
  if (!Number.isFinite(rawZone)) return 1;
  const lastDigit = Math.abs(rawZone) % 10;
  if (lastDigit === 0) return ZONE_COUNT_PER_FLOOR;
  return ((lastDigit - 1) % ZONE_COUNT_PER_FLOOR) + 1;
}

function zoneIndexFromLetter(letter: string): number | null {
  const normalized = letter.trim().toUpperCase();
  if (!/^[A-E]$/.test(normalized)) return null;
  return normalized.charCodeAt(0) - 64;
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
      return normalizeZoneIndex(thirdPart);
    }

    // Plant equipment: S002-TYPE-FLOOR-SEQ (e.g., S002-CHILLER-B1-001)
    // Use the sequence number as zone
    if (parts.length >= 4) {
      const fourthPart = parseInt(parts[3], 10);
      if (!isNaN(fourthPart)) return normalizeZoneIndex(fourthPart);
    }
  }

  // Fallback: last numeric segment
  const numMatch = code.match(/-(\d+)$/);
  if (numMatch) return normalizeZoneIndex(parseInt(numMatch[1], 10));

  return 0;
}

/**
 * Build a zone key for grouping equipment.
 * Returns "Zone-{floor}-{zoneNum}" for zone-grid placement.
 */
export function buildZoneKey(code: string): string {
  const floor = normalizeFloorCode(extractFloor(code));
  if (isPlantFloor(floor)) {
    return `Zone-${floor}-${PLANT_ZONE_SUFFIX}`;
  }

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

  const sortedEquipment = [...equipment].sort((a, b) => {
    const codeA = ((a as { code?: string }).code || a.id || '').toString();
    const codeB = ((b as { code?: string }).code || b.id || '').toString();
    return codeA.localeCompare(codeB);
  });

  // Multiple items → adaptive grid that fills the full zone rectangle.
  const aspectRatio = zoneBounds.width / Math.max(zoneBounds.depth, 0.01);
  const cols = Math.max(1, Math.ceil(Math.sqrt(count * aspectRatio)));
  const rows = Math.max(1, Math.ceil(count / cols));

  const paddingX = Math.min(zoneBounds.width * 0.12, 0.6);
  const paddingZ = Math.min(zoneBounds.depth * 0.1, 0.9);
  const usableWidth = Math.max(zoneBounds.width - paddingX * 2, zoneBounds.width * 0.5);
  const usableDepth = Math.max(zoneBounds.depth - paddingZ * 2, zoneBounds.depth * 0.5);
  const spacingX = cols === 1 ? 0 : usableWidth / (cols - 1);
  const spacingZ = rows === 1 ? 0 : usableDepth / (rows - 1);
  const startX = zoneBounds.minX + paddingX;
  const startZ = zoneBounds.minZ + paddingZ;

  sortedEquipment.forEach((eq, idx) => {
    const col = idx % cols;
    const row = Math.floor(idx / cols);

    let x = startX + col * spacingX;
    let z = startZ + row * spacingZ;

    // Seeded jitter for deterministic placement
    x = addJitter(x, 0.03, idx * 7 + 1);
    z = addJitter(z, 0.03, idx * 13 + 3);

    x = clamp(x, zoneBounds.minX + paddingX * 0.4, zoneBounds.maxX - paddingX * 0.4);
    z = clamp(z, zoneBounds.minZ + paddingZ * 0.4, zoneBounds.maxZ - paddingZ * 0.4);

    positions.set(eq.id, { x, y: floorY, z });
  });

  return positions;
}

function makeZoneBounds(zoneIndex: number): ZoneBounds {
  const normalizedZoneIndex = Math.min(Math.max(zoneIndex, 1), ZONE_COUNT_PER_FLOOR);
  const minX = BUILDING_MIN_X + (normalizedZoneIndex - 1) * ZONE_STRIP_WIDTH;
  const maxX = minX + ZONE_STRIP_WIDTH;
  return {
    minX,
    maxX,
    minZ: BUILDING_MIN_Z,
    maxZ: BUILDING_MAX_Z,
    centerX: (minX + maxX) / 2,
    centerZ: (BUILDING_MIN_Z + BUILDING_MAX_Z) / 2,
    width: ZONE_STRIP_WIDTH,
    depth: BUILDING_MAX_Z - BUILDING_MIN_Z,
  };
}

/**
 * Generate synthetic zone bounds for a floor.
 * Non-plant floors are split into 5 full-depth strips across the 28m × 18m floor plate.
 * Plant floors (B1/R) share the full floor area for all equipment.
 */
export function generateSyntheticZoneBounds(floorCode: string): Record<string, ZoneBounds> {
  const normalizedFloor = normalizeFloorCode(floorCode);
  const bounds: Record<string, ZoneBounds> = {};

  if (isPlantFloor(normalizedFloor)) {
    bounds[`Zone-${normalizedFloor}-${PLANT_ZONE_SUFFIX}`] = fullFloorBounds();
    return bounds;
  }

  for (let zoneIndex = 1; zoneIndex <= ZONE_COUNT_PER_FLOOR; zoneIndex++) {
    bounds[`Zone-${normalizedFloor}-${zoneIndex}`] = makeZoneBounds(zoneIndex);
  }

  return bounds;
}

export function normalizeDeskZoneKey(zoneId: string, floorHint?: string | number): string | null {
  const rawZoneId = zoneId?.trim();
  const floorHintString = typeof floorHint === 'number'
    ? `L${Math.max(0, floorHint)}`
    : floorHint?.trim();
  const floorMatch = rawZoneId?.match(/(?:^|-)((?:B\d)|(?:L\d+)|G|R)(?:-|$)/i);
  const floor = normalizeFloorCode((floorMatch?.[1] || floorHintString || 'L0').toUpperCase());

  if (isPlantFloor(floor)) {
    return `Zone-${floor}-${PLANT_ZONE_SUFFIX}`;
  }

  const letterMatch = rawZoneId?.match(/-([A-E])$/i);
  const letterZone = letterMatch ? zoneIndexFromLetter(letterMatch[1]) : null;
  if (letterZone) {
    return `Zone-${floor}-${letterZone}`;
  }

  const numericMatches = rawZoneId?.match(/\d+/g);
  const lastNumeric = numericMatches?.length ? parseInt(numericMatches[numericMatches.length - 1], 10) : NaN;
  if (!Number.isNaN(lastNumeric)) {
    return `Zone-${floor}-${normalizeZoneIndex(lastNumeric)}`;
  }

  return null;
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
