/**
 * SiteCard Component - Site overview card for dashboard
 *
 * Displays:
 * - Site name and type badge
 * - Equipment count
 * - Active alerts (color-coded: red critical, yellow warning)
 * - Status indicator (online/offline)
 *
 * Requirement: DASH-01 - Multi-site overview
 */

import { Card, Text, Badge, Flex } from "@tremor/react";
import { Building2, Cpu, AlertTriangle } from "lucide-react";
import type { Site } from "../lib/api";

interface SiteCardProps {
  site: Site;
  onClick?: (site: Site) => void;
}

/**
 * Get badge color based on site status
 */
function getStatusColor(status: Site["status"]): "green" | "yellow" | "red" {
  switch (status) {
    case "normal":
      return "green";
    case "warning":
      return "yellow";
    case "critical":
      return "red";
    default:
      return "green";
  }
}

/**
 * Get badge color based on alert count
 */
function getAlertColor(alertCount: number, status: Site["status"]): "green" | "yellow" | "red" {
  if (status === "critical" || alertCount > 3) {
    return "red";
  }
  if (status === "warning" || alertCount > 0) {
    return "yellow";
  }
  return "green";
}

export function SiteCard({ site, onClick }: SiteCardProps) {
  const handleClick = () => {
    if (onClick) {
      onClick(site);
    }
  };

  return (
    <Card
      className={`p-4 transition-all duration-200 ${
        onClick ? "cursor-pointer hover:shadow-lg hover:border-bidvest-blue-300" : ""
      }`}
      onClick={handleClick}
    >
      {/* Header: Name and Status */}
      <Flex justifyContent="between" alignItems="start" className="mb-3">
        <div className="flex items-center gap-2">
          <Building2 className="h-5 w-5 text-bidvest-blue-600" />
          <Text className="font-semibold text-gray-900">{site.name}</Text>
        </div>
        <Badge color={getStatusColor(site.status)} size="sm">
          {site.status}
        </Badge>
      </Flex>

      {/* Location */}
      <Text className="text-sm text-gray-500 mb-3">{site.location}</Text>

      {/* Type Badge */}
      <Badge color="gray" size="sm" className="mb-3">
        {site.type}
      </Badge>

      {/* Stats Row */}
      <Flex justifyContent="between" className="mt-3 pt-3 border-t border-gray-100">
        {/* Equipment Count */}
        <div className="flex items-center gap-1">
          <Cpu className="h-4 w-4 text-gray-400" />
          <Text className="text-sm text-gray-600">
            {site.equipment_count} equipment
          </Text>
        </div>

        {/* Alert Count */}
        <div className="flex items-center gap-1">
          <AlertTriangle
            className={`h-4 w-4 ${
              site.alert_count > 0 ? "text-amber-500" : "text-gray-400"
            }`}
          />
          <Badge color={getAlertColor(site.alert_count, site.status)} size="sm">
            {site.alert_count} alerts
          </Badge>
        </div>
      </Flex>
    </Card>
  );
}

export default SiteCard;
