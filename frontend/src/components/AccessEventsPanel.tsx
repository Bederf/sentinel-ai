/**
 * AccessEventsPanel Component - Badge event table with filtering
 *
 * Features:
 * - Table of recent badge events (Time, Person, Door, Direction, Status)
 * - Color-coded: green for granted, red for denied
 * - Filter tabs: All | Denied | After-Hours
 * - Auto-refresh every 10 seconds
 * - Follows SENTINEL dark theme design
 */

import { useState, useEffect, useCallback } from "react";
import { RefreshCw, AlertTriangle, DoorOpen, Clock, UserX, Moon } from "lucide-react";
import { securityApi } from "../lib/api";
import type { BadgeEvent } from "../lib/api";

type EventFilter = "all" | "denied" | "after-hours";

interface AccessEventsPanelProps {
  /** Refresh key to force data reload from parent */
  refreshKey?: number;
}

export function AccessEventsPanel({ refreshKey }: AccessEventsPanelProps) {
  const [events, setEvents] = useState<BadgeEvent[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [filter, setFilter] = useState<EventFilter>("all");
  const [isRefreshing, setIsRefreshing] = useState(false);

  const fetchEvents = useCallback(async (showRefreshing = false) => {
    try {
      if (showRefreshing) setIsRefreshing(true);

      let result: { events: BadgeEvent[]; count: number };
      switch (filter) {
        case "denied":
          result = await securityApi.getDeniedEvents();
          break;
        case "after-hours":
          result = await securityApi.getAfterHoursEvents();
          break;
        default:
          result = await securityApi.getEvents({ limit: 50 });
      }

      setEvents(result.events);
      setError(null);
    } catch (err) {
      console.error("Failed to fetch badge events:", err);
      setError("Failed to load access events");
    } finally {
      setLoading(false);
      setIsRefreshing(false);
    }
  }, [filter]);

  // Fetch on mount and filter change
  useEffect(() => {
    setLoading(true);
    fetchEvents();
  }, [fetchEvents]);

  // Re-fetch when parent triggers refresh
  useEffect(() => {
    if (refreshKey !== undefined && refreshKey > 0) {
      fetchEvents(true);
    }
  }, [refreshKey, fetchEvents]);

  // Auto-refresh every 10 seconds
  useEffect(() => {
    const interval = setInterval(() => {
      fetchEvents(true);
    }, 10000);
    return () => clearInterval(interval);
  }, [fetchEvents]);

  const formatTimestamp = (ts: string) => {
    const date = new Date(ts);
    return date.toLocaleTimeString("en-ZA", {
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
      hour12: false,
    });
  };

  const formatDate = (ts: string) => {
    const date = new Date(ts);
    return date.toLocaleDateString("en-ZA", {
      day: "2-digit",
      month: "short",
    });
  };

  const filters: { id: EventFilter; label: string; icon: typeof DoorOpen }[] = [
    { id: "all", label: "All Events", icon: DoorOpen },
    { id: "denied", label: "Denied", icon: UserX },
    { id: "after-hours", label: "After-Hours", icon: Moon },
  ];

  // Loading state
  if (loading && events.length === 0) {
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
            {[1, 2, 3, 4, 5].map((i) => (
              <div
                key={i}
                className="h-8 rounded"
                style={{ background: "var(--color-sentinel-bg-secondary)" }}
              />
            ))}
          </div>
        </div>
      </div>
    );
  }

  return (
    <div
      className="rounded-md overflow-hidden"
      style={{
        background: "var(--color-sentinel-bg-panel)",
        border: "1px solid var(--color-sentinel-border)",
      }}
    >
      {/* Header with filter tabs */}
      <div
        className="p-4 flex flex-col sm:flex-row sm:items-center justify-between gap-3"
        style={{ borderBottom: "1px solid var(--color-sentinel-border)" }}
      >
        <div className="flex items-center gap-2">
          <DoorOpen className="h-5 w-5" style={{ color: "var(--color-sentinel-blue)" }} />
          <span
            className="font-medium text-sm"
            style={{ color: "var(--color-sentinel-text-primary)" }}
          >
            Access Events
          </span>
          <span
            className="text-xs px-2 py-0.5 rounded"
            style={{
              background: "var(--color-sentinel-bg-secondary)",
              color: "var(--color-sentinel-text-secondary)",
            }}
          >
            {events.length}
          </span>
        </div>

        <div className="flex items-center gap-2">
          {/* Filter tabs */}
          <div
            className="flex rounded overflow-hidden"
            style={{ border: "1px solid var(--color-sentinel-border)" }}
          >
            {filters.map((f) => {
              const Icon = f.icon;
              const isActive = filter === f.id;
              return (
                <button
                  key={f.id}
                  onClick={() => setFilter(f.id)}
                  className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium transition-colors"
                  style={{
                    background: isActive
                      ? "var(--color-sentinel-bg-secondary)"
                      : "transparent",
                    color: isActive
                      ? "var(--color-sentinel-text-primary)"
                      : "var(--color-sentinel-text-secondary)",
                    borderRight: "1px solid var(--color-sentinel-border)",
                  }}
                >
                  <Icon className="h-3.5 w-3.5" />
                  {f.label}
                </button>
              );
            })}
          </div>

          {/* Refresh button */}
          <button
            onClick={() => fetchEvents(true)}
            disabled={isRefreshing}
            className="p-1.5 rounded transition-colors hover:brightness-110 disabled:opacity-50"
            style={{
              background: "var(--color-sentinel-bg-secondary)",
              border: "1px solid var(--color-sentinel-border)",
            }}
            aria-label="Refresh events"
          >
            <RefreshCw
              className={`h-3.5 w-3.5 ${isRefreshing ? "animate-spin" : ""}`}
              style={{ color: "var(--color-sentinel-text-secondary)" }}
            />
          </button>
        </div>
      </div>

      {/* Error state */}
      {error && (
        <div className="p-4">
          <div
            className="flex items-center gap-2 text-sm"
            style={{ color: "var(--color-sentinel-red)" }}
          >
            <AlertTriangle className="h-4 w-4" />
            <span>{error}</span>
          </div>
        </div>
      )}

      {/* Events table */}
      {!error && (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr
                style={{
                  background: "var(--color-sentinel-bg-secondary)",
                  borderBottom: "1px solid var(--color-sentinel-border)",
                }}
              >
                <th
                  className="text-left px-4 py-2 font-medium text-xs uppercase tracking-wider"
                  style={{ color: "var(--color-sentinel-text-secondary)" }}
                >
                  Time
                </th>
                <th
                  className="text-left px-4 py-2 font-medium text-xs uppercase tracking-wider"
                  style={{ color: "var(--color-sentinel-text-secondary)" }}
                >
                  Person
                </th>
                <th
                  className="text-left px-4 py-2 font-medium text-xs uppercase tracking-wider"
                  style={{ color: "var(--color-sentinel-text-secondary)" }}
                >
                  Door
                </th>
                <th
                  className="text-left px-4 py-2 font-medium text-xs uppercase tracking-wider"
                  style={{ color: "var(--color-sentinel-text-secondary)" }}
                >
                  Direction
                </th>
                <th
                  className="text-left px-4 py-2 font-medium text-xs uppercase tracking-wider"
                  style={{ color: "var(--color-sentinel-text-secondary)" }}
                >
                  Status
                </th>
              </tr>
            </thead>
            <tbody>
              {events.length === 0 ? (
                <tr>
                  <td
                    colSpan={5}
                    className="px-4 py-8 text-center text-sm"
                    style={{ color: "var(--color-sentinel-text-disabled)" }}
                  >
                    {filter === "denied"
                      ? "No denied access events"
                      : filter === "after-hours"
                        ? "No after-hours access events"
                        : "No access events recorded"}
                  </td>
                </tr>
              ) : (
                events.map((event) => (
                  <tr
                    key={event.event_id}
                    className="transition-colors hover:brightness-110"
                    style={{
                      borderBottom: "1px solid var(--color-sentinel-border)",
                      background: !event.granted
                        ? "rgba(220, 38, 38, 0.05)"
                        : "transparent",
                    }}
                  >
                    {/* Time */}
                    <td className="px-4 py-2.5">
                      <div className="flex items-center gap-1.5">
                        <Clock
                          className="h-3.5 w-3.5"
                          style={{ color: "var(--color-sentinel-text-disabled)" }}
                        />
                        <div>
                          <span
                            className="text-xs font-mono block"
                            style={{ color: "var(--color-sentinel-text-primary)" }}
                          >
                            {formatTimestamp(event.timestamp)}
                          </span>
                          <span
                            className="text-xs"
                            style={{ color: "var(--color-sentinel-text-disabled)" }}
                          >
                            {formatDate(event.timestamp)}
                          </span>
                        </div>
                      </div>
                    </td>

                    {/* Person */}
                    <td className="px-4 py-2.5">
                      <span
                        className="text-sm"
                        style={{ color: "var(--color-sentinel-text-primary)" }}
                      >
                        {event.person_name || "Unknown"}
                      </span>
                      <span
                        className="text-xs block"
                        style={{ color: "var(--color-sentinel-text-disabled)" }}
                      >
                        {event.badge_id}
                      </span>
                    </td>

                    {/* Door */}
                    <td className="px-4 py-2.5">
                      <span
                        className="text-sm"
                        style={{ color: "var(--color-sentinel-text-primary)" }}
                      >
                        {event.door_id}
                      </span>
                    </td>

                    {/* Direction */}
                    <td className="px-4 py-2.5">
                      <span
                        className="inline-flex items-center gap-1 text-xs font-medium px-2 py-0.5 rounded"
                        style={{
                          background:
                            event.direction === "entry"
                              ? "rgba(59, 130, 246, 0.15)"
                              : "rgba(168, 85, 247, 0.15)",
                          color:
                            event.direction === "entry"
                              ? "var(--color-sentinel-blue)"
                              : "#a855f7",
                        }}
                      >
                        {event.direction === "entry" ? "Entry" : "Exit"}
                      </span>
                    </td>

                    {/* Status */}
                    <td className="px-4 py-2.5">
                      <span
                        className="inline-flex items-center gap-1 text-xs font-medium px-2 py-0.5 rounded"
                        style={{
                          background: event.granted
                            ? "rgba(16, 185, 129, 0.15)"
                            : "rgba(220, 38, 38, 0.15)",
                          color: event.granted
                            ? "var(--color-sentinel-green)"
                            : "var(--color-sentinel-red)",
                        }}
                      >
                        {event.granted ? "Granted" : "Denied"}
                      </span>
                      {event.reason && !event.granted && (
                        <span
                          className="text-xs block mt-0.5"
                          style={{ color: "var(--color-sentinel-text-disabled)" }}
                        >
                          {event.reason}
                        </span>
                      )}
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

export default AccessEventsPanel;
