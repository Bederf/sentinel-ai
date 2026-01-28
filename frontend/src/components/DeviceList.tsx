/**
 * DeviceList Component - Display and selection of control devices
 *
 * Features:
 * - Device list with status indicators
 * - Safety status visualization
 * - Filtering and sorting
 * - Selection management
 */

import { useState, useMemo } from "react";
import { Search, Filter, Battery, Activity, AlertTriangle } from "lucide-react";
import type { Device } from "../lib/api";

interface DeviceListProps {
  devices: Device[];
  selectedDevice: Device | null;
  onDeviceSelect: (device: Device) => void;
}

interface FilterOptions {
  showOnline: boolean;
  showOffline: boolean;
  sortBy: "name" | "status" | "safety";
}

export function DeviceList({ devices, selectedDevice, onDeviceSelect }: DeviceListProps) {
  const [searchQuery, setSearchQuery] = useState("");
  const [showFilters, setShowFilters] = useState(false);
  const [filters, setFilters] = useState<FilterOptions>({
    showOnline: true,
    showOffline: false,
    sortBy: "name",
  });

  const filteredDevices = useMemo(() => {
    // Filter by search query
    let filtered = devices.filter((device) =>
      device.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
      (device.type || device.device_type || '').toLowerCase().includes(searchQuery.toLowerCase()) ||
      device.location.toLowerCase().includes(searchQuery.toLowerCase())
    );

    // Filter by status
    filtered = filtered.filter((device) => {
      if (device.status === "online" && !filters.showOnline) return false;
      if (device.status === "offline" && !filters.showOffline) return false;
      return true;
    });

    // Sort
    switch (filters.sortBy) {
      case "name":
        filtered.sort((a, b) => a.name.localeCompare(b.name));
        break;
      case "status":
        filtered.sort((a, b) => {
          const statusA = a.status || "offline";
          const statusB = b.status || "offline";
          if (statusA !== statusB) {
            return statusA === "online" ? -1 : 1;
          }
          return a.name.localeCompare(b.name);
        });
        break;
      case "safety":
        filtered.sort((a, b) => {
          const safetyOrder: Record<string, number> = { safe: 0, warning: 1, critical: 2 };
          const safetyA = a.safety_status || "unknown";
          const safetyB = b.safety_status || "unknown";
          const orderA = safetyOrder[safetyA] ?? 3;
          const orderB = safetyOrder[safetyB] ?? 3;
          if (orderA !== orderB) {
            return orderA - orderB;
          }
          return a.name.localeCompare(b.name);
        });
        break;
    }

    return filtered;
  }, [devices, searchQuery, filters]);

  const getSafetyIcon = (safetyStatus: string) => {
    switch (safetyStatus) {
      case "safe":
        return <Activity className="h-3 w-3 text-green-500" />;
      case "warning":
        return <AlertTriangle className="h-3 w-3 text-yellow-500" />;
      case "critical":
        return <AlertTriangle className="h-3 w-3 text-red-500" />;
      default:
        return <Activity className="h-3 w-3 text-gray-500" />;
    }
  };

  const getStatusIcon = (status: string) => {
    switch (status) {
      case "online":
        return <Battery className="h-3 w-3 text-green-500" />;
      case "offline":
        return <Battery className="h-3 w-3 text-gray-500" />;
      default:
        return <Battery className="h-3 w-3 text-gray-400" />;
    }
  };

  return (
    <div className="h-full flex flex-col">
      {/* Search Bar */}
      <div className="p-4 border-b" style={{ borderColor: "var(--color-sentinel-border)" }}>
        <div className="relative">
          <Search
            className="absolute left-3 top-1/2 transform -translate-y-1/2 h-4 w-4"
            style={{ color: "var(--color-sentinel-text-secondary)" }}
          />
          <input
            type="text"
            placeholder="Search devices..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="w-full pl-9 pr-8 py-2 text-sm rounded"
            style={{
              background: "var(--color-sentinel-bg-secondary)",
              border: "1px solid var(--color-sentinel-border)",
              color: "var(--color-sentinel-text-primary)",
              outline: "none",
            }}
          />
          <button
            onClick={() => setShowFilters(!showFilters)}
            className="absolute right-2 top-1/2 transform -translate-y-1/2 p-1 rounded"
            style={{ color: "var(--color-sentinel-text-secondary)" }}
            title="Filters"
          >
            <Filter className="h-4 w-4" />
          </button>
        </div>
      </div>

      {/* Filters */}
      {showFilters && (
        <div
          className="p-4 border-b space-y-3"
          style={{
            borderColor: "var(--color-sentinel-border)",
            background: "var(--color-sentinel-bg-secondary)",
          }}
        >
          <div className="space-y-2">
            <label className="flex items-center gap-2 text-sm">
              <input
                type="checkbox"
                checked={filters.showOnline}
                onChange={(e) => setFilters({ ...filters, showOnline: e.target.checked })}
              />
              <span style={{ color: "var(--color-sentinel-text-primary)" }}>Online</span>
            </label>
            <label className="flex items-center gap-2 text-sm">
              <input
                type="checkbox"
                checked={filters.showOffline}
                onChange={(e) => setFilters({ ...filters, showOffline: e.target.checked })}
              />
              <span style={{ color: "var(--color-sentinel-text-primary)" }}>Offline</span>
            </label>
          </div>

          <div>
            <label className="text-xs" style={{ color: "var(--color-sentinel-text-secondary)" }}>
              Sort by:
            </label>
            <select
              value={filters.sortBy}
              onChange={(e) => setFilters({ ...filters, sortBy: e.target.value as any })}
              className="w-full mt-1 py-1 px-2 text-sm rounded"
              style={{
                background: "var(--color-sentinel-bg-primary)",
                border: "1px solid var(--color-sentinel-border)",
                color: "var(--color-sentinel-text-primary)",
              }}
            >
              <option value="name">Name</option>
              <option value="status">Status</option>
              <option value="safety">Safety Priority</option>
            </select>
          </div>
        </div>
      )}

      {/* Device List */}
      <div className="flex-1 overflow-y-auto">
        {filteredDevices.map((device) => (
          <button
            key={device.id}
            onClick={() => onDeviceSelect(device)}
            className={`w-full text-left p-4 border-b transition-colors ${
              selectedDevice?.id === device.id
                ? "bg-blue-500/10"
                : "hover:bg-slate-500/5"
            }`}
            style={{ borderColor: "var(--color-sentinel-border)" }}
          >
            <div className="flex items-start justify-between mb-1">
              <div className="flex-1">
                <div
                  className="font-medium text-sm truncate"
                  style={{ color: "var(--color-sentinel-text-primary)" }}
                >
                  {device.name}
                </div>
                <div
                  className="text-xs"
                  style={{ color: "var(--color-sentinel-text-secondary)" }}
                >
                  {device.type || device.device_type} • {device.location}
                </div>
              </div>
              <div className="flex items-center gap-1 ml-2">
                {getStatusIcon(device.status || "offline")}
                {getSafetyIcon(device.safety_status || "unknown")}
              </div>
            </div>
            <div className="flex items-center gap-4 text-xs mt-2">
              <span
                className={`px-2 py-0.5 rounded ${
                  (device.status || "offline") === "online"
                    ? "bg-green-500/10 text-green-500"
                    : "bg-gray-500/10 text-gray-500"
                }`}
              >
                {(device.status || "offline").toUpperCase()}
              </span>
              {device.last_communication && (
                <span style={{ color: "var(--color-sentinel-text-secondary)" }}>
                  {formatLastCommunication(device.last_communication)}
                </span>
              )}
              {device.current_value !== undefined && (
                <span style={{ color: "var(--color-sentinel-text-secondary)" }}>
                  {device.current_value}
                </span>
              )}
            </div>
          </button>
        ))}

        {filteredDevices.length === 0 && (
          <div className="p-4 text-center">
            <div
              className="py-8"
              style={{ color: "var(--color-sentinel-text-secondary)" }}
            >
              No devices found
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

function formatLastCommunication(timestamp: string): string {
  const date = new Date(timestamp);
  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  const diffMinutes = Math.floor(diffMs / (1000 * 60));

  if (diffMinutes < 1) return "Just now";
  if (diffMinutes < 60) return `${diffMinutes}m ago`;

  const diffHours = Math.floor(diffMinutes / 60);
  if (diffHours < 24) return `${diffHours}h ago`;

  return `${Math.floor(diffHours / 24)}d ago`;
}