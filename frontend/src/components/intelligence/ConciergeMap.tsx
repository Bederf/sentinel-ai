/**
 * ConciergeMap — Site-scoped meeting room map for concierge operations.
 *
 * Layout:
 * - centre node: Meeting Rooms
 * - first ring: room nodes
 * - second ring: signal nodes for the expanded room only
 */

import { useEffect, useRef, useCallback, useState } from "react";
import cytoscape from "cytoscape";
import type { Core } from "cytoscape";
import type { ConciergeRoom, ConciergeSignalSummary } from "../../lib/api";
import { conciergeApi } from "../../lib/api";

// ---- Severity colour mapping ----

const SEVERITY_COLORS: Record<string, string> = {
  low: "var(--color-sentinel-green)",
  medium: "var(--color-sentinel-amber)",
  high: "var(--color-sentinel-amber)",
  critical: "var(--color-sentinel-red)",
};

const SEVERITY_BG: Record<string, string> = {
  low: "rgba(46,204,113,0.12)",
  medium: "rgba(241,196,15,0.12)",
  high: "rgba(230,126,34,0.12)",
  critical: "rgba(231,76,60,0.12)",
};

// ---- Helpers ----

function sizeFromSignalCount(count: number): number {
  if (count <= 1) return 32;
  if (count <= 3) return 48;
  if (count <= 5) return 64;
  return 80;
}

function colorFromSeverity(sev: string): string {
  return SEVERITY_COLORS[sev] || SEVERITY_COLORS.low;
}

function bgFromSeverity(sev: string): string {
  return SEVERITY_BG[sev] || SEVERITY_BG.low;
}

function glowOpacity(urgency: number): number {
  return 0.15 + urgency * 0.55;
}

function _signalLabelFromType(signalType: string): string {
  switch (signalType) {
    case "booking_conflict":
      return "Block";
    case "no_show_pattern":
    case "booking_no_show":
      return "Ghost";
    default:
      return "Info";
  }
}

function getRoomDisplayName(room: ConciergeRoom): string {
  const raw = (room.room_id || "").trim();
  if (!raw) return "";

  // Strip site prefix: S002-L1-MR2 -> L1-MR2
  const compact = raw.replace(/^S\d{3}-/i, "");
  const base = compact && compact !== raw ? compact : raw;

  // Abbreviate common room types so labels fit inside circles cleanly
  return base
    .replace(/\bfocus\s*room\b/gi, "FR")
    .replace(/\bmeeting\s*room\b/gi, "MR")
    .replace(/\bconference\s*room\b/gi, "CR")
    .replace(/\bboard\s*room\b/gi, "BR")
    .replace(/\bopen\s*space\b/gi, "OS")
    .replace(/\btraining\s*room\b/gi, "TR")
    .replace(/\bhuddle\s*room\b/gi, "HR");
}

function roomLabel(room: ConciergeRoom): string {
  return getRoomDisplayName(room);
}

function _labelSizeForText(value: string, minSize = 40, maxSize = 72): number {
  const cleaned = value.replace(/\s+/g, " ").trim();
  if (!cleaned) return minSize;
  const estimated = cleaned.length * 7 + 16;
  return Math.min(maxSize, Math.max(minSize, estimated));
}

type CategoryKey = "ghost" | "block_risk" | "info";

interface SignalCategory {
  key: CategoryKey;
  label: string;
  severity: string;
  signals: ConciergeSignalSummary[];
}

interface Point {
  x: number;
  y: number;
}

type RoomPositions = Record<string, Point>;

function categoryKeyFromSignal(signalType: string): CategoryKey {
  switch (signalType) {
    case "booking_conflict":
      return "block_risk";
    case "no_show_pattern":
    case "booking_no_show":
      return "ghost";
    default:
      return "info";
  }
}

function categoryLabelFromKey(key: CategoryKey): string {
  switch (key) {
    case "ghost":
      return "Ghost";
    case "block_risk":
      return "Block";
    case "info":
      return "Info";
  }
}

const _CATEGORY_BORDER_COLORS: Record<CategoryKey, string> = {
  ghost: "var(--color-sentinel-red)",
  block_risk: "var(--color-sentinel-amber)",
  info: "var(--color-sentinel-amber)",
};

function severityRank(severity: string): number {
  switch (severity) {
    case "critical":
      return 4;
    case "high":
      return 3;
    case "medium":
      return 2;
    default:
      return 1;
  }
}

function buildSignalCategories(room: ConciergeRoom): SignalCategory[] {
  const categories = new Map<CategoryKey, SignalCategory>();

  room.signals.forEach((signal) => {
    const key = categoryKeyFromSignal(signal.signal_type);
    const existing = categories.get(key);

    if (!existing) {
      categories.set(key, {
        key,
        label: categoryLabelFromKey(key),
        severity: signal.severity,
        signals: [signal],
      });
      return;
    }

    existing.signals.push(signal);
    if (severityRank(signal.severity) > severityRank(existing.severity)) {
      existing.severity = signal.severity;
    }
  });

  return Array.from(categories.values()).sort((left, right) => {
    const severityDelta = severityRank(right.severity) - severityRank(left.severity);
    if (severityDelta !== 0) return severityDelta;
    return right.signals.length - left.signals.length;
  });
}

function pickPrimarySignalId(room: ConciergeRoom): string | null {
  if (!room.signals.length) return null;
  const ranked = [...room.signals].sort((left, right) => {
    const severityDelta = severityRank(right.severity) - severityRank(left.severity);
    if (severityDelta !== 0) return severityDelta;
    return new Date(right.created_at).getTime() - new Date(left.created_at).getTime();
  });
  return ranked[0]?.id ?? null;
}

function buildDefaultRoomPositions(rooms: ConciergeRoom[], dims: CanvasDims): RoomPositions {
  const { centreX, centreY, maxRadius } = dims;
  const gap = 24; // visual breathing room between adjacent room circles
  const diameters = rooms.map((r) => sizeFromSignalCount(r.signal_count));
  const perimeterNeeded = diameters.reduce((acc, d) => acc + d, 0) + gap * Math.max(0, rooms.length);
  const radiusNeeded = Math.max(120, perimeterNeeded / (2 * Math.PI));
  const ringRadius = Math.min(Math.max(maxRadius - 70, 120), radiusNeeded);
  return Object.fromEntries(
    rooms.map((room, i) => {
      const distance = rooms.length === 1 ? 120 : ringRadius;
      const angle = rooms.length === 1 ? 0 : (i / rooms.length) * 2 * Math.PI - Math.PI / 2;
      return [
        room.room_id,
        {
          x: centreX + distance * Math.cos(angle),
          y: centreY + distance * Math.sin(angle),
        },
      ];
    }),
  );
}

// ---- Props ----

interface ConciergeMapProps {
  siteId: string;
  onSignalSelect: (room: ConciergeRoom, signalId: string) => void;
}

const REFRESH_INTERVAL_MS = 30 * 1000;

// ---- Element builders (extracted for ESLint max-lines) ----

interface CanvasDims { centreX: number; centreY: number; maxRadius: number; }

interface NodeData {
  data: Record<string, unknown>;
  position: { x: number; y: number };
  locked?: boolean;
  classes: string;
}

function buildRoomNodes(rooms: ConciergeRoom[], positions: RoomPositions, dims: CanvasDims): NodeData[] {
  const defaults = buildDefaultRoomPositions(rooms, dims);
  return rooms.map((room) => {
    const position = positions[room.room_id] || defaults[room.room_id];
    return {
      data: {
        id: room.room_id,
        label: roomLabel(room),
        node_type: "room",
        signal_count: room.signal_count,
        highest_severity: room.highest_severity,
        urgency_score: room.urgency_score,
        domains: room.domains,
        _room: room,
      },
      position,
      classes: "room",
    };
  });
}

function buildCentreNode(dims: CanvasDims): NodeData {
  return {
    data: {
      id: "meeting-rooms-root",
      label: "Meeting Rooms",
      node_type: "root",
      highest_severity: "low",
    },
    position: { x: dims.centreX, y: dims.centreY },
    locked: true,
    classes: "root",
  };
}

function buildRoomEdges(rooms: ConciergeRoom[]) {
  return rooms.map((room) => ({
    data: {
      id: `room-edge-${room.room_id}`,
      source: "meeting-rooms-root",
      target: room.room_id,
    },
    classes: "room-edge",
  }));
}

function buildChildElements(
  expandedRoomId: string | null,
  expandedCategoryKey: CategoryKey | null,
  rooms: ConciergeRoom[],
  allNodes: NodeData[],
  dims: CanvasDims,
) {
  const summaryNodes: NodeData[] = [];
  const summaryEdges: { data: Record<string, string>; classes: string }[] = [];
  // We intentionally do NOT spawn a node per-signal.
  // Rendering one bubble per signal causes overlap/visual clutter (as seen in screenshots).
  // Instead we keep a single category bubble (Ghost/Block/Info) and show a count in its label.
  const issueNodes: NodeData[] = [];
  const issueEdges: { data: Record<string, string>; classes: string }[] = [];
  if (!expandedRoomId) return { summaryNodes, summaryEdges, issueNodes, issueEdges };

  const room = rooms.find((candidate) => candidate.room_id === expandedRoomId);
  const roomNode = allNodes.find((candidate) => candidate.data.id === expandedRoomId);
  if (!room || !roomNode) return { summaryNodes, summaryEdges, issueNodes, issueEdges };

  const categories = buildSignalCategories(room);
  if (!categories.length) return { summaryNodes, summaryEdges, issueNodes, issueEdges };

  const centreX = dims.centreX;
  const centreY = dims.centreY;
  const dirX = roomNode.position.x - centreX;
  const dirY = roomNode.position.y - centreY;
  const baseAngle = dirX === 0 && dirY === 0 ? -Math.PI / 2 : Math.atan2(dirY, dirX);
  const roomDiameter = sizeFromSignalCount(room.signal_count);
  const roomRadius = roomDiameter / 2;
  const childDistance = Math.max(roomRadius + 70, 90);
  const spread = categories.length > 1 ? Math.min(Math.PI / 2, categories.length * 0.25) : 0;
  const startAngle = baseAngle - spread / 2;

  categories.forEach((category, index) => {
    const angle =
      categories.length > 1
        ? startAngle + (index / (categories.length - 1)) * spread
        : baseAngle;

    const categoryNodeId = `summary-${room.room_id}-${category.key}`;
    const categoryPosition = {
      x: roomNode.position.x + childDistance * Math.cos(angle),
      y: roomNode.position.y + childDistance * Math.sin(angle),
    };
    const categoryLabel = category.label;
    const categorySize = Math.max(46, 44 + Math.min(22, category.signals.length * 2));

    summaryNodes.push({
      data: {
        id: categoryNodeId,
        label: categoryLabel,
        node_type: "category",
        category_key: category.key,
        highest_severity: category.severity,
        offset_x: categoryPosition.x - roomNode.position.x,
        offset_y: categoryPosition.y - roomNode.position.y,
        node_size: categorySize,
        signal_ids: category.signals.map((s) => s.id),
        _room: room,
      },
      position: categoryPosition,
      classes: "category",
    });

    summaryEdges.push({
      data: {
        id: `summary-edge-${room.room_id}-${category.key}`,
        source: room.room_id,
        target: categoryNodeId,
      },
      classes: "summary-edge",
    });

    // No per-signal nodes.
    // Clicking the category bubble should navigate to the most relevant signal in that category.
    void expandedCategoryKey;
  });

  return { summaryNodes, summaryEdges, issueNodes, issueEdges };
}

