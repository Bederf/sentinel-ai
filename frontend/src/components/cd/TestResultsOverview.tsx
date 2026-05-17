/**
 * CD Workflow — Test Results Overview Tab
 *
 * Displays summary statistics, current status, and timeline
 * for CI/CD pipeline test execution.
 */

import { useMemo } from "react";
import { CheckCircle2, XCircle, Clock, AlertTriangle, PlayCircle, RotateCcw } from "lucide-react";
import { Timeline, type TimelineEvent } from "./Timeline";
import { KPICard } from "../KPICard";
import { StatusBadge } from "../StatusBadge";
import { EmptyState } from "../EmptyState";
import { Panel } from "../Panel";

export type TestRunStatus = "pending" | "running" | "passed" | "failed" | "cancelled";

export interface TestRunSummary {
  runId: string;
  branch: string;
  commit: string;
  commitMessage: string;
  author: string;
  startedAt?: string;
  completedAt?: string;
  duration?: string;
  status: TestRunStatus;
  totalTests: number;
  passedTests: number;
  failedTests: number;
  skippedTests: number;
  coverage?: number;
}

interface TestResultsOverviewProps {
  summary: TestRunSummary | null;
  timeline: TimelineEvent[];
  onRerun?: () => void;
  onEventClick?: (event: TimelineEvent) => void;
}

function formatDuration(duration?: string): string {
  if (!duration) return "—";
  return duration;
}

