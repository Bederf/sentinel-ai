/**
 * OptimizationSettings Component - Per-building AI optimization controls
 *
 * Displays:
 * - Site list with optimization status and toggles
 * - Bulk enable/disable controls
 * - Per-site settings detail panel
 * - Optimization history for each site
 * - Stats summary (sites optimized, savings, pending)
 *
 * Follows SENTINEL dark theme design.
 */

import { useState, useEffect, useCallback } from "react";
import {
  Settings as SettingsIcon,
  CheckCircle2,
  AlertTriangle,
  RefreshCw,
  Filter,
  ChevronRight,
  ChevronDown,
  Zap,
  DollarSign,
  Clock,
} from "lucide-react";
import api, { type Site } from "../lib/api";
import { OptimizationStatusBadge, type OptimizationStatus } from "./OptimizationStatusBadge";
import { OptimizationToggle } from "./OptimizationToggle";

interface OptimizationSettingsProps {
  /** Filter sites to show (default: all) */
  sites?: Site[];
  /** Auto-refresh interval in milliseconds (0 to disable) */
  refreshInterval?: number;
  /** Callback when settings are changed */
  onSettingsChange?: () => void;
}

interface SiteWithOptimizationStatus extends Site {
  optimizationStatus?: OptimizationStatus;
  optimizationError?: string;
}

type FilterMode = "all" | "enabled" | "disabled";

/**
 * Format currency in ZAR
 */
function formatCurrency(amount: number): string {
  return new Intl.NumberFormat("en-ZA", {
    style: "currency",
    currency: "ZAR",
    minimumFractionDigits: 0,
    maximumFractionDigits: 0,
  }).format(amount);
}

/**
 * Format timestamp as relative time
 */
function formatRelativeTime(timestamp: string): string {
  const now = new Date();
  const time = new Date(timestamp);
  const diffMs = now.getTime() - time.getTime();
  const diffMins = Math.floor(diffMs / 60000);

  if (diffMins < 1) return "just now";
  if (diffMins < 60) return `${diffMins}m ago`;

  const diffHours = Math.floor(diffMins / 60);
  if (diffHours < 24) return `${diffHours}h ago`;

  const diffDays = Math.floor(diffHours / 24);
  return `${diffDays}d ago`;
}