// eslint-disable-next-line @typescript-eslint/no-explicit-any
function getCyStylesheet(): any[] {
  return [
    {
      selector: "node",
      style: {
        label: "data(label)",
        "font-family": "'DM Mono', 'JetBrains Mono', monospace",
        "font-size": 8,
        color: "var(--color-sentinel-text-secondary)",
        "text-valign": "bottom",
        "text-halign": "center",
        "text-margin-y": 8,
        "min-zoomed-font-size": 6,
      },
    },
    {
      selector: "node.room",
      style: {
        shape: "ellipse",
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        width: (ele: any) => sizeFromSignalCount(ele.data("signal_count")),
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        height: (ele: any) => sizeFromSignalCount(ele.data("signal_count")),
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        "background-color": (ele: any) => bgFromSeverity(ele.data("highest_severity")),
        "border-width": 2,
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        "border-color": (ele: any) => colorFromSeverity(ele.data("highest_severity")),
        "text-valign": "center",
        "text-halign": "center",
        "text-wrap": "wrap",
        // Keep labels constrained to the circle diameter so they don't explode visually.
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        "text-max-width": (ele: any) => Math.max(34, sizeFromSignalCount(ele.data("signal_count")) * 0.78),
        "text-margin-y": 0,
        "font-weight": 700,
        "z-index": 5,
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        "shadow-blur": (ele: any) => 8 + ele.data("urgency_score") * 20,
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        "shadow-color": (ele: any) => colorFromSeverity(ele.data("highest_severity")),
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        "shadow-opacity": (ele: any) => glowOpacity(ele.data("urgency_score")),
        "shadow-offset-x": 0, "shadow-offset-y": 0,
        color: "var(--color-sentinel-text-primary)",
      },
    },
    {
      selector: "node.root",
      style: {
        shape: "round-rectangle",
        width: 96,
        height: 48,
        "background-color": "var(--color-sentinel-bg-panel)",
        "border-width": 1.5,
        "border-color": "var(--color-sentinel-border)",
        color: "var(--color-sentinel-text-primary)",
        "font-size": 10,
        "font-weight": 600,
        "text-valign": "center",
        "text-halign": "center",
        "text-margin-y": 0,
        "z-index": 25,
      },
    },
    {
      selector: "node.category",
      style: {
        shape: "ellipse",
        width: (ele: any) => Number(ele.data("node_size") || 44),
        height: (ele: any) => Number(ele.data("node_size") || 44),
        "background-color": "var(--color-sentinel-bg-panel)",
        "border-width": 2,
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        "border-color": (ele: any) => colorFromSeverity(ele.data("highest_severity")),
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        "shadow-color": (ele: any) => colorFromSeverity(ele.data("highest_severity")),
        "shadow-blur": 12,
        "shadow-opacity": 0.28,
        "shadow-offset-x": 0,
        "shadow-offset-y": 0,
        color: "var(--color-sentinel-text-primary)",
        "font-size": 10,
        "font-weight": 600,
        "text-max-width": 70,
        "text-wrap": "wrap",
        "text-margin-y": 0,
        "text-valign": "center",
        "text-halign": "center",
        "z-index": 16,
      },
    },
    {
      selector: "node.signal",
      style: {
        shape: "ellipse",
        width: (ele: any) => Number(ele.data("node_size") || 26),
        height: (ele: any) => Number(ele.data("node_size") || 26),
        "background-color": "var(--color-sentinel-bg-panel)",
        "border-width": 2,
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        "border-color": (ele: any) => colorFromSeverity(ele.data("highest_severity")),
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        "shadow-color": (ele: any) => colorFromSeverity(ele.data("highest_severity")),
        "shadow-blur": 14,
        "shadow-opacity": 0.35,
        "shadow-offset-x": 0,
        "shadow-offset-y": 0,
        color: "var(--color-sentinel-text-secondary)",
        "font-size": 8,
        "text-max-width": 56,
        "text-wrap": "wrap",
        "text-margin-y": 0,
        "z-index": 18,
      },
    },
    {
      selector: "edge.room-edge",
      style: {
        width: 1.5,
        opacity: 0.5,
        "line-color": "var(--color-sentinel-border)",
        "curve-style": "straight",
        "z-index": 8,
      },
    },
    {
      selector: "edge.summary-edge",
      style: {
        width: 1.5,
        opacity: 0.6,
        "line-color": "var(--color-sentinel-border)",
        "curve-style": "straight",
        "z-index": 10,
      },
    },
    {
      selector: "edge.signal-edge",
      style: {
        width: 1.5,
        opacity: 0.7,
        "line-color": "var(--color-sentinel-border)",
        "curve-style": "straight",
        "z-index": 12,
      },
    },
  ];
}

