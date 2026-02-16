/**
 * 2D OCCUPANCY MARKERS COMPONENT
 *
 * Renders animated dots representing people on the 2D floor plan SVG.
 * Handles:
 * - Dot rendering with persona colors
 * - Smooth animation (CSS transitions)
 * - Movement indicators
 * - Click handling (for future equipment integration)
 */

import React from 'react';
import type { Person, PersonaType } from '@/lib/occupancySimulation';
import { getPersonaColor } from '@/lib/occupancySimulation';

interface OccupancyMarkers2DProps {
  people: Person[];
  selectedFloor: number;
  scale?: number; // Coordinate transform (default: 1)
  offsetX?: number; // SVG offset
  offsetY?: number;
  onPersonClick?: (person: Person) => void;
}

/**
 * Main component for rendering occupancy dots on 2D floor plan
 */
export const OccupancyMarkers2D: React.FC<OccupancyMarkers2DProps> = ({
  people,
  selectedFloor,
  scale = 1,
  offsetX = 0,
  offsetY = 0,
  onPersonClick,
}) => {
  // Filter people on selected floor
  const visiblePeople = people.filter(p => p.floor === selectedFloor);

  return (
    <g className="occupancy-markers-2d" data-testid="occupancy-markers-2d">
      {visiblePeople.map(person => (
        <g
          key={person.id}
          data-testid={`person-${person.id}`}
          className="person-group"
        >
          {/* Main dot (person) */}
          <circle
            cx={person.x * scale + offsetX}
            cy={person.y * scale + offsetY}
            r={5}
            fill={getPersonaColor(person.persona)}
            opacity={person.state === 'exiting' ? 0.5 : 1.0}
            strokeWidth={0.5}
            stroke="rgba(255, 255, 255, 0.3)"
            className="occupancy-dot"
            style={{
              filter: `drop-shadow(0 0 4px ${getPersonaColor(person.persona)}) drop-shadow(0 0 8px ${getPersonaColor(person.persona)}15)`,
              cursor: onPersonClick ? 'pointer' : 'default',
              transition: person.moving
                ? 'cx 0.3s ease-in-out, cy 0.3s ease-in-out, opacity 0.3s ease'
                : 'opacity 0.3s ease',
            }}
            onClick={() => onPersonClick?.(person)}
          />

          {/* Optional: Glow effect for entering/exiting */}
          {(person.state === 'entering' || person.state === 'exiting') && (
            <circle
              cx={person.x * scale + offsetX}
              cy={person.y * scale + offsetY}
              r={7}
              fill="none"
              stroke={getPersonaColor(person.persona)}
              strokeWidth={1}
              opacity={0.4}
              className="occupancy-pulse"
              style={{
                animation: 'pulse 1.5s ease-in-out infinite',
              }}
            />
          )}

          {/* Optional: Path indicator (where person is heading) */}
          {person.moving && person.targetX !== person.x && person.targetY !== person.y && (
            <line
              x1={person.x * scale + offsetX}
              y1={person.y * scale + offsetY}
              x2={person.targetX * scale + offsetX}
              y2={person.targetY * scale + offsetY}
              stroke={getPersonaColor(person.persona)}
              strokeWidth={0.5}
              opacity={0.2}
              strokeDasharray="2,2"
              className="occupancy-path"
            />
          )}

          {/* Tooltip on hover (optional) */}
          <title>{`${person.persona.toUpperCase()} - Zone: ${person.zoneId}`}</title>
        </g>
      ))}

      {/* CSS animations */}
      <defs>
        <style>{`
          @keyframes pulse {
            0%, 100% {
              r: 7;
              stroke-width: 1;
              opacity: 0.4;
            }
            50% {
              r: 10;
              stroke-width: 0.5;
              opacity: 0.1;
            }
          }

          .occupancy-dot {
            transition: all 0.3s ease;
          }

          .occupancy-dot:hover {
            r: 6;
            filter: drop-shadow(0 0 6px currentColor) !important;
          }
        `}</style>
      </defs>
    </g>
  );
};

export default OccupancyMarkers2D;
