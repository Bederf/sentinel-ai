import { EquipmentMarker } from './EquipmentMarker';
import type { Equipment, ZoneCentroid } from '@/lib/api/sites';

interface EquipmentMarkersProps {
  equipment: Equipment[];
  selectedFloors: Set<number>;
  onEquipmentClick: (id: string) => void;
  zoneCentroids?: Record<string, ZoneCentroid>;
}

/**
 * Type-specific position offsets from zone centroid.
 * Applied relative to zone centroid to spread equipment naturally within zone.
 */
const TYPE_OFFSET_MAP: Record<string, [number, number]> = {
  'chiller': [-12, -8],      // Plant room - back left
  'ahu': [10, 8],            // Plant room - back right
  'fcu': [-1, 0],            // Slightly left of center
  'fcuventilation': [-1, 0],
  'vav': [0, -2],            // Slightly front
  'cooling_tower': [-10, -10],
  'ct': [-10, -10],
  'generator': [-14, 0],
  'gen': [-14, 0],
  'dali': [1, 1],            // Spread across zone
  'luminaire': [1, 1],
  'lum': [1, 1],
  'meter': [-2, 5],
  'mtr': [-2, 5],
  'ups': [0, -5],
  'ats': [-3, -5],
  'switch': [5, 5],
  'db': [5, 5],
  'distribution_board': [5, 5],
  'transformer': [-8, 8],
  'tx': [-8, 8],
  'fire': [10, -5],
  'sprinkler': [10, -5],
  'cctv': [12, 5],
  'access': [12, 0],
  'acc': [12, 0],
};

function getEquipmentPosition(
  equipment: Equipment,
  zoneCentroids?: Record<string, ZoneCentroid>
): [number, number, number] {
  const code = (equipment as any).code || '';

  // Extract floor from code (e.g., "S002-CHILLER-B1-001" → B1)
  const floorMatch = code.match(/-(B\d|G|L\d+|R)-/);
  const floorCode = floorMatch ? floorMatch[1] : 'G';

  // Normalize floor code (L0 instead of G for consistency)
  const normalizedFloor = floorCode === 'G' ? 'L0' : floorCode;

  // Map floor to Y coordinate (height)
  const floorHeights: Record<string, number> = {
    'B1': 0.5,
    'B2': -2.5,
    'G': 3.5,
    'L0': 3.5,
    'L1': 6.5,
    'L2': 9.5,
    'R': 12.5,
  };
  const y = floorHeights[normalizedFloor] || floorHeights[floorCode] || 3.5;

  // Extract zone letter from equipment code
  // Supports both formats: Zone-L1-A (end match) or numeric (e.g., 001)
  const zoneMatch = code.match(/-([A-Z0-9]+)$/);
  const zoneLetterOrNum = zoneMatch ? zoneMatch[1] : 'A';
  const zoneLetter = /^[A-Z]$/.test(zoneLetterOrNum) ? zoneLetterOrNum : 'A';

  // Get type-specific offset
  const type = (equipment as any).equipment_type?.toLowerCase() || '';
  const [typeOffsetX, typeOffsetZ] = TYPE_OFFSET_MAP[type] || [0, 0];

  // Try to use zone centroids for accurate positioning
  if (zoneCentroids) {
    const zoneId = `Zone-${normalizedFloor}-${zoneLetter}`;
    const centroid = zoneCentroids[zoneId];

    if (centroid) {
      // Position relative to zone centroid with type offset
      return [centroid.x + typeOffsetX, y, centroid.z + typeOffsetZ];
    }
  }

  // Fallback: Use simple zone letter offset
  // Old format: A=0, B=6, C=12, D=18, E=24 (6m per zone × 5 zones = 30m)
  const zoneOffset = (zoneLetter.charCodeAt(0) - 65) * 6;
  const baseX = zoneOffset + 3;    // Center of zone
  const baseZ = 10;                // Mid-depth of zone

  // Apply type offset to baseline position
  return [baseX + typeOffsetX, y, baseZ + typeOffsetZ];
}

function getFloorIdFromCode(code: string): number {
  const floorMatch = code.match(/-(B\d|G|L\d+|R)-/);
  const floorCode = floorMatch ? floorMatch[1] : 'G';

  const floorMap: Record<string, number> = {
    'B1': 0,
    'B2': -1,
    'G': 1,
    'L1': 2,
    'L2': 3,
    'R': 4,
  };

  return floorMap[floorCode] ?? 1;
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
        const floorId = getFloorIdFromCode((eq as any).code || '');
        if (!selectedFloors.has(floorId)) {
          return null;
        }

        // Use zone centroids for accurate positioning, fallback to zone letter offsets
        const position = getEquipmentPosition(eq, zoneCentroids);
        return (
          <EquipmentMarker
            key={eq.id || (eq as any).code}
            equipment={eq}
            position={position}
            onClick={() => onEquipmentClick(eq.id || (eq as any).code)}
          />
        );
      })}
    </group>
  );
}