// ---- Loading / Error / Empty states ----

function MapPlaceholder({ children }: { children: React.ReactNode }) {
  return (
    <div className="h-full flex items-center justify-center" style={{ background: "var(--color-sentinel-bg-canvas)" }}>
      {children}
    </div>
  );
}

function EmptyConciergeMindMap() {
  const roomNodes = [
    { label: "Room Registry", top: "18%", left: "50%" },
    { label: "Meeting Rooms", top: "50%", left: "18%" },
    { label: "Occupancy", top: "50%", left: "82%" },
    { label: "Bookings", top: "82%", left: "50%" },
  ];

  return (
    <div className="relative h-full w-full overflow-hidden" style={{ background: "var(--color-sentinel-bg-canvas)" }}>
      <div className="absolute inset-0 opacity-30" style={{ backgroundImage: "radial-gradient(circle at center, rgba(255,255,255,0.05) 0, rgba(255,255,255,0.01) 45%, transparent 70%)" }} />

      <div className="absolute left-1/2 top-1/2 h-px w-[58%] -translate-x-1/2 -translate-y-1/2" style={{ background: "var(--color-sentinel-border)" }} />
      <div className="absolute left-1/2 top-1/2 h-[58%] w-px -translate-x-1/2 -translate-y-1/2" style={{ background: "var(--color-sentinel-border)" }} />

      <div
        className="absolute left-1/2 top-1/2 flex h-24 w-24 -translate-x-1/2 -translate-y-1/2 items-center justify-center rounded-xl text-center"
        style={{
          background: "var(--color-sentinel-bg-panel)",
          border: "1px solid var(--color-sentinel-border)",
          color: "var(--color-sentinel-text-primary)",
          boxShadow: "0 0 24px rgba(59,130,246,0.14)",
        }}
      >
        <div>
          <div className="text-[11px] font-semibold">Meeting</div>
          <div className="text-[11px] font-semibold">Rooms</div>
        </div>
      </div>

      {roomNodes.map((node) => (
        <div
          key={node.label}
          className="absolute flex h-16 w-16 -translate-x-1/2 -translate-y-1/2 items-center justify-center rounded-full text-center"
          style={{
            top: node.top,
            left: node.left,
            background: "rgba(148, 163, 184, 0.08)",
            border: "1px solid rgba(148, 163, 184, 0.25)",
            color: "var(--color-sentinel-text-secondary)",
          }}
        >
          <span className="px-2 text-[10px] font-medium leading-tight">{node.label}</span>
        </div>
      ))}

      <div className="absolute left-4 top-4 pointer-events-none">
        <div
          className="rounded-md px-3 py-2"
          style={{
            background: "rgba(15, 23, 42, 0.82)",
            border: "1px solid var(--color-sentinel-border)",
            backdropFilter: "blur(6px)",
          }}
        >
          <p className="text-[11px] font-medium" style={{ color: "var(--color-sentinel-text-primary)" }}>
            No active room signals
          </p>
          <p className="text-[10px]" style={{ color: "var(--color-sentinel-text-secondary)" }}>
            The mind map stays visible while SENTINEL waits for room registry or signal activity.
          </p>
        </div>
      </div>
    </div>
  );
}

// ---- Cytoscape hook ----

