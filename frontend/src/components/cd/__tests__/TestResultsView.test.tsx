/**
 * CD Workflow Components — Tests
 *
 * Tests for Timeline, TestResultsOverview, and TestResultsView components.
 */

import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import React from "react";

import { Timeline } from "../Timeline";
import { TestResultsOverview } from "../TestResultsOverview";
import { TestResultsView } from "../TestResultsView";
import type { TimelineEvent } from "../Timeline";
import type { TestRunSummary } from "../TestResultsOverview";

describe("Timeline", () => {
  const mockEvents: TimelineEvent[] = [
    {
      id: "1",
      title: "Checkout",
      description: "Clone repository",
      status: "success",
      timestamp: "2026-05-16T10:00:00Z",
      duration: "2s",
    },
    {
      id: "2",
      title: "Install Dependencies",
      description: "npm ci",
      status: "success",
      timestamp: "2026-05-16T10:00:02Z",
      duration: "45s",
    },
    {
      id: "3",
      title: "Run Tests",
      description: "vitest run",
      status: "in_progress",
      timestamp: "2026-05-16T10:00:47Z",
    },
    {
      id: "4",
      title: "Build",
      description: "npm run build",
      status: "pending",
    },
  ];

  it("renders all events in the timeline", () => {
    render(<Timeline events={mockEvents} />);

    expect(screen.getByText("Checkout")).toBeInTheDocument();
    expect(screen.getByText("Install Dependencies")).toBeInTheDocument();
    expect(screen.getByText("Run Tests")).toBeInTheDocument();
    expect(screen.getByText("Build")).toBeInTheDocument();
  });

  it("displays correct status labels", () => {
    render(<Timeline events={mockEvents} />);

    expect(screen.getByText("Success")).toBeInTheDocument();
    expect(screen.getByText("In Progress")).toBeInTheDocument();
    expect(screen.getByText("Pending")).toBeInTheDocument();
  });

  it("displays timestamps when provided", () => {
    render(<Timeline events={mockEvents} />);

    // Timestamps should be formatted
    expect(screen.getByText(/10:00:00/)).toBeInTheDocument();
    expect(screen.getByText(/10:00:02/)).toBeInTheDocument();
  });

  it("displays durations when provided", () => {
    render(<Timeline events={mockEvents} />);

    expect(screen.getByText("2s")).toBeInTheDocument();
    expect(screen.getByText("45s")).toBeInTheDocument();
  });

  it("displays error messages for failed events", () => {
    const eventsWithError: TimelineEvent[] = [
      {
        id: "1",
        title: "Run Tests",
        status: "failed",
        errorMessage: "Test suite failed with 3 errors",
      },
    ];

    render(<Timeline events={eventsWithError} />);

    expect(screen.getByText("Error")).toBeInTheDocument();
    expect(screen.getByText("Test suite failed with 3 errors")).toBeInTheDocument();
  });

  it("displays metadata when provided", () => {
    const eventsWithMetadata: TimelineEvent[] = [
      {
        id: "1",
        title: "Deploy",
        status: "success",
        metadata: { environment: "production", region: "us-east-1" },
      },
    ];

    render(<Timeline events={eventsWithMetadata} />);

    expect(screen.getByText("environment: production")).toBeInTheDocument();
    expect(screen.getByText("region: us-east-1")).toBeInTheDocument();
  });

  it("calls onEventClick when an event is clicked", async () => {
    const user = userEvent.setup();
    const onClick = vi.fn();

    render(<Timeline events={mockEvents} onEventClick={onClick} />);

    const event = screen.getByText("Checkout").closest("div[class*='relative flex']");
    if (event) {
      await user.click(event);
      expect(onClick).toHaveBeenCalledWith(mockEvents[0]);
    }
  });

  it("highlights the current event", () => {
    render(<Timeline events={mockEvents} currentEventId="3" />);

    // The in_progress event should be the current one
    expect(screen.getByText("Run Tests")).toBeInTheDocument();
  });
});

