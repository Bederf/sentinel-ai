/**
 * Equipment positioning algorithms for Digital Twin visualization
 *
 * Provides zone-grid-based distribution of equipment within building zones.
 * Supports office (S002: 001-099 per floor) and hospital (S005: 001-099 single floor)
 * formats. Zone count per floor is derived dynamically from equipment codes.
 */

import type { Equipment } from '@/lib/api/sites';
import { extractFloorFromCode, extractFloorFromZoneKey } from '@/utils/floorExtraction';

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
const MAX_ZONES_PER_FLOOR = 99; // Supports hospital-scale: 001-099 per floor
const PLANT_ZONE_SUFFIX = 'plant';
const ZONE_STRIP_COUNT = 5; // visual columns across building width

function normalizeFloorCode(floor: string): string {
  return floor === 'G' ? 'L0' : floor;
}

function canonicalZoneKeyForFloorIndex(floor: string, zoneIndex: number): string | null {
  const normalized = normalizeFloorCode(floor).toUpperCase();
  const zone = Math.max(1, Math.min(zoneIndex, MAX_ZONES_PER_FLOOR));
  if (normalized === 'L0') return `Zone-${String(zone).padStart(3, '0')}`;
  const levelMatch = normalized.match(/^L(\d+)$/);
  if (!levelMatch) return null;
  const level = parseInt(levelMatch[1], 10);
  if (Number.isNaN(level) || level < 0 || level > 9) return null;
  return `Zone-${level}${String(zone - 1).padStart(2, '0')}`;
}

function canonicalZoneKeyFromCode(code: string): string | null {
  if (!code) return null;

  const directZone = code.match(/^Zone-(\d{3})$/i);
  if (directZone?.[1]) return `Zone-${directZone[1]}`;

  const canonicalPlant = code.match(/^S\d+-[A-Z]+-(B\d+|R)-\d+/i);
  if (canonicalPlant?.[1]) return `Zone-${canonicalPlant[1].toUpperCase()}-${PLANT_ZONE_SUFFIX}`;

  const canonicalZone = code.match(/^S\d+-[A-Z]+-(\d{3})(?:-|$)/i);
  if (canonicalZone?.[1]) return `Zone-${canonicalZone[1]}`;

  return null;
}

function zoneIndexFromCanonicalZoneKey(zoneKey: string): number {
  const match = zoneKey.match(/^Zone-(\d{3})$/i);
  if (!match) return 0;
  const raw = parseInt(match[1], 10);
  if (Number.isNaN(raw)) return 0;
  const floorRelative = raw % 100;
  const floor = Math.floor(raw / 100);
  return floor === 0 ? floorRelative || raw : floorRelative + 1;
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

/**
 * Resolve the effective zone count for each floor from equipment codes.
 * Used to generate the correct number of zone strips per floor dynamically.
 */
export function resolveMaxZonePerFloor(equipment: Equipment[]): Record<string, number> {
  const maxZones: Record<string, number> = {};
  for (const eq of equipment) {
    const code = ((eq as { code?: string }).code || eq.id || '').toString();
    const zoneKey = buildZoneKey(eq);
    const floor = normalizeFloorCode(extractFloorFromZoneKey(zoneKey) || extractFloor(code));
    const zoneNum = zoneIndexFromCanonicalZoneKey(zoneKey) || extractZoneNumberFromCode(code);
    if (floor && zoneNum > 0) {
      const current = maxZones[floor] ?? 0;
      if (zoneNum > current) maxZones[floor] = zoneNum;
    }
  }
  return maxZones;
}

/**
 * Extract floor-relative zone index from equipment code.
 * Supports:
 *   Office:     S002-AHU-204  → zone 4 (floor 2, zone 4)
 *   Hospital:   S005-AHU-L1-042 → zone 42 (floor L1, zone 42)
 *   Plant:      S002-CHILLER-B1-001 → 1
 */
export function extractZoneNumberFromCode(code: string): number {
  if (!code) return 0;

  const canonicalKey = canonicalZoneKeyFromCode(code);
  const canonicalIndex = canonicalKey ? zoneIndexFromCanonicalZoneKey(canonicalKey) : 0;
  if (canonicalIndex > 0) return canonicalIndex;

  // Hospital format: S{hospital}-TYPE-{floor}-{zone} e.g. S005-AHU-L1-042
  // Matches the last numeric segment after a floor identifier
  const hospitalMatch = code.match(/-(L\d+|B\d+|G|R)-(\d+)$/i);
  if (hospitalMatch) {
    return Math.min(parseInt(hospitalMatch[2], 10), MAX_ZONES_PER_FLOOR);
  }

  // Office format: S002-TYPE-204 or S002-TYPE-015
  // 3-digit office: 200-299 → floor encoded in hundreds, zone = last 2 digits
  // 3-digit office: 100-199 → direct zone 1-99 (no floor encoding)
  // 2-digit office: 01-99 → direct zone 1-99
  const parts = code.split('-');
  if (parts.length >= 3) {
    const thirdPart = parseInt(parts[2], 10);
    if (!isNaN(thirdPart) && thirdPart > 0) {
      if (thirdPart >= 200 && thirdPart <= 299) {
        return Math.min(thirdPart % 100, MAX_ZONES_PER_FLOOR);
      }
      if (thirdPart >= 100 && thirdPart <= 199) {
        return Math.min(thirdPart % 100 || 100, MAX_ZONES_PER_FLOOR);
      }
      return Math.min(thirdPart, MAX_ZONES_PER_FLOOR);
    }
  }

  // Last numeric segment fallback
  const numMatch = code.match(/-(\d+)$/);
  if (numMatch) {
    return Math.min(parseInt(numMatch[1], 10), MAX_ZONES_PER_FLOOR);
  }

  return 0;
}

function zoneIndexFromLetter(letter: string): number | null {
  const normalized = letter.trim().toUpperCase();
  if (!/^[A-E]$/.test(normalized)) return null;
  return normalized.charCodeAt(0) - 64;
}

/**
 * Extract floor code from equipment code.
 */
export function extractFloor(code: string): string {
  return extractFloorFromZoneKey(code) || extractFloorFromCode(code) || 'L0';
}

/**
 * Extract the zone number from equipment code.
 */
export function extractZoneNumber(code: string): number {
  return extractZoneNumberFromCode(code);
}

/**
 * Build a zone key for grouping equipment.
 * Returns "Zone-{floor}-{zoneNum}" for zone-grid placement.
 */
export function buildZoneKey(equipment: Equipment | string): string {
  if (typeof equipment === 'string') {
    const canonical = canonicalZoneKeyFromCode(equipment);
    if (canonical) return canonical;
    const floor = normalizeFloorCode(extractFloor(equipment));
    if (isPlantFloor(floor)) {
      return `Zone-${floor}-${PLANT_ZONE_SUFFIX}`;
    }
    const zoneNum = extractZoneNumberFromCode(equipment);
    return canonicalZoneKeyForFloorIndex(floor, zoneNum) || `Zone-${floor}-${zoneNum}`;
  }

  if ((equipment as any).zone_key) {
    return (equipment as any).zone_key;
  }

  const code = ((equipment as { code?: string }).code || equipment.id || '').toString();
  const canonical = canonicalZoneKeyFromCode(code);
  if (canonical) return canonical;

  const floor = normalizeFloorCode(extractFloor(code));
  if (isPlantFloor(floor)) {
    return `Zone-${floor}-${PLANT_ZONE_SUFFIX}`;
  }

  const zoneNum = extractZoneNumberFromCode(code);
  return canonicalZoneKeyForFloorIndex(floor, zoneNum) || `Zone-${floor}-${zoneNum}`;
}

/**
 * Clamp value to [min, max] range
 */
export function clamp(val: number, min: number, max: number): number {
  return Math.max(min, Math.min(max, val));
}

/**
 * Add seeded jitter based on zone number for deterministic placement.
 */
export function addJitter(value: number, maxJitterPercent: number = 0.1, seed: number = 0): number {
  const hash = Math.sin(seed * 9301 + 49297) * 49297;
  const rand = hash - Math.floor(hash);
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

    x = addJitter(x, 0.03, idx * 7 + 1);
    z = addJitter(z, 0.03, idx * 13 + 3);

    x = clamp(x, zoneBounds.minX + paddingX * 0.4, zoneBounds.maxX - paddingX * 0.4);
    z = clamp(z, zoneBounds.minZ + paddingZ * 0.4, zoneBounds.maxZ - paddingZ * 0.4);

    positions.set(eq.id, { x, y: floorY, z });
  });

  return positions;
}