function useConciergeGraph(
  containerRef: React.RefObject<HTMLDivElement | null>,
  siteId: string,
  rooms: ConciergeRoom[],
  expandedRoomId: string | null,
  expandedCategoryKey: CategoryKey | null,
  roomPositions: RoomPositions,
  onRoomPositionChange: (roomId: string, position: Point) => void,
  onRoomToggle: (room: ConciergeRoom) => void,
  onCategoryToggle: (room: ConciergeRoom, categoryKey: CategoryKey) => void,
  onSignalSelect: (room: ConciergeRoom, signalId: string) => void,
  onSignalResolved: () => void,
) {
  const cyRef = useRef<Core | null>(null);
  const [containerReady, setContainerReady] = useState(false);

  // Initialize containerReady once the DOM is ready
  useEffect(() => {
    const el = containerRef.current;
    if (el) setContainerReady(true);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Watch for container resize so we re-init when layout settles
  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    const ro = new ResizeObserver(() => {
      if (containerReady && el.clientWidth > 0 && el.clientHeight > 0) {
        setContainerReady((v) => !v);
        setContainerReady((v) => !v);
      }
    });
    ro.observe(el);
    return () => ro.disconnect();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [containerReady]);

  useEffect(() => {
    if (!containerReady || !containerRef.current || rooms.length === 0) return;
    const el = containerRef.current;
    const w = el.clientWidth;
    const h = el.clientHeight;
    // If container has no real dimensions yet, defer until it does
    if (w === 0 || h === 0) return;
    const dims: CanvasDims = { centreX: w / 2, centreY: h / 2, maxRadius: Math.min(w, h) / 2 - 60 };

    const centreNode = buildCentreNode(dims);
    const nodes = buildRoomNodes(rooms, roomPositions, dims);
    const roomEdges = buildRoomEdges(rooms);
    const { summaryNodes, summaryEdges, issueNodes, issueEdges } = buildChildElements(
      expandedRoomId,
      expandedCategoryKey,
      rooms,
      nodes,
      dims,
    );

    if (cyRef.current) cyRef.current.destroy();

    const cy = cytoscape({
      container: el,
      elements: [
        { group: "nodes" as const, ...centreNode },
        ...nodes.map((n) => ({ group: "nodes" as const, ...n })),
        ...summaryNodes.map((n) => ({ group: "nodes" as const, ...n })),
        ...issueNodes.map((n) => ({ group: "nodes" as const, ...n })),
        ...roomEdges.map((e) => ({ group: "edges" as const, ...e })),
        ...summaryEdges.map((e) => ({ group: "edges" as const, ...e })),
        ...issueEdges.map((e) => ({ group: "edges" as const, ...e })),
      ],
      style: getCyStylesheet(),
      layout: { name: "preset" },
      userZoomingEnabled: true,
      userPanningEnabled: true,
      boxSelectionEnabled: false,
      minZoom: 0.3,
      maxZoom: 3,
    });
    cyRef.current = cy;

    const adjustRoomLabelSizes = () => {
      cy.nodes("node.room").forEach((node) => {
        const size = node.width();
        // Keep labels inside the circle; avoid explosive scaling on large viewports.
        const fontSize = Math.min(14, Math.max(8, size * 0.22));
        node.style("font-size", `${fontSize}px`);
      });
    };

    adjustRoomLabelSizes();
    cy.on("layoutstop", adjustRoomLabelSizes);

    cy.on("tap", "node.room", (evt) => {
      const rd = evt.target.data("_room") as ConciergeRoom | undefined;
      if (!rd) return;

      // First tap expands the room context; second tap drills into top signal.
      if (expandedRoomId === rd.room_id) {
        const primarySignalId = pickPrimarySignalId(rd);
        if (primarySignalId) {
          onSignalSelect(rd, primarySignalId);
          return;
        }
      }

      onRoomToggle(rd);
    });
    cy.on("tap", "node.category", (evt) => {
      const room = evt.target.data("_room") as ConciergeRoom | undefined;
      const categoryKey = evt.target.data("category_key") as CategoryKey | undefined;
      if (!room || !categoryKey) return;

      // Prefer opening the highest-priority signal in this category instead of expanding
      // multiple overlapping per-signal nodes.
      const signalIds = (evt.target.data("signal_ids") as string[] | undefined) || [];
      if (signalIds.length > 0) {
        onSignalSelect(room, signalIds[0]);
        return;
      }

      // Fallback (no signals) — just toggle selection state.
      onCategoryToggle(room, categoryKey);
    });
    cy.on("drag", "node.room", (evt) => {
      const roomNode = evt.target;
      const roomId = roomNode.id();
      const anchor = roomNode.position();

      cy.nodes('[node_type = "category"]').forEach((node) => {
        const room = node.data("_room") as ConciergeRoom | undefined;
        if (!room || room.room_id !== roomId) return;

        const dx = Number(node.data("offset_x") || 0);
        const dy = Number(node.data("offset_y") || 0);
        node.position({ x: anchor.x + dx, y: anchor.y + dy });
      });

      cy.nodes('[node_type = "signal"]').forEach((node) => {
        const room = node.data("_room") as ConciergeRoom | undefined;
        if (!room || room.room_id !== roomId) return;

        const dx = Number(node.data("offset_x") || 0);
        const dy = Number(node.data("offset_y") || 0);
        node.position({ x: anchor.x + dx, y: anchor.y + dy });
      });

      adjustRoomLabelSizes();
    });
    cy.on("dragfree", "node.room", (evt) => {
      const roomNode = evt.target;
      onRoomPositionChange(roomNode.id(), roomNode.position());
    });
    cy.on("dragfree", "node.category", async (evt) => {
      const categoryNode = evt.target;
      const categoryPosition = categoryNode.position();
      const room = categoryNode.data("_room") as ConciergeRoom | undefined;
      const signalIds = (categoryNode.data("signal_ids") as string[] | undefined) || [];
      if (!room || signalIds.length === 0) return;

      const roomNode = cy.getElementById(room.room_id);
      const revert = () => {
        if (!roomNode.length) return;
        const anchor = roomNode.position();
        const dx = Number(categoryNode.data("offset_x") || 0);
        const dy = Number(categoryNode.data("offset_y") || 0);
        categoryNode.animate({ position: { x: anchor.x + dx, y: anchor.y + dy } }, { duration: 180 });
      };

      // Drop inside the room circle = resolve this category's signals.
      if (roomNode.length) {
        const roomPosition = roomNode.position();
        const dx = categoryPosition.x - roomPosition.x;
        const dy = categoryPosition.y - roomPosition.y;
        const distance = Math.sqrt(dx * dx + dy * dy);
        const roomDiameter = roomNode.width() || sizeFromSignalCount(room.signal_count);
        const captureRadius = roomDiameter / 2 + 12;
        if (distance <= captureRadius) {
          try {
            await Promise.all(
              signalIds.map((id) => conciergeApi.resolveSignal(siteId, room.room_id, id, "resolved", "Resolved via drag-to-room")),
            );
            categoryNode.animate(
              { style: { opacity: 0, "border-color": "var(--color-sentinel-green)" } },
              {
                duration: 220,
                complete: () => {
                  categoryNode.remove();
                  onSignalResolved();
                },
              },
            );
            return;
          } catch {
            revert();
            return;
          }
        }
      }

      // Drop near the centre root = resolve as well.
      const root = cy.getElementById("meeting-rooms-root");
      if (root.length) {
        const rootPosition = root.position();
        const dxRoot = categoryPosition.x - rootPosition.x;
        const dyRoot = categoryPosition.y - rootPosition.y;
        const distanceToRoot = Math.sqrt(dxRoot * dxRoot + dyRoot * dyRoot);
        const resolutionRadius = 56;
        if (distanceToRoot <= resolutionRadius) {
          try {
            await Promise.all(
              signalIds.map((id) => conciergeApi.resolveSignal(siteId, room.room_id, id, "resolved", "Resolved via drag-to-root")),
            );
            categoryNode.remove();
            onSignalResolved();
            return;
          } catch {
            revert();
            return;
          }
        }
      }

      // Otherwise snap back to its orbit position.
      revert();
    });
    cy.on("mouseover", "node.room", (evt) => { evt.target.style("border-width", 3); evt.target.style("z-index", 20); });
    cy.on("mouseout", "node.room", (evt) => { evt.target.style("border-width", 2); evt.target.style("z-index", 5); });
    // Category nodes have variable size; avoid overriding width/height on hover.
    cy.fit(undefined, 40);

    return () => { cy.destroy(); cyRef.current = null; };
  }, [
    containerReady,
    siteId,
    rooms,
    expandedRoomId,
    expandedCategoryKey,
    roomPositions,
    onRoomPositionChange,
    onRoomToggle,
    onCategoryToggle,
    onSignalSelect,
    onSignalResolved,
    containerRef,
  ]);
}

// ---- Main component ----

export function ConciergeMap({ siteId, onSignalSelect }: ConciergeMapProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [rooms, setRooms] = useState<ConciergeRoom[]>([]);
  const [expandedRoomId, setExpandedRoomId] = useState<string | null>(null);
  const [expandedCategoryKey, setExpandedCategoryKey] = useState<CategoryKey | null>(null);
  const [roomPositions, setRoomPositions] = useState<RoomPositions>({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const totalSignals = rooms.reduce((sum, room) => sum + room.signal_count, 0);

  const fetchRooms = useCallback(async () => {
    try {
      const data = await conciergeApi.getRooms(siteId);
      setRooms(data.rooms || []);
      setRoomPositions((current) => {
        const next: RoomPositions = {};
        (data.rooms || []).forEach((room) => {
          if (current[room.room_id]) {
            next[room.room_id] = current[room.room_id];
          }
        });
        return next;
      });
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load rooms");
    } finally {
      setLoading(false);
    }
  }, [siteId]);

  useEffect(() => {
    fetchRooms();
    const iv = setInterval(fetchRooms, REFRESH_INTERVAL_MS);
    return () => clearInterval(iv);
  }, [fetchRooms]);

  const handleRoomToggle = useCallback((room: ConciergeRoom) => {
    setExpandedRoomId((current) => {
      const next = current === room.room_id ? null : room.room_id;
      setExpandedCategoryKey(null);
      return next;
    });
  }, []);

  const handleCategoryToggle = useCallback((room: ConciergeRoom, categoryKey: CategoryKey) => {
    setExpandedRoomId(room.room_id);
    setExpandedCategoryKey((current) => (expandedRoomId === room.room_id && current === categoryKey ? null : categoryKey));
  }, [expandedRoomId]);

  const handleRoomPositionChange = useCallback((roomId: string, position: Point) => {
    setRoomPositions((current) => ({ ...current, [roomId]: position }));
  }, []);

  const handleSignalResolved = useCallback(() => {
    void fetchRooms();
    setExpandedRoomId(null);
    setExpandedCategoryKey(null);
  }, [fetchRooms]);

  useConciergeGraph(
    containerRef,
    siteId,
    rooms,
    expandedRoomId,
    expandedCategoryKey,
    roomPositions,
    handleRoomPositionChange,
    handleRoomToggle,
    handleCategoryToggle,
    onSignalSelect,
    handleSignalResolved,
  );

  if (loading) {
    return (
      <MapPlaceholder>
        <div className="text-center">
          <div className="w-8 h-8 border-2 border-blue-500 border-t-transparent rounded-full animate-spin mx-auto mb-3" />
          <p className="text-xs text-gray-500">Loading meeting room signals...</p>
        </div>
      </MapPlaceholder>
    );
  }

  if (error) {
    return (
      <MapPlaceholder>
        <div className="text-center max-w-sm">
          <p className="text-xs text-red-400 mb-2">Failed to load room data</p>
          <p className="text-[10px] text-gray-500">{error}</p>
          <button
            onClick={fetchRooms}
            className="mt-3 px-3 py-1 text-xs rounded border border-gray-700 text-gray-400 hover:text-gray-200 hover:border-gray-500 transition-colors"
          >
            Retry
          </button>
        </div>
      </MapPlaceholder>
    );
  }

  if (rooms.length === 0) {
    return <EmptyConciergeMindMap />;
  }

  return (
    <div className="relative w-full h-full" style={{ background: "var(--color-sentinel-bg-canvas)" }}>
      <div ref={containerRef} className="w-full h-full concierge-cytoscape-map" />

      {totalSignals === 0 && (
        <div className="absolute left-4 top-4 pointer-events-none">
          <div
            className="rounded-md px-3 py-2"
            style={{
              background: "rgba(15, 23, 42, 0.82)",
              border: "1px solid var(--color-sentinel-border)",
              backdropFilter: "blur(6px)",
            }}
          >
            <p className="text-[11px] font-medium" style={{ color: "var(--color-sentinel-text-primary)" }}>
              No active room signals
            </p>
            <p className="text-[10px]" style={{ color: "var(--color-sentinel-text-secondary)" }}>
              The meeting room map stays visible and will light up when new signals arrive.
            </p>
          </div>
        </div>
      )}
    </div>
  );
}
