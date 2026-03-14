import { useState, useMemo, useEffect, useRef } from 'react';
// @ts-nocheck
import { Canvas } from '@react-three/fiber';
import { OrbitControls, PerspectiveCamera } from '@react-three/drei';
import { X, Snowflake, Wind, Zap, BarChart3, Lightbulb, Flame, Droplet, Video, Lock, Radio, Circle, Wrench, Gauge, Thermometer, ChevronDown, Users, Workflow, History } from 'lucide-react';
import { OccupancySimulation, type Person } from '@/lib/occupancySimulation';
import { BuildingSelector } from '@/components/BuildingSelector';

import { BuildingModel } from './BuildingModel';
import { EquipmentMarkers } from './EquipmentMarkers';
import { EquipmentDetailPanel } from './EquipmentDetailPanel';
import { FloorSelector } from './FloorSelector';
import { StatsBar } from './StatsBar';
import { AlertBanner } from './AlertBanner';
import { Compass } from '../3d/Compass';
import { FloorPlan2D } from './FloorPlan2D';
import { PredictiveFaultOverlay } from './PredictiveFaultOverlay';
import { AnimatedEnergyFlow } from './AnimatedEnergyFlow';
import { HistoricalTimeline } from './HistoricalTimeline';
import { OccupancyMarkers3DFiber } from './OccupancyMarkers3DFiber';
import { useOccupancySync } from '@/hooks/useOccupancySync';
import { useEquipmentStatusSSE } from '@/hooks/useEquipmentStatusSSE';
import type { EnergyFlow } from '@/lib/api';
import { digitalTwinApi } from '@/lib/api';
import { useTheme } from '@/contexts/ThemeContext';
import { useEquipmentData } from '@/hooks/useEquipmentData';
import { useSitesList } from '@/hooks/useSitesList';