/**
 * Make zone bounds for a single zone strip within a floor.
 * Zones are laid out in ZONE_STRIP_COUNT columns × auto rows grid.
 */
function makeZoneBounds(zoneIndex: number, _maxZones: number): ZoneBounds {
  const stripsX = ZONE_STRIP_COUNT;
  const stripWidth = (BUILDING_MAX_X - BUILDING_MIN_X) / stripsX;
  const stripIndex = (zoneIndex - 1) % stripsX;
  const minX = BUILDING_MIN_X + stripIndex * stripWidth;
  const maxX = minX + stripWidth;
  return {
    minX,
    maxX,
    minZ: BUILDING_MIN_Z,
    maxZ: BUILDING_MAX_Z,
    centerX: (minX + maxX) / 2,
    centerZ: (BUILDING_MIN_Z + BUILDING_MAX_Z) / 2,
    width: stripWidth,
    depth: BUILDING_MAX_Z - BUILDING_MIN_Z,
  };
}

/**
 * Generate synthetic zone bounds for a floor.
 * Non-plant floors are split into zone strips — zone count derived from equipment.
 * Plant floors (B1/R) share the full floor area for all equipment.
 */
export function generateSyntheticZoneBounds(
  floorCode: string,
  maxZonesPerFloor: number = MAX_ZONES_PER_FLOOR
): Record<string, ZoneBounds> {
  const normalizedFloor = normalizeFloorCode(floorCode);
  const bounds: Record<string, ZoneBounds> = {};

  if (isPlantFloor(normalizedFloor)) {
    bounds[`Zone-${normalizedFloor}-${PLANT_ZONE_SUFFIX}`] = fullFloorBounds();
    return bounds;
  }

  const effectiveMax = Math.max(1, Math.min(maxZonesPerFloor, MAX_ZONES_PER_FLOOR));
  for (let zoneIndex = 1; zoneIndex <= effectiveMax; zoneIndex++) {
    const zoneBounds = makeZoneBounds(zoneIndex, effectiveMax);
    bounds[`Zone-${normalizedFloor}-${zoneIndex}`] = zoneBounds;
    const canonicalZoneKey = canonicalZoneKeyForFloorIndex(normalizedFloor, zoneIndex);
    if (canonicalZoneKey) {
      bounds[canonicalZoneKey] = zoneBounds;
    }
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
  if (numericMatches) {
    const last = parseInt(numericMatches[numericMatches.length - 1], 10);
    if (!isNaN(last)) {
      return `Zone-${floor}-${last}`;
    }
  }

  return null;
}
