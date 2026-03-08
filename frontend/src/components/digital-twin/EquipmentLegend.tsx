import { useState } from 'react';
import { ChevronDown, ChevronUp } from 'lucide-react';
import type { Equipment } from '@/lib/api/sites';
import { TYPE_COLORS } from './EquipmentMarker';

interface EquipmentLegendProps {
  equipment: Equipment[];
}

export function EquipmentLegend({ equipment }: EquipmentLegendProps) {
  const [expanded, setExpanded] = useState(true);

  // Count equipment by type
  const typeCounts: Record<string, number> = {};
  equipment.forEach((eq) => {
    const type = ((eq as any).equipment_type || (eq as any).type || 'unknown').toLowerCase();
    if (type !== 'unknown') {
      typeCounts[type] = (typeCounts[type] || 0) + 1;
    }
  });

  const types = Object.entries(typeCounts).sort((a, b) => b[1] - a[1]);

  return (
    <div
      className="absolute left-4 bottom-4 z-10 matrix-panel"
      style={{
        background: 'rgba(6, 14, 24, 0.92)',
        padding: expanded ? '10px 12px' : '6px 8px',
        maxHeight: expanded ? '280px' : 'auto',
        overflowY: expanded ? 'auto' : 'hidden',
      }}
    >
      {/* Header */}
      <button
        onClick={() => setExpanded(!expanded)}
        className="w-full flex items-center justify-between gap-2"
        style={{
          color: '#00FF41',
          fontFamily: 'Orbitron, monospace',
          fontSize: '10px',
          fontWeight: 700,
          letterSpacing: '0.15em',
          textTransform: 'uppercase',
          textShadow: '0 0 8px rgba(0, 255, 65, 0.3)',
        }}
      >
        <span>EQUIPMENT</span>
        {expanded ? <ChevronDown className="h-3 w-3" /> : <ChevronUp className="h-3 w-3" />}
      </button>

      {/* Legend items */}
      {expanded && (
        <div
          className="mt-2 grid gap-x-4 gap-y-1"
          style={{
            gridTemplateColumns: 'repeat(auto-fill, minmax(100px, 1fr))',
          }}
        >
          {types.map(([type, _count]) => {
            const color = TYPE_COLORS[type] || '#666666';
            return (
              <div key={type} className="flex items-center gap-2">
                <span
                  className="inline-block rounded-sm flex-none"
                  style={{
                    width: '10px',
                    height: '10px',
                    backgroundColor: color,
                    boxShadow: `0 0 4px ${color}66`,
                  }}
                />
                <span
                  style={{
                    color: 'rgba(255, 255, 255, 0.85)',
                    fontFamily: 'Share Tech Mono, monospace',
                    fontSize: '10px',
                    whiteSpace: 'nowrap',
                  }}
                >
                  {type.toUpperCase()}
                </span>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
