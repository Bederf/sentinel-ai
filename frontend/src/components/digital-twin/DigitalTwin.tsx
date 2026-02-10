import { useState, useMemo } from 'react';
import { Canvas } from '@react-three/fiber';
import { OrbitControls, PerspectiveCamera } from '@react-three/drei';
import { BuildingModel } from './BuildingModel';
import { EquipmentMarkers } from './EquipmentMarkers';
import { EquipmentDetailPanel } from './EquipmentDetailPanel';
import { FloorSelector } from './FloorSelector';
import { StatsBar } from './StatsBar';
import { AlertBanner } from './AlertBanner';
import { useEquipmentData } from '@/hooks/useEquipmentData';

const FLOORS = [
  { id: 0, label: 'B1 - Basement', code: 'B1' },
  { id: 1, label: 'G - Ground', code: 'G' },
  { id: 2, label: 'L1 - First Floor', code: 'L1' },
  { id: 3, label: 'L2 - Second Floor', code: 'L2' },
  { id: 4, label: 'R - Roof', code: 'R' },
];

export function DigitalTwin() {
  const { equipment } = useEquipmentData('site-002');
  const [selectedEquipment, setSelectedEquipment] = useState<string | null>(null);
  const [selectedFloors, setSelectedFloors] = useState<Set<number>>(new Set([0, 1, 2, 3, 4]));

  const toggleFloor = (floor: number) => {
    const newFloors = new Set(selectedFloors);
    if (newFloors.has(floor)) {
      newFloors.delete(floor);
    } else {
      newFloors.add(floor);
    }
    setSelectedFloors(newFloors);
  };

  const isolateFloor = (floor: number) => {
    setSelectedFloors(new Set([floor]));
  };

  // Find selected equipment data
  const selectedEquipmentData = useMemo(
    () => equipment.find((e) => e.id === selectedEquipment || (e as any).code === selectedEquipment),
    [equipment, selectedEquipment]
  );

  return (
    <div className="h-full flex flex-col" style={{ background: 'var(--color-sentinel-bg-canvas)' }}>
      {/* Alert Banner */}
      <AlertBanner equipment={equipment} />

      {/* Stats Bar */}
      <StatsBar equipment={equipment} selectedFloors={selectedFloors} />

      {/* Main 3D Canvas and Controls */}
      <div className="flex-1 relative overflow-hidden">
        <Canvas>
          {/* Lighting */}
          <ambientLight intensity={0.5} />
          <directionalLight position={[10, 10, 5]} intensity={0.8} />

          {/* Camera */}
          <PerspectiveCamera makeDefault position={[15, 12, 15]} fov={50} />

          {/* Building */}
          <BuildingModel
            selectedFloors={selectedFloors}
            onFloorClick={toggleFloor}
            onFloorDoubleClick={isolateFloor}
          />

          {/* Equipment Markers */}
          <EquipmentMarkers
            equipment={equipment}
            selectedFloors={selectedFloors}
            onEquipmentClick={(id) => setSelectedEquipment(id)}
          />

          {/* Controls */}
          <OrbitControls
            enableDamping
            dampingFactor={0.05}
            minDistance={10}
            maxDistance={50}
            autoRotate={false}
          />
        </Canvas>

        {/* Floor Selector Overlay */}
        <FloorSelector
          floors={FLOORS}
          selectedFloors={selectedFloors}
          onToggle={toggleFloor}
          onIsolate={isolateFloor}
        />
      </div>

      {/* Equipment Detail Panel */}
      {selectedEquipmentData && (
        <EquipmentDetailPanel
          equipment={selectedEquipmentData}
          onClose={() => setSelectedEquipment(null)}
        />
      )}
    </div>
  );
}
