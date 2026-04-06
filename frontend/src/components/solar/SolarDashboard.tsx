/**
 * SolarDashboard - Full Solar & BESS Dashboard View
 *
 * Brings together all 6 solar components in a responsive grid layout
 * with a building selector for multi-site support.
 *
 * Layout:
 *   Row 1: Overview Panel | BESS Status | Energy Flow Diagram
 *   Row 2: Inverter Status Matrix (full width)
 *   Row 3: (removed) financial cards moved out of ops view
 */

import { useState, useEffect, useCallback } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { Sun, Building2, ChevronDown, RefreshCw } from "lucide-react";
import { authorizedFetch } from "@/lib/api/client";
import { fetchSolarSites } from "../../lib/solarApi";
import type { SolarSite } from "../../lib/solarApi";
import { useModuleAccess } from "../../hooks/useModuleAccess";
import { PageLoading } from "../PageLoading";
import { SolarOverviewPanel } from "./SolarOverviewPanel";
import { BESSStatusPanel } from "./BESSStatusPanel";
import { InverterStatusMatrix } from "./InverterStatusMatrix";
import { EnergyFlowDiagram } from "./EnergyFlowDiagram";

/**
 * SolarDashboard - Main solar & BESS monitoring view
 *
 * Components use React Query hooks for automatic caching, deduplication, and
 * request management. The refresh button invalidates all solar queries.
 *
 * Layout:
 * - Row 1: Overview (generation, performance) | BESS (SOC, mode) | Energy Flow
 * - Row 2: Inverter Status Matrix (full width)
 * - Row 3: intentionally omitted (financial cards are non-operational)
 */
interface BridgeTelemetrySummary {
  status: "live" | "unavailable";
  zones_with_readings?: number;
  zone_count?: number;
  power?: {
    hvac_kw?: number;
    lighting_kw?: number;
    total_kw?: number;
  };
}

interface SolarDashboardProps {
  siteId?: string;
}

