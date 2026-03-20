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
      <Building2
        className="absolute left-3 top-1/2 transform -translate-y-1/2 h-4 w-4"
        style={{ color: "var(--color-grafana-text-secondary)" }}
      />

      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        disabled={disabled}
        className="w-full rounded-md appearance-none cursor-pointer pl-9 pr-9 py-2.5 text-sm transition-colors focus:outline-none focus:ring-0"
        style={{
          background: "var(--color-grafana-bg-secondary)",
          border: "1px solid var(--color-grafana-border)",
          color: "var(--color-grafana-text-primary)",
          boxShadow: "inset 0 1px 0 rgba(255,255,255,0.03)",
          outline: "none",
          opacity: disabled ? 0.5 : 1,
          cursor: disabled ? "not-allowed" : "pointer",
        }}
        aria-label="Select building"
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

      <ChevronDown
        className="absolute right-2 top-1/2 transform -translate-y-1/2 h-4 w-4 pointer-events-none"
        style={{ color: "var(--color-grafana-text-secondary)" }}
      />
    </div>
  );
}
