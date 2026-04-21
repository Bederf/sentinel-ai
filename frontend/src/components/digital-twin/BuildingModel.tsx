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
    { id: 0, y: 0, width: 30, depth: 20, color: '#003d1a' },    // Basement - Dark forest green
    { id: 1, y: 3, width: 30, depth: 20, color: '#005723' },    // Ground - Medium forest green
    { id: 2, y: 6, width: 30, depth: 20, color: '#00712d' },    // L1 - Emerald green
    { id: 3, y: 9, width: 30, depth: 20, color: '#008b37' },    // L2 - Bright emerald
    { id: 4, y: 12, width: 25, depth: 15, color: '#00a541' },   // Roof - Matrix neon green
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
              emissive={floor.color}
              emissiveIntensity={0.3}
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
                color="var(--color-sentinel-green)"
                linewidth={1}
                transparent
                opacity={0.4}
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
            color="var(--color-sentinel-green)"
            linewidth={1}
            transparent
            opacity={0.2}
          />
        </lineSegments>
      </group>

      {/* Ambient green light for Matrix theme */}
      <pointLight position={[15, 8, 15]} color="var(--color-sentinel-green)" intensity={0.3} distance={50} />
    </group>
  );
}