export function SolarDashboard({ siteId: propSiteId }: SolarDashboardProps) {
  const queryClient = useQueryClient();
  const [solarSites, setSolarSites] = useState<SolarSite[]>([]);
  const [selectedSiteId, setSelectedSiteId] = useState<string>(propSiteId ?? "");
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [bridgeTelemetry, setBridgeTelemetry] = useState<BridgeTelemetrySummary | null>(null);
  const [sentinelGuidance, setSentinelGuidance] = useState<string | null>(null);
  const [sentinelPosture, setSentinelPosture] = useState<string | null>(null);
  const { isActive: isSolarActive } = useModuleAccess('solar');

  // Refetch all solar data when module is activated (eliminates 30s stale data lag)
  useEffect(() => {
    if (isSolarActive) {
      queryClient.invalidateQueries({ queryKey: ['solar-overview'] });
      queryClient.invalidateQueries({ queryKey: ['solar-bess'] });
      queryClient.invalidateQueries({ queryKey: ['solar-inverters'] });
      queryClient.invalidateQueries({ queryKey: ['solar-performance'] });
      queryClient.invalidateQueries({ queryKey: ['solar-financial'] });
    }
  }, [isSolarActive, queryClient]);

  // Fetch solar sites on mount
  useEffect(() => {
    fetchSolarSites()
      .then((sites) => {
        // Deduplicate sites by site_id
        const uniqueSites = Array.from(
          new Map(sites.map((site) => [site.site_id, site])).values()
        );
        setSolarSites(uniqueSites);
        if (propSiteId) {
          const requested = uniqueSites.find((site) => site.site_id === propSiteId);
          if (requested) {
            setSelectedSiteId(requested.site_id);
            return;
          }
        }
        if (uniqueSites.length > 0 && !selectedSiteId) {
          const preferredSite =
            uniqueSites.find((site) => site.site_id === "site-002")
            ?? uniqueSites.find((site) => /sandton city office tower/i.test(site.site_name || ""))
            ?? uniqueSites[0];
          setSelectedSiteId(preferredSite.site_id);
        }
      })
      .catch(() => {
        // Fallback if API not available
        // Fallback: empty state when API is unavailable
        setSolarSites([]);
        // selectedSiteId stays empty if no API data
      });
  }, [selectedSiteId, propSiteId]);

  useEffect(() => {
    if (!selectedSiteId) return;
    let mounted = true;

    async function loadTelemetrySummary() {
      try {
        const [rawTelemetryResp, stateResp] = await Promise.all([
          authorizedFetch(`/api/sites/${encodeURIComponent(selectedSiteId)}/telemetry`).catch(() => null),
          authorizedFetch(`/api/building-state/${encodeURIComponent(selectedSiteId)}`).catch(() => null),
        ]);
        if (!mounted) return;

        if (rawTelemetryResp && rawTelemetryResp.ok) {
          const raw = await rawTelemetryResp.json();
          setBridgeTelemetry({
            status: "live",
            zones_with_readings: raw?.zones_with_readings ?? 0,
            zone_count: raw?.zone_count ?? 0,
            power: raw?.power ?? {},
          });
        } else {
          setBridgeTelemetry({ status: "unavailable" });
        }

        if (stateResp && stateResp.ok) {
          const state = await stateResp.json();
          setSentinelGuidance(state?.payload?.operator_guidance?.headline || null);
          setSentinelPosture(state?.payload?.building_posture || null);
        } else {
          setSentinelGuidance(null);
          setSentinelPosture(null);
        }
      } catch {
        if (mounted) {
          setBridgeTelemetry({ status: "unavailable" });
          setSentinelGuidance(null);
          setSentinelPosture(null);
        }
      }
    }

    loadTelemetrySummary();
    return () => {
      mounted = false;
    };
  }, [selectedSiteId]);

  // Refetch all solar data when module is activated
  useEffect(() => {
    if (isSolarActive) {
      queryClient.invalidateQueries({ queryKey: ['solar-overview'] });
      queryClient.invalidateQueries({ queryKey: ['solar-bess'] });
      queryClient.invalidateQueries({ queryKey: ['solar-inverters'] });
      queryClient.invalidateQueries({ queryKey: ['solar-performance'] });
      queryClient.invalidateQueries({ queryKey: ['solar-financial'] });
    }
  }, [isSolarActive, queryClient]);

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
            <div className="flex items-center gap-2">
              <h1
                className="text-2xl font-bold"
                style={{ color: "var(--color-sentinel-text-primary)" }}
              >
                Solar &amp; BESS
              </h1>
            </div>
            <p
              className="text-sm"
              style={{ color: "var(--color-sentinel-text-secondary)" }}
            >
              Generation, Storage and Dispatch Operations
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
                  {site.site_name} — {site.site_name}
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
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 mb-4">
        <div className="rounded-lg p-4" style={{ background: "var(--color-sentinel-bg-panel)", border: "1px solid var(--color-sentinel-border)" }}>
          <div className="flex items-center justify-between mb-2">
            <h2 className="text-sm font-semibold" style={{ color: "var(--color-sentinel-text-primary)" }}>
              Raw Bridge Telemetry
            </h2>
            <span
              className="text-xs px-2 py-1 rounded"
              style={{
                background: bridgeTelemetry?.status === "live" ? "rgba(16,185,129,0.15)" : "rgba(245,158,11,0.15)",
                color: bridgeTelemetry?.status === "live" ? "#10B981" : "#F59E0B",
              }}
            >
              {bridgeTelemetry?.status === "live" ? "Live" : "Unavailable"}
            </span>
          </div>
          <p className="text-xs" style={{ color: "var(--color-sentinel-text-secondary)" }}>
            Zones: {bridgeTelemetry?.zones_with_readings ?? 0}/{bridgeTelemetry?.zone_count ?? 0}
          </p>
          <p className="text-xs mt-1" style={{ color: "var(--color-sentinel-text-secondary)" }}>
            Power: HVAC {(bridgeTelemetry?.power?.hvac_kw ?? 0).toFixed(2)} kW · Lighting {(bridgeTelemetry?.power?.lighting_kw ?? 0).toFixed(2)} kW · Total {(bridgeTelemetry?.power?.total_kw ?? 0).toFixed(2)} kW
          </p>
        </div>
        <div className="rounded-lg p-4" style={{ background: "var(--color-sentinel-bg-panel)", border: "1px solid var(--color-sentinel-border)" }}>
          <h2 className="text-sm font-semibold mb-2" style={{ color: "var(--color-sentinel-text-primary)" }}>
            SENTINEL Solar Interpretation
          </h2>
          <p className="text-xs capitalize" style={{ color: "var(--color-sentinel-text-secondary)" }}>
            Posture: <span style={{ color: "var(--color-sentinel-text-primary)" }}>{sentinelPosture || "unknown"}</span>
          </p>
          <p className="text-xs mt-1" style={{ color: "var(--color-sentinel-text-secondary)" }}>
            {sentinelGuidance || "No active guidance yet."}
          </p>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4 mb-4">
        <div
          className="rounded-lg overflow-hidden"
          style={{ background: "var(--color-sentinel-bg-panel)", border: "1px solid var(--color-sentinel-border)" }}
        >
          <SolarOverviewPanel siteId={selectedSiteId} />
        </div>
        <div
          className="rounded-lg overflow-hidden"
          style={{ background: "var(--color-sentinel-bg-panel)", border: "1px solid var(--color-sentinel-border)" }}
        >
          <BESSStatusPanel siteId={selectedSiteId} />
        </div>
        <div
          className="rounded-lg overflow-hidden"
          style={{ background: "var(--color-sentinel-bg-panel)", border: "1px solid var(--color-sentinel-border)" }}
        >
          <EnergyFlowDiagram siteId={selectedSiteId} />
        </div>
      </div>

      {/* Row 2: Inverter Matrix (full width) */}
      <div className="mb-4">
        <div
          className="rounded-lg overflow-hidden"
          style={{ background: "var(--color-sentinel-bg-panel)", border: "1px solid var(--color-sentinel-border)" }}
        >
          <InverterStatusMatrix siteId={selectedSiteId} />
        </div>
      </div>

      </>
      )}
    </div>
  );
}

export default SolarDashboard;
