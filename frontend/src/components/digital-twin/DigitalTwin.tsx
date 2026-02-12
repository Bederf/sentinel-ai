import { useState, useMemo, useEffect } from 'react';
import { Canvas } from '@react-three/fiber';
import { OrbitControls, PerspectiveCamera } from '@react-three/drei';
import { ChevronDown, X } from 'lucide-react';
import type { ZoneCentroid, Site } from '@/lib/api/sites';
import { sitesApi } from '@/lib/api/sites';
import { BuildingModel } from './BuildingModel';
import { EquipmentMarkers } from './EquipmentMarkers';
import { EquipmentDetailPanel } from './EquipmentDetailPanel';
import { FloorSelector } from './FloorSelector';
import { StatsBar } from './StatsBar';
import { AlertBanner } from './AlertBanner';
import { Compass } from '../3d/Compass';
import { FloorPlan2D } from './FloorPlan2D';
import { ViewToggle } from './ViewToggle';
import { useEquipmentData } from '@/hooks/useEquipmentData';
import { useSitesList } from '@/hooks/useSitesList';
import { useZoneCentroids } from '@/hooks/useZoneCentroids';
import { useZoneBounds } from '@/hooks/useZoneBounds';
import {
  distributeEquipmentInZone,
  extractFloor,
  extractZoneLetter,
  type EquipmentPosition,
} from '@/utils/equipmentPositioning';

const FLOORS = [
  { id: 0, label: 'B1 - Basement', code: 'B1' },
  { id: 1, label: 'L0 - Ground', code: 'L0' },
  { id: 2, label: 'L1 - First Floor', code: 'L1' },
  { id: 3, label: 'L2 - Second Floor', code: 'L2' },
  { id: 4, label: 'R - Roof', code: 'R' },
];

// Equipment type to icon/emoji mapping
const EQUIPMENT_ICONS: Record<string, string> = {
  'chiller': '❄️',
  'ahu': '🌬️',
  'fcu': '💨',
  'vav': '🎚️',
  'cooling_tower': '🌊',
  'ct': '🌊',
  'generator': '⚡',
  'gen': '⚡',
  'ups': '🔋',
  'transformer': '⚙️',
  'tx': '⚙️',
  'ats': '🔀',
  'dali': '💡',
  'luminaire': '💡',
  'lum': '💡',
  'meter': '📊',
  'mtr': '📊',
  'fire': '🔥',
  'sprinkler': '💧',
  'cctv': '📹',
  'access': '🔐',
  'acc': '🔐',
  'sensor': '📡',
  'pump': '🔵',
  'boiler': '🟠',
  'hvac_zone': '🎛️',
};

// Floor code → Y height (BuildingModel floor.y + 0.5 offset above slab)
const FLOOR_Y: Record<string, number> = {
  B2: -2.5,
  B1: 0.5,
  G: 3.5,
  L0: 3.5,
  L1: 6.5,
  L2: 9.5,
  R: 12.5,
};

// Floor code → floor selector ID
const FLOOR_ID: Record<string, number> = {
  B2: -1,
  B1: 0,
  G: 1,
  L0: 1,
  L1: 2,
  L2: 3,
  R: 4,
};

