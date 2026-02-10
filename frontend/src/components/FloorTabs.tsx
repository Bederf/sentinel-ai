// Floor selector tab component for 2D floor editor

import { ChevronDown, ChevronUp } from "lucide-react";
import { useState } from "react";

export interface FloorTab {
  level: string;
  label: string;
}

export interface FloorTabsProps {
  floors: FloorTab[];
  activeFloor: string;
  onFloorChange: (floor: string) => void;
  equipmentCount?: Record<string, number>;
}

/**
 * Horizontal tab selector for floors with equipment count badges
 */
export function FloorTabs({
  floors,
  activeFloor,
  onFloorChange,
  equipmentCount = {},
}: FloorTabsProps) {
  const [isExpanded, setIsExpanded] = useState(false);

  // For mobile: show dropdown; for desktop: show horizontal tabs
  const isMobileLayout = floors.length > 6;

  if (isMobileLayout && isExpanded) {
    return (
      <div className="bg-white border border-gray-200 rounded-lg p-3 mb-4">
        <button
          onClick={() => setIsExpanded(false)}
          className="flex items-center justify-between w-full text-sm font-medium text-gray-900 hover:text-gray-700"
        >
          <span>Floors ({floors.length})</span>
          <ChevronUp className="h-4 w-4" />
        </button>

        <div className="grid grid-cols-2 sm:grid-cols-3 gap-2 mt-3">
          {floors.map((floor) => {
            const isActive = floor.level === activeFloor;
            const count = equipmentCount[floor.level] || 0;

            return (
              <button
                key={floor.level}
                onClick={() => {
                  onFloorChange(floor.level);
                  setIsExpanded(false);
                }}
                className={`p-2 rounded-lg text-sm font-medium transition-colors ${
                  isActive
                    ? "bg-blue-100 text-blue-700 border border-blue-300"
                    : "bg-gray-50 text-gray-700 border border-gray-200 hover:bg-gray-100"
                }`}
              >
                <div className="font-semibold">{floor.level}</div>
                <div className="text-xs text-gray-500">{floor.label}</div>
                {count > 0 && (
                  <div className="mt-1 inline-block bg-blue-500 text-white text-xs px-2 py-1 rounded">
                    {count} {count === 1 ? "item" : "items"}
                  </div>
                )}
              </button>
            );
          })}
        </div>
      </div>
    );
  }

  if (isMobileLayout) {
    const activeTab = floors.find((f) => f.level === activeFloor);
    return (
      <button
        onClick={() => setIsExpanded(true)}
        className="w-full mb-4 p-3 bg-white border border-gray-200 rounded-lg flex items-center justify-between hover:bg-gray-50"
      >
        <div className="text-left">
          <div className="font-medium text-gray-900">{activeTab?.level}</div>
          <div className="text-sm text-gray-500">{activeTab?.label}</div>
        </div>
        <ChevronDown className="h-5 w-5 text-gray-400" />
      </button>
    );
  }

  // Desktop layout: horizontal tabs
  return (
    <div className="flex gap-2 mb-4 overflow-x-auto pb-2">
      {floors.map((floor) => {
        const isActive = floor.level === activeFloor;
        const count = equipmentCount[floor.level] || 0;

        return (
          <button
            key={floor.level}
            onClick={() => onFloorChange(floor.level)}
            className={`flex-shrink-0 px-4 py-2 rounded-lg border transition-colors whitespace-nowrap ${
              isActive
                ? "bg-blue-100 text-blue-700 border-blue-300 font-medium"
                : "bg-white text-gray-700 border-gray-200 hover:bg-gray-50"
            }`}
          >
            <div className="font-semibold text-sm">{floor.level}</div>
            <div className="text-xs text-gray-500">{floor.label}</div>
            {count > 0 && (
              <div className="mt-1 inline-block ml-1 bg-blue-500 text-white text-xs px-1.5 py-0.5 rounded">
                {count}
              </div>
            )}
          </button>
        );
      })}
    </div>
  );
}
