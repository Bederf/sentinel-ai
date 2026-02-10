import { useState, useMemo, useEffect } from 'react';
import { Canvas } from '@react-three/fiber';
import { OrbitControls, PerspectiveCamera } from '@react-three/drei';
import type { ZoneCentroid } from '@/lib/api/sites';
import { sitesApi } from '@/lib/api/sites';
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
  // Use building ID 'site-002' (Sandton City Office Tower)
  const buildingId = 'site-002';
  const { equipment, loading, error } = useEquipmentData(buildingId);
  const [selectedEquipment, setSelectedEquipment] = useState<string | null>(null);
  const [selectedFloors, setSelectedFloors] = useState<Set<number>>(new Set([0, 1, 2, 3, 4]));
  const [zoneCentroids, setZoneCentroids] = useState<Record<string, ZoneCentroid>>({});
  const [_centroidsLoading, _setCentroidsLoading] = useState(false);
  const [_centroidsError, _setCentroidsError] = useState<string | null>(null);

  // Load zone centroids for accurate equipment positioning
  useEffect(() => {
    async function loadCentroids() {
      if (!buildingId) return;

      _setCentroidsLoading(true);
      _setCentroidsError(null);

      try {
        const response = await sitesApi.getZoneCentroids(buildingId);
        if (response && response.centroids) {
          setZoneCentroids(response.centroids);
        }
      } catch (err) {
        const errorMsg = err instanceof Error ? err.message : 'Failed to load zone centroids';
        _setCentroidsError(errorMsg);
        console.warn('Failed to load zone centroids, using fallback positioning:', errorMsg);
        // Don't throw - continue with fallback zone letter offsets
      } finally {
        _setCentroidsLoading(false);
      }
    }

    loadCentroids();
  }, [buildingId]);

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

  // Loading state
  if (loading && equipment.length === 0) {
    return (
      <div className="h-full flex items-center justify-center bg-gradient-to-b from-slate-900 to-slate-800">
        <div className="text-center">
          <div className="mb-4">
            <div className="inline-block">
              <div className="animate-spin rounded-full h-16 w-16 border-4 border-slate-600 border-t-blue-500" />
            </div>
          </div>
          <p className="text-xl font-semibold text-slate-100 mb-2">Loading Building Data</p>
          <p className="text-sm text-slate-400">Fetching equipment from Supabase...</p>
        </div>
      </div>
    );
  }

  // Error state
  if (error) {
    return (
      <div className="h-full flex items-center justify-center bg-gradient-to-b from-slate-900 to-slate-800">
        <div className="text-center">
          <div className="mb-4 text-6xl">⚠️</div>
          <p className="text-xl font-semibold text-red-400 mb-2">Failed to Load Equipment</p>
          <p className="text-sm text-slate-400 max-w-md">{error}</p>
          <button
            onClick={() => window.location.reload()}
            className="mt-6 px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-lg text-sm font-medium transition"
          >
            Retry
          </button>
        </div>
      </div>
    );
  }

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
            zoneCentroids={Object.keys(zoneCentroids).length > 0 ? zoneCentroids : undefined}
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
