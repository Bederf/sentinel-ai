/**
 * 2D Floor Plan View for Digital Twin
 *
 * SVG-based interactive floor plan showing:
 * - Zone boundaries
 * - Equipment distribution with health coloring
 * - Equipment selection and interaction
 * - Floor-filtered view with zone labels
 */

import { EquipmentMarker2D } from './EquipmentMarker2D';
import { OccupancyMarkers2D } from './OccupancyMarkers2D';
import {
  extractFloor,
  type ZoneBounds,
  type EquipmentPosition,
} from '@/utils/equipmentPositioning';
import type { Equipment } from '@/lib/api/sites';
import type { Person } from '@/lib/occupancySimulation';

interface FloorPlan2DProps {
  equipment: Equipment[];
  selectedFloors: Set<number>;
  zoneBounds: Record<string, ZoneBounds>;
  equipmentPositions: Map<string, EquipmentPosition>;
  onEquipmentClick: (id: string) => void;
  selectedEquipment: string | null;
  occupancyEnabled?: boolean;
  people?: Person[];
}

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

/**
 * Get health color based on equipment health score
 * - Green (#22c55e): 60%+
 * - Yellow (#f59e0b): 30-60%
 * - Red (#ef4444): <30%
 */
function _getHealthColor(healthScore: number | undefined | null): string {
  const score = healthScore || 100;
  if (score >= 60) return '#22c55e';
  if (score >= 30) return '#f59e0b';
  return '#ef4444';
}

/**
 * 2D floor plan SVG visualization
 *
 * Layout:
 * - Building bounds: X: -15..15 (30m width), Z: -10..10 (20m depth)
 * - Grid lines every 5m for reference
 * - Zone boundaries with labels
 * - Equipment markers with health colors
 * - Legend showing health status meanings
 */
export function FloorPlan2D({
  equipment,
  selectedFloors,
  zoneBounds,
  equipmentPositions,
  onEquipmentClick,
  selectedEquipment,
  occupancyEnabled = false,
  people = [],
}: FloorPlan2DProps) {
  // Filter equipment by selected floors
  const visibleEquipment = equipment.filter((eq) => {
    const code = (eq as any).code || eq.id || '';
    const floor = extractFloor(code);
    const floorId = FLOOR_ID[floor] ?? 1;
    return selectedFloors.has(floorId);
  });

  // Filter zones by selected floors
  const visibleZones = Object.entries(zoneBounds).filter(([zoneId]) => {
    const floor = zoneId.match(/Zone-(B\d|G|L\d+|R)-/)?.[1];
    const floorId = FLOOR_ID[floor || 'L0'] ?? 1;
    return selectedFloors.has(floorId);
  });

  return (
    <div className="w-full h-full flex items-center justify-center bg-slate-900">
      <svg
        viewBox="-15 -10 30 20"
        className="w-full h-full"
        style={{ maxWidth: '90%', maxHeight: '90%' }}
        xmlns="http://www.w3.org/2000/svg"
      >
        {/* Grid lines (every 5m) */}
        <g opacity={0.1}>
          {[-10, -5, 0, 5, 10].map((x) => (
            <line
              key={`v${x}`}
              x1={x}
              y1={-10}
              x2={x}
              y2={10}
              stroke="#666"
              strokeWidth={0.02}
            />
          ))}
          {[-5, 0, 5].map((z) => (
            <line
              key={`h${z}`}
              x1={-15}
              y1={z}
              x2={15}
              y2={z}
              stroke="#666"
              strokeWidth={0.02}
            />
          ))}
        </g>

        {/* Building outline */}
        <rect x={-15} y={-10} width={30} height={20} fill="none" stroke="#444" strokeWidth={0.1} />

        {/* Zone boundaries */}
        {visibleZones.map(([zoneId, bounds]) => (
          <g key={zoneId}>
            {/* Zone background */}
            <rect
              x={bounds.minX}
              y={bounds.minZ}
              width={bounds.width}
              height={bounds.depth}
              fill="#1e293b"
              stroke="#334155"
              strokeWidth={0.05}
              opacity={0.3}
            />
            {/* Zone label */}
            <text
              x={bounds.centerX}
              y={bounds.centerZ}
              fontSize={0.6}
              fill="#64748b"
              textAnchor="middle"
              dominantBaseline="middle"
              fontWeight="bold"
              pointerEvents="none"
            >
              {zoneId.split('-').pop()}
            </text>
          </g>
        ))}

        {/* Equipment markers */}
        {visibleEquipment.map((eq) => {
          const pos = equipmentPositions.get(eq.id);
          if (!pos) return null;

          return (
            <EquipmentMarker2D
              key={eq.id}
              equipment={eq}
              x={pos.x}
              z={pos.z}
              selected={selectedEquipment === eq.id}
              onClick={() => onEquipmentClick(eq.id)}
            />
          );
        })}

        {/* Occupancy overlay (rendered on top) */}
        {occupancyEnabled && people.length > 0 && (
          <OccupancyMarkers2D
            people={people}
            selectedFloor={Array.from(selectedFloors)[0] || 1}
            scale={1}
            offsetX={0}
            offsetY={0}
          />
        )}

        {/* Legend (bottom-left corner) */}
        <g transform="translate(-14, -9)">
          <text
            fontSize={0.4}
            fill="#94a3b8"
            fontWeight="bold"
            dominantBaseline="middle"
          >
            Health Status
          </text>

          {/* Healthy */}
          <circle cx={0} cy={0.6} r={0.15} fill="#22c55e" />
          <text
            x={0.3}
            y={0.6}
            fontSize={0.35}
            fill="#94a3b8"
            dominantBaseline="middle"
          >
            Healthy (60%+)
          </text>

          {/* Warning */}
          <circle cx={0} cy={1.1} r={0.15} fill="#f59e0b" />
          <text
            x={0.3}
            y={1.1}
            fontSize={0.35}
            fill="#94a3b8"
            dominantBaseline="middle"
          >
            Warning (30-60%)
          </text>

          {/* Critical */}
          <circle cx={0} cy={1.6} r={0.15} fill="#ef4444" />
          <text
            x={0.3}
            y={1.6}
            fontSize={0.35}
            fill="#94a3b8"
            dominantBaseline="middle"
          >
            Critical (&lt;30%)
          </text>
        </g>
      </svg>
    </div>
  );
}
