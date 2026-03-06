/**
 * Dynamic Floor Extraction and Management
 *
 * Supports multiple building types:
 * - Site-002 (Office): S002-TYPE-ZONE (zone encodes floor: 001-099=L0, 100-199=L1, 200-299=L2)
 * - Site-005 (Hospital): site-005-UMH-TYPE-FLOOR-ID (explicit floor: B1, L1-L9, R)
 * - Site-012 (Generic): S012-TYPE-FLOOR-ID (explicit floor: G, R)
 */

export interface Floor {
  id: number;
  label: string;
  code: string;
  y: number; // 3D height for rendering
}

/**
 * Extract floor code from equipment code pattern
 *
 * Handles:
 * - S002-TYPE-ZONE_ID → Extract floor from zone (001-099=L0, 100-199=L1, 200-299=L2)
 * - site-005-UMH-TYPE-FLOOR-ID → Extract FLOOR (B1, L1-L9, R)
 * - S012-TYPE-FLOOR-ID → Extract FLOOR (G, R)
 */
export function extractFloorFromCode(code: string): string | null {
  if (!code) return null;

  // Site-005 format: site-005-UMH-TYPE-FLOOR-ID or site-005-UMH-TYPE-FLOOR-ID.POINT
  if (code.startsWith('site-005-UMH-')) {
    const match = code.match(/site-005-UMH-[^-]+-([^-.]+)/);
    if (match && match[1]) return match[1]; // B1, L1-L9, R
  }

  // S012 format: S012-TYPE-FLOOR-ID or S012-TYPE-FLOOR-ID.POINT
  if (code.startsWith('S012-')) {
    const match = code.match(/S012-[^-]+-([^-.]+)/);
    if (match && match[1]) return match[1]; // G, R
  }

  // Site-002 format: S002-TYPE-ZONE_ID or S002-TYPE-FLOOR-ID
  if (code.startsWith('S002-')) {
    const parts = code.split('-');
    const thirdPart = parts[2] || '';

    // Explicit floor codes: S002-CHILLER-B1-001, S002-INV-R-002, S002-AHU-L2-001
    if (/^(B[12]|R|G)$/i.test(thirdPart)) return thirdPart.toUpperCase();
    if (/^L\d+$/i.test(thirdPart)) return thirdPart.toUpperCase();

    // Utility codes: S002-MTR-W-MAIN (W=Water) → basement
    if (thirdPart === 'W') return 'B1';

    // Zone-encoded floor: S002-FCU-204 → zone 204 → L2
    const zoneMatch = code.match(/S002-[^-]+-(\d+)/);
    if (zoneMatch && zoneMatch[1]) {
      const zone = parseInt(zoneMatch[1]);
      if (zone >= 1 && zone <= 99) return 'L0';
      if (zone >= 100 && zone <= 199) return 'L1';
      if (zone >= 200 && zone <= 299) return 'L2';
    }
  }

  return null;
}

/**
 * Generate floor list from equipment codes
 * Returns sorted array of unique floors
 */
export function generateFloorsFromEquipment(
  equipment: Array<{ code?: string; [key: string]: any }>
): string[] {
  const floors = new Set<string>();

  equipment.forEach((eq) => {
    const floor = extractFloorFromCode((eq as any).code);
    if (floor) floors.add(floor);
  });

  // Sort naturally: B1 first, then L0-L9, then R last
  return Array.from(floors).sort((a, b) => {
    // B1 first
    if (a === 'B1') return -1;
    if (b === 'B1') return 1;

    // G (Ground) early
    if (a === 'G') return -1;
    if (b === 'G') return 1;

    // L levels in numeric order
    const aIsL = a.match(/L(\d+)/);
    const bIsL = b.match(/L(\d+)/);
    if (aIsL && bIsL) {
      return parseInt(aIsL[1]) - parseInt(bIsL[1]);
    }
    if (aIsL) return -1;
    if (bIsL) return 1;

    // R (Roof) last
    if (a === 'R') return 1;
    if (b === 'R') return -1;

    return a.localeCompare(b);
  });
}

/**
 * Generate Y coordinate for 3D rendering based on floor code
 * Each floor is 3 units tall
 */
export function getFloorY(floorCode: string): number {
  // Y offsets aligned with BuildingModel.tsx slab positions (+0.5 to sit ON the slab)
  // BuildingModel slabs: B1=0, G/L0=3, L1=6, L2=9, R=12
  const baseY: Record<string, number> = {
    B1: 0.5,   // Basement slab at Y=0
    G: 3.5,    // Ground slab at Y=3
    L0: 3.5,   // Ground (alternative)
  };

  if (baseY[floorCode]) return baseY[floorCode];

  // Parse L# and calculate: L1=6.5, L2=9.5, L3=12.5, etc.
  const match = floorCode.match(/L(\d+)/);
  if (match) {
    const level = parseInt(match[1]);
    return 3.5 + level * 3; // L1=6.5, L2=9.5, L3=12.5
  }

  // Roof slab at Y=12 in BuildingModel → equipment at 12.5
  if (floorCode === 'R') return 12.5;

  // Default to ground if unknown
  return 3.5;
}

/**
 * Generate floor selector ID (for UI state management)
 * IDs are sequential: B1=-1, G/L0=1, L1=2, L2=3, ..., L9=12, R=13
 */
export function getFloorId(floorCode: string): number {
  if (floorCode === 'B1') return 0;
  if (floorCode === 'G' || floorCode === 'L0') return 1;

  const match = floorCode.match(/L(\d+)/);
  if (match) {
    const level = parseInt(match[1]);
    return level + 1; // L1=2, L2=3, L3=4, ..., L9=10
  }

  if (floorCode === 'R') return 4; // Roof — matches BuildingModel floor id=4

  return 1; // Default to ground
}

/**
 * Convert floor code to human-readable label
 */
export function getFloorLabel(floorCode: string): string {
  const labels: Record<string, string> = {
    B1: 'B1 - Basement',
    B2: 'B2 - Basement 2',
    G: 'G - Ground',
    L0: 'L0 - Ground',
    L1: 'L1 - Level 1',
    L2: 'L2 - Level 2',
    L3: 'L3 - Level 3',
    L4: 'L4 - Level 4',
    L5: 'L5 - Level 5',
    L6: 'L6 - Level 6',
    L7: 'L7 - Level 7',
    L8: 'L8 - Level 8',
    L9: 'L9 - Level 9',
    R: 'R - Roof',
  };

  return labels[floorCode] || floorCode;
}

/**
 * Generate Floor objects from floor codes
 */
export function generateFloors(floorCodes: string[]): Floor[] {
  return floorCodes.map((code) => ({
    id: getFloorId(code),
    label: getFloorLabel(code),
    code,
    y: getFloorY(code),
  }));
}