import { useZoneBounds } from '@/hooks/useZoneBounds';
import { useStoredPositions } from '@/hooks/useStoredPositions';
import {
  buildZoneKey,
  distributeEquipmentInZone,
  extractFloor,
  generateSyntheticZoneBounds,
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
  const { theme } = useTheme();

  // Site selection state - auto-select first site when loaded
  const [selectedSiteId, setSelectedSiteId] = useState<string>('');

  // Load available sites via React Query hook (auto-caching, deduplication)
  const { data: sites = [], isLoading: sitesLoading } = useSitesList();

  // Auto-select first available site as default
  useEffect(() => {
    if (!selectedSiteId && sites.length > 0) {
      setSelectedSiteId(sites[0].id);
    }
  }, [sites, selectedSiteId]);

  const siteId = selectedSiteId;
  const { equipment, loading, error } = useEquipmentData(siteId);
  const { equipmentUpdates: realtimeUpdates, predictions: ssePredicitions, isConnected: sseConnected } = useEquipmentStatusSSE(siteId);
  const [showPredictions, setShowPredictions] = useState(false);
  const [showEnergyFlows, setShowEnergyFlows] = useState(false);
  const [energyFlows, setEnergyFlows] = useState<EnergyFlow[]>([]);
  const [isTimeline, setIsTimeline] = useState(false);
  const [isTimelinePlaying, setIsTimelinePlaying] = useState(false);
  const [_timelineTimestamp, setTimelineTimestamp] = useState<Date | null>(null);
  const [selectedEquipment, setSelectedEquipment] = useState<string | null>(null);
  const [equipmentTypeFilter, setEquipmentTypeFilter] = useState<string | null>(null);
  const [equipmentDropdownOpen, setEquipmentDropdownOpen] = useState(false);
  const equipmentDropdownRef = useRef<HTMLDivElement>(null);

  // Close dropdown when clicking outside
  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (equipmentDropdownRef.current && !equipmentDropdownRef.current.contains(event.target as Node)) {
        setEquipmentDropdownOpen(false);
      }
    }
    if (equipmentDropdownOpen) {
      document.addEventListener('mousedown', handleClickOutside);
      return () => document.removeEventListener('mousedown', handleClickOutside);
    }
  }, [equipmentDropdownOpen]);

  // View mode toggle: 2D floor plan or 3D visualization (default: 3D)
  const [viewMode, setViewMode] = useState<'2D' | '3D'>('3D');
  // Equipment detail panel minimize state (default: minimized)
  const [isEquipmentPanelMinimized, setIsEquipmentPanelMinimized] = useState(true);

  // Occupancy simulation state
  const [occupancyEnabled, setOccupancyEnabled] = useState(true);
  const [people, setPeople] = useState<Person[]>([]);
  const simulationRef = useRef<OccupancySimulation | null>(null);

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
      // Auto-select ALL floors so all equipment is visible immediately
      setSelectedFloors(new Set(dynamicFloors.map(f => f.id)));
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [dynamicFloors]);

  // Initialize occupancy simulation engine
  useEffect(() => {
    if (!simulationRef.current) {
      // Create multi-floor zones for Phase 2 testing
      // This layout allows testing elevator transitions between floors
      const defaultZones = [
        // Floor 0 (Ground)
        { id: 'zone-1', name: 'Reception', x: -20, y: -20, w: 35, h: 35, floor: 0, maxOccupancy: 6, type: 'entry' as const },
        { id: 'zone-2', name: 'Workspace-A', x: 20, y: 20, w: 35, h: 35, floor: 0, maxOccupancy: 20, type: 'office' as const },
        { id: 'zone-4', name: 'Common', x: -20, y: -65, w: 35, h: 35, floor: 0, maxOccupancy: 8, type: 'common' as const },
        { id: 'zone-5', name: 'Utility', x: -65, y: 20, w: 35, h: 35, floor: 0, maxOccupancy: 2, type: 'utility' as const },

        // Floor 1 (Level 1) - For multi-floor testing
        { id: 'zone-3', name: 'Meeting-1', x: -65, y: -65, w: 35, h: 35, floor: 1, maxOccupancy: 10, type: 'meeting' as const },
        { id: 'zone-6', name: 'Meeting-2', x: -20, y: -65, w: 35, h: 35, floor: 1, maxOccupancy: 8, type: 'meeting' as const },
        { id: 'zone-7', name: 'Kitchen', x: 20, y: -65, w: 35, h: 35, floor: 1, maxOccupancy: 6, type: 'common' as const },
      ];
      simulationRef.current = new OccupancySimulation(defaultZones);

      // Spawn initial people for testing
      for (let i = 0; i < 15; i++) {
        const personas = ['worker', 'security', 'cleaner', 'visitor'] as const;
        const persona = personas[Math.floor(Math.random() * personas.length)];
        const zones = defaultZones.filter(z => z.type !== 'utility');
        const zone = zones[Math.floor(Math.random() * zones.length)];
        simulationRef.current.spawnPerson(persona, zone.id);
      }
    }
  }, []);

  // Animation loop (60fps)
  useEffect(() => {
    if (!occupancyEnabled || !simulationRef.current) return;

    let lastTime = performance.now();
    let animationFrameId: number;

    const animate = (currentTime: number) => {
      const deltaTime = (currentTime - lastTime) / 1000; // Convert to seconds
      lastTime = currentTime;

      // Update simulation
      const updatedPeople = simulationRef.current!.tick(deltaTime);
      setPeople(updatedPeople);

      animationFrameId = requestAnimationFrame(animate);
    };

    animationFrameId = requestAnimationFrame(animate);
    return () => cancelAnimationFrame(animationFrameId);
  }, [occupancyEnabled]);

  // Energy flow polling (every 10s when visible)
  useEffect(() => {
    if (!showEnergyFlows || !siteId) return;

    let cancelled = false;
    const fetchFlows = async () => {
      try {
        const result = await digitalTwinApi.getEnergyFlows(siteId);
        if (!cancelled) setEnergyFlows(result.flows);
      } catch (err) {
        console.warn('Failed to fetch energy flows:', err);
      }
    };

    fetchFlows();
    const interval = setInterval(fetchFlows, 10_000);
    return () => { cancelled = true; clearInterval(interval); };
  }, [showEnergyFlows, siteId]);

  // Phase 4: Sync with SimulationContext occupancy targets
  const { simulationTime, totalOccupancy } = useOccupancySync({
    siteId: siteId || '',
    simulationRef,
    enabled: occupancyEnabled,
  });

  // Load zone bounds for adaptive equipment positioning
  const zoneBounds = useZoneBounds(siteId);

  // Load stored positions from site_3d_configs (overrides algorithmic)
  const storedPositions = useStoredPositions(siteId || '');

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

  const resolvedZoneBounds = useMemo(() => {
    const mergedBounds: Record<string, import('@/utils/equipmentPositioning').ZoneBounds> = { ...zoneBounds };
    const floorsNeeded = new Set<string>();

    filteredEquipment.forEach((eq) => {
      const code = (eq as any).code || eq.id || '';
      const floor = extractFloor(code);
      floorsNeeded.add(floor === 'G' ? 'L0' : floor);
    });

    if (floorsNeeded.size === 0) {
      dynamicFloors.forEach((floor) => {
        floorsNeeded.add(floor.code === 'G' ? 'L0' : floor.code);
      });
    }

    floorsNeeded.forEach((floor) => {
      Object.assign(mergedBounds, generateSyntheticZoneBounds(floor));
    });

    return mergedBounds;
  }, [dynamicFloors, filteredEquipment, zoneBounds]);

  // Pre-calculate equipment positions with 3-tier priority:
  // 1. Stored positions from site_3d_configs (user-placed, persistent)
  // 2. Canonical per-floor zone strips spanning the full slab
  // 3. Center-of-floor fallback if a position still cannot be resolved
  const equipmentPositions = useMemo(() => {
    const positions = new Map<string, EquipmentPosition>();

    // Tier 1: Apply stored positions first (these are authoritative)
    const needsAlgorithmic: typeof filteredEquipment = [];

    filteredEquipment.forEach((eq) => {
      const stored = storedPositions[eq.id];
      if (stored) {
        // Stored position found — use it (x, y in stored = x, z in 3D)
        const floorY = getFloorY(stored.floor === 'G' ? 'L0' : stored.floor);
        positions.set(eq.id, { x: stored.x, y: floorY, z: stored.y });
      } else {
        needsAlgorithmic.push(eq);
      }
    });

    // Tier 2+3: Algorithmic placement for equipment without stored positions
    if (needsAlgorithmic.length > 0) {
      // Group by zone key
      const byZone: Record<string, typeof needsAlgorithmic> = {};
      needsAlgorithmic.forEach((eq) => {
        const code = (eq as any).code || eq.id || '';
        const zoneKey = buildZoneKey(code);

        if (!byZone[zoneKey]) byZone[zoneKey] = [];
        byZone[zoneKey].push(eq);
      });

      // Distribute within zones
      Object.entries(byZone).forEach(([zoneKey, zoneEquipment]) => {
        const bounds = resolvedZoneBounds[zoneKey];
        if (!bounds) return;

        const floor = zoneKey.split('-')[1] || 'L0';
        const floorY = getFloorY(floor);

        const distributed = distributeEquipmentInZone(zoneEquipment, bounds, floorY);
        distributed.forEach((pos, id) => positions.set(id, pos));
      });

      // Final fallback for unpositioned equipment
      needsAlgorithmic.forEach((eq) => {
        if (!positions.has(eq.id)) {
          const code = (eq as any).code || eq.id || '';
          const floor = extractFloor(code) || 'L0';
          const floorY = getFloorY(floor === 'G' ? 'L0' : floor);
          positions.set(eq.id, { x: 0, y: floorY, z: 0 });
        }
      });
    }

    return positions;
  }, [filteredEquipment, resolvedZoneBounds, storedPositions]);

  // Find selected equipment data
  const selectedEquipmentData = useMemo(
    () =>
      filteredEquipment.find((e) => e.id === selectedEquipment || (e as any).code === selectedEquipment),
    [filteredEquipment, selectedEquipment]
  );

  // Loading state
  if (loading && equipment.length === 0) {
    return (
      <div
        className="h-full flex items-center justify-center"
        style={{ background: 'var(--color-sentinel-bg-canvas)' }}
      >
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
      <div
        className="h-full flex items-center justify-center"
        style={{ background: 'var(--color-sentinel-bg-canvas)' }}
      >
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

  const rootClass = `h-full flex flex-col ${
    theme === 'matrix'
      ? 'matrix-theme bg-gradient-to-br from-[#060E18] via-[#0a1420] to-[#060E18]'
      : ''
  }`;

  return (
    <div className={rootClass}>
      {/* Alert Banner */}
      <AlertBanner equipment={equipment} />

      {/* Site Selector and Equipment Filter */}
      <div
        className="px-6 py-4 border-b"
        style={{
          borderColor:
            theme === 'matrix'
              ? 'var(--color-matrix-green)'
              : 'var(--color-sentinel-border)',
          opacity: theme === 'matrix' ? 0.3 : 1,
        }}
      >
        <div className="flex items-center justify-between gap-4 mb-4">
          <div className="flex items-center gap-4 flex-wrap">
            <div className="flex items-center gap-3">
              <label className="text-sm font-medium" style={{ color: 'var(--color-sentinel-text-secondary)' }}>
                Building:
              </label>
              <BuildingSelector
                value={selectedSiteId}
                onChange={setSelectedSiteId}
                sites={sites}
                disabled={sitesLoading}
              />
            </div>

            {/* Equipment type filter dropdown with icons */}
            <div className="relative" ref={equipmentDropdownRef}>
              <button
                onClick={() => setEquipmentDropdownOpen(!equipmentDropdownOpen)}
                className={`matrix-btn flex items-center gap-2 ${equipmentTypeFilter ? 'matrix-btn-active' : ''}`}
                style={{ minWidth: '160px', justifyContent: 'space-between' }}
              >
                <span className="flex items-center gap-2">
                  {equipmentTypeFilter ? (
                    <>
                      <span className="flex items-center">{EQUIPMENT_ICONS[equipmentTypeFilter] || DEFAULT_ICON}</span>
                      <span>{equipmentTypeFilter.toUpperCase()}</span>
                      <span className="text-xs opacity-75">({equipmentCountByType[equipmentTypeFilter] || 0})</span>
                    </>
                  ) : (
                    <>
                      <span>ALL EQUIPMENT</span>
                      <span className="text-xs opacity-75">({equipment.length})</span>
                    </>
                  )}
                </span>
                <ChevronDown className={`w-3 h-3 transition-transform ${equipmentDropdownOpen ? 'rotate-180' : ''}`} />
              </button>

              {equipmentDropdownOpen && (
                <div
                  className="absolute top-full left-0 mt-1 z-50 rounded-lg border p-2 min-w-[280px] max-h-[320px] overflow-y-auto"
                  style={{
                    background: theme === 'matrix' ? 'rgba(6, 14, 24, 0.97)' : 'var(--color-sentinel-bg)',
                    borderColor: theme === 'matrix' ? 'var(--color-matrix-green)' : 'var(--color-sentinel-border)',
                    boxShadow: theme === 'matrix'
                      ? '0 4px 24px rgba(0, 255, 65, 0.15), 0 0 1px rgba(0, 255, 65, 0.3)'
                      : '0 4px 24px rgba(0,0,0,0.2)',
                  }}
                >
                  <div className="flex flex-wrap gap-2">
                    <button
                      onClick={() => { setEquipmentTypeFilter(null); setEquipmentDropdownOpen(false); }}
                      className={`matrix-btn ${!equipmentTypeFilter ? 'matrix-btn-active' : ''}`}
                    >
                      ALL ({equipment.length})
                    </button>

                    {equipmentTypes.map((type) => (
                      <button
                        key={type}
                        onClick={() => {
                          setEquipmentTypeFilter(equipmentTypeFilter === type ? null : type);
                          setEquipmentDropdownOpen(false);
                        }}
                        className={`matrix-btn ${equipmentTypeFilter === type ? 'matrix-btn-active' : ''}`}
                      >
                        <span className="flex items-center">{EQUIPMENT_ICONS[type] || DEFAULT_ICON}</span>
                        <span>{type.toUpperCase()}</span>
                        <span className="text-xs opacity-75">({equipmentCountByType[type] || 0})</span>
                      </button>
                    ))}
                  </div>
                </div>
              )}
            </div>
          </div>

          {/* 2D/3D Toggle */}
          <div className="flex items-center gap-2 ml-4 pl-4 border-l" style={{ borderColor: 'var(--color-sentinel-border)' }}>
            <button
              onClick={() => setViewMode('3D')}
              className={`matrix-btn ${viewMode === '3D' ? 'matrix-btn-active' : ''}`}
            >
              3D
            </button>
            <button
              onClick={() => setViewMode('2D')}
              className={`matrix-btn ${viewMode === '2D' ? 'matrix-btn-active' : ''}`}
            >
              2D
            </button>

            {/* Occupancy Toggle */}
            <button
              onClick={() => setOccupancyEnabled(!occupancyEnabled)}
              className={`matrix-btn flex items-center gap-2 ${occupancyEnabled ? 'matrix-btn-active' : ''}`}
              title="Toggle occupancy simulation overlay"
            >
              <Users className="w-4 h-4" />
              <span>Occupancy</span>
              {occupancyEnabled && people.length > 0 && (
                <span className="text-xs opacity-75">({people.length})</span>
              )}
            </button>

            {/* Predictions Toggle */}
            <button
              onClick={() => setShowPredictions(!showPredictions)}
              className={`matrix-btn flex items-center gap-2 ${showPredictions ? 'matrix-btn-active' : ''}`}
              title="Toggle predictive fault overlay"
            >
              <BarChart3 className="w-4 h-4" />
              <span>Predictions</span>
              {showPredictions && ssePredicitions.length > 0 && (
                <span className="text-xs opacity-75">({ssePredicitions.length})</span>
              )}
            </button>

            {/* Energy Flows Toggle */}
            <button
              onClick={() => setShowEnergyFlows(!showEnergyFlows)}
              className={`matrix-btn flex items-center gap-2 ${showEnergyFlows ? 'matrix-btn-active' : ''}`}
              title="Toggle animated energy flow paths"
            >
              <Workflow className="w-4 h-4" />
              <span>Flows</span>
              {showEnergyFlows && energyFlows.length > 0 && (
                <span className="text-xs opacity-75">({energyFlows.length})</span>
              )}
            </button>

            {/* Timeline Toggle */}
            <button
              onClick={() => {
                const next = !isTimeline;
                setIsTimeline(next);
                if (!next) {
                  setIsTimelinePlaying(false);
                  setTimelineTimestamp(null);
                }
              }}
              className={`matrix-btn flex items-center gap-2 ${isTimeline ? 'matrix-btn-active' : ''}`}
              title="Toggle historical timeline scrubber"
            >
              <History className="w-4 h-4" />
              <span>Timeline</span>
            </button>

            {/* SSE Connection Indicator */}
            <div
              className="w-2.5 h-2.5 rounded-full"
              title={sseConnected ? 'Real-time connected' : 'Real-time disconnected'}
              style={{ backgroundColor: sseConnected ? '#22C55E' : '#6B7280' }}
            />

            {/* Simulation Time Display (Phase 4) */}
            {occupancyEnabled && simulationTime && (
              <div className="flex items-center gap-2 pl-3 ml-2" style={{ borderLeft: '1px solid var(--color-sentinel-border)' }}>
                <div className="text-xs flex flex-col">
                  <span style={{ color: 'var(--color-text-secondary)' }}>Simulation</span>
                  <span className="font-mono font-semibold" style={{ color: 'var(--color-primary)' }}>
                    {simulationTime.toLocaleTimeString()}
                  </span>
                </div>
                {totalOccupancy > 0 && (
                  <div className="text-xs flex flex-col ml-2">
                    <span style={{ color: 'var(--color-text-secondary)' }}>Total</span>
                    <span className="font-mono font-semibold" style={{ color: 'var(--color-accent)' }}>
                      {totalOccupancy} people
                    </span>
                  </div>
                )}
              </div>
            )}
          </div>
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
              equipmentPositions={equipmentPositions}
              realtimeUpdates={realtimeUpdates}
            />

            {/* Predictive Fault Overlay */}
            {showPredictions && ssePredicitions.length > 0 && (
              <PredictiveFaultOverlay
                predictions={ssePredicitions}
                equipmentPositions={
                  new Map(
                    Array.from(equipmentPositions.entries()).map(([id, pos]) => [id, [pos.x, pos.y, pos.z] as [number, number, number]])
                  )
                }
              />
            )}

            {/* Animated Energy Flows */}
            {showEnergyFlows && energyFlows.length > 0 && (
              <AnimatedEnergyFlow
                flows={energyFlows}
                equipmentPositions={
                  new Map(
                    Array.from(equipmentPositions.entries()).map(([id, pos]) => [id, [pos.x, pos.y, pos.z] as [number, number, number]])
                  )
                }
                visible={showEnergyFlows}
              />
            )}

            {/* Occupancy dots — subtle cyan spheres on floor surfaces */}
            {occupancyEnabled && people.length > 0 && (
              <OccupancyMarkers3DFiber people={people} />
            )}

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
            zoneBounds={resolvedZoneBounds}
            equipmentPositions={equipmentPositions}
            onEquipmentClick={setSelectedEquipment}
            selectedEquipment={selectedEquipment}
            occupancyEnabled={occupancyEnabled}
            people={people}
          />
        )}

        {/* Historical Timeline Scrubber */}
        {isTimeline && (
          <HistoricalTimeline
            onTimestampChange={(ts) => setTimelineTimestamp(ts)}
            isPlaying={isTimelinePlaying}
            onPlayPause={() => setIsTimelinePlaying(!isTimelinePlaying)}
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
