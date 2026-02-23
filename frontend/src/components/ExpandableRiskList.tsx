/**
 * ExpandableRiskList Component - Collapsible at-risk equipment list
 *
 * Shows equipment with warning/critical status within a SiteCard:
 * - Expand/collapse toggle with chevron icon
 * - Equipment rows sorted by risk (critical first, then by lowest health)
 * - Each row shows status icon, name, type, health %, navigation arrow
 * - Click row to navigate to control
 * - Click status badge to open RiskDetailModal
 *
 * Follows SENTINEL dark theme design.
 */

import { useState, useEffect } from "react";
import {
  ChevronDown,
  AlertCircle,
  AlertTriangle,
  ChevronRight,
  Loader2,
} from "lucide-react";
import api from '@/lib/api';
import type { BuildingEquipmentItem } from '@/lib/api';

interface ExpandableRiskListProps {
  siteId: string;
  expanded: boolean;
  onToggle: () => void;
  onEquipmentClick: (equipment: BuildingEquipmentItem) => void;
  onStatusBadgeClick: (equipment: BuildingEquipmentItem) => void;
}

export function ExpandableRiskList({
  siteId,
  expanded,
  onToggle,
  onEquipmentClick,
  onStatusBadgeClick,
}: ExpandableRiskListProps) {
  const [equipment, setEquipment] = useState<BuildingEquipmentItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [hasFetched, setHasFetched] = useState(false);

  // Lazy load equipment when first expanded
  useEffect(() => {
    if (expanded && !hasFetched) {
      const loadEquipment = async () => {
        setLoading(true);
        try {
          // Map site ID to building ID (site-002 -> sandton)
          const buildingId = siteId === "site-002" ? "sandton" : siteId;
          const response = await api.getBuildingEquipment(buildingId);

          // Filter for at-risk equipment: explicit status OR health-based degradation
          // Aligns with SafetySummary logic in sites_aggregation.py
          const riskEquipment = response.equipment.filter((e) => {
            if (e.status === "warning" || e.status === "critical") return true;
            if (e.status === "offline" || e.status === "maintenance") return true;
            // Health-based: normal status but degraded health
            // Backend returns health_score, not health
            const health = (e as any).health_score ?? (e as any).health ?? 100;
            if (health < 80) return true;
            return false;
          });

          // Sort: critical first, then warning, then by lowest health
          riskEquipment.sort((a, b) => {
            const priority = (s: string) =>
              s === "critical" ? 0 : s === "warning" ? 1 : s === "offline" ? 2 : 3;
            const pa = priority(a.status);
            const pb = priority(b.status);
            if (pa !== pb) return pa - pb;
            const ha = (a as any).health_score ?? (a as any).health ?? 100;
            const hb = (b as any).health_score ?? (b as any).health ?? 100;
            return ha - hb;
          });

          setEquipment(riskEquipment as any);
          setHasFetched(true);
        } catch (error) {
          console.error("Failed to load at-risk equipment:", error);
          setEquipment([]);
          setHasFetched(true);
        } finally {
          setLoading(false);
        }
      };

      loadEquipment();
    }
  }, [expanded, hasFetched, siteId]);

  // Handle row click - navigate to control
  const handleRowClick = (
    e: React.MouseEvent,
    eq: BuildingEquipmentItem
  ) => {
    // Don't trigger if clicking the status badge
    if ((e.target as HTMLElement).closest("[data-status-badge]")) {
      return;
    }
    onEquipmentClick(eq);
  };

  // Handle status badge click
  const handleStatusClick = (
    e: React.MouseEvent,
    eq: BuildingEquipmentItem
  ) => {
    e.stopPropagation();
    onStatusBadgeClick(eq);
  };

  return (
    <div
      className="border-t"
      style={{ borderColor: "var(--color-sentinel-border)" }}
    >
      {/* Toggle Header */}
      <button
        onClick={onToggle}
        className="w-full p-3 flex items-center justify-between hover:bg-white/5 transition-colors"
      >
        <span
          className="text-xs font-medium"
          style={{ color: "var(--color-sentinel-text-secondary)" }}
        >
          At-Risk Equipment
        </span>
        <div
          className="transition-transform duration-200"
          style={{ transform: expanded ? "rotate(180deg)" : "rotate(0deg)" }}
        >
          <ChevronDown
            className="h-4 w-4"
            style={{ color: "var(--color-sentinel-text-secondary)" }}
          />
        </div>
      </button>

      {/* Expandable Content */}
      <div
        className="overflow-hidden transition-all duration-200 ease-in-out"
        style={{
          maxHeight: expanded ? "400px" : "0",
          opacity: expanded ? 1 : 0,
        }}
      >
        <div className="px-3 pb-3">
          {loading ? (
            <div className="flex items-center justify-center py-4">
              <Loader2
                className="h-5 w-5 animate-spin"
                style={{ color: "var(--color-sentinel-text-disabled)" }}
              />
            </div>
          ) : equipment.length === 0 ? (
            <div
              className="text-center py-4 text-xs"
              style={{ color: "var(--color-sentinel-text-disabled)" }}
            >
              No at-risk equipment
            </div>
          ) : (
            <div className="space-y-1.5">
              {equipment.map((eq) => (
                <div
                  key={eq.id}
                  onClick={(e) => handleRowClick(e, eq)}
                  className="flex items-center justify-between p-2 rounded cursor-pointer hover:brightness-110 transition-all"
                  style={{
                    background:
                      eq.status === "critical"
                        ? "rgba(220, 38, 38, 0.1)"
                        : ((eq as any).health_score ?? (eq as any).health ?? 100) < 57
                        ? "rgba(220, 38, 38, 0.1)"
                        : "rgba(245, 158, 11, 0.1)",
                    border: `1px solid ${
                      eq.status === "critical"
                        ? "rgba(220, 38, 38, 0.2)"
                        : ((eq as any).health_score ?? (eq as any).health ?? 100) < 57
                        ? "rgba(220, 38, 38, 0.2)"
                        : "rgba(245, 158, 11, 0.2)"
                    }`,
                  }}
                >
                  {/* Left: Status icon + Equipment info */}
                  <div className="flex items-center gap-2 flex-1 min-w-0">
                    {/* Status badge (clickable) */}
                    <button
                      data-status-badge
                      onClick={(e) => handleStatusClick(e, eq)}
                      className="flex-shrink-0 p-1 rounded hover:bg-white/10 transition-colors"
                      title="View risk details"
                    >
                      {eq.status === "critical" || ((eq as any).health_score ?? (eq as any).health ?? 100) < 57 ? (
                        <AlertCircle
                          className="h-4 w-4"
                          style={{ color: "var(--color-sentinel-red)" }}
                        />
                      ) : (
                        <AlertTriangle
                          className="h-4 w-4"
                          style={{ color: "var(--color-sentinel-amber)" }}
                        />
                      )}
                    </button>

                    {/* Equipment name + type */}
                    <div className="min-w-0 flex-1">
                      <div
                        className="text-xs font-medium truncate"
                        style={{ color: "var(--color-sentinel-text-primary)" }}
                      >
                        {eq.name}
                      </div>
                      <div
                        className="text-xs truncate"
                        style={{ color: "var(--color-sentinel-text-disabled)" }}
                      >
                        {eq.type}
                      </div>
                    </div>
                  </div>

                  {/* Right: Health score + Arrow */}
                  <div className="flex items-center gap-2 flex-shrink-0">
                    <div
                      className="text-xs font-semibold"
                      style={{
                        color:
                          eq.status === "critical" || ((eq as any).health_score ?? (eq as any).health ?? 100) < 57
                            ? "var(--color-sentinel-red)"
                            : "var(--color-sentinel-amber)",
                      }}
                    >
                      {(eq as any).health_score ?? eq.health ?? '—'}%
                    </div>
                    <ChevronRight
                      className="h-4 w-4"
                      style={{ color: "var(--color-sentinel-text-disabled)" }}
                    />
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

export default ExpandableRiskList;
