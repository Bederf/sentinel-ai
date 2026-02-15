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
  const [expanded, setExpanded] = useState(false);

  return (
    <div
      className="absolute left-4 top-4 z-10 matrix-panel"
      style={{
        background: 'rgba(6, 14, 24, 0.95)',
        padding: expanded ? '8px' : '6px',
      }}
    >
      {/* Header */}
      <button
        onClick={() => setExpanded(!expanded)}
        className="w-full flex items-center justify-between"
        style={{
          color: '#00FF41',
          fontFamily: 'Orbitron, monospace',
          fontSize: expanded ? '11px' : '10px',
          fontWeight: 700,
          letterSpacing: '0.1em',
          textTransform: 'uppercase',
          textShadow: '0 0 8px rgba(0, 255, 65, 0.3)',
          marginBottom: expanded ? '6px' : '0px',
        }}
      >
        <h3 className="font-bold" style={{ fontSize: expanded ? '12px' : '10px' }}>
          {expanded ? 'FLOORS' : '⊞'}
        </h3>
        {expanded ? <ChevronUp className="h-3 w-3" /> : <ChevronDown className="h-3 w-3" />}
      </button>

      {/* Floor List */}
      {expanded && (
        <div className="space-y-1">
          {floors.map((floor) => {
            const isSelected = selectedFloors.has(floor.id);
            return (
              <div key={floor.id} className="flex items-center gap-1 text-xs">
                {/* Checkbox */}
                <input
                  type="checkbox"
                  checked={isSelected}
                  onChange={() => onToggle(floor.id)}
                  className="matrix-checkbox"
                  style={{
                    width: '14px',
                    height: '14px',
                  }}
                />

                {/* Label */}
                <label
                  className="flex-1 cursor-pointer transition-opacity"
                  style={{
                    color: isSelected ? '#00FF41' : 'rgba(0, 255, 65, 0.4)',
                    fontSize: '10px',
                    fontFamily: 'Share Tech Mono, monospace',
                  }}
                >
                  {floor.label}
                </label>

                {/* Isolate button - simplified */}
                <button
                  onClick={() => onIsolate(floor.id)}
                  className="matrix-btn text-xs px-1 py-0"
                  style={{
                    fontSize: '9px',
                    fontWeight: 600,
                    minWidth: '28px',
                    padding: '2px 4px',
                  }}
                  title="Show only this floor"
                >
                  {isSelected ? '⊙' : '○'}
                </button>
              </div>
            );
          })}
        </div>
      )}

      {/* Info text - only show when expanded */}
      {expanded && (
        <div
          className="text-xs mt-2 pt-2 border-t"
          style={{
            color: 'rgba(0, 255, 65, 0.5)',
            borderColor: 'rgba(0, 255, 65, 0.2)',
            fontFamily: 'Share Tech Mono, monospace',
            fontSize: '9px',
          }}
        >
          [{selectedFloors.size}/{floors.length}]
        </div>
      )}

      {/* Collapsed view - show count only */}
      {!expanded && (
        <div
          style={{
            color: 'rgba(0, 255, 65, 0.6)',
            fontFamily: 'Share Tech Mono, monospace',
            fontSize: '9px',
            marginTop: '2px',
            textAlign: 'center',
          }}
        >
          {selectedFloors.size}/{floors.length}
        </div>
      )}
    </div>
  );
}
