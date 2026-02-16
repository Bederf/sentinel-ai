import { useState, useMemo, useEffect } from 'react';
import { Canvas } from '@react-three/fiber';
import { OrbitControls, PerspectiveCamera } from '@react-three/drei';
import { X, Snowflake, Wind, Zap, BarChart3, Lightbulb, Flame, Droplet, Video, Lock, Radio, Circle, Wrench, Gauge, Thermometer } from 'lucide-react';
import { BuildingSelector } from '@/components/BuildingSelector';
import type { ZoneCentroid, Site } from '@/lib/api/sites';
import { BuildingModel } from './BuildingModel';
import { EquipmentMarkers } from './EquipmentMarkers';
import { EquipmentDetailPanel } from './EquipmentDetailPanel';
import { FloorSelector } from './FloorSelector';
import { StatsBar } from './StatsBar';
import { AlertBanner } from './AlertBanner';
import { Compass } from '../3d/Compass';
import { FloorPlan2D } from './FloorPlan2D';
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
import {
  generateFloorsFromEquipment,
  generateFloors,
  getFloorY,
} from '@/utils/floorExtraction';

// Equipment type to icon mapping (using Lucide React for reliability)
const EQUIPMENT_ICONS: Record<string, React.ReactNode> = {
  'chiller': <Snowflake className="w-4 h-4" />,
  'ahu': <Wind className="w-4 h-4" />,
  'fcu': <Wind className="w-4 h-4" />,
  'vav': <Wind className="w-4 h-4" />,
  'cooling_tower': <Droplet className="w-4 h-4" />,
  'ct': <Droplet className="w-4 h-4" />,
  'generator': <Zap className="w-4 h-4" />,
  'gen': <Zap className="w-4 h-4" />,
  'ups': <Zap className="w-4 h-4" />,
  'transformer': <Wrench className="w-4 h-4" />,
  'tx': <Wrench className="w-4 h-4" />,
  'ats': <Zap className="w-4 h-4" />,
  'dali': <Lightbulb className="w-4 h-4" />,
  'luminaire': <Lightbulb className="w-4 h-4" />,
  'lum': <Lightbulb className="w-4 h-4" />,
  'meter': <BarChart3 className="w-4 h-4" />,
  'mtr': <BarChart3 className="w-4 h-4" />,
  'fire': <Flame className="w-4 h-4" />,
  'sprinkler': <Droplet className="w-4 h-4" />,
  'cctv': <Video className="w-4 h-4" />,
  'access': <Lock className="w-4 h-4" />,
  'acc': <Lock className="w-4 h-4" />,
  'sensor': <Radio className="w-4 h-4" />,
  'pump': <Circle className="w-4 h-4" />,
  'boiler': <Flame className="w-4 h-4" />,
  'hvac_zone': <Wind className="w-4 h-4" />,
  'jace': <Wind className="w-4 h-4" />,
  'lift': <Zap className="w-4 h-4" />,
  'cold': <Snowflake className="w-4 h-4" />,
  'medgas': <Radio className="w-4 h-4" />,
  'msb': <Zap className="w-4 h-4" />,
  'kef': <Wind className="w-4 h-4" />,
  'split': <Thermometer className="w-4 h-4" />,
};

// Default icon for unknown equipment types
const DEFAULT_ICON = <Gauge className="w-4 h-4" />;

