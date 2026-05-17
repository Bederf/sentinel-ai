/**
 * CD Workflow — Timeline Component
 *
 * Visual timeline for displaying CI/CD pipeline stages and events.
 * Shows progression through build, test, deploy phases with status indicators.
 */

import { CheckCircle2, Circle, XCircle, Clock, AlertCircle, PlayCircle } from "lucide-react";

export type TimelineStatus = "pending" | "in_progress" | "success" | "failed" | "skipped" | "cancelled";

export interface TimelineEvent {
  id: string;
  title: string;
  description?: string;
  status: TimelineStatus;
  timestamp?: string;
  duration?: string;
  errorMessage?: string;
  metadata?: Record<string, string>;
}

interface TimelineProps {
  events: TimelineEvent[];
  currentEventId?: string;
  onEventClick?: (event: TimelineEvent) => void;
}

const statusConfig: Record<TimelineStatus, { icon: React.ReactNode; color: string; bgColor: string; borderColor: string; label: string }> = {
  pending: {
    icon: <Circle className="h-4 w-4" />,
    color: "var(--color-sentinel-text-disabled)",
    bgColor: "var(--color-sentinel-bg-secondary)",
    borderColor: "var(--color-sentinel-border)",
    label: "Pending",
  },
  in_progress: {
    icon: <PlayCircle className="h-4 w-4 animate-pulse" />,
    color: "var(--color-sentinel-blue)",
    bgColor: "rgba(59, 130, 246, 0.15)",
    borderColor: "var(--color-sentinel-blue)",
    label: "In Progress",
  },
  success: {
    icon: <CheckCircle2 className="h-4 w-4" />,
    color: "var(--color-sentinel-green)",
    bgColor: "rgba(16, 185, 129, 0.15)",
    borderColor: "var(--color-sentinel-green)",
    label: "Success",
  },
  failed: {
    icon: <XCircle className="h-4 w-4" />,
    color: "var(--color-sentinel-red)",
    bgColor: "rgba(220, 38, 38, 0.15)",
    borderColor: "var(--color-sentinel-red)",
    label: "Failed",
  },
  skipped: {
    icon: <Clock className="h-4 w-4" />,
    color: "var(--color-sentinel-text-secondary)",
    bgColor: "var(--color-sentinel-bg-secondary)",
    borderColor: "var(--color-sentinel-border)",
    label: "Skipped",
  },
  cancelled: {
    icon: <AlertCircle className="h-4 w-4" />,
    color: "var(--color-sentinel-amber)",
    bgColor: "rgba(245, 158, 11, 0.15)",
    borderColor: "var(--color-sentinel-amber)",
    label: "Cancelled",
  },
};

function formatTimestamp(timestamp: string): string {
  try {
    const date = new Date(timestamp);
    return date.toLocaleString("en-ZA", {
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
      hour12: false,
    });
  } catch {
    return timestamp;
  }
}

export function Timeline({ events, currentEventId, onEventClick }: TimelineProps) {
  const activeIndex = events.findIndex((e) => e.id === currentEventId);
  const lastCompletedIndex = events.reduce((lastIdx, event, idx) => {
    if (event.status === "success") return idx;
    return lastIdx;
  }, -1);

  return (
    <div className="relative">
      {/* Vertical connector line */}
      <div
        className="absolute left-[19px] top-8 bottom-8 w-0.5"
        style={{ background: "var(--color-sentinel-border)" }}
      />

      {/* Progress line (only up to last completed) */}
      {lastCompletedIndex >= 0 && (
        <div
          className="absolute left-[19px] top-8 w-0.5"
          style={{
            height: `${Math.max(0, lastCompletedIndex) * 80 + 40}px`,
            background: "var(--color-sentinel-green)",
          }}
        />
      )}

      {/* Events */}
      <div className="space-y-0">
        {events.map((event, index) => {
          const config = statusConfig[event.status];
          const isActive = event.id === currentEventId;
          const isClickable = onEventClick && event.status !== "pending";

          return (
            <div
              key={event.id}
              className={`relative flex gap-4 py-4 ${isClickable ? "cursor-pointer" : ""}`}
              onClick={() => isClickable && onEventClick(event)}
              style={{
                opacity: event.status === "pending" ? 0.6 : 1,
              }}
            >
              {/* Status icon */}
              <div
                className="relative z-10 flex-shrink-0 w-10 h-10 rounded-full flex items-center justify-center border-2 transition-all"
                style={{
                  background: config.bgColor,
                  borderColor: isActive ? config.borderColor : config.borderColor,
                  color: config.color,
                  boxShadow: isActive ? `0 0 0 4px ${config.bgColor}` : "none",
                }}
              >
                {config.icon}
              </div>

              {/* Content */}
              <div className="flex-1 min-w-0">
                {/* Header row */}
                <div className="flex items-start justify-between gap-2">
                  <div className="flex-1 min-w-0">
                    <h4
                      className="text-sm font-medium truncate"
                      style={{ color: "var(--color-sentinel-text-primary)" }}
                    >
                      {event.title}
                    </h4>
                    {event.description && (
                      <p
                        className="text-xs mt-0.5 line-clamp-2"
                        style={{ color: "var(--color-sentinel-text-secondary)" }}
                      >
                        {event.description}
                      </p>
                    )}
                  </div>

                  {/* Status badge */}
                  <span
                    className="flex-shrink-0 text-[10px] font-medium uppercase tracking-wider px-2 py-0.5 rounded-full border"
                    style={{
                      background: config.bgColor,
                      borderColor: config.borderColor,
                      color: config.color,
                    }}
                  >
                    {config.label}
                  </span>
                </div>

                {/* Metadata row */}
                <div className="flex items-center gap-3 mt-2">
                  {event.timestamp && (
                    <span
                      className="text-[10px] font-mono"
                      style={{ color: "var(--color-sentinel-text-disabled)" }}
                    >
                      {formatTimestamp(event.timestamp)}
                    </span>
                  )}
                  {event.duration && (
                    <span
                      className="text-[10px]"
                      style={{ color: "var(--color-sentinel-text-secondary)" }}
                    >
                      {event.duration}
                    </span>
                  )}
                  {index <= lastCompletedIndex && index < events.length - 1 && (
                    <span
                      className="text-[10px]"
                      style={{ color: "var(--color-sentinel-green)" }}
                    >
                      ✓ Complete
                    </span>
                  )}
                </div>

                {/* Error message */}
                {event.errorMessage && (
                  <div
                    className="mt-2 p-2 rounded text-xs border"
                    style={{
                      background: "rgba(220, 38, 38, 0.1)",
                      borderColor: "rgba(220, 38, 38, 0.3)",
                      color: "var(--color-sentinel-red)",
                    }}
                  >
                    <div className="flex items-center gap-1.5 mb-1">
                      <AlertCircle className="h-3 w-3" />
                      <span className="font-medium">Error</span>
                    </div>
                    {event.errorMessage}
                  </div>
                )}

                {/* Additional metadata */}
                {event.metadata && Object.keys(event.metadata).length > 0 && (
                  <div className="flex flex-wrap gap-2 mt-2">
                    {Object.entries(event.metadata).map(([key, value]) => (
                      <span
                        key={key}
                        className="text-[10px] px-1.5 py-0.5 rounded"
                        style={{
                          background: "var(--color-sentinel-bg-secondary)",
                          color: "var(--color-sentinel-text-secondary)",
                        }}
                      >
                        {key}: {value}
                      </span>
                    ))}
                  </div>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

export default Timeline;
