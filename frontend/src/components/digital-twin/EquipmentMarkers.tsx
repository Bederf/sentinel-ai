import { EquipmentMarker } from './EquipmentMarker';
import type { Equipment } from '@/lib/api/sites';

interface EquipmentMarkersProps {
  equipment: Equipment[];
  selectedFloors: Set<number>;
  onEquipmentClick: (id: string) => void;
}

function getEquipmentPosition(equipment: Equipment): [number, number, number] {
  const code = (equipment as any).code || '';

  // Extract floor from code (e.g., "S002-CHILLER-B1-001" → B1)
  const floorMatch = code.match(/-(B\d|G|L\d+|R)-/);
  const floorCode = floorMatch ? floorMatch[1] : 'G';

  // Map floor to Y coordinate
  const floorHeights: Record<string, number> = {
    'B1': 0.5,
    'B2': -2.5,
    'G': 3.5,
    'L1': 6.5,
    'L2': 9.5,
    'R': 12.5,
  };
  const y = floorHeights[floorCode] || 3.5;

  // Extract zone letter for X/Z spread
  const zoneMatch = code.match(/-([A-Z])$/);
  const zone = zoneMatch ? zoneMatch[1].charCodeAt(0) - 65 : 0; // A=0, B=3, C=6...
  const zoneOffset = zone * 3;

  // Type-specific positioning
  const type = (equipment as any).equipment_type?.toLowerCase() || '';
  const typePositioning: Record<string, [number, number]> = {
    'chiller': [-12, -8],
    'ahu': [10, 8],
    'fcu': [zoneOffset - 10, zoneOffset - 5],
    'fcuventilation': [zoneOffset - 10, zoneOffset - 5],
    'vav': [zoneOffset - 8, zoneOffset - 3],
    'cooling_tower': [-10, -10],
    'ct': [-10, -10],
    'generator': [-14, 0],
    'gen': [-14, 0],
    'dali': [8, -8],
    'luminaire': [8, -8],
    'lum': [8, -8],
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

  const [xOffset, zOffset] = typePositioning[type] || [Math.random() * 6 - 3, Math.random() * 6 - 3];

  return [xOffset, y, zOffset];
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
}: EquipmentMarkersProps) {
  return (
    <group>
      {equipment.map((eq) => {
        const floorId = getFloorIdFromCode((eq as any).code || '');
        if (!selectedFloors.has(floorId)) {
          return null;
        }

        const position = getEquipmentPosition(eq);
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
