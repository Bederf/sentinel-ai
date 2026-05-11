/**
 * Floor selector tab component for 2D floor editor.
 * Uses Sentinel dark-theme design tokens — pass darkTheme=true when
 * rendered inside a dark-theme container (SiteDetail, Dashboard).
 */

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
  /** Pass true when rendered inside a dark-theme container. Defaults to true. */
  darkTheme?: boolean;
}

/**
 * Horizontal tab selector for floors with equipment count badges.
 * Dark-theme by default — uses Sentinel design tokens throughout.
 */
export function FloorTabs({
  floors,
  activeFloor,
  onFloorChange,
  equipmentCount = {},
  darkTheme: _darkTheme = true,
}: FloorTabsProps) {
  const [isExpanded, setIsExpanded] = useState(false);

  const isMobileLayout = floors.length > 6;

  if (isMobileLayout && isExpanded) {
    return (
      <div
        className="rounded-lg p-3 mb-4"
        style={{
          background: "var(--color-sentinel-bg-panel)",
          border: "1px solid var(--color-sentinel-border)",
        }}
      >
        <button
          onClick={() => setIsExpanded(false)}
          className="flex items-center justify-between w-full text-sm font-medium transition-colors hover:brightness-110"
          style={{ color: "var(--color-sentinel-text-primary)" }}
        >
          <span>Floors ({floors.length})</span>
          <ChevronUp className="h-4 w-4" style={{ color: "var(--color-sentinel-text-secondary)" }} />
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
                className="p-2 rounded-lg text-sm font-medium transition-colors"
                style={{
                  background: isActive ? "rgba(59, 130, 246, 0.15)" : "var(--color-sentinel-bg-secondary)",
                  border: `1px solid ${isActive ? "rgba(59, 130, 246, 0.4)" : "var(--color-sentinel-border)"}`,
                  color: isActive ? "var(--color-sentinel-blue-light)" : "var(--color-sentinel-text-secondary)",
                }}
              >
                <div className="font-semibold">{floor.level}</div>
                <div className="text-xs" style={{ color: "var(--color-sentinel-text-disabled)" }}>{floor.label}</div>
                {count > 0 && (
                  <div
                    className="mt-1 inline-block text-white text-xs px-2 py-1 rounded"
                    style={{ background: "var(--color-sentinel-blue)" }}
                  >
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
        className="w-full mb-4 p-3 rounded-lg flex items-center justify-between transition-colors hover:brightness-110"
        style={{
          background: "var(--color-sentinel-bg-secondary)",
          border: "1px solid var(--color-sentinel-border)",
          color: "var(--color-sentinel-text-primary)",
        }}
      >
        <div className="text-left">
          <div className="font-medium">{activeTab?.level}</div>
          <div className="text-sm" style={{ color: "var(--color-sentinel-text-secondary)" }}>{activeTab?.label}</div>
        </div>
        <ChevronDown className="h-5 w-5" style={{ color: "var(--color-sentinel-text-secondary)" }} />
      </button>
    );
  }

  // Desktop layout: horizontal tabs — Sentinel dark-theme
  return (
    <div className="flex gap-2 mb-4 overflow-x-auto pb-2">
      {floors.map((floor) => {
        const isActive = floor.level === activeFloor;
        const count = equipmentCount[floor.level] || 0;

        return (
          <button
            key={floor.level}
            onClick={() => onFloorChange(floor.level)}
            className="flex-shrink-0 px-4 py-2 rounded-lg border transition-colors whitespace-nowrap"
            style={{
              background: isActive ? "rgba(59, 130, 246, 0.15)" : "var(--color-sentinel-bg-secondary)",
              border: `1px solid ${isActive ? "rgba(59, 130, 246, 0.4)" : "var(--color-sentinel-border)"}`,
              color: isActive ? "var(--color-sentinel-blue-light)" : "var(--color-sentinel-text-secondary)",
              fontWeight: isActive ? 600 : 400,
            }}
          >
            <div className="text-sm font-semibold">{floor.level}</div>
            <div className="text-xs" style={{ color: "var(--color-sentinel-text-disabled)" }}>{floor.label}</div>
            {count > 0 && (
              <div
                className="mt-1 inline-block ml-1 text-white text-xs px-1.5 py-0.5 rounded"
                style={{ background: "var(--color-sentinel-blue)" }}
              >
                {count}
              </div>
            )}
          </button>
        );
      })}
    </div>
  );
}