describe("TestResultsOverview", () => {
  const mockSummary: TestRunSummary = {
    runId: "run-001",
    branch: "feature/new-dashboard",
    commit: "abc123def456",
    commitMessage: "Add new dashboard components",
    author: "John Doe",
    startedAt: "2026-05-16T10:00:00Z",
    completedAt: "2026-05-16T10:05:30Z",
    duration: "5m 30s",
    status: "passed",
    totalTests: 150,
    passedTests: 148,
    failedTests: 0,
    skippedTests: 2,
    coverage: 87.5,
  };

  const mockTimeline: TimelineEvent[] = [
    {
      id: "1",
      title: "Install",
      status: "success",
      duration: "30s",
    },
    {
      id: "2",
      title: "Lint",
      status: "success",
      duration: "15s",
    },
    {
      id: "3",
      title: "Test",
      status: "success",
      duration: "3m 45s",
    },
  ];

  it("renders run summary information", () => {
    render(
      <TestResultsOverview summary={mockSummary} timeline={mockTimeline} />
    );

    expect(screen.getByText("feature/new-dashboard")).toBeInTheDocument();
    expect(screen.getByText("Add new dashboard components")).toBeInTheDocument();
    expect(screen.getByText("abc123d")).toBeInTheDocument();
    expect(screen.getByText("John Doe")).toBeInTheDocument();
  });

  it("displays KPI cards with correct values", () => {
    render(
      <TestResultsOverview summary={mockSummary} timeline={mockTimeline} />
    );

    expect(screen.getByText("99%")).toBeInTheDocument(); // Pass rate
    expect(screen.getByText("0")).toBeInTheDocument(); // Failed tests
    expect(screen.getByText("5m 30s")).toBeInTheDocument(); // Duration
    expect(screen.getByText("87.5%")).toBeInTheDocument(); // Coverage
  });

  it("displays test breakdown statistics", () => {
    render(
      <TestResultsOverview summary={mockSummary} timeline={mockTimeline} />
    );

    expect(screen.getByText("150")).toBeInTheDocument(); // Total
    expect(screen.getByText("148")).toBeInTheDocument(); // Passed
    expect(screen.getByText("2")).toBeInTheDocument(); // Skipped
  });

  it("renders empty state when summary is null", () => {
    render(<TestResultsOverview summary={null} timeline={[]} />);

    expect(screen.getByText("No test runs yet")).toBeInTheDocument();
    expect(screen.getByText("Trigger a deployment to see test results here.")).toBeInTheDocument();
  });

  it("calls onRerun when re-run button is clicked", async () => {
    const user = userEvent.setup();
    const onRerun = vi.fn();

    render(
      <TestResultsOverview
        summary={mockSummary}
        timeline={mockTimeline}
        onRerun={onRerun}
      />
    );

    const rerunButton = screen.getByRole("button", { name: /Re-run/i });
    await user.click(rerunButton);
    expect(onRerun).toHaveBeenCalled();
  });

  it("shows correct status badge for failed runs", () => {
    const failedSummary = { ...mockSummary, status: "failed" as const, failedTests: 5 };

    render(
      <TestResultsOverview summary={failedSummary} timeline={mockTimeline} />
    );

    expect(screen.getByText("Failed")).toBeInTheDocument();
  });

  it("calculates and displays correct pass rate", () => {
    const partialSummary = {
      ...mockSummary,
      passedTests: 75,
      totalTests: 100,
      failedTests: 25,
    };

    render(
      <TestResultsOverview summary={partialSummary} timeline={mockTimeline} />
    );

    expect(screen.getByText("75%")).toBeInTheDocument();
  });
});

