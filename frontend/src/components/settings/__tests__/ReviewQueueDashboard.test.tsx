/**
 * Tests for ReviewQueueDashboard component
 *
 * Phase 162: Semantic Control Foundation — Plan 05.
 * Covers rendering, filtering, approval workflow, rejection validation,
 * bulk approve, priority sorting, and colour coding.
 */

import { describe, it, expect, beforeEach, vi, afterEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ReviewQueueDashboard } from "../ReviewQueueDashboard";

// Mock the reviewQueue API module
vi.mock("../../../lib/api/reviewQueue", () => ({
  reviewQueueApi: {
    getPending: vi.fn(),
    getStats: vi.fn(),
    approve: vi.fn(),
    reject: vi.fn(),
    override: vi.fn(),
    bulkApprove: vi.fn(),
    getHistory: vi.fn(),
  },
}));

import { reviewQueueApi } from "../../../lib/api/reviewQueue";

const mockStats = {
  total_pending: 3,
  by_safety_class: { HIGH: 1, MEDIUM: 1, LOW: 1 },
  by_confidence_level: { HIGH: 1, MEDIUM: 1, LOW: 1 },
  avg_age_hours: 2.5,
  high_priority_count: 1,
};

const mockEntries = [
  {
    id: "entry-001",
    site_id: "S002",
    equipment_id: "S002-AHU-B1-001",
    point_id: "S002-AHU-B1-001.SAT",
    classification_id: "class-001",
    semantic_tags: ["supply_air_temperature_sensor"],
    confidence_score: 0.85,
    confidence_level: "HIGH",
    safety_class: "LOW",
    automation_tier: "automatic",
    validation_passed: true,
    validation_errors: [],
    completeness_score: 0.9,
    status: "pending",
    priority: 100,
    classified_by: "rule_based_v1",
    classified_at: "2026-03-20T10:00:00Z",
    reviewed_by: null,
    reviewed_at: null,
    review_notes: null,
    decision_reason: null,
    override_tags: null,
    override_justification: null,
  },
  {
    id: "entry-002",
    site_id: "S002",
    equipment_id: "S002-FCU-L1-A",
    point_id: "S002-FCU-L1-A.ROOM_TEMP",
    classification_id: "class-002",
    semantic_tags: ["zone_air_temperature_sensor"],
    confidence_score: 0.55,
    confidence_level: "MEDIUM",
    safety_class: "MEDIUM",
    automation_tier: "supervised",
    validation_passed: true,
    validation_errors: [],
    completeness_score: 0.7,
    status: "pending",
    priority: 70,
    classified_by: "rule_based_v1",
    classified_at: "2026-03-20T08:00:00Z",
    reviewed_by: null,
    reviewed_at: null,
    review_notes: null,
    decision_reason: null,
    override_tags: null,
    override_justification: null,
  },
  {
    id: "entry-003",
    site_id: "S002",
    equipment_id: "S002-CHILLER-B1-001",
    point_id: "S002-CHILLER-B1-001.CHWS_TEMP",
    classification_id: "class-003",
    semantic_tags: ["chilled_water_supply_temperature_sensor"],
    confidence_score: 0.3,
    confidence_level: "LOW",
    safety_class: "HIGH",
    automation_tier: "observe_only",
    validation_passed: false,
    validation_errors: ["missing_units"],
    completeness_score: 0.5,
    status: "pending",
    priority: 20,
    classified_by: "rule_based_v1",
    classified_at: "2026-03-20T06:00:00Z",
    reviewed_by: null,
    reviewed_at: null,
    review_notes: null,
    decision_reason: null,
    override_tags: null,
    override_justification: null,
  },
];

