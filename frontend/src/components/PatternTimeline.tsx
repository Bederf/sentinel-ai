/**
 * PatternTimeline Component - Cross-site pattern recognition visualization
 *
 * Shows how a failure pattern has progressed across sites:
 * - Historical failures (completed)
 * - Current prediction (at risk)
 * - Timeline with connecting line
 */

import { CheckCircle, AlertTriangle, XCircle } from "lucide-react";

interface SimilarFailure {
  site: string;
  equipment: string;
  failure_date: string;
  common_factors: string[];
}

interface PatternTimelineProps {
  currentSite: string;
  currentEquipment: string;
  predictedDate: string;
  similarFailures: SimilarFailure[];
}

export function PatternTimeline({
  currentSite,
  currentEquipment,
  predictedDate,
  similarFailures,
}: PatternTimelineProps) {
  // Sort failures by date
  const sortedFailures = [...similarFailures].sort(
    (a, b) => new Date(a.failure_date).getTime() - new Date(b.failure_date).getTime()
  );

  // Format date for display
  const formatDate = (dateString: string) => {
    const date = new Date(dateString);
    return date.toLocaleDateString("en-ZA", {
      month: "short",
      year: "numeric",
    });
  };

  const formatFullDate = (dateString: string) => {
    const date = new Date(dateString);
    return date.toLocaleDateString("en-ZA", {
      day: "numeric",
      month: "long",
      year: "numeric",
    });
  };

  // All timeline items (past failures + current prediction)
  const timelineItems = [
    ...sortedFailures.map((failure) => ({
      type: "failure" as const,
      site: failure.site,
      equipment: failure.equipment,
      date: failure.failure_date,
      factors: failure.common_factors,
    })),
    {
      type: "prediction" as const,
      site: currentSite,
      equipment: currentEquipment,
      date: predictedDate,
      factors: [],
    },
  ];

  if (timelineItems.length <= 1) {
    return null; // Don't show if no historical pattern
  }

  return (
    <div
      className="rounded-lg overflow-hidden"
      style={{
        background: "var(--color-grafana-bg-panel)",
        border: "1px solid var(--color-grafana-border)",
      }}
    >
      {/* Header */}
      <div
        className="px-4 py-3 flex items-center gap-2"
        style={{ borderBottom: "1px solid var(--color-grafana-border)" }}
      >
        <div
          className="p-1.5 rounded"
          style={{ background: "rgba(184, 119, 217, 0.15)" }}
        >
          <AlertTriangle className="h-4 w-4" style={{ color: "var(--color-grafana-purple)" }} />
        </div>
        <div>
          <h3
            className="font-semibold text-sm"
            style={{ color: "var(--color-grafana-text-primary)" }}
          >
            Pattern Recognition Timeline
          </h3>
          <p
            className="text-xs"
            style={{ color: "var(--color-grafana-text-secondary)" }}
          >
            This failure pattern has been detected across {sortedFailures.length + 1} sites
          </p>
        </div>
      </div>

      <div className="p-4">
        {/* Timeline */}
        <div className="relative">
          {/* Connecting line */}
          <div
            className="absolute left-6 top-8 bottom-8 w-0.5"
            style={{ background: "var(--color-grafana-border)" }}
          />

          {/* Timeline items */}
          <div className="space-y-6">
            {timelineItems.map((item, index) => {
              const isFailure = item.type === "failure";
              const isPrediction = item.type === "prediction";

              return (
                <div key={index} className="relative flex gap-4">
                  {/* Icon */}
                  <div
                    className="relative z-10 flex-shrink-0 w-12 h-12 rounded-full flex items-center justify-center"
                    style={{
                      background: isFailure
                        ? "rgba(242, 73, 92, 0.15)"
                        : "rgba(255, 152, 48, 0.15)",
                      border: `2px solid ${
                        isFailure ? "var(--color-status-error)" : "var(--color-status-warning)"
                      }`,
                    }}
                  >
                    {isFailure ? (
                      <XCircle
                        className="h-6 w-6"
                        style={{ color: "var(--color-status-error)" }}
                      />
                    ) : (
                      <AlertTriangle
                        className="h-6 w-6 animate-pulse"
                        style={{ color: "var(--color-status-warning)" }}
                      />
                    )}
                  </div>

                  {/* Content */}
                  <div className="flex-1 pb-2">
                    {/* Date label */}
                    <div
                      className="text-xs font-medium uppercase tracking-wider mb-1"
                      style={{
                        color: isFailure
                          ? "var(--color-status-error)"
                          : "var(--color-status-warning)",
                      }}
                    >
                      {formatDate(item.date)}
                      {isPrediction && " (Predicted)"}
                    </div>

                    {/* Site and equipment */}
                    <div
                      className="font-semibold mb-1"
                      style={{ color: "var(--color-grafana-text-primary)" }}
                    >
                      {item.site}
                    </div>
                    <div
                      className="text-sm mb-2"
                      style={{ color: "var(--color-grafana-text-secondary)" }}
                    >
                      {item.equipment}
                      {isFailure && " - Failed"}
                      {isPrediction && " - At Risk"}
                    </div>

                    {/* Status badge */}
                    <div
                      className="inline-flex items-center gap-1.5 px-2 py-1 rounded text-xs font-medium"
                      style={{
                        background: isFailure
                          ? "rgba(242, 73, 92, 0.15)"
                          : "rgba(255, 152, 48, 0.15)",
                        color: isFailure
                          ? "var(--color-status-error)"
                          : "var(--color-status-warning)",
                      }}
                    >
                      {isFailure ? (
                        <>
                          <XCircle className="h-3 w-3" />
                          Equipment failure on {formatFullDate(item.date)}
                        </>
                      ) : (
                        <>
                          <AlertTriangle className="h-3 w-3" />
                          Predicted failure by {formatFullDate(item.date)}
                        </>
                      )}
                    </div>

                    {/* Common factors for failures */}
                    {isFailure && item.factors.length > 0 && (
                      <div className="mt-2 flex flex-wrap gap-1">
                        {item.factors.map((factor, i) => (
                          <span
                            key={i}
                            className="text-xs px-2 py-0.5 rounded"
                            style={{
                              background: "var(--color-grafana-bg-secondary)",
                              color: "var(--color-grafana-text-secondary)",
                            }}
                          >
                            {factor}
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

        {/* Pattern insight */}
        <div
          className="mt-4 p-3 rounded-lg flex items-start gap-3"
          style={{
            background: "rgba(184, 119, 217, 0.1)",
            border: "1px solid var(--color-grafana-purple)30",
          }}
        >
          <CheckCircle
            className="h-5 w-5 flex-shrink-0 mt-0.5"
            style={{ color: "var(--color-grafana-purple)" }}
          />
          <div>
            <span
              className="text-sm font-medium"
              style={{ color: "var(--color-grafana-purple)" }}
            >
              AI Pattern Insight
            </span>
            <p
              className="text-sm mt-1"
              style={{ color: "var(--color-grafana-text-secondary)" }}
            >
              Similar equipment at {sortedFailures.length} other site
              {sortedFailures.length > 1 ? "s" : ""} experienced this exact failure pattern.
              The AI model has identified matching conditions at {currentSite}, suggesting
              preventive action could avoid a repeat failure.
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}

export default PatternTimeline;
