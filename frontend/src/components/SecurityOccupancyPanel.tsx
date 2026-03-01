/**
 * SecurityOccupancyPanel Component - Badge-based occupancy with cross-module recommendations
 *
 * Features:
 * - Per-zone occupancy display with count and bar chart
 * - Building total occupancy prominently displayed
 * - Cross-module recommendations section:
 *   - HVAC setpoint relaxation recommendations
 *   - Lighting dimming recommendations
 * - Follows SENTINEL dark theme design
 */

import { useState, useEffect, useCallback } from "react";
import {
  Users,
  Thermometer,
  Lightbulb,
  AlertTriangle,
  Building2,
} from "lucide-react";
import { isExpectedApiError, securityApi } from '@/lib/api';
import type { SecurityOccupancy, OccupancyRecommendation } from '@/lib/api';

/** Maximum capacity per zone for bar chart display */
const ZONE_CAPACITY = 30;

interface SecurityOccupancyPanelProps {
  siteId?: string;
  /** Refresh key to force data reload from parent */
  refreshKey?: number;
}

export function SecurityOccupancyPanel({ siteId = "", refreshKey }: SecurityOccupancyPanelProps) {
  const [zones, setZones] = useState<SecurityOccupancy[]>([]);
  const [totalOccupancy, setTotalOccupancy] = useState(0);
  const [recommendations, setRecommendations] = useState<OccupancyRecommendation[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchData = useCallback(async (_showRefreshing = false) => {
    try {

      const [occupancyResult, recsResult] = await Promise.all([
        securityApi.getOccupancy(siteId),
        securityApi.getOccupancyRecommendations(siteId),
      ]);

      setZones(occupancyResult.zones || []);
      setTotalOccupancy(occupancyResult.total_occupancy || 0);
      setRecommendations(recsResult.recommendations || []);
      setError(null);
    } catch (err) {
      if (!isExpectedApiError(err)) {
        console.error("Failed to fetch occupancy data:", err);
      }
      setError("Failed to load occupancy data");
    } finally {
      setLoading(false);
    }
  }, [siteId]);

  // Fetch on mount
  useEffect(() => {
    fetchData();
  }, [fetchData]);

  // Re-fetch when parent triggers refresh
  useEffect(() => {
    if (refreshKey !== undefined && refreshKey > 0) {
      fetchData(true);
    }
  }, [refreshKey, fetchData]);

  // Auto-refresh every 15 seconds
  useEffect(() => {
    const interval = setInterval(() => {
      fetchData(true);
    }, 15000);
    return () => clearInterval(interval);
  }, [fetchData]);

  const getOccupancyPercent = (count: number) =>
    Math.min(100, Math.round((count / ZONE_CAPACITY) * 100));

  const getOccupancyColor = (count: number) => {
    const pct = getOccupancyPercent(count);
    if (pct > 70) return "var(--color-sentinel-red)";
    if (pct >= 40) return "var(--color-sentinel-amber)";
    if (pct > 0) return "var(--color-sentinel-green)";
    return "var(--color-sentinel-text-disabled)";
  };

  // Loading state
  if (loading && zones.length === 0) {
    return (
      <div
        className="rounded-md overflow-hidden"
        style={{
          background: "var(--color-sentinel-bg-panel)",
          border: "1px solid var(--color-sentinel-border)",
        }}
      >
        <div className="p-4">
          <div className="animate-pulse space-y-3">
            {[1, 2, 3].map((i) => (
              <div
                key={i}
                className="h-10 rounded"
                style={{ background: "var(--color-sentinel-bg-secondary)" }}
              />
            ))}
          </div>
        </div>
      </div>
    );
  }

  // Error state
  if (error) {
    return (
      <div
        className="rounded-md overflow-hidden"
        style={{
          background: "var(--color-sentinel-bg-panel)",
          border: "1px solid var(--color-sentinel-border)",
        }}
      >
        <div className="p-4">
          <div
            className="flex items-center gap-2 text-sm"
            style={{ color: "var(--color-sentinel-red)" }}
          >
            <AlertTriangle className="h-4 w-4" />
            <span>{error}</span>
          </div>
        </div>
      </div>
    );
  }

  const hvacRecs = recommendations.filter((r) => r.recommendation_type === "hvac");
  const lightingRecs = recommendations.filter(
    (r) => r.recommendation_type === "lighting"
  );

  return (
    <div className="space-y-4">
      {/* Building Total Occupancy */}
      <div
        className="rounded-md p-5"
        style={{
          background: "var(--color-sentinel-bg-panel)",
          border: "1px solid var(--color-sentinel-border)",
        }}
      >
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-3">
            <div
              className="p-2.5 rounded"
              style={{ background: "rgba(59, 130, 246, 0.15)" }}
            >
              <Building2
                className="h-6 w-6"
                style={{ color: "var(--color-sentinel-blue)" }}
              />
            </div>
            <div>
              <span
                className="font-medium text-sm block"
                style={{ color: "var(--color-sentinel-text-primary)" }}
              >
                Building Occupancy
              </span>
              <span
                className="text-xs"
                style={{ color: "var(--color-sentinel-text-secondary)" }}
              >
                Badge-based tracking across {zones.length} zones
              </span>
            </div>
          </div>
          <div className="text-right">
            <span
              className="text-3xl font-bold block"
              style={{ color: getOccupancyColor(totalOccupancy) }}
            >
              {totalOccupancy}
            </span>
            <span
              className="text-xs"
              style={{ color: "var(--color-sentinel-text-secondary)" }}
            >
              people in building
            </span>
          </div>
        </div>

        {/* Per-zone bars */}
        <div className="space-y-2.5">
          {zones.map((zone) => {
            const pct = getOccupancyPercent(zone.occupancy_count);
            return (
              <div key={zone.zone_id} className="flex items-center gap-3">
                <span
                  className="text-xs w-36 truncate"
                  style={{ color: "var(--color-sentinel-text-secondary)" }}
                  title={zone.zone_name}
                >
                  {zone.zone_name}
                </span>
                <div
                  className="flex-1 h-5 rounded overflow-hidden relative"
                  style={{ background: "var(--color-sentinel-bg-secondary)" }}
                >
                  <div
                    className="h-full rounded transition-all duration-500"
                    style={{
                      width: `${pct}%`,
                      background: getOccupancyColor(zone.occupancy_count),
                      minWidth: zone.occupancy_count > 0 ? "4px" : "0",
                    }}
                  />
                </div>
                <span
                  className="text-xs w-12 text-right font-mono"
                  style={{ color: getOccupancyColor(zone.occupancy_count) }}
                >
                  {zone.occupancy_count}
                </span>
              </div>
            );
          })}
        </div>
      </div>

      {/* Cross-module Recommendations */}
      {recommendations.length > 0 && (
        <div
          className="rounded-md overflow-hidden"
          style={{
            background: "var(--color-sentinel-bg-panel)",
            border: "1px solid var(--color-sentinel-border)",
          }}
        >
          <div
            className="p-4 flex items-center gap-2"
            style={{ borderBottom: "1px solid var(--color-sentinel-border)" }}
          >
            <Users
              className="h-5 w-5"
              style={{ color: "var(--color-sentinel-amber)" }}
            />
            <span
              className="font-medium text-sm"
              style={{ color: "var(--color-sentinel-text-primary)" }}
            >
              Cross-Module Recommendations
            </span>
            <span
              className="text-xs px-2 py-0.5 rounded"
              style={{
                background: "rgba(245, 158, 11, 0.15)",
                color: "var(--color-sentinel-amber)",
              }}
            >
              {recommendations.length}
            </span>
          </div>

          <div className="p-4 space-y-3">
            {/* HVAC Recommendations */}
            {hvacRecs.length > 0 && (
              <div className="space-y-2">
                {hvacRecs.map((rec, idx) => (
                  <div
                    key={`hvac-${idx}`}
                    className="flex items-start gap-3 p-3 rounded"
                    style={{
                      background: "rgba(59, 130, 246, 0.05)",
                      border: "1px solid rgba(59, 130, 246, 0.15)",
                    }}
                  >
                    <div
                      className="p-1.5 rounded flex-shrink-0 mt-0.5"
                      style={{ background: "rgba(59, 130, 246, 0.15)" }}
                    >
                      <Thermometer
                        className="h-4 w-4"
                        style={{ color: "var(--color-sentinel-blue)" }}
                      />
                    </div>
                    <div className="flex-1 min-w-0">
                      <span
                        className="text-sm block"
                        style={{ color: "var(--color-sentinel-text-primary)" }}
                      >
                        {rec.zone_name}{" "}
                        <span style={{ color: "var(--color-sentinel-text-secondary)" }}>
                          (occupancy: {rec.current_occupancy})
                        </span>
                      </span>
                      <span
                        className="text-xs block mt-0.5"
                        style={{ color: "var(--color-sentinel-blue)" }}
                      >
                        {rec.action}
                      </span>
                      {rec.detail && (
                        <span
                          className="text-xs block mt-0.5"
                          style={{ color: "var(--color-sentinel-text-disabled)" }}
                        >
                          {rec.detail}
                        </span>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            )}

            {/* Lighting Recommendations */}
            {lightingRecs.length > 0 && (
              <div className="space-y-2">
                {lightingRecs.map((rec, idx) => (
                  <div
                    key={`lighting-${idx}`}
                    className="flex items-start gap-3 p-3 rounded"
                    style={{
                      background: "rgba(245, 158, 11, 0.05)",
                      border: "1px solid rgba(245, 158, 11, 0.15)",
                    }}
                  >
                    <div
                      className="p-1.5 rounded flex-shrink-0 mt-0.5"
                      style={{ background: "rgba(245, 158, 11, 0.15)" }}
                    >
                      <Lightbulb
                        className="h-4 w-4"
                        style={{ color: "var(--color-sentinel-amber)" }}
                      />
                    </div>
                    <div className="flex-1 min-w-0">
                      <span
                        className="text-sm block"
                        style={{ color: "var(--color-sentinel-text-primary)" }}
                      >
                        {rec.zone_name}{" "}
                        <span style={{ color: "var(--color-sentinel-text-secondary)" }}>
                          (occupancy: {rec.current_occupancy})
                        </span>
                      </span>
                      <span
                        className="text-xs block mt-0.5"
                        style={{ color: "var(--color-sentinel-amber)" }}
                      >
                        {rec.action}
                      </span>
                      {rec.detail && (
                        <span
                          className="text-xs block mt-0.5"
                          style={{ color: "var(--color-sentinel-text-disabled)" }}
                        >
                          {rec.detail}
                        </span>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

export default SecurityOccupancyPanel;