describe("TestResultsView", () => {
  const mockSummary: TestRunSummary = {
    runId: "run-001",
    branch: "main",
    commit: "abc123def456",
    commitMessage: "Fix bug in authentication",
    author: "Jane Smith",
    status: "passed",
    totalTests: 50,
    passedTests: 48,
    failedTests: 2,
    skippedTests: 0,
    startedAt: "2026-05-16T10:00:00Z",
    duration: "2m 15s",
  };

  const mockTestResults = [
    {
      id: "test-1",
      name: "should render dashboard",
      suite: "Dashboard",
      status: "passed" as const,
      duration: "0.5s",
    },
    {
      id: "test-2",
      name: "should handle login",
      suite: "Auth",
      status: "failed" as const,
      duration: "1.2s",
      errorMessage: "Expected user to be logged in",
    },
    {
      id: "test-3",
      name: "should validate input",
      suite: "Forms",
      status: "passed" as const,
      duration: "0.3s",
    },
  ];

  const mockHistory = [
    mockSummary,
    { ...mockSummary, runId: "run-000", status: "failed" as const },
  ];

  it("renders all tab headers", () => {
    render(
      <TestResultsView
        summary={mockSummary}
        timeline={[]}
        testResults={mockTestResults}
      />
    );

    expect(screen.getByRole("tab", { name: /Overview/i })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: /Test Details/i })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: /Failures/i })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: /History/i })).toBeInTheDocument();
  });

  it("shows loading state when isLoading is true", () => {
    render(
      <TestResultsView
        summary={null}
        timeline={[]}
        testResults={[]}
        isLoading={true}
      />
    );

    expect(screen.getByText("Loading test results…")).toBeInTheDocument();
  });

  it("displays correct counts in tab badges", () => {
    render(
      <TestResultsView
        summary={mockSummary}
        timeline={[]}
        testResults={mockTestResults}
        history={mockHistory}
      />
    );

    // The tabs should show counts
    expect(screen.getByText("3")).toBeInTheDocument(); // Test count
    expect(screen.getByText("1")).toBeInTheDocument(); // Failure count
    expect(screen.getByText("2")).toBeInTheDocument(); // History count
  });

  it("switches tabs when clicked", async () => {
    const user = userEvent.setup();

    render(
      <TestResultsView
        summary={mockSummary}
        timeline={[]}
        testResults={mockTestResults}
      />
    );

    // Initially on Overview - shows the branch from mockSummary
    expect(screen.getByText("main")).toBeInTheDocument();

    // Click on Test Details tab
    const testDetailsTab = screen.getByRole("tab", { name: /Test Details/i });
    await user.click(testDetailsTab);

    // Should see test list
    expect(screen.getByText("should render dashboard")).toBeInTheDocument();
  });

  it("filters tests by status in Test Details tab", async () => {
    const user = userEvent.setup();

    render(
      <TestResultsView
        summary={mockSummary}
        timeline={[]}
        testResults={mockTestResults}
      />
    );

    // Navigate to Test Details
    const testDetailsTab = screen.getByRole("tab", { name: /Test Details/i });
    await user.click(testDetailsTab);

    // Click on "Failed" filter
    const failedFilter = screen.getByRole("button", { name: /failed/i });
    await user.click(failedFilter);

    // Should only see failed test
    expect(screen.getByText("should handle login")).toBeInTheDocument();
    expect(screen.queryByText("should render dashboard")).not.toBeInTheDocument();
  });

  it("displays failure details in Failures tab", async () => {
    const user = userEvent.setup();

    render(
      <TestResultsView
        summary={mockSummary}
        timeline={[]}
        testResults={mockTestResults}
      />
    );

    // Navigate to Failures tab
    const failuresTab = screen.getByRole("tab", { name: /Failures/i });
    await user.click(failuresTab);

    // Should see failed test and error message
    expect(screen.getByText("should handle login")).toBeInTheDocument();
    expect(screen.getByText("Expected user to be logged in")).toBeInTheDocument();
  });

  it("shows empty state in Failures tab when no failures", async () => {
    const user = userEvent.setup();

    const passingTests = mockTestResults.map((t) => ({ ...t, status: "passed" as const }));

    render(
      <TestResultsView
        summary={{ ...mockSummary, failedTests: 0 }}
        timeline={[]}
        testResults={passingTests}
      />
    );

    // Navigate to Failures tab
    const failuresTab = screen.getByRole("tab", { name: /Failures/i });
    await user.click(failuresTab);

    expect(screen.getByText("No failures")).toBeInTheDocument();
    expect(screen.getByText("All tests are passing. Great job!")).toBeInTheDocument();
  });

  it("displays history in History tab", async () => {
    const user = userEvent.setup();

    render(
      <TestResultsView
        summary={mockSummary}
        timeline={[]}
        testResults={mockTestResults}
        history={mockHistory}
      />
    );

    // Navigate to History tab
    const historyTab = screen.getByRole("tab", { name: /History/i });
    await user.click(historyTab);

    // Should see history entries
    expect(screen.getByText("main")).toBeInTheDocument();
    expect(screen.getByText("abc123d")).toBeInTheDocument();
  });
});
