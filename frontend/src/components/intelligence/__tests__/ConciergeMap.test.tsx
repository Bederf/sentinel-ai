/**
 * Concierge Intelligence UI Component Tests
 * Phase 161-05 — Acceptance tests for ConciergeMap, RoomDetailPanel, SignalDrillDown
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@/test-utils";
import type { ConciergeRoom, ConciergeSignalSummary, ConciergeSignalDetail } from "../../../lib/api";

// ---- Mock data builders ----

function makeMockRoom(overrides: Partial<ConciergeRoom> = {}): ConciergeRoom {
  return {
    room_id: "FA2-1Q1-MR-01",
    building: "FA2",
    quadrant: "1Q1",
    room_type: "MR",
    floor: 1,
    friendly_name: "Meeting Room 01",
    capacity: 10,
    signal_count: 3,
    domains: ["space_optimisation", "email"],
    highest_severity: "high",
    latest_signal_at: "2026-03-14T09:12:00Z",
    urgency_score: 1.0,
    signals: [
      { id: "sig-1", signal_type: "booking_conflict", severity: "high", summary: "Block booking detected", created_at: "2026-03-14T09:12:00Z" },
      { id: "sig-2", signal_type: "booking_saturation", severity: "medium", summary: "85% saturated", created_at: "2026-03-14T07:00:00Z" },
      { id: "sig-3", signal_type: "complaint_email", severity: "high", summary: "Complaint from user", created_at: "2026-03-15T10:30:00Z" },
    ],
    ...overrides,
  };
}

const _mockSignals: ConciergeSignalSummary[] = [
  { id: "sig-1", signal_type: "booking_conflict", severity: "high", summary: "Block booking detected", created_at: "2026-03-14T09:12:00Z" },
  { id: "sig-2", signal_type: "booking_saturation", severity: "medium", summary: "85% saturated", created_at: "2026-03-14T07:00:00Z" },
];

const _mockDetail: ConciergeSignalDetail = {
  id: "sig-1",
  signal_type: "booking_conflict",
  signal_subtype: "block_booking",
  severity: "high",
  confidence: 0.92,
  summary: "Block booking detected: Bronwyn Mollentze holds FA2-1Q1-MR-01",
  source_module: "space_optimisation",
  raw_content: null,
  metadata: {
    organiser: "Bronwyn Mollentze",
    from_name: "Site 002 Helpdesk",
    from_email: "helpdesk@site002.example.com",
    subject: "Fw: Meeting room catering issue - FA2-1Q1-MR-01",
    logical_site_id: "site-002",
    room_id: "FA2-1Q1-MR-01",
    to: ["intake@sentinel-ai.co.za"],
    cc: ["facilities.manager@site002.example.com"],
    thread_participants: [
      "helpdesk@site002.example.com",
      "intake@sentinel-ai.co.za",
      "aisha.assistant@site002.example.com",
    ],
    thread_messages: [
      {
        from_name: "Site 002 Helpdesk",
        from_email: "helpdesk@site002.example.com",
        to: ["intake@sentinel-ai.co.za"],
        cc: ["facilities.manager@site002.example.com"],
        subject: "Fw: Meeting room catering issue - FA2-1Q1-MR-01",
        body_plain: "Please see below and advise.",
      },
      {
        from_name: "Executive Assistant Aisha Patel",
        from_email: "aisha.assistant@site002.example.com",
        to: ["helpdesk@site002.example.com"],
        subject: "Meeting room catering issue - FA2-1Q1-MR-01",
        body_plain: "Catering has not arrived and the delegates are waiting.",
      },
    ],
  },
  created_at: "2026-03-14T09:12:00Z",
  related_signals: [
    { id: "sig-2", signal_type: "booking_saturation", severity: "medium", summary: "85% saturated", created_at: "2026-03-14T07:00:00Z" },
  ],
  evidence_basis: ["Calendar analysis shows 4 consecutive weekly blocks"],
  suggested_action: "Speak privately with Bronwyn about room sharing",
  advisory_label: "For awareness only. Act at your discretion.",
  issue_cluster: null,
};

const _mockNonBlockDetail: ConciergeSignalDetail = {
  ..._mockDetail,
  signal_type: "complaint_email",
  summary: "Complaint from Shaun Grose: Room constantly booked by the same organiser",
  metadata: {
    ..._mockDetail.metadata,
    subject: "Room FA2-1Q1-MR-02 always blocked",
    from_name: "Shaun Grose",
    from_email: "SGrose@fnb.co.za",
  },
  related_signals: _mockDetail.related_signals,
  issue_cluster: {
    id: "cluster-1",
    title: "Email escalation cluster",
    cluster_state: "emerging",
    severity: "high",
  },
};

// ---- Mock the API module ----

vi.mock("../../../lib/api", async () => {
  const actual = await vi.importActual("../../../lib/api");
  return {
    ...(actual as object),
    conciergeApi: {
      getRooms: vi.fn().mockResolvedValue({ rooms: [makeMockRoom()] }),
      getRoomSignals: vi.fn().mockResolvedValue(_mockSignals),
      getSignalDetail: vi.fn().mockResolvedValue(_mockDetail),
      resolveSignal: vi.fn().mockResolvedValue({ signal_id: "sig-1", room_id: "FA2-1Q1-MR-01", site_id: "S001", resolution_state: "acknowledged" }),
      getDashboard: vi.fn().mockResolvedValue({ cards: [] }),
    },
  };
});

vi.mock("cytoscape", () => ({
  default: vi.fn(() => ({
    on: vi.fn(),
    fit: vi.fn(),
    destroy: vi.fn(),
    nodes: vi.fn(() => ({ forEach: vi.fn() })),
    getElementById: vi.fn(() => ({
      length: 0,
      position: () => ({ x: 0, y: 0 }),
      width: () => 0,
    })),
  })),
}));

// ---- RoomDetailPanel: rendering ----

describe("RoomDetailPanel rendering", () => {
  let RoomDetailPanel: typeof import("../RoomDetailPanel").RoomDetailPanel;

  beforeEach(async () => {
    RoomDetailPanel = (await import("../RoomDetailPanel")).RoomDetailPanel;
  });

  it("renders room name in header", () => {
    render(<RoomDetailPanel siteId="S001" room={makeMockRoom()} onClose={vi.fn()} onSignalSelect={vi.fn()} />);
    expect(screen.getByText("Meeting Room 01")).toBeInTheDocument();
  });

  it("shows signal count badge", () => {
    render(<RoomDetailPanel siteId="S001" room={makeMockRoom()} onClose={vi.fn()} onSignalSelect={vi.fn()} />);
    expect(screen.getByText("3 signals")).toBeInTheDocument();
  });

  it("renders signal cards after loading", async () => {
    render(<RoomDetailPanel siteId="S001" room={makeMockRoom()} onClose={vi.fn()} onSignalSelect={vi.fn()} />);
    await waitFor(() => {
      expect(screen.getByText("Block booking detected")).toBeInTheDocument();
    });
  });

  it("has close button with aria-label", () => {
    render(<RoomDetailPanel siteId="S001" room={makeMockRoom()} onClose={vi.fn()} onSignalSelect={vi.fn()} />);
    expect(screen.getByLabelText("Close panel")).toBeInTheDocument();
  });
});

// ---- RoomDetailPanel: interactions ----

describe("RoomDetailPanel interactions", () => {
  let RoomDetailPanel: typeof import("../RoomDetailPanel").RoomDetailPanel;

  beforeEach(async () => {
    RoomDetailPanel = (await import("../RoomDetailPanel")).RoomDetailPanel;
  });

  it("fires onSignalSelect when signal card tapped", async () => {
    const onSignalSelect = vi.fn();
    render(<RoomDetailPanel siteId="S001" room={makeMockRoom()} onClose={vi.fn()} onSignalSelect={onSignalSelect} />);
    await waitFor(() => {
      expect(screen.getByText("Block booking detected")).toBeInTheDocument();
    });
    const card = screen.getByText("Block booking detected").closest("button");
    if (card) fireEvent.click(card);
    expect(onSignalSelect).toHaveBeenCalledWith("sig-1");
  });

  it("fires onClose when close button clicked", () => {
    const onClose = vi.fn();
    render(<RoomDetailPanel siteId="S001" room={makeMockRoom()} onClose={onClose} onSignalSelect={vi.fn()} />);
    fireEvent.click(screen.getByLabelText("Close panel"));
    expect(onClose).toHaveBeenCalled();
  });
});

// ---- SignalDrillDown: content ----

describe("SignalDrillDown content", () => {
  let SignalDrillDown: typeof import("../SignalDrillDown").SignalDrillDown;

  beforeEach(async () => {
    SignalDrillDown = (await import("../SignalDrillDown")).SignalDrillDown;
  });

  it("shows advisory label text", async () => {
    render(<SignalDrillDown siteId="S001" roomId="FA2-1Q1-MR-01" signalId="sig-1" onBack={vi.fn()} />);
    await waitFor(() => {
      expect(screen.getByText(/awareness.*discretion/i)).toBeInTheDocument();
    });
  });

  it("shows signal summary", async () => {
    render(<SignalDrillDown siteId="S001" roomId="FA2-1Q1-MR-01" signalId="sig-1" onBack={vi.fn()} />);
    await waitFor(() => {
      expect(screen.getByText(/Block booking detected/)).toBeInTheDocument();
    });
  });

  it("shows confidence percentage", async () => {
    const { conciergeApi } = await import("../../../lib/api");
    vi.mocked(conciergeApi.getSignalDetail).mockResolvedValueOnce(_mockNonBlockDetail);
    render(<SignalDrillDown siteId="S001" roomId="FA2-1Q1-MR-01" signalId="sig-1" onBack={vi.fn()} />);
    await waitFor(() => {
      expect(screen.getByText("Confidence: 92%")).toBeInTheDocument();
    });
  });

  it("shows suggested action section", async () => {
    const { conciergeApi } = await import("../../../lib/api");
    vi.mocked(conciergeApi.getSignalDetail).mockResolvedValueOnce(_mockNonBlockDetail);
    render(<SignalDrillDown siteId="S001" roomId="FA2-1Q1-MR-01" signalId="sig-1" onBack={vi.fn()} />);
    await waitFor(() => {
      expect(screen.getByText("Suggested Action")).toBeInTheDocument();
    });
  });

  it("shows affected parties and thread participants", async () => {
    const { conciergeApi } = await import("../../../lib/api");
    vi.mocked(conciergeApi.getSignalDetail).mockResolvedValueOnce(_mockNonBlockDetail);
    render(<SignalDrillDown siteId="S001" roomId="FA2-1Q1-MR-01" signalId="sig-1" onBack={vi.fn()} />);
    await waitFor(() => {
      expect(screen.getByText("Affected Parties")).toBeInTheDocument();
      expect(screen.getByText("Reported By")).toBeInTheDocument();
      expect(screen.getAllByText(/Site 002 Helpdesk helpdesk@site002\.example\.com/).length).toBeGreaterThan(0);
      expect(screen.getAllByText(/Executive Assistant Aisha Patel aisha\.assistant@site002\.example\.com/).length).toBeGreaterThan(0);
      expect(screen.getByText("Thread Summary")).toBeInTheDocument();
      expect(screen.getByText("Messages In Thread")).toBeInTheDocument();
      expect(screen.getByText("Email Timeline")).toBeInTheDocument();
      expect(screen.getByText("Initial Email")).toBeInTheDocument();
      expect(screen.getByText("Reply 1")).toBeInTheDocument();
    });
  });
});

// ---- SignalDrillDown: interactions ----

describe("SignalDrillDown interactions", () => {
  let SignalDrillDown: typeof import("../SignalDrillDown").SignalDrillDown;

  beforeEach(async () => {
    SignalDrillDown = (await import("../SignalDrillDown")).SignalDrillDown;
  });

  it("fires onBack when back button clicked", () => {
    const onBack = vi.fn();
    render(<SignalDrillDown siteId="S001" roomId="FA2-1Q1-MR-01" signalId="sig-1" onBack={onBack} />);
    fireEvent.click(screen.getByLabelText("Back to room"));
    expect(onBack).toHaveBeenCalled();
  });

  it("shows related signals section", async () => {
    const { conciergeApi } = await import("../../../lib/api");
    vi.mocked(conciergeApi.getSignalDetail).mockResolvedValueOnce(_mockNonBlockDetail);
    render(<SignalDrillDown siteId="S001" roomId="FA2-1Q1-MR-01" signalId="sig-1" onBack={vi.fn()} />);
    await waitFor(() => {
      expect(screen.getByText("Related Signals")).toBeInTheDocument();
    });
  });

  it("displays severity badge", async () => {
    render(<SignalDrillDown siteId="S001" roomId="FA2-1Q1-MR-01" signalId="sig-1" onBack={vi.fn()} />);
    await waitFor(() => {
      expect(screen.getByText("high")).toBeInTheDocument();
    });
  });
});

describe("SignalDrillDown block actions", () => {
  let SignalDrillDown: typeof import("../SignalDrillDown").SignalDrillDown;

  beforeEach(async () => {
    SignalDrillDown = (await import("../SignalDrillDown")).SignalDrillDown;
  });

  it("shows block booking header and action buttons", async () => {
    render(<SignalDrillDown siteId="S001" roomId="FA2-1Q1-MR-01" signalId="sig-1" onBack={vi.fn()} />);
    await screen.findByText("Block Booking Risk");
    await screen.findByRole("button", { name: /Resolve/i });
    await screen.findByRole("button", { name: /Archive/i });
  });

  it("resolves block signal and closes the panel", async () => {
    const onBack = vi.fn();
    const { conciergeApi } = await import("../../../lib/api");
    const resolveMock = vi.mocked(conciergeApi.resolveSignal);
    resolveMock.mockResolvedValueOnce({ signal_id: "sig-1", room_id: "FA2-1Q1-MR-01", site_id: "S001", resolution_state: "resolved" });
    render(<SignalDrillDown siteId="S001" roomId="FA2-1Q1-MR-01" signalId="sig-1" onBack={onBack} />);
    await waitFor(() => expect(screen.getByRole("button", { name: /Resolve/i })).toBeInTheDocument());
    fireEvent.click(screen.getByRole("button", { name: /Resolve/i }));
    await waitFor(() => {
      expect(resolveMock).toHaveBeenCalledWith(
        "S001",
        "FA2-1Q1-MR-01",
        "sig-1",
        "resolved",
        "Resolved via block booking detail",
      );
    });
    expect(onBack).toHaveBeenCalled();
  });

  it("archives block signal with the archive note", async () => {
    const onBack = vi.fn();
    const { conciergeApi } = await import("../../../lib/api");
    const resolveMock = vi.mocked(conciergeApi.resolveSignal);
    resolveMock.mockResolvedValueOnce({ signal_id: "sig-1", room_id: "FA2-1Q1-MR-01", site_id: "S001", resolution_state: "resolved" });
    render(<SignalDrillDown siteId="S001" roomId="FA2-1Q1-MR-01" signalId="sig-1" onBack={onBack} />);
    await waitFor(() => expect(screen.getByRole("button", { name: /Archive/i })).toBeInTheDocument());
    fireEvent.click(screen.getByRole("button", { name: /Archive/i }));
    await waitFor(() => {
      expect(resolveMock).toHaveBeenCalledWith(
        "S001",
        "FA2-1Q1-MR-01",
        "sig-1",
        "resolved",
        "Archived via block booking detail",
      );
    });
    expect(onBack).toHaveBeenCalled();
  });
});

// ---- ConciergeMap: states ----

describe("ConciergeMap states", () => {
  let ConciergeMap: typeof import("../ConciergeMap").ConciergeMap;

  beforeEach(async () => {
    ConciergeMap = (await import("../ConciergeMap")).ConciergeMap;
  });

  it("renders loading state initially", () => {
    render(<ConciergeMap siteId="S001" onSignalSelect={vi.fn()} />);
    expect(screen.getByText("Loading meeting room signals...")).toBeInTheDocument();
  });

  it("clears loading after fetch", async () => {
    render(<ConciergeMap siteId="S001" onSignalSelect={vi.fn()} />);
    await waitFor(() => {
      expect(screen.queryByText("Loading meeting room signals...")).not.toBeInTheDocument();
    });
  });

  it("shows empty state when no rooms", async () => {
    const { conciergeApi } = await import("../../../lib/api");
    vi.mocked(conciergeApi.getRooms).mockResolvedValueOnce({ rooms: [] });
    render(<ConciergeMap siteId="S001" onSignalSelect={vi.fn()} />);
    await waitFor(() => {
      expect(screen.getByText("No meeting room signals for this building")).toBeInTheDocument();
    });
  });
});