export function OptimizationSettings({
  sites: propSites,
  refreshInterval = 30000,
  onSettingsChange,
}: OptimizationSettingsProps) {
  const [sites, setSites] = useState<Site[]>([]);
  const [siteStatuses, setSiteStatuses] = useState<Record<string, SiteWithOptimizationStatus>>({});
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [filterMode, setFilterMode] = useState<FilterMode>("all");
  const [expandedSite, setExpandedSite] = useState<string | null>(null);
  // Reserved for future bulk operations
  // eslint-disable-next-line @typescript-eslint/no-unused-vars
  const [, setShowBulkConfirm] = useState<"enable" | "disable" | null>(null);
  const [stats, setStats] = useState({
    totalSites: 0,
    optimizedSites: 0,
    enabledSites: 0,
    totalSavings: 0,
    pendingRecommendations: 0,
  });

  /**
   * Fetch all sites
   */
  const fetchSites = useCallback(async () => {
    try {
      if (propSites) {
        setSites(propSites);
      } else {
        const allSites = await api.getSites();
        setSites(allSites);
      }
    } catch (err) {
      console.error("Failed to fetch sites:", err);
    }
  }, [propSites]);

  /**
   * Fetch optimization status for all sites
   */
  const fetchOptimizationStatuses = useCallback(async () => {
    setRefreshing(true);

    try {
      const statuses: Record<string, SiteWithOptimizationStatus> = {};
      let optimizedCount = 0;
      let enabledCount = 0;
      let pendingCount = 0;

      for (const site of sites) {
        if (!site.optimization_enabled) continue;

        try {
          const status = await api.getOptimizationStatus(site.id);
          statuses[site.id] = {
            ...site,
            optimizationStatus: status.optimization_status,
          };

          if (status.optimization_status === "optimized") optimizedCount++;
          if (status.optimization_enabled) enabledCount++;
          if (status.optimization_status === "recommendation_pending") pendingCount++;
        } catch (err) {
          console.error(`Failed to fetch status for ${site.id}:`, err);
          statuses[site.id] = {
            ...site,
            optimizationStatus: "error",
            optimizationError: err instanceof Error ? err.message : "Failed to fetch status",
          };
        }
      }

      setSiteStatuses(statuses);
      setStats({
        totalSites: sites.length,
        optimizedSites: optimizedCount,
        enabledSites: enabledCount,
        totalSavings: optimizedCount * 1250, // Demo: R1,250 per optimized site
        pendingRecommendations: pendingCount,
      });
    } catch (err) {
      console.error("Failed to fetch optimization statuses:", err);
    } finally {
      setRefreshing(false);
      setLoading(false);
    }
  }, [sites]);

  /**
   * Load initial data
   */
  useEffect(() => {
    fetchSites();
  }, [fetchSites]);

  /**
   * Fetch optimization statuses after sites are loaded
   */
  useEffect(() => {
    if (sites.length > 0) {
      fetchOptimizationStatuses();
    }
  }, [sites, fetchOptimizationStatuses]);

  /**
   * Set up auto-refresh
   */
  useEffect(() => {
    if (refreshInterval <= 0) return;

    const intervalId = setInterval(() => {
      fetchOptimizationStatuses();
    }, refreshInterval);

    return () => clearInterval(intervalId);
  }, [refreshInterval, fetchOptimizationStatuses]);

  /**
   * Handle toggle change for a site
   */
  const handleToggleChange = async (siteId: string, enabled: boolean) => {
    try {
      await api.toggleOptimization(siteId, enabled);

      // Update local state
      setSites((prev) =>
        prev.map((site) =>
          site.id === siteId ? { ...site, optimization_enabled: enabled } : site
        )
      );

      // Refresh optimization statuses
      await fetchOptimizationStatuses();

      // Notify parent
      if (onSettingsChange) {
        onSettingsChange();
      }
    } catch (err) {
      console.error("Failed to toggle optimization:", err);
      alert(err instanceof Error ? err.message : "Failed to toggle optimization");
    }
  };

  /**
   * Handle bulk enable/disable
   * Reserved for future implementation
   */
  // const handleBulkAction = async (action: "enable" | "disable") => {
  //   const sitesToUpdate = sites.filter((site) =>
  //     action === "enable" ? !site.optimization_enabled : site.optimization_enabled
  //   );
  //
  //   if (sitesToUpdate.length === 0) {
  //     alert(`No sites to ${action}`);
  //     setShowBulkConfirm(null);
  //     return;
  //   }
  //
  //   if (!confirm(`Are you sure you want to ${action} optimization for ${sitesToUpdate.length} sites?`)) {
  //     return;
  //   }
  //
  //   try {
  //     for (const site of sitesToUpdate) {
  //       await api.toggleOptimization(site.id, action === "enable");
  //     }
  //
  //     // Update local state
  //     setSites((prev) =>
  //       prev.map((site) =>
  //         sitesToUpdate.some((s) => s.id === site.id)
  //           ? { ...site, optimization_enabled: action === "enable" }
  //           : site
  //       )
  //     );
  //
  //     // Refresh optimization statuses
  //     await fetchOptimizationStatuses();
  //
  //     // Notify parent
  //     if (onSettingsChange) {
  //       onSettingsChange();
  //     }
  //
  //     setShowBulkConfirm(null);
  //   } catch (err) {
  //     console.error(`Failed to bulk ${action}:`, err);
  //     alert(err instanceof Error ? err.message : `Failed to ${action} optimization`);
  //   }
  // };

  /**
   * Filter sites based on filter mode
   */
  const filteredSites = sites.filter((site) => {
    if (filterMode === "all") return true;
    if (filterMode === "enabled") return site.optimization_enabled;
    if (filterMode === "disabled") return !site.optimization_enabled;
    return true;
  });

  // Loading state
  if (loading) {
    return (
      <div className="bg-gray-900 border border-gray-800 rounded-lg p-6">
        <div className="flex items-center gap-2 mb-4">
          <SettingsIcon className="w-5 h-5 text-gray-400" />
          <h2 className="text-lg font-semibold text-gray-200">AI Optimization Settings</h2>
        </div>
        <div className="space-y-3">
          {[...Array(5)].map((_, i) => (
            <div key={i} className="animate-pulse">
              <div className="h-16 bg-gray-800 rounded"></div>
            </div>
          ))}
        </div>
      </div>
    );
  }

  return (
    <div className="bg-gray-900 border border-gray-800 rounded-lg p-6">
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <div className="flex items-center gap-2">
          <SettingsIcon className="w-5 h-5 text-gray-400" />
          <h2 className="text-lg font-semibold text-gray-200">AI Optimization Settings</h2>
        </div>

        <div className="flex items-center gap-2">
          <button
            onClick={() => setShowBulkConfirm("enable")}
            className="px-3 py-1.5 text-sm bg-green-600 hover:bg-green-700 text-white rounded-md transition-colors"
          >
            Enable All
          </button>
          <button
            onClick={() => setShowBulkConfirm("disable")}
            className="px-3 py-1.5 text-sm bg-red-600 hover:bg-red-700 text-white rounded-md transition-colors"
          >
            Disable All
          </button>
          <button
            onClick={fetchOptimizationStatuses}
            disabled={refreshing}
            className="p-2 bg-gray-800 hover:bg-gray-700 text-gray-300 rounded-md transition-colors disabled:opacity-50"
            title="Refresh optimization status"
          >
            <RefreshCw className={`w-4 h-4 ${refreshing ? "animate-spin" : ""}`} />
          </button>
        </div>
      </div>

      {/* Stats Summary */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4 mb-6">
        <div className="flex items-center gap-3 p-3 rounded bg-blue-900/10 border border-blue-900/30">
          <CheckCircle2 className="w-5 h-5 text-blue-400" />
          <div>
            <div className="text-xs text-blue-300">Sites Optimized</div>
            <div className="text-lg font-semibold text-gray-200">
              {stats.optimizedSites} / {stats.totalSites}
            </div>
          </div>
        </div>

        <div className="flex items-center gap-3 p-3 rounded bg-green-900/10 border border-green-900/30">
          <Zap className="w-5 h-5 text-green-400" />
          <div>
            <div className="text-xs text-green-300">Sites Enabled</div>
            <div className="text-lg font-semibold text-gray-200">{stats.enabledSites}</div>
          </div>
        </div>

        <div className="flex items-center gap-3 p-3 rounded bg-yellow-900/10 border border-yellow-900/30">
          <AlertTriangle className="w-5 h-5 text-yellow-400" />
          <div>
            <div className="text-xs text-yellow-300">Pending Actions</div>
            <div className="text-lg font-semibold text-gray-200">{stats.pendingRecommendations}</div>
          </div>
        </div>

        <div className="flex items-center gap-3 p-3 rounded bg-purple-900/10 border border-purple-900/30">
          <DollarSign className="w-5 h-5 text-purple-400" />
          <div>
            <div className="text-xs text-purple-300">Est. Monthly Savings</div>
            <div className="text-lg font-semibold text-gray-200">{formatCurrency(stats.totalSavings)}</div>
          </div>
        </div>
      </div>

      {/* Filters */}
      <div className="flex items-center gap-2 mb-4">
        <Filter className="w-4 h-4 text-gray-400" />
        <span className="text-sm text-gray-400">Filter:</span>
        <button
          onClick={() => setFilterMode("all")}
          className={`px-3 py-1 text-sm rounded-md transition-colors ${
            filterMode === "all"
              ? "bg-blue-600 text-white"
              : "bg-gray-800 text-gray-300 hover:bg-gray-700"
          }`}
        >
          All ({sites.length})
        </button>
        <button
          onClick={() => setFilterMode("enabled")}
          className={`px-3 py-1 text-sm rounded-md transition-colors ${
            filterMode === "enabled"
              ? "bg-green-600 text-white"
              : "bg-gray-800 text-gray-300 hover:bg-gray-700"
          }`}
        >
          Enabled ({sites.filter((s) => s.optimization_enabled).length})
        </button>
        <button
          onClick={() => setFilterMode("disabled")}
          className={`px-3 py-1 text-sm rounded-md transition-colors ${
            filterMode === "disabled"
              ? "bg-red-600 text-white"
              : "bg-gray-800 text-gray-300 hover:bg-gray-700"
          }`}
        >
          Disabled ({sites.filter((s) => !s.optimization_enabled).length})
        </button>
      </div>

      {/* Site List */}
      <div className="space-y-2">
        {filteredSites.length === 0 ? (
          <div className="text-center py-8 text-gray-500 text-sm">
            No sites found with current filters
          </div>
        ) : (
          filteredSites.map((site) => {
            const siteStatus = siteStatuses[site.id];
            const isExpanded = expandedSite === site.id;

            return (
              <div
                key={site.id}
                className="border border-gray-800 rounded overflow-hidden"
              >
                {/* Site Row */}
                <div
                  className="flex items-center justify-between p-4 hover:bg-gray-800/50 cursor-pointer transition-colors"
                  onClick={() => setExpandedSite(isExpanded ? null : site.id)}
                >
                  <div className="flex items-center gap-4 flex-1">
                    <div className="flex-1">
                      <div className="font-medium text-gray-200">{site.name}</div>
                      <div className="text-xs text-gray-500">{site.location}</div>
                    </div>

                    {site.optimization_enabled && siteStatus?.optimizationStatus && (
                      <OptimizationStatusBadge
                        status={siteStatus.optimizationStatus}
                        size="sm"
                        lastOptimization={site.last_optimization}
                      />
                    )}

                    <div className="text-xs text-gray-500 w-32">
                      {site.optimization_settings?.last_analysis
                        ? formatRelativeTime(site.optimization_settings.last_analysis)
                        : "Never analyzed"}
                    </div>

                    <div
                      onClick={(e) => e.stopPropagation()}
                      className="w-32"
                    >
                      <OptimizationToggle
                        siteId={site.id}
                        enabled={site.optimization_enabled || false}
                        onToggle={(enabled) => handleToggleChange(site.id, enabled)}
                      />
                    </div>

                    <button className="p-1 text-gray-400 hover:text-gray-200">
                      {isExpanded ? (
                        <ChevronDown className="w-4 h-4" />
                      ) : (
                        <ChevronRight className="w-4 h-4" />
                      )}
                    </button>
                  </div>
                </div>

                {/* Expanded Detail Panel */}
                {isExpanded && (
                  <div className="p-4 border-t border-gray-800 bg-gray-800/30">
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                      {/* Optimization Mode */}
                      <div>
                        <div className="text-xs text-gray-400 mb-1">Mode</div>
                        <div className="text-sm text-gray-200">
                          {site.optimization_settings?.mode === "automatic"
                            ? "Automatic (Supervised)"
                            : "Supervised"}
                        </div>
                      </div>

                      {/* Analysis Interval */}
                      <div>
                        <div className="text-xs text-gray-400 mb-1">Analysis Interval</div>
                        <div className="text-sm text-gray-200">
                          {site.optimization_settings?.analysis_interval_minutes || 15} minutes
                        </div>
                      </div>

                      {/* Last Optimization */}
                      <div>
                        <div className="text-xs text-gray-400 mb-1">Last Optimization</div>
                        <div className="text-sm text-gray-200">
                          {site.last_optimization
                            ? new Date(site.last_optimization).toLocaleString()
                            : "Never"}
                        </div>
                      </div>

                      {/* Status */}
                      <div>
                        <div className="text-xs text-gray-400 mb-1">Status</div>
                        <div className="text-sm text-gray-200">
                          {site.optimization_enabled ? (
                            <span className="text-green-400">Enabled</span>
                          ) : (
                            <span className="text-red-400">Disabled</span>
                          )}
                        </div>
                      </div>
                    </div>

                    {/* Optimization History */}
                    {site.optimization_history && site.optimization_history.length > 0 && (
                      <div className="mt-4">
                        <div className="text-xs text-gray-400 mb-2">Recent History</div>
                        <div className="space-y-1">
                          {site.optimization_history.slice(0, 5).map((entry, idx) => (
                            <div
                              key={idx}
                              className="flex items-center gap-2 text-xs p-2 rounded bg-gray-900/50"
                            >
                              <Clock className="w-3 h-3 text-gray-500" />
                              <span className="text-gray-500">
                                {formatRelativeTime(entry.timestamp)}
                              </span>
                              <span className="text-gray-400">{entry.action}</span>
                              <span
                                className={
                                  entry.result === "success"
                                    ? "text-green-400"
                                    : "text-red-400"
                                }
                              >
                                {entry.result}
                              </span>
                            </div>
                          ))}
                        </div>
                      </div>
                    )}
                  </div>
                )}
              </div>
            );
          })
        )}
      </div>

      {/* Auto-refresh indicator */}
      {refreshing && (
        <div className="mt-4 text-xs text-gray-500 flex items-center gap-1">
          <RefreshCw className="w-3 h-3 animate-spin" />
          Refreshing optimization status...
        </div>
      )}
    </div>
  );
}

export default OptimizationSettings;