export function DigitalTwin() {
  // Site selection state - auto-select first site when loaded
  const [selectedBuildingId, setSelectedBuildingId] = useState<string>('');

  // Load available sites via React Query hook (auto-caching, deduplication)
  const { data: sites = [], isLoading: sitesLoading } = useSitesList();

  // Auto-select site-002 as default
  useEffect(() => {
    if (!selectedBuildingId && sites.length > 0) {
      // Try to select site-002 first
      const site002 = sites.find(s => s.code === 'site-002' || s.id === 'site-002');
      if (site002) {
        setSelectedBuildingId(site002.id);
      } else {
        // Fallback to first site if site-002 not found
        setSelectedBuildingId(sites[0].id);
      }
    }
  }, [sites, selectedBuildingId]);

  const buildingId = selectedBuildingId;
  const { equipment, loading, error } = useEquipmentData(buildingId);
  const [selectedEquipment, setSelectedEquipment] = useState<string | null>(null);
  const [equipmentTypeFilter, setEquipmentTypeFilter] = useState<string | null>(null);
  // View mode toggle: 2D floor plan or 3D visualization (default: 3D)
  const [viewMode, setViewMode] = useState<'2D' | '3D'>('3D');
  // Equipment detail panel minimize state (default: minimized)
  const [isEquipmentPanelMinimized, setIsEquipmentPanelMinimized] = useState(true);

  // Dynamically generate floors from equipment data
  const dynamicFloors = useMemo(() => {
    if (equipment.length === 0) return [];
    const floorCodes = generateFloorsFromEquipment(equipment);
    return generateFloors(floorCodes);
  }, [equipment]);

  // Initialize selected floors when floors change
  const [selectedFloors, setSelectedFloors] = useState<Set<number>>(new Set());

  useEffect(() => {
    if (dynamicFloors.length > 0 && selectedFloors.size === 0) {
      // Auto-select ground floor (L0/G) or first floor if available
      const groundFloor = dynamicFloors.find((f) => f.code === 'L0' || f.code === 'G');
      if (groundFloor) {
        setSelectedFloors(new Set([groundFloor.id]));
      } else {
        setSelectedFloors(new Set([dynamicFloors[0].id]));
      }
    }
  }, [dynamicFloors]);

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
        const floorY = getFloorY(floor);

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
    <div className="matrix-theme h-full flex flex-col bg-gradient-to-br from-[#060E18] via-[#0a1420] to-[#060E18]">
      {/* Alert Banner */}
      <AlertBanner equipment={equipment} />

      {/* Site Selector and Equipment Filter */}
      <div className="px-6 py-4 border-b" style={{ borderColor: 'var(--color-matrix-green)', opacity: 0.3 }}>
        <div className="flex items-center justify-between gap-4 mb-4">
          <div className="flex items-center gap-3">
            <label className="text-sm font-medium" style={{ color: 'var(--color-sentinel-text-secondary)' }}>
              Building:
            </label>
            <BuildingSelector
              value={selectedBuildingId}
              onChange={setSelectedBuildingId}
              sites={sites}
              disabled={sitesLoading}
            />
          </div>

          {/* 2D/3D Toggle - Moved to header next to building selector */}
            <div className="flex items-center gap-2 ml-4 pl-4 border-l" style={{ borderColor: 'var(--color-sentinel-border)' }}>
              <button
                onClick={() => setViewMode('3D')}
                className={`matrix-btn ${
                  viewMode === '3D' ? 'matrix-btn-active' : ''
                }`}
              >
                3D
              </button>
              <button
                onClick={() => setViewMode('2D')}
                className={`matrix-btn ${
                  viewMode === '2D' ? 'matrix-btn-active' : ''
                }`}
              >
                2D
              </button>
            </div>
          </div>

          {/* Equipment count */}
          <div className="text-sm font-medium" style={{ color: 'var(--color-sentinel-text-secondary)' }}>
            Total Equipment: <span style={{ color: 'var(--color-sentinel-text-primary)' }}>{filteredEquipment.length}</span>
          </div>

        {/* Equipment Type Filter - Professional HUD-style buttons */}
        <div className="flex flex-wrap gap-2">
          <button
            onClick={() => setEquipmentTypeFilter(null)}
            className={`matrix-btn ${
              !equipmentTypeFilter ? 'matrix-btn-active' : ''
            }`}
          >
            ALL ({equipment.length})
          </button>

          {equipmentTypes.map((type) => (
            <button
              key={type}
              onClick={() => setEquipmentTypeFilter(equipmentTypeFilter === type ? null : type)}
              className={`matrix-btn ${
                equipmentTypeFilter === type ? 'matrix-btn-active' : ''
              }`}
            >
              <span className="flex items-center">{EQUIPMENT_ICONS[type] || DEFAULT_ICON}</span>
              <span>{type.toUpperCase()}</span>
              <span className="text-xs opacity-75">({equipmentCountByType[type] || 0})</span>
            </button>
          ))}
        </div>
      </div>

      {/* Stats Bar */}
      <StatsBar equipment={filteredEquipment} selectedFloors={selectedFloors} />

      {/* Main Canvas and Controls */}
      <div className="flex-1 relative overflow-hidden">
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
          floors={dynamicFloors}
          selectedFloors={selectedFloors}
          onToggle={toggleFloor}
          onIsolate={isolateFloor}
        />

        {/* Filter indicator overlay */}
        {equipmentTypeFilter && (
          <div className="absolute top-4 right-20 bg-blue-600 text-white px-4 py-2 rounded-lg shadow-lg flex items-center gap-2">
            <span className="text-sm font-medium flex items-center gap-2">
              Filtering: {EQUIPMENT_ICONS[equipmentTypeFilter] || DEFAULT_ICON} {equipmentTypeFilter.toUpperCase()}
            </span>
            <button
              onClick={() => setEquipmentTypeFilter(null)}
              className="hover:bg-blue-700 p-1 rounded transition"
            >
              <X className="h-4 w-4" />
            </button>
          </div>
        )}

        {/* Equipment Detail Panel - Right side overlay */}
        {selectedEquipmentData && (
          <>
            {/* Minimize/Expand Button */}
            <button
              onClick={() => setIsEquipmentPanelMinimized(!isEquipmentPanelMinimized)}
              className="absolute right-2 top-2 z-50 p-2 rounded-lg transition-colors hover:bg-opacity-80"
              style={{
                background: 'var(--color-sentinel-bg-secondary)',
                border: '1px solid var(--color-sentinel-border)',
                color: 'var(--color-sentinel-text-primary)'
              }}
              title={isEquipmentPanelMinimized ? 'Expand equipment panel' : 'Minimize equipment panel'}
            >
              {isEquipmentPanelMinimized ? '📋' : '→'}
            </button>

            {/* Equipment Detail Panel */}
            {!isEquipmentPanelMinimized && (
              <div className="absolute right-0 top-0 bottom-0 w-96 shadow-2xl overflow-y-auto z-50"
                style={{ 
                  borderLeft: '2px solid var(--color-sentinel-accent)',
                  borderColor: 'var(--color-sentinel-border)',
                  background: 'var(--color-sentinel-bg-secondary)'
                }}>
                <EquipmentDetailPanel
                  equipment={selectedEquipmentData}
                  onClose={() => setSelectedEquipment(null)}
                />
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}