export function DigitalTwin() {
  // Site selection state - auto-select first site when loaded
  const [selectedBuildingId, setSelectedBuildingId] = useState<string>('');

  // Load available sites via React Query hook (auto-caching, deduplication)
  const { data: sites = [], isLoading: sitesLoading } = useSitesList();

  // Auto-select first site when sites load
  useEffect(() => {
    if (!selectedBuildingId && sites.length > 0) {
      setSelectedBuildingId(sites[0].id);
    }
  }, [sites, selectedBuildingId]);

  const buildingId = selectedBuildingId;
  const { equipment, loading, error } = useEquipmentData(buildingId);
  const [selectedEquipment, setSelectedEquipment] = useState<string | null>(null);
  // By default, only show ground floor (1) for performance - user can select more
  const [selectedFloors, setSelectedFloors] = useState<Set<number>>(new Set([1]));
  const [equipmentTypeFilter, setEquipmentTypeFilter] = useState<string | null>(null);
  // View mode toggle: 2D floor plan or 3D visualization (default: 3D)
  const [viewMode, setViewMode] = useState<'2D' | '3D'>('3D');

  // Load zone centroids via React Query hook (auto-caching, deduplication)
  const { data: zoneCentroids = {} } = useZoneCentroids(buildingId);

  // Load zone bounds for adaptive equipment positioning
  const zoneBounds = useZoneBounds(buildingId);

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

  // Extract unique equipment types from current equipment
  const equipmentTypes = useMemo(() => {
    const types = new Set<string>();
    equipment.forEach((eq) => {
      const type = ((eq as any).equipment_type || (eq as any).type || 'unknown').toLowerCase();
      if (type !== 'unknown') {
        types.add(type);
      }
    });
    return Array.from(types).sort();
  }, [equipment]);

  // Count equipment by type
  const equipmentCountByType = useMemo(() => {
    const counts: Record<string, number> = {};
    equipment.forEach((eq) => {
      const type = ((eq as any).equipment_type || (eq as any).type || 'unknown').toLowerCase();
      counts[type] = (counts[type] || 0) + 1;
    });
    return counts;
  }, [equipment]);

  // Filter equipment based on selected type
  const filteredEquipment = useMemo(() => {
    if (!equipmentTypeFilter) return equipment;
    return equipment.filter((eq) => {
      const type = ((eq as any).equipment_type || (eq as any).type || 'unknown').toLowerCase();
      return type === equipmentTypeFilter;
    });
  }, [equipment, equipmentTypeFilter]);

  // Pre-calculate equipment positions using new positioning algorithm
  // This is shared between 2D and 3D views to ensure consistency
  const equipmentPositions = useMemo(() => {
    const positions = new Map<string, EquipmentPosition>();

    // If zone bounds available, use adaptive grid distribution
    if (zoneBounds && Object.keys(zoneBounds).length > 0) {
      // Group equipment by zone
      const byZone: Record<string, typeof filteredEquipment> = {};
      filteredEquipment.forEach((eq) => {
        const code = (eq as any).code || eq.id || '';
        const floor = extractFloor(code);
        const zone = extractZoneLetter(code);
        const zoneKey = `Zone-${floor === 'G' ? 'L0' : floor}-${zone}`;

        if (!byZone[zoneKey]) byZone[zoneKey] = [];
        byZone[zoneKey].push(eq);
      });

      // Distribute each zone's equipment
      Object.entries(byZone).forEach(([zoneKey, zoneEquipment]) => {
        const bounds = zoneBounds[zoneKey];
        if (!bounds) return;

        const floor = zoneKey.split('-')[1] || 'L0';
        const floorY = FLOOR_Y[floor] || 3.5;

        const distributed = distributeEquipmentInZone(zoneEquipment, bounds, floorY);
        distributed.forEach((pos, id) => positions.set(id, pos));
      });
    }

    return positions;
  }, [filteredEquipment, zoneBounds]);

  // Find selected equipment data
  const selectedEquipmentData = useMemo(
    () =>
      filteredEquipment.find((e) => e.id === selectedEquipment || (e as any).code === selectedEquipment),
    [filteredEquipment, selectedEquipment]
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

      {/* Site Selector and Equipment Filter */}
      <div className="px-6 py-4 border-b" style={{ borderColor: 'var(--color-sentinel-border)' }}>
        <div className="flex items-center justify-between gap-4 mb-4">
          <div className="flex items-center gap-3">
            <label className="text-sm font-medium" style={{ color: 'var(--color-sentinel-text-secondary)' }}>
              Building:
            </label>
            <div className="relative w-64">
              <select
                value={selectedBuildingId}
                onChange={(e) => setSelectedBuildingId(e.target.value)}
                disabled={sitesLoading}
                className="w-full pl-3 pr-8 py-2 text-sm rounded appearance-none cursor-pointer"
                style={{
                  background: 'var(--color-sentinel-bg-secondary)',
                  border: '1px solid var(--color-sentinel-border)',
                  color: 'var(--color-sentinel-text-primary)',
                  outline: 'none',
                }}
              >
                {sites.length > 0 ? (
                  sites.map((site) => (
                    <option key={site.id} value={site.id}>
                      {site.name}
                    </option>
                  ))
                ) : (
                  <option key="no-sites" disabled value="">
                    {sitesLoading ? 'Loading sites...' : 'No buildings available'}
                  </option>
                )}
              </select>
              <ChevronDown
                className="absolute right-3 top-1/2 transform -translate-y-1/2 h-4 w-4 pointer-events-none"
                style={{ color: 'var(--color-sentinel-text-secondary)' }}
              />
            </div>
          </div>

          {/* Equipment count */}
          <div className="text-sm font-medium" style={{ color: 'var(--color-sentinel-text-secondary)' }}>
            Total Equipment: <span style={{ color: 'var(--color-sentinel-text-primary)' }}>{filteredEquipment.length}</span>
          </div>
        </div>

        {/* Equipment Type Filter - Professional HUD-style buttons */}
        <div className="flex flex-wrap gap-2">
          <button
            onClick={() => setEquipmentTypeFilter(null)}
            className={`px-3 py-1.5 text-sm font-medium rounded transition ${
              !equipmentTypeFilter
                ? 'bg-blue-600 text-white'
                : 'bg-slate-700 text-slate-300 hover:bg-slate-600'
            }`}
          >
            All ({equipment.length})
          </button>

          {equipmentTypes.map((type) => (
            <button
              key={type}
              onClick={() => setEquipmentTypeFilter(equipmentTypeFilter === type ? null : type)}
              className={`px-3 py-1.5 text-sm font-medium rounded transition flex items-center gap-2 ${
                equipmentTypeFilter === type
                  ? 'bg-blue-600 text-white'
                  : 'bg-slate-700 text-slate-300 hover:bg-slate-600'
              }`}
            >
              <span>{EQUIPMENT_ICONS[type] || '🏗️'}</span>
              <span>{type.toUpperCase()}</span>
              <span className="text-xs opacity-75">({equipmentCountByType[type] || 0})</span>
            </button>
          ))}
        </div>
      </div>

      {/* Stats Bar */}
      <StatsBar equipment={filteredEquipment} selectedFloors={selectedFloors} />

      {/* Main Canvas and Controls - 2D/3D Toggle */}
      <div className="flex-1 relative overflow-hidden">
        {/* View Toggle Button */}
        <ViewToggle viewMode={viewMode} onToggle={setViewMode} />

        {/* Conditional View Rendering */}
        {viewMode === '3D' ? (
          <Canvas>
            {/* Lighting */}
            <ambientLight intensity={0.5} />
            <directionalLight position={[10, 10, 5]} intensity={0.8} />

            {/* Compass for orientation */}
            <Compass />

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
              equipment={filteredEquipment}
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
        ) : (
          <FloorPlan2D
            equipment={filteredEquipment}
            selectedFloors={selectedFloors}
            zoneBounds={zoneBounds}
            equipmentPositions={equipmentPositions}
            onEquipmentClick={setSelectedEquipment}
            selectedEquipment={selectedEquipment}
          />
        )}

        {/* Floor Selector Overlay */}
        <FloorSelector
          floors={FLOORS}
          selectedFloors={selectedFloors}
          onToggle={toggleFloor}
          onIsolate={isolateFloor}
        />

        {/* Filter indicator overlay */}
        {equipmentTypeFilter && (
          <div className="absolute top-4 right-20 bg-blue-600 text-white px-4 py-2 rounded-lg shadow-lg flex items-center gap-2">
            <span className="text-sm font-medium">
              Filtering: {EQUIPMENT_ICONS[equipmentTypeFilter] || '🏗️'} {equipmentTypeFilter.toUpperCase()}
            </span>
            <button
              onClick={() => setEquipmentTypeFilter(null)}
              className="hover:bg-blue-700 p-1 rounded transition"
            >
              <X className="h-4 w-4" />
            </button>
          </div>
        )}
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
