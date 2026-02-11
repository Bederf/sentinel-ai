import { EquipmentMarker } from './EquipmentMarker';
import type { Equipment, ZoneCentroid } from '@/lib/api/sites';

interface EquipmentMarkersProps {
  equipment: Equipment[];
  selectedFloors: Set<number>;
  onEquipmentClick: (id: string) => void;
  zoneCentroids?: Record<string, ZoneCentroid>;
}

/**
 * Building from BuildingModel.tsx: Width=30 (X: -15..+15), Depth=20 (Z: -10..+10)
 * Landing page building:           Width=12 (X: -6..+6),   Depth=8  (Z: -4..+4)
 *
 * 5 zones (A–E) spread across building width.
 * Equipment x/z offsets kept SMALL (max ±2) so nothing escapes the floor slab.
 */

// Fallback zone centroids: 5 zones across building width, centered on Z
const ZONE_FALLBACK: Record<string, { x: number; z: number }> = {
  A: { x: -10, z: 0 },
  B: { x: -5,  z: 0 },
  C: { x:  0,  z: 0 },
  D: { x:  5,  z: 0 },
  E: { x:  10, z: 0 },
};

// Small type offsets WITHIN a zone (max ±2 to stay in bounds)
const TYPE_OFFSET: Record<string, [number, number]> = {
  chiller:       [-1.5, -2],    ahu:           [ 1.5,  2],
  fcu:           [-0.5,  0.5],  fcuventilation:[-0.5,  0.5],
  vav:           [ 0,   -1],    cooling_tower: [-2,   -2],
  ct:            [-2,   -2],    generator:     [-1.5,  1.5],
  gen:           [-1.5,  1.5],  dali:          [ 0.5,  0.5],
  luminaire:     [ 0.5,  0.5],  lum:           [ 0.5,  0.5],
  meter:         [-1,    1.5],  mtr:           [-1,    1.5],
  ups:           [ 0,   -1.5],  ats:           [-1,   -1.5],
  switch:        [ 1,    1],    db:            [ 1,    1],
  distribution_board: [1, 1],   transformer:   [-1.5,  1],
  tx:            [-1.5,  1],    fire:          [ 1.5, -1],
  sprinkler:     [ 1.5, -1],    cctv:          [ 2,    1],
  access:        [ 2,    0],    acc:           [ 2,    0],
  sensor:        [ 0,    0],    pump:          [-1,   -1],
  boiler:        [ 1,   -1.5],  hvac_zone:     [ 0,    0],
  solar:         [ 0,    2],    bess:          [ 1.5, -2],
  mcc:           [-1,   -1],    fire_panel:    [ 1.5, -1],
};

// Floor code → Y height (BuildingModel floor.y + 0.5 offset above slab)
const FLOOR_Y: Record<string, number> = {
  B2: -2.5, B1: 0.5, G: 3.5, L0: 3.5, L1: 6.5, L2: 9.5, R: 12.5,
};

// Floor code → floor selector ID
const FLOOR_ID: Record<string, number> = {
  B2: -1, B1: 0, G: 1, L0: 1, L1: 2, L2: 3, R: 4,
};

function clamp(val: number, min: number, max: number): number {
  return Math.max(min, Math.min(max, val));
}

/** Extract floor from code: S002-CHILLER-B1-001 → B1 */
function extractFloor(code: string): string {
  const m = code.match(/-(B\d|G|L\d+|R)-/i);
  return m ? m[1].toUpperCase() : 'G';
}

/** Extract zone letter from end of code: ...-A or ...-001 (numeric → distribute) */
function extractZoneLetter(code: string): string {
  const letterMatch = code.match(/-([A-E])$/i);
  if (letterMatch) return letterMatch[1].toUpperCase();
  const numMatch = code.match(/-(\d+)$/);
  if (numMatch) {
    const idx = (parseInt(numMatch[1], 10) - 1) % 5;
    return String.fromCharCode(65 + idx);
  }
  return 'C'; // center
}

function getEquipmentPosition(
  equipment: Equipment,
  zoneCentroids?: Record<string, ZoneCentroid>,
): [number, number, number] {
  const code = (equipment as any).code || equipment.id || '';
  const type = ((equipment as any).equipment_type || (equipment as any).type || '').toLowerCase();

  const floorCode = extractFloor(code);
  const y = FLOOR_Y[floorCode] ?? FLOOR_Y['G'];
  const zoneLetter = extractZoneLetter(code);
  const normalizedFloor = floorCode === 'G' ? 'L0' : floorCode;
  const [dx, dz] = TYPE_OFFSET[type] || [0, 0];

  // Try API centroids first
  if (zoneCentroids) {
    const zoneId = `Zone-${normalizedFloor}-${zoneLetter}`;
    const centroid = zoneCentroids[zoneId];
    if (centroid) {
      return [
        clamp(centroid.x + dx, -14, 14),
        y,
        clamp(centroid.z + dz, -9, 9),
      ];
    }
  }

  // Fallback: 5-zone layout
  const fb = ZONE_FALLBACK[zoneLetter] || ZONE_FALLBACK['C'];
  return [
    clamp(fb.x + dx, -14, 14),
    y,
    clamp(fb.z + dz, -9, 9),
  ];
}

function getFloorIdFromCode(code: string): number {
  return FLOOR_ID[extractFloor(code)] ?? 1;
}

export function EquipmentMarkers({
  equipment,
  selectedFloors,
  onEquipmentClick,
  zoneCentroids,
}: EquipmentMarkersProps) {
  return (
    <group>
      {equipment.map((eq) => {
        const code = (eq as any).code || eq.id || '';
        const floorId = getFloorIdFromCode(code);
        if (!selectedFloors.has(floorId)) return null;

        const position = getEquipmentPosition(eq, zoneCentroids);
        return (
          <EquipmentMarker
            key={eq.id || code}
            equipment={eq}
            position={position}
            onClick={() => onEquipmentClick(eq.id || code)}
          />
        );
      })}
    </group>
  );
}
