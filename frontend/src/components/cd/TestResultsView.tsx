/**
 * CD Workflow — Test Results View
 *
 * Main container component for displaying CI/CD test results.
 * Features:
 * - Overview tab with KPIs and pipeline timeline
 * - Test details tab with individual test results
 * - Failure analysis tab for debugging
 * - History tab for previous runs
 */

import { useState } from "react";
import { PlayCircle, ListChecks, AlertCircle, History, FileText } from "lucide-react";
import { TabBar } from "../TabBar";
import { PageLoading } from "../PageLoading";
import { EmptyState } from "../EmptyState";
import { TestResultsOverview, type TestRunSummary } from "./TestResultsOverview";
import type { TimelineEvent } from "./Timeline";

export interface TestResult {
  id: string;
  name: string;
  suite: string;
  status: "passed" | "failed" | "skipped";
  duration: string;
  errorMessage?: string;
  stackTrace?: string;
}

export interface TestResultsViewProps {
  /** Current test run summary (null if loading or no runs) */
  summary: TestRunSummary | null;
  /** Pipeline timeline events */
  timeline: TimelineEvent[];
  /** Individual test results */
  testResults: TestResult[];
  /** Historical test runs */
  history?: TestRunSummary[];
  /** Loading state */
  isLoading?: boolean;
  /** Callback to re-run tests */
  onRerun?: () => void;
  /** Callback when a timeline event is clicked */
  onEventClick?: (event: TimelineEvent) => void;
  /** Callback when a test result is clicked */
  onTestClick?: (test: TestResult) => void;
  /** Callback to view a historical run */
  onViewHistory?: (run: TestRunSummary) => void;
}

const TABS = [
  { id: "overview", label: "Overview", icon: <PlayCircle className="h-4 w-4" /> },
  { id: "tests", label: "Test Details", icon: <ListChecks className="h-4 w-4" /> },
  { id: "failures", label: "Failures", icon: <AlertCircle className="h-4 w-4" /> },
  { id: "history", label: "History", icon: <History className="h-4 w-4" /> },
];

