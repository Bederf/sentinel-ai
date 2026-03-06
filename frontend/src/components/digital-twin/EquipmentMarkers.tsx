import { EquipmentMarker } from './EquipmentMarker';
import type { Equipment } from '@/lib/api/sites';
import type { EquipmentPosition } from '@/utils/equipmentPositioning';
import { extractFloorFromCode, getFloorId } from '@/utils/floorExtraction';

interface EquipmentMarkersProps {
  equipment: Equipment[];
  selectedFloors: Set<number>;
  onEquipmentClick: (id: string) => void;
  equipmentPositions: Map<string, EquipmentPosition>;
}

function getFloorIdFromCode(code: string): number {
  return getFloorId(extractFloorFromCode(code) || 'L0');
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
