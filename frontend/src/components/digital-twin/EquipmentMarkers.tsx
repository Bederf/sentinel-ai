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

  // Map floor to Y coordinate - MUST match BuildingModel.tsx floor positions
  // BuildingModel: B1=0, L0=3, L1=6, L2=9, R=12
  // Outdoor equipment positioned outside/above building
  const floorHeights: Record<string, number> = {
    'B1': 0,        // Basement - at ground level floor
    'B2': -2,       // Deep basement - below
    'G': 3,
    'L0': 3,        // Ground floor - matches building
    'L1': 6,        // First floor - matches building
    'L2': 9,        // Second floor - matches building
    'R': 14,        // Roof - above building (roof is at Y=12)
  };
  const y = floorHeights[normalizedFloor] || floorHeights[floorCode] || 3;

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

  // Fallback: Use zone letter offset within building bounds
  // Building is 30m × 20m centered at (0, 0)
  // X: -15 to +15, Z: -10 to +10
  // 5 zones (A-E) each 6m wide
  const zoneIndex = zoneLetter.charCodeAt(0) - 65; // A=0, B=1, C=2, D=3, E=4
  const baseX = -12 + (zoneIndex * 6);    // A=-12, B=-6, C=0, D=6, E=12 (zone centers)
  const baseZ = 0;                         // Center depth of zone

  // Apply type offset to baseline position
  return [baseX + typeOffsetX, y, baseZ + typeOffsetZ];
}

function getFloorIdFromCode(code: string): number {
  const floorMatch = code.match(/-(B\d|G|L\d+|R)-/);
  const floorCode = floorMatch ? floorMatch[1] : 'L0';

  // Floor IDs must match FLOORS array in DigitalTwin.tsx
  // B1(0), L0(1), L1(2), L2(3), R(4)
  const floorMap: Record<string, number> = {
    'B1': 0,    // Basement
    'B2': -1,   // Deep basement (not in building)
    'G': 1,     // Legacy: maps to L0
    'L0': 1,    // Ground floor
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
