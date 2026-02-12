/**
 * 2D SVG Equipment Marker for Floor Plan
 *
 * Displays equipment as an SVG circle with:
 * - Health-based fill color
 * - Selection ring animation when selected
 * - Hover scale effect
 * - Equipment code tooltip on hover
 */

import type { Equipment } from '@/lib/api/sites';

interface EquipmentMarker2DProps {
  equipment: Equipment;
  x: number;
  z: number;
  selected: boolean;
  onClick: () => void;
}

/**
 * Get health color based on equipment health score
 */
function getHealthColor(healthScore: number | undefined | null): string {
  const score = healthScore || 100;
  if (score >= 60) return '#22c55e';
  if (score >= 30) return '#f59e0b';
  return '#ef4444';
}

/**
 * 2D SVG marker for equipment in floor plan
 *
 * Features:
 * - Circle (0.25m radius) with health color
 * - Selection ring (pulsing animation when selected)
 * - Hover tooltip showing equipment code and health
 * - Click handler for selection
 */
export function EquipmentMarker2D({
  equipment,
  x,
  z,
  selected,
  onClick,
}: EquipmentMarker2DProps) {
  const healthScore = equipment.health_score || 100;
  const healthColor = getHealthColor(healthScore);
  const code = (equipment as any).code || equipment.id || '';

  return (
    <g
      transform={`translate(${x}, ${z})`}
      onClick={onClick}
      style={{ cursor: 'pointer' }}
      className="transition-transform hover:scale-110"
    >
      {/* Main health status circle */}
      <circle r={0.25} fill={healthColor} opacity={0.85} />

      {/* Selection ring - pulsing animation when selected */}
      {selected && (
        <>
          <circle
            r={0.4}
            fill="none"
            stroke="#3b82f6"
            strokeWidth={0.06}
          />
          <style>
            {`
              @keyframes pulse-ring {
                0%, 100% { r: 0.4; opacity: 1; }
                50% { r: 0.55; opacity: 0.5; }
              }
            `}
          </style>
          <circle
            r={0.4}
            fill="none"
            stroke="#3b82f6"
            strokeWidth={0.06}
            opacity={0.6}
            style={{
              animation: 'pulse-ring 1.5s ease-in-out infinite',
            }}
          />
        </>
      )}

      {/* Tooltip on hover */}
      <title>{`${code} - Health: ${healthScore}%`}</title>

      {/* Optional: small text label for code (comment out if too cluttered) */}
      {/* <text
        x={0}
        y={0}
        fontSize={0.15}
        fill="white"
        textAnchor="middle"
        dominantBaseline="middle"
        pointerEvents="none"
      >
        {code.split('-').slice(-1)[0]}
      </text> */}
    </g>
  );
}
