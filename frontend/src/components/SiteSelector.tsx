/**
 * SiteSelector Component - dropdown for selecting site filter.
 * Uses the same native select styling as BuildingSelector.
 */

import { Building2, ChevronDown } from "lucide-react";
import type { Site } from '@/lib/api';

interface SiteSelectorProps {
  sites: Site[];
  selectedSiteId: string | null;
  onSiteChange: (siteId: string | null) => void;
  includeAllOption?: boolean;
}

export function SiteSelector({
  sites,
  selectedSiteId,
  onSiteChange,
  includeAllOption = true,
}: SiteSelectorProps) {
  const handleChange = (value: string) => {
    // "all" means no filter
    onSiteChange(value === "all" ? null : value);
  };

  return (
    <div className="relative w-full">
      <Building2
        className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 transform"
        style={{ color: "var(--color-grafana-text-secondary)" }}
      />

      <select
        value={selectedSiteId ?? "all"}
        onChange={(event) => handleChange(event.target.value)}
        className="w-full rounded-md appearance-none cursor-pointer pl-9 pr-9 py-2.5 text-sm transition-colors focus:outline-none focus:ring-0"
        style={{
          background: "var(--color-grafana-bg-secondary)",
          border: "1px solid var(--color-grafana-border)",
          color: "var(--color-grafana-text-primary)",
          boxShadow: "inset 0 1px 0 rgba(255,255,255,0.03)",
          outline: "none",
        }}
        aria-label="Select site"
      >
        {includeAllOption && <option value="all">All Sites</option>}
        {!includeAllOption && <option value="all">Select a site</option>}
        {sites.map((site) => (
          <option key={site.id} value={site.id}>
            {site.name}
          </option>
        ))}
      </select>

      <ChevronDown
        className="pointer-events-none absolute right-2 top-1/2 h-4 w-4 -translate-y-1/2 transform"
        style={{ color: "var(--color-grafana-text-secondary)" }}
      />
    </div>
  );
}

export default SiteSelector;
