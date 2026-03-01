import { EquipmentMarker } from './EquipmentMarker';
import type { Equipment } from '@/lib/api/sites';
import type { EquipmentPosition } from '@/utils/equipmentPositioning';

interface EquipmentMarkersProps {
  equipment: Equipment[];
  selectedFloors: Set<number>;
  onEquipmentClick: (id: string) => void;
  equipmentPositions: Map<string, EquipmentPosition>;
}

// Floor code → floor selector ID
const FLOOR_ID: Record<string, number> = {
  B2: -1, B1: 0, G: 1, L0: 1, L1: 2, L2: 3, R: 4,
};

/** Extract floor from code: S002-CHILLER-B1-001 → B1 */
function extractFloor(code: string): string {
  const m = code.match(/-(B\d|G|L\d+|R)-/i);
  return m ? m[1].toUpperCase() : 'G';
}

function getFloorIdFromCode(code: string): number {
  return FLOOR_ID[extractFloor(code)] ?? 1;
}

function getPositionTuple(
  equipment: Equipment,
  equipmentPositions: Map<string, EquipmentPosition>,
): [number, number, number] | null {
  const pos = equipmentPositions.get(equipment.id);
  if (pos) return [pos.x, pos.y, pos.z];
  return null;
}

export function EquipmentMarkers({
  equipment,
  selectedFloors,
  onEquipmentClick,
  equipmentPositions,
}: EquipmentMarkersProps) {
  return (
    <group>
      {equipment.map((eq) => {
        const code = (eq as any).code || eq.id || '';
        const floorId = getFloorIdFromCode(code);
        if (!selectedFloors.has(floorId)) return null;

        const position = getPositionTuple(eq, equipmentPositions);
        if (!position) return null;

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
