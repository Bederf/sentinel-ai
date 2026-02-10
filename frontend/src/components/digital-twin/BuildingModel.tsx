import { useRef } from 'react';
import { BoxGeometry } from 'three';

interface Floor {
  id: number;
  y: number;
  width: number;
  depth: number;
  color: string;
}

interface BuildingModelProps {
  selectedFloors: Set<number>;
  onFloorClick: (floor: number) => void;
  onFloorDoubleClick: (floor: number) => void;
}

export function BuildingModel({
  selectedFloors,
  onFloorClick,
  onFloorDoubleClick,
}: BuildingModelProps) {
  const floorRefs = useRef<any[]>([]);

  const floors: Floor[] = [
    { id: 0, y: 0, width: 30, depth: 20, color: '#8b5cf6' },    // Basement - purple
    { id: 1, y: 3, width: 30, depth: 20, color: '#06b6d4' },    // Ground - cyan
    { id: 2, y: 6, width: 30, depth: 20, color: '#0ea5e9' },    // L1 - blue
    { id: 3, y: 9, width: 30, depth: 20, color: '#3b82f6' },    // L2 - indigo
    { id: 4, y: 12, width: 25, depth: 15, color: '#6366f1' },   // Roof - indigo
  ];

  const handleFloorClick = (e: any, floor: number) => {
    e.stopPropagation();
    onFloorClick(floor);
  };

  const handleFloorDoubleClick = (e: any, floor: number) => {
    e.stopPropagation();
    onFloorDoubleClick(floor);
  };

  return (
    <group>
      {/* Floors */}
      {floors.map((floor, idx) => {
        const isSelected = selectedFloors.has(floor.id);
        return (
          <mesh
            key={floor.id}
            position={[0, floor.y, 0]}
            onClick={(e) => handleFloorClick(e, floor.id)}
            onDoubleClick={(e) => handleFloorDoubleClick(e, floor.id)}
            visible={isSelected}
            ref={(el) => (floorRefs.current[idx] = el)}
          >
            <boxGeometry args={[floor.width, 0.4, floor.depth]} />
            <meshStandardMaterial
              color={floor.color}
              transparent
              opacity={0.6}
              metalness={0.3}
              roughness={0.7}
            />
          </mesh>
        );
      })}

      {/* Floor edges for better visibility */}
      {floors.map((floor) => {
        const isSelected = selectedFloors.has(floor.id);
        if (!isSelected) return null;

        return (
          <group key={`edge-${floor.id}`} position={[0, floor.y, 0]}>
            <lineSegments>
              <edgesGeometry
                args={[new BoxGeometry(floor.width, 0.4, floor.depth)]}
                attach="geometry"
              />
              <lineBasicMaterial
                attach="material"
                color="#fff"
                linewidth={1}
                transparent
                opacity={0.3}
              />
            </lineSegments>
          </group>
        );
      })}

      {/* Building outline walls */}
      <group>
        <lineSegments>
          <edgesGeometry args={[new BoxGeometry(30, 15, 20)]} attach="geometry" />
          <lineBasicMaterial
            attach="material"
            color="#666"
            linewidth={1}
            transparent
            opacity={0.2}
          />
        </lineSegments>
      </group>
    </group>
  );
}
