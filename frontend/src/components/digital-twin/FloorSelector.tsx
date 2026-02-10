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
      className="absolute left-4 top-4 rounded-lg shadow-lg p-3 max-w-xs z-10"
      style={{
        background: 'var(--color-sentinel-bg-panel)',
        border: '1px solid var(--color-sentinel-border)',
      }}
    >
      {/* Header */}
      <button
        onClick={() => setExpanded(!expanded)}
        className="w-full flex items-center justify-between mb-3"
        style={{ color: 'var(--color-sentinel-text-primary)' }}
      >
        <h3 className="font-bold text-sm">Floors</h3>
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
                  className="w-4 h-4 rounded cursor-pointer"
                  style={{
                    accentColor: 'var(--color-sentinel-accent)',
                  }}
                />

                {/* Label */}
                <label
                  className="flex-1 cursor-pointer hover:opacity-80 transition-opacity"
                  style={{
                    color: isSelected
                      ? 'var(--color-sentinel-text-primary)'
                      : 'var(--color-sentinel-text-disabled)',
                  }}
                >
                  {floor.label}
                </label>

                {/* Isolate button */}
                <button
                  onClick={() => onIsolate(floor.id)}
                  className="px-2 py-1 rounded text-xs transition-colors"
                  style={{
                    background: isSelected
                      ? 'var(--color-sentinel-accent)'
                      : 'var(--color-sentinel-bg-secondary)',
                    color:
                      isSelected ? 'white' : 'var(--color-sentinel-text-secondary)',
                    border: '1px solid var(--color-sentinel-border)',
                  }}
                  title="Show only this floor"
                >
                  Show
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
          color: 'var(--color-sentinel-text-disabled)',
          borderColor: 'var(--color-sentinel-border)',
        }}
      >
        {selectedFloors.size} / {floors.length} floors selected
      </div>
    </div>
  );
}
