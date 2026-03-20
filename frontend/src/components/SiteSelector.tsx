/**
 * SiteSelector Component - Dropdown for selecting site filter
 *
 * Uses Tremor Select component with "All Sites" option.
 *
 * Props:
 * - sites: List of sites to display
 * - selectedSiteId: Currently selected site ID (null for all)
 * - onSiteChange: Callback when selection changes
 */

import { Select, SelectItem } from "@tremor/react";
import { Building2 } from "lucide-react";
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
    <Select
      value={selectedSiteId ?? "all"}
      onValueChange={handleChange}
      icon={Building2}
      placeholder="Select a site"
    >
      {includeAllOption && <SelectItem value="all">All Sites</SelectItem>}
      {sites.map((site) => (
        <SelectItem key={site.id} value={site.id}>
          {site.name}
        </SelectItem>
      ))}
    </Select>
  );
}

export default SiteSelector;
