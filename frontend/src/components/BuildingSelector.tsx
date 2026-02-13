/**
 * StandardBuilding Selector Component
 *
 * Standardized building/site dropdown selector used across all dashboard pages.
 * Provides consistent styling and icons (Building2 + ChevronDown).
 */

import { Building2, ChevronDown } from "lucide-react";

interface BuildingSelectorProps {
  value: string;
  onChange: (value: string) => void;
  sites: Array<{ id: string; name: string }>;
  disabled?: boolean;
  /**
   * Show optional "All Buildings" option for filtering use cases.
   * When enabled, user can select empty string to show all sites.
   */
  allowAllOption?: boolean;
}

export function BuildingSelector({
  value,
  onChange,
  sites,
  disabled = false,
  allowAllOption = false,
}: BuildingSelectorProps) {
  return (
    <div className="relative w-full">
      {/* Building Icon */}
      <Building2
        className="absolute left-3 top-1/2 transform -translate-y-1/2 h-4 w-4"
        style={{ color: "var(--color-sentinel-text-secondary)" }}
      />

      {/* Select Element */}
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        disabled={disabled}
        className="w-full pl-9 pr-8 py-2 text-sm rounded appearance-none cursor-pointer"
        style={{
          background: "var(--color-sentinel-bg-secondary)",
          border: "1px solid var(--color-sentinel-border)",
          color: "var(--color-sentinel-text-primary)",
          outline: "none",
          opacity: disabled ? 0.5 : 1,
          cursor: disabled ? "not-allowed" : "pointer",
        }}
      >
        {allowAllOption && (
          <option value="">All Buildings</option>
        )}
        {sites.map((site) => (
          <option key={site.id} value={site.id}>
            {site.name}
          </option>
        ))}
      </select>

      {/* Chevron Icon */}
      <ChevronDown
        className="absolute right-2 top-1/2 transform -translate-y-1/2 h-4 w-4 pointer-events-none"
        style={{ color: "var(--color-sentinel-text-secondary)" }}
      />
    </div>
  );
}
