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
  const floorCode = floorMatch ? floorMatch[1] : 'L0';

  // Normalize floor code (L0 is ground, G is legacy)
  const normalizedFloor = floorCode === 'G' ? 'L0' : floorCode;

  // Map floor to Y coordinate (height)
  // Outdoor equipment (Roof, Basement) positioned outside building envelope
  const floorHeights: Record<string, number> = {
    'B1': -3,       // Basement: below ground level
    'B2': -5,       // Deep basement
    'G': 3.5,
    'L0': 3.5,      // Ground floor (inside)
    'L1': 6.5,      // First floor (inside)
    'L2': 9.5,      // Second floor (inside)
    'R': 15,        // Roof: above building envelope
  };
  const y = floorHeights[normalizedFloor] || floorHeights[floorCode] || 3.5;

  // For outdoor equipment (Basement, Roof), position around building perimeter
  if (normalizedFloor === 'B1' || normalizedFloor === 'B2' || normalizedFloor === 'R') {
    // Extract numeric ID from code for perimeter distribution (e.g., "S002-CHILLER-B1-001" → 001)
    const numMatch = code.match(/-(\d+)$/);
    const itemNum = numMatch ? parseInt(numMatch[1], 10) : 0;
    
    // Distribute around building perimeter (30m × 20m building)
    // Position around edges at distance from center
    const buildingEdge = 20; // Distance from center to building edge
    const angleStep = (itemNum % 8) * (Math.PI / 4); // 8 positions around building
    
    const x = Math.sin(angleStep) * buildingEdge;
    const z = Math.cos(angleStep) * buildingEdge;
    
    return [x, y, z];
  }

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
  const floorCode = floorMatch ? floorMatch[1] : 'L0';

  const floorMap: Record<string, number> = {
    'B1': 0,
    'B2': -1,
    'G': 1,     // Legacy support for G (maps to same height as L0)
    'L0': 1,    // Ground floor (Level 0)
    'L1': 2,    // First floor
    'L2': 3,    // Second floor
    'R': 4,     // Roof
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