function TestDetailsPanel({
  tests,
  onTestClick,
}: {
  tests: TestResult[];
  onTestClick?: (test: TestResult) => void;
}) {
  const [filter, setFilter] = useState<"all" | "passed" | "failed" | "skipped">("all");

  const filteredTests = tests.filter((t) => {
    if (filter === "all") return true;
    return t.status === filter;
  });

  const groupedBySuite = filteredTests.reduce((acc, test) => {
    if (!acc[test.suite]) acc[test.suite] = [];
    acc[test.suite].push(test);
    return acc;
  }, {} as Record<string, TestResult[]>);

  if (tests.length === 0) {
    return (
      <EmptyState
        icon={ListChecks}
        title="No test results"
        subtext="Test details will appear here once the test run completes."
      />
    );
  }

  return (
    <div className="space-y-4">
      {/* Filter tabs */}
      <div className="flex gap-2">
        {(["all", "passed", "failed", "skipped"] as const).map((f) => (
          <button
            key={f}
            onClick={() => setFilter(f)}
            className="px-3 py-1.5 text-xs font-medium rounded-lg border transition-colors capitalize"
            style={{
              background: filter === f ? "var(--color-sentinel-blue)" : "var(--color-sentinel-bg-panel)",
              borderColor: filter === f ? "var(--color-sentinel-blue)" : "var(--color-sentinel-border)",
              color: filter === f ? "white" : "var(--color-sentinel-text-primary)",
            }}
          >
            {f} ({tests.filter((t) => f === "all" || t.status === f).length})
          </button>
        ))}
      </div>

      {/* Test list */}
      <div className="space-y-4">
        {Object.entries(groupedBySuite).map(([suite, suiteTests]) => (
          <div
            key={suite}
            className="rounded-lg border overflow-hidden"
            style={{
              background: "var(--color-sentinel-bg-panel)",
              borderColor: "var(--color-sentinel-border)",
            }}
          >
            {/* Suite header */}
            <div
              className="px-4 py-2 text-xs font-medium uppercase tracking-wider"
              style={{
                background: "var(--color-sentinel-bg-secondary)",
                color: "var(--color-sentinel-text-secondary)",
              }}
            >
              {suite}
            </div>

            {/* Tests */}
            <div className="divide-y" style={{ borderColor: "var(--color-sentinel-border)" }}>
              {suiteTests.map((test) => (
                <div
                  key={test.id}
                  className={`px-4 py-3 flex items-center justify-between gap-4 ${
                    onTestClick ? "cursor-pointer hover:bg-white/5" : ""
                  }`}
                  onClick={() => onTestClick?.(test)}
                >
                  <div className="flex items-center gap-3 min-w-0">
                    <div
                      className="flex-shrink-0 w-2 h-2 rounded-full"
                      style={{
                        background:
                          test.status === "passed"
                            ? "var(--color-sentinel-green)"
                            : test.status === "failed"
                            ? "var(--color-sentinel-red)"
                            : "var(--color-sentinel-amber)",
                      }}
                    />
                    <span
                      className="text-sm truncate"
                      style={{ color: "var(--color-sentinel-text-primary)" }}
                    >
                      {test.name}
                    </span>
                  </div>
                  <div className="flex items-center gap-3 flex-shrink-0">
                    <span
                      className="text-xs font-mono"
                      style={{ color: "var(--color-sentinel-text-disabled)" }}
                    >
                      {test.duration}
                    </span>
                    <span
                      className="text-[10px] font-medium uppercase tracking-wider px-2 py-0.5 rounded-full"
                      style={{
                        background:
                          test.status === "passed"
                            ? "rgba(16, 185, 129, 0.15)"
                            : test.status === "failed"
                            ? "rgba(220, 38, 38, 0.15)"
                            : "rgba(245, 158, 11, 0.15)",
                        color:
                          test.status === "passed"
                            ? "var(--color-sentinel-green)"
                            : test.status === "failed"
                            ? "var(--color-sentinel-red)"
                            : "var(--color-sentinel-amber)",
                      }}
                    >
                      {test.status}
                    </span>
                  </div>
                </div>
              ))}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

function FailuresPanel({
  tests,
  onTestClick,
}: {
  tests: TestResult[];
  onTestClick?: (test: TestResult) => void;
}) {
  const failedTests = tests.filter((t) => t.status === "failed");

  if (failedTests.length === 0) {
    return (
      <EmptyState
        icon={ListChecks}
        title="No failures"
        subtext="All tests are passing. Great job!"
      />
    );
  }

  return (
    <div className="space-y-4">
      <div
        className="p-4 rounded-lg border"
        style={{
          background: "rgba(220, 38, 38, 0.05)",
          borderColor: "rgba(220, 38, 38, 0.3)",
        }}
      >
        <div className="flex items-center gap-2">
          <AlertCircle className="h-4 w-4" style={{ color: "var(--color-sentinel-red)" }} />
          <span
            className="text-sm font-medium"
            style={{ color: "var(--color-sentinel-red)" }}
          >
            {failedTests.length} test{failedTests.length === 1 ? "" : "s"} failed
          </span>
        </div>
      </div>

      {failedTests.map((test) => (
        <div
          key={test.id}
          className="rounded-lg border overflow-hidden"
          style={{
            background: "var(--color-sentinel-bg-panel)",
            borderColor: "rgba(220, 38, 38, 0.3)",
          }}
        >
          <div
            className="px-4 py-3 flex items-center justify-between gap-4 cursor-pointer hover:bg-white/5"
            onClick={() => onTestClick?.(test)}
          >
            <div>
              <div
                className="text-sm font-medium"
                style={{ color: "var(--color-sentinel-text-primary)" }}
              >
                {test.name}
              </div>
              <div
                className="text-xs mt-0.5"
                style={{ color: "var(--color-sentinel-text-secondary)" }}
              >
                {test.suite}
              </div>
            </div>
            <span
              className="text-xs font-mono"
              style={{ color: "var(--color-sentinel-text-disabled)" }}
            >
              {test.duration}
            </span>
          </div>

          {(test.errorMessage || test.stackTrace) && (
            <div
              className="px-4 py-3 border-t text-xs font-mono overflow-x-auto"
              style={{
                background: "rgba(220, 38, 38, 0.05)",
                borderColor: "rgba(220, 38, 38, 0.2)",
                color: "var(--color-sentinel-red)",
              }}
            >
              {test.errorMessage && <div>{test.errorMessage}</div>}
              {test.stackTrace && (
                <pre className="mt-2 text-[10px] opacity-80 whitespace-pre-wrap">
                  {test.stackTrace}
                </pre>
              )}
            </div>
          )}
        </div>
      ))}
    </div>
  );
}

function HistoryPanel({
  history,
  onViewHistory,
}: {
  history: TestRunSummary[];
  onViewHistory?: (run: TestRunSummary) => void;
}) {
  if (history.length === 0) {
    return (
      <EmptyState
        icon={History}
        title="No history yet"
        subtext="Previous test runs will appear here."
      />
    );
  }

  return (
    <div className="rounded-lg border overflow-hidden" style={{ borderColor: "var(--color-sentinel-border)" }}>
      <table className="w-full text-sm">
        <thead>
          <tr
            style={{
              background: "var(--color-sentinel-bg-secondary)",
              borderBottom: "1px solid var(--color-sentinel-border)",
            }}
          >
            {["Branch", "Commit", "Status", "Duration", "Tests", "Time"].map((h) => (
              <th
                key={h}
                className="px-4 py-2 text-left text-xs font-medium"
                style={{ color: "var(--color-sentinel-text-secondary)" }}
              >
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {history.map((run) => (
            <tr
              key={run.runId}
              className={onViewHistory ? "cursor-pointer hover:bg-white/5" : ""}
              style={{ borderBottom: "1px solid var(--color-sentinel-border)" }}
              onClick={() => onViewHistory?.(run)}
            >
              <td
                className="px-4 py-3"
                style={{ color: "var(--color-sentinel-text-primary)" }}
              >
                {run.branch}
              </td>
              <td
                className="px-4 py-3 font-mono text-xs"
                style={{ color: "var(--color-sentinel-text-secondary)" }}
              >
                {run.commit.substring(0, 7)}
              </td>
              <td className="px-4 py-3">
                <span
                  className="text-[10px] font-medium uppercase tracking-wider px-2 py-0.5 rounded-full"
                  style={{
                    background:
                      run.status === "passed"
                        ? "rgba(16, 185, 129, 0.15)"
                        : run.status === "failed"
                        ? "rgba(220, 38, 38, 0.15)"
                        : "rgba(245, 158, 11, 0.15)",
                    color:
                      run.status === "passed"
                        ? "var(--color-sentinel-green)"
                        : run.status === "failed"
                        ? "var(--color-sentinel-red)"
                        : "var(--color-sentinel-amber)",
                  }}
                >
                  {run.status}
                </span>
              </td>
              <td
                className="px-4 py-3 text-xs"
                style={{ color: "var(--color-sentinel-text-secondary)" }}
              >
                {run.duration || "—"}
              </td>
              <td
                className="px-4 py-3 text-xs"
                style={{ color: "var(--color-sentinel-text-secondary)" }}
              >
                {run.passedTests}/{run.totalTests}
              </td>
              <td
                className="px-4 py-3 text-xs"
                style={{ color: "var(--color-sentinel-text-disabled)" }}
              >
                {run.startedAt
                  ? new Date(run.startedAt).toLocaleDateString("en-ZA")
                  : "—"}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function TestResultsView({
  summary,
  timeline,
  testResults,
  history = [],
  isLoading = false,
  onRerun,
  onEventClick,
  onTestClick,
  onViewHistory,
}: TestResultsViewProps) {
  const [activeTab, setActiveTab] = useState("overview");

  // Calculate tab counts
  const failedCount = testResults.filter((t) => t.status === "failed").length;

  const tabsWithCounts = TABS.map((tab) => ({
    ...tab,
    count:
      tab.id === "tests"
        ? testResults.length
        : tab.id === "failures"
        ? failedCount
        : tab.id === "history"
        ? history.length
        : undefined,
  }));

  if (isLoading) {
    return <PageLoading message="Loading test results…" />;
  }

  return (
    <div
      className="h-full overflow-y-auto"
      style={{ background: "var(--color-sentinel-bg-canvas)" }}
    >
      <div className="space-y-6 p-4 md:p-6">
        {/* Header */}
        <div className="flex items-center justify-between">
          <div>
            <h1
              className="text-xl font-semibold"
              style={{ color: "var(--color-sentinel-text-primary)" }}
            >
              CD Test Results
            </h1>
            <p
              className="text-sm mt-1"
              style={{ color: "var(--color-sentinel-text-secondary)" }}
            >
              Continuous deployment pipeline test execution and analysis
            </p>
          </div>
          {onRerun && (
            <button
              onClick={onRerun}
              className="flex items-center gap-2 px-4 py-2 text-sm font-medium rounded-lg border transition-colors"
              style={{
                background: "var(--color-sentinel-bg-panel)",
                borderColor: "var(--color-sentinel-border)",
                color: "var(--color-sentinel-text-primary)",
              }}
            >
              <PlayCircle className="h-4 w-4" />
              Run Tests
            </button>
          )}
        </div>

        {/* Tab navigation */}
        <TabBar
          tabs={tabsWithCounts}
          active={activeTab}
          onChange={setActiveTab}
          accentColor="var(--color-sentinel-blue)"
        />

        {/* Tab content */}
        {activeTab === "overview" && (
          <TestResultsOverview
            summary={summary}
            timeline={timeline}
            onRerun={onRerun}
            onEventClick={onEventClick}
          />
        )}

        {activeTab === "tests" && (
          <TestDetailsPanel tests={testResults} onTestClick={onTestClick} />
        )}

        {activeTab === "failures" && (
          <FailuresPanel tests={testResults} onTestClick={onTestClick} />
        )}

        {activeTab === "history" && (
          <HistoryPanel history={history} onViewHistory={onViewHistory} />
        )}
      </div>
    </div>
  );
}

export default TestResultsView;