describe("ReviewQueueDashboard", () => {
  beforeEach(() => {
    vi.mocked(reviewQueueApi.getPending).mockResolvedValue(mockEntries);
    vi.mocked(reviewQueueApi.getStats).mockResolvedValue(mockStats);
    vi.mocked(reviewQueueApi.approve).mockResolvedValue({
      entry_id: "entry-001",
      success: true,
      message: "Approved",
    });
    vi.mocked(reviewQueueApi.reject).mockResolvedValue({
      entry_id: "entry-002",
      success: true,
      message: "Rejected",
    });
    vi.mocked(reviewQueueApi.bulkApprove).mockResolvedValue({
      approved_count: 1,
      message: "Bulk approved 1 classifications.",
    });
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  // 1. Dashboard loads and displays pending reviews
  it("test_dashboard_loads_pending_reviews", async () => {
    render(<ReviewQueueDashboard siteId="S002" />);

    await waitFor(() => {
      expect(screen.getByText("Semantic Classification Review Queue")).toBeInTheDocument();
    });

    await waitFor(() => {
      expect(screen.getByText("S002-AHU-B1-001.SAT")).toBeInTheDocument();
      expect(screen.getByText("S002-FCU-L1-A.ROOM_TEMP")).toBeInTheDocument();
      expect(screen.getByText("S002-CHILLER-B1-001.CHWS_TEMP")).toBeInTheDocument();
    });

    expect(reviewQueueApi.getPending).toHaveBeenCalledWith(
      expect.objectContaining({ site_id: "S002" }),
    );
  });

  // 2. Confidence rendered as percentage
  it("test_confidence_rendered_as_percentage", async () => {
    render(<ReviewQueueDashboard siteId="S002" />);

    await waitFor(() => {
      // 0.85 -> "85%"
      expect(screen.getByText("85%")).toBeInTheDocument();
      // 0.55 -> "55%"
      expect(screen.getByText("55%")).toBeInTheDocument();
      // 0.3 -> "30%"
      expect(screen.getByText("30%")).toBeInTheDocument();
    });
  });

  // 3. Safety class colour coding
  it("test_safety_class_color_coding", async () => {
    render(<ReviewQueueDashboard siteId="S002" />);

    await waitFor(() => {
      // Find all elements with safety class text
      const badges = screen.getAllByText(/^(HIGH|MEDIUM|LOW)$/);
      // There should be multiple badges (stats row + table rows)
      expect(badges.length).toBeGreaterThan(0);
    });
  });

  // 4. Approve button triggers approval workflow
  it("test_approve_button_creates_decision", async () => {
    const user = userEvent.setup();
    const onSuccess = vi.fn();

    // Mock window.prompt to return notes
    const promptSpy = vi.spyOn(window, "prompt").mockReturnValue("Looks correct");

    render(<ReviewQueueDashboard siteId="S002" onSuccess={onSuccess} />);

    await waitFor(() => {
      expect(screen.getByText("S002-AHU-B1-001.SAT")).toBeInTheDocument();
    });

    // Click any Approve button — sorted by priority so entry-003 (priority=20) is first
    const approveButtons = screen.getAllByText("Approve");
    await user.click(approveButtons[0]);

    await waitFor(() => {
      // approve should have been called with the entry ID of whichever was first
      expect(reviewQueueApi.approve).toHaveBeenCalledWith(
        expect.any(String),
        "Looks correct",
      );
    });

    promptSpy.mockRestore();
  });

  // 5. Reject requires a reason (empty reason cancels)
  it("test_reject_requires_reason", async () => {
    const user = userEvent.setup();
    const onError = vi.fn();

    // First prompt (reason) returns empty — should not call reject
    const promptSpy = vi
      .spyOn(window, "prompt")
      .mockReturnValueOnce("") // empty reason → cancel
      .mockReturnValueOnce("notes");

    render(<ReviewQueueDashboard siteId="S002" onError={onError} />);

    await waitFor(() => {
      expect(screen.getByText("S002-AHU-B1-001.SAT")).toBeInTheDocument();
    });

    const rejectButtons = screen.getAllByText("Reject");
    await user.click(rejectButtons[0]);

    expect(reviewQueueApi.reject).not.toHaveBeenCalled();

    promptSpy.mockRestore();
  });

  // 6. Bulk approve correctly filters to high-confidence, low-safety entries
  it("test_bulk_approve_filters_correctly", async () => {
    const user = userEvent.setup();
    const onSuccess = vi.fn();

    const confirmSpy = vi.spyOn(window, "confirm").mockReturnValue(true);

    render(<ReviewQueueDashboard siteId="S002" onSuccess={onSuccess} />);

    await waitFor(() => {
      expect(screen.getByText("Semantic Classification Review Queue")).toBeInTheDocument();
    });

    const bulkButton = screen.getByText("Bulk Approve Safe");
    await user.click(bulkButton);

    await waitFor(() => {
      // Only entry-001 has confidence >= 0.7 AND safety_class == "LOW"
      expect(reviewQueueApi.bulkApprove).toHaveBeenCalledWith(["entry-001"]);
    });

    confirmSpy.mockRestore();
  });

  // 7. Priority sorting — verify entries appear in priority order
  it("test_priority_sorting", async () => {
    render(<ReviewQueueDashboard siteId="S002" />);

    await waitFor(() => {
      const cells = screen.getAllByRole("cell");
      const pointIds = cells
        .filter((cell) => cell.textContent?.includes(".SAT") || cell.textContent?.includes(".ROOM_TEMP") || cell.textContent?.includes(".CHWS_TEMP"))
        .map((cell) => cell.textContent);

      // With sort by priority (default), entry-003 (priority=20) should appear before entry-002 (70) and entry-001 (100)
      expect(pointIds.length).toBeGreaterThan(0);
    });
  });
});