function formatTimestamp(timestamp?: string): string {
  if (!timestamp) return "—";
  try {
    return new Date(timestamp).toLocaleString("en-ZA", {
      year: "numeric",
      month: "short",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return timestamp;
  }
}

export function TestResultsOverview({
  summary,
  timeline,
  onRerun,
  onEventClick,
}: TestResultsOverviewProps) {
  const stats = useMemo(() => {
    if (!summary) return null;
    const passRate = summary.totalTests > 0
      ? Math.round((summary.passedTests / summary.totalTests) * 100)
      : 0;
    return {
      passRate,
      isPassing: summary.status === "passed" || (passRate >= 80 && summary.failedTests === 0),
    };
  }, [summary]);

  const currentEventId = useMemo(() => {
    const inProgress = timeline.find((e) => e.status === "in_progress");
    if (inProgress) return inProgress.id;

    const lastCompleted = [...timeline].reverse().find(
      (e) => e.status === "success" || e.status === "failed"
    );
    if (lastCompleted) return lastCompleted.id;

    return timeline[0]?.id;
  }, [timeline]);

  if (!summary) {
    return (
      <EmptyState
        icon={PlayCircle}
        title="No test runs yet"
        subtext="Trigger a deployment to see test results here."
        cta={
          onRerun && (
            <button
              onClick={onRerun}
              className="px-4 py-2 text-sm font-medium rounded-lg border transition-colors"
              style={{
                background: "var(--color-sentinel-bg-panel)",
                borderColor: "var(--color-sentinel-border)",
                color: "var(--color-sentinel-text-primary)",
              }}
            >
              Run Tests
            </button>
          )
        }
      />
    );
  }

  const getStatusBadge = () => {
    switch (summary.status) {
      case "passed":
        return <StatusBadge status="completed" label="Passed" />;
      case "failed":
        return <StatusBadge status="failed" label="Failed" />;
      case "running":
        return <StatusBadge status="pending" label="Running" />;
      case "cancelled":
        return <StatusBadge status="warning" label="Cancelled" />;
      default:
        return <StatusBadge status="pending" label="Pending" />;
    }
  };

  return (
    <div className="space-y-6">
      {/* Run header with actions */}
      <div
        className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 p-4 rounded-lg border"
        style={{
          background: "var(--color-sentinel-bg-panel)",
          borderColor: "var(--color-sentinel-border)",
        }}
      >
        <div className="flex items-start gap-3">
          <div
            className="p-2 rounded-lg"
            style={{
              background: summary.status === "passed"
                ? "rgba(16, 185, 129, 0.15)"
                : summary.status === "failed"
                ? "rgba(220, 38, 38, 0.15)"
                : "var(--color-sentinel-bg-secondary)",
              color: summary.status === "passed"
                ? "var(--color-sentinel-green)"
                : summary.status === "failed"
                ? "var(--color-sentinel-red)"
                : "var(--color-sentinel-text-secondary)",
            }}
          >
            {summary.status === "passed" ? (
              <CheckCircle2 className="h-5 w-5" />
            ) : summary.status === "failed" ? (
              <XCircle className="h-5 w-5" />
            ) : summary.status === "running" ? (
              <PlayCircle className="h-5 w-5 animate-pulse" />
            ) : (
              <AlertTriangle className="h-5 w-5" />
            )}
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h3
                className="text-sm font-medium"
                style={{ color: "var(--color-sentinel-text-primary)" }}
              >
                {summary.branch}
              </h3>
              {getStatusBadge()}
            </div>
            <p
              className="text-xs mt-1 line-clamp-1"
              style={{ color: "var(--color-sentinel-text-secondary)" }}
            >
              {summary.commitMessage}
            </p>
            <div
              className="flex items-center gap-3 mt-2 text-[10px]"
              style={{ color: "var(--color-sentinel-text-disabled)" }}
            >
              <span>{summary.commit.substring(0, 7)}</span>
              <span>•</span>
              <span>{summary.author}</span>
              <span>•</span>
              <span>{formatTimestamp(summary.startedAt)}</span>
            </div>
          </div>
        </div>

        {onRerun && summary.status !== "running" && (
          <button
            onClick={onRerun}
            className="flex items-center gap-2 px-3 py-2 text-xs font-medium rounded-lg border transition-colors"
            style={{
              background: "var(--color-sentinel-bg-secondary)",
              borderColor: "var(--color-sentinel-border)",
              color: "var(--color-sentinel-text-primary)",
            }}
          >
            <RotateCcw className="h-3.5 w-3.5" />
            Re-run
          </button>
        )}
      </div>

      {/* KPI Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <KPICard
          title="Pass Rate"
          value={`${stats?.passRate ?? 0}%`}
          icon={<CheckCircle2 className="h-5 w-5" />}
          accentColor={stats?.isPassing ? "green" : "red"}
          subtitle={`${summary.passedTests} of ${summary.totalTests} tests`}
        />
        <KPICard
          title="Failed Tests"
          value={summary.failedTests}
          icon={<XCircle className="h-5 w-5" />}
          accentColor={summary.failedTests > 0 ? "red" : "green"}
          subtitle={summary.failedTests > 0 ? "Requires attention" : "All tests passing"}
        />
        <KPICard
          title="Duration"
          value={formatDuration(summary.duration)}
          icon={<Clock className="h-5 w-5" />}
          accentColor="blue"
        />
        <KPICard
          title="Code Coverage"
          value={summary.coverage !== undefined ? `${summary.coverage}%` : "—"}
          icon={
            <svg className="h-5 w-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <circle cx="12" cy="12" r="10" />
              <path d="M12 6v6l4 2" />
            </svg>
          }
          accentColor="purple"
          progress={summary.coverage}
        />
      </div>

      {/* Test breakdown */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        {[
          { label: "Total", value: summary.totalTests, color: "var(--color-sentinel-text-primary)" },
          { label: "Passed", value: summary.passedTests, color: "var(--color-sentinel-green)" },
          { label: "Failed", value: summary.failedTests, color: "var(--color-sentinel-red)" },
          { label: "Skipped", value: summary.skippedTests, color: "var(--color-sentinel-amber)" },
        ].map((stat) => (
          <div
            key={stat.label}
            className="p-3 rounded-lg border text-center"
            style={{
              background: "var(--color-sentinel-bg-panel)",
              borderColor: "var(--color-sentinel-border)",
            }}
          >
            <div
              className="text-lg font-medium"
              style={{ color: stat.color }}
            >
              {stat.value}
            </div>
            <div
              className="text-[10px] uppercase tracking-wider mt-1"
              style={{ color: "var(--color-sentinel-text-secondary)" }}
            >
              {stat.label}
            </div>
          </div>
        ))}
      </div>

      {/* Timeline */}
      <Panel
        header={{
          icon: <PlayCircle className="h-4 w-4" />,
          title: "Pipeline Timeline",
          accentColor: "var(--color-sentinel-blue)",
        }}
      >
        {timeline.length > 0 ? (
          <div className="p-4">
            <Timeline
              events={timeline}
              currentEventId={currentEventId}
              onEventClick={onEventClick}
            />
          </div>
        ) : (
          <EmptyState
            icon={Clock}
            title="No timeline events"
            subtext="Pipeline stages will appear here once the test run begins."
          />
        )}
      </Panel>
    </div>
  );
}

export default TestResultsOverview;
