/**
 * SolarDashboard - Full Solar & BESS Dashboard View
 *
 * Brings together all 6 solar components in a responsive grid layout
 * with a building selector for multi-site support.
 *
 * Layout:
 *   Row 1: Overview Panel | BESS Status | Energy Flow Diagram
 *   Row 2: Inverter Status Matrix (full width)
 *   Row 3: Financial Report | Forecast vs Actual Chart
 */

import { useState, useEffect, useCallback } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { Sun, Building2, ChevronDown, RefreshCw } from "lucide-react";
import { fetchSolarSites } from "../../lib/solarApi";
import type { SolarSite } from "../../lib/solarApi";
import { PageLoading } from "../PageLoading";
import { SolarOverviewPanel } from "./SolarOverviewPanel";
import { BESSStatusPanel } from "./BESSStatusPanel";
import { InverterStatusMatrix } from "./InverterStatusMatrix";
import { EnergyFlowDiagram } from "./EnergyFlowDiagram";
import { SolarFinancialReport } from "./SolarFinancialReport";
import { ForecastActualChart } from "./ForecastActualChart";
import { SolarAnnualCard } from "./SolarAnnualCard";

/**
 * SolarDashboard - Main solar & BESS monitoring view
 *
 * Components use React Query hooks for automatic caching, deduplication, and
 * request management. The refresh button invalidates all solar queries.
 *
 * Layout:
 * - Row 1: Overview (generation, performance) | BESS (SOC, mode) | Energy Flow
 * - Row 2: Inverter Status Matrix (full width)
 * - Row 3: Financial Report | Forecast vs Actual Chart
 */
export function SolarDashboard() {
  const queryClient = useQueryClient();
  const [solarSites, setSolarSites] = useState<SolarSite[]>([]);
  const [selectedSiteId, setSelectedSiteId] = useState<string>("");
  const [isRefreshing, setIsRefreshing] = useState(false);

  // Fetch solar sites on mount
  useEffect(() => {
    fetchSolarSites()
      .then((sites) => {
        // Deduplicate sites by site_id
        const uniqueSites = Array.from(
          new Map(sites.map((site) => [site.site_id, site])).values()
        );
        setSolarSites(uniqueSites);
        if (uniqueSites.length > 0 && !selectedSiteId) {
          setSelectedSiteId(uniqueSites[0].site_id);
        }
      })
      .catch(() => {
        // Fallback if API not available
        setSolarSites([
          { site_id: "site-002", site_name: "Solar Campus", building_name: "Sandton City Office Tower", plants: 2, connectors: 3, last_poll: null },
        ]);
        if (!selectedSiteId) setSelectedSiteId("site-002");
      });
  }, [selectedSiteId]);

  /**
   * Refresh all solar queries via React Query
   *
   * Invalidates all solar queries (overview, BESS, inverters, performance, financial)
   * which triggers refetch of stale data. This respects React Query's stale time,
   * so in-cache data is immediately refetched while fresh data is used as-is.
   */
  const handleRefresh = useCallback(() => {
    setIsRefreshing(true);
    // Invalidate all solar-related queries
    queryClient.invalidateQueries({ queryKey: ['solar-overview'] });
    queryClient.invalidateQueries({ queryKey: ['solar-bess'] });
    queryClient.invalidateQueries({ queryKey: ['solar-inverters'] });
    queryClient.invalidateQueries({ queryKey: ['solar-performance'] });
    queryClient.invalidateQueries({ queryKey: ['solar-financial'] });
    setTimeout(() => setIsRefreshing(false), 1000);
  }, [queryClient]);

  return (
    <div
      className="h-full overflow-y-auto p-4 md:p-6"
      style={{ background: "var(--color-sentinel-bg-canvas)" }}
    >
      {/* Header */}
      <div className="flex items-center justify-between mb-6 flex-wrap gap-3">
        <div className="flex items-center gap-3">
          <div
            className="p-2 rounded"
            style={{ background: "rgba(245, 158, 11, 0.15)" }}
          >
            <Sun className="h-5 w-5" style={{ color: "var(--color-sentinel-amber)" }} />
          </div>
          <div>
            <h2
              className="text-lg font-semibold"
              style={{ color: "var(--color-sentinel-text-primary)" }}
            >
              Solar & BESS
            </h2>
            <p
              className="text-xs"
              style={{ color: "var(--color-sentinel-text-secondary)" }}
            >
              Generation, storage, dispatch, and financial performance
            </p>
          </div>
        </div>

        <div className="flex items-center gap-3">
          {/* Building Selector */}
          <div className="relative">
            <Building2
              className="absolute left-3 top-1/2 transform -translate-y-1/2 h-4 w-4"
              style={{ color: "var(--color-sentinel-text-secondary)" }}
            />
            <ChevronDown
              className="absolute right-2 top-1/2 transform -translate-y-1/2 h-3 w-3 pointer-events-none"
              style={{ color: "var(--color-sentinel-text-secondary)" }}
            />
            <select
              value={selectedSiteId}
              onChange={(e) => setSelectedSiteId(e.target.value)}
              className="pl-9 pr-7 py-1.5 text-sm rounded appearance-none cursor-pointer"
              style={{
                background: "var(--color-sentinel-bg-secondary)",
                border: "1px solid var(--color-sentinel-border)",
                color: "var(--color-sentinel-text-primary)",
                outline: "none",
                minWidth: "250px",
              }}
            >
              {solarSites.map((site) => (
                <option key={site.site_id} value={site.site_id}>
                  {site.building_name} — {site.site_name}
                </option>
              ))}
            </select>
          </div>

          {/* Refresh */}
          <button
            onClick={handleRefresh}
            className="p-2 rounded"
            style={{
              background: "var(--color-sentinel-bg-secondary)",
              border: "1px solid var(--color-sentinel-border)",
              color: "var(--color-sentinel-text-secondary)",
              cursor: "pointer",
            }}
            title="Refresh all panels"
          >
            <RefreshCw
              className={`h-4 w-4 ${isRefreshing ? "animate-spin" : ""}`}
            />
          </button>
        </div>
      </div>

      {/* Row 1: Overview + BESS + Energy Flow */}
      {!selectedSiteId ? (
        <PageLoading message="Loading solar sites..." />
      ) : (
      <>
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4 mb-4">
        <div
          className="glass-panel overflow-hidden"
        >
          <SolarOverviewPanel siteId={selectedSiteId} />
        </div>
        <div
          className="glass-panel overflow-hidden"
        >
          <BESSStatusPanel siteId={selectedSiteId} />
        </div>
        <div
          className="glass-panel overflow-hidden"
        >
          <EnergyFlowDiagram siteId={selectedSiteId} />
        </div>
      </div>

      {/* Row 2: Inverter Matrix (full width) */}
      <div className="mb-4">
        <div
          className="glass-panel overflow-hidden"
        >
          <InverterStatusMatrix siteId={selectedSiteId} />
        </div>
      </div>

      {/* Row 3: Financial Report + Forecast Chart */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 mb-4">
        <div
          className="glass-panel overflow-hidden"
        >
          <SolarFinancialReport siteId={selectedSiteId} />
        </div>
        <div
          className="glass-panel overflow-hidden"
        >
          <ForecastActualChart siteId={selectedSiteId} />
        </div>
      </div>

      {/* Row 4: Annual Simulation Results (365 days) */}
      <div className="mb-4">
        <div
          className="glass-panel overflow-hidden"
        >
          <SolarAnnualCard siteId={selectedSiteId} />
        </div>
      </div>
      </>
      )}
    </div>
  );
}

export default SolarDashboard;
