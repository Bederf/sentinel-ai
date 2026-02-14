import { ChevronDown, ChevronUp } from 'lucide-react';
import { useState } from 'react';

interface Floor {
  id: number;
  label: string;
  code: string;
}

interface FloorSelectorProps {
  floors: Floor[];
  selectedFloors: Set<number>;
  onToggle: (floor: number) => void;
  onIsolate: (floor: number) => void;
}

export function FloorSelector({
  floors,
  selectedFloors,
  onToggle,
  onIsolate,
}: FloorSelectorProps) {
  const [expanded, setExpanded] = useState(true);

  return (
    <div
      className="absolute left-4 top-4 p-3 max-w-xs z-10 matrix-panel"
      style={{
        background: 'rgba(6, 14, 24, 0.95)',
      }}
    >
      {/* Header */}
      <button
        onClick={() => setExpanded(!expanded)}
        className="w-full flex items-center justify-between mb-3"
        style={{ 
          color: '#00FF41',
          fontFamily: 'Orbitron, monospace',
          fontSize: '12px',
          fontWeight: 700,
          letterSpacing: '0.15em',
          textTransform: 'uppercase',
          textShadow: '0 0 8px rgba(0, 255, 65, 0.3)',
        }}
      >
        <h3 className="font-bold text-sm">FLOORS</h3>
        {expanded ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
      </button>

      {/* Floor List */}
      {expanded && (
        <div className="space-y-2">
          {floors.map((floor) => {
            const isSelected = selectedFloors.has(floor.id);
            return (
              <div key={floor.id} className="flex items-center gap-2 text-xs">
                {/* Checkbox */}
                <input
                  type="checkbox"
                  checked={isSelected}
                  onChange={() => onToggle(floor.id)}
                  className="matrix-checkbox"
                  style={{
                    width: '16px',
                    height: '16px',
                  }}
                />

                {/* Label */}
                <label
                  className="flex-1 cursor-pointer transition-opacity"
                  style={{
                    color: isSelected ? '#00FF41' : 'rgba(0, 255, 65, 0.4)',
                    fontSize: '12px',
                    fontFamily: 'Share Tech Mono, monospace',
                  }}
                >
                  {floor.label}
                </label>

                {/* Isolate button */}
                <button
                  onClick={() => onIsolate(floor.id)}
                  className="matrix-btn text-xs px-2 py-1"
                  style={{
                    fontSize: '10px',
                    fontWeight: 600,
                    minWidth: '40px',
                  }}
                  title="Show only this floor"
                >
                  {isSelected ? 'VIEW' : 'SHOW'}
                </button>
              </div>
            );
          })}
        </div>
      )}

      {/* Info text */}
      <div
        className="text-xs mt-3 pt-3 border-t"
        style={{
          color: 'rgba(0, 255, 65, 0.5)',
          borderColor: 'rgba(0, 255, 65, 0.2)',
          fontFamily: 'Share Tech Mono, monospace',
          fontSize: '10px',
        }}
      >
        [{selectedFloors.size}/{floors.length} ACTIVE]
      </div>
    </div>
  );
}
