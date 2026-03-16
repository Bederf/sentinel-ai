/**
 * ConciergeMap — Cytoscape.js gravitational circle mind map.
 *
 * Rooms orbit a centre anchor. Size = signal count, position = urgency
 * (high urgency = close to centre), colour = highest severity.
 *
 * Phase 161-04 — Concierge Intelligence Dashboard.
 */

import { useEffect, useRef, useCallback, useState } from "react";
import cytoscape from "cytoscape";
import type { Core } from "cytoscape";
import type { ConciergeRoom } from "../../lib/api";
import { conciergeApi } from "../../lib/api";

// ---- Severity colour mapping ----

const SEVERITY_COLORS: Record<string, string> = {
  low: "#2ecc71",
  medium: "#f1c40f",
  high: "#e67e22",
  critical: "#e74c3c",
};

const SEVERITY_BG: Record<string, string> = {
  low: "#0d1f15",
  medium: "#1a1800",
  high: "#1f1208",
  critical: "#1f0d0d",
};

// ---- Domain colour chips ----

const DOMAIN_COLORS: Record<string, string> = {
  space_optimisation: "#f4900c",
  email: "#4a9eff",
  hvac: "#e74c3c",
  maintenance: "#f1c40f",
  cleaning: "#1abc9c",
  general: "#8b7fd4",
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

// ---- Props ----

interface ConciergeMapProps {
  siteId: string;
  onRoomSelect: (room: ConciergeRoom) => void;
}

const REFRESH_INTERVAL_MS = 5 * 60 * 1000;

// ---- Element builders (extracted for ESLint max-lines) ----

interface CanvasDims {
  centreX: number;
  centreY: number;
  maxRadius: number;
}

interface NodeData {
  data: Record<string, unknown>;
  position: { x: number; y: number };
  locked?: boolean;
  classes: string;
}

function buildRoomNodes(rooms: ConciergeRoom[], dims: CanvasDims): NodeData[] {
  const { centreX, centreY, maxRadius } = dims;
  const anchor: NodeData = {
    data: {
      id: "__centre__",
      label: "Fairlands",
      node_type: "anchor",
      signal_count: 0,
      highest_severity: "low",
      urgency_score: 0,
    },
    position: { x: centreX, y: centreY },
    locked: true,
    classes: "anchor",
  };
  const roomNodes = rooms.map((room, i) => {
    const distance = maxRadius * (1 - room.urgency_score);
    const angle = (i / rooms.length) * 2 * Math.PI - Math.PI / 2;
    return {
      data: {
        id: room.room_id,
        label: room.friendly_name || room.room_id,
        node_type: "room",
        signal_count: room.signal_count,
        highest_severity: room.highest_severity,
        urgency_score: room.urgency_score,
        domains: room.domains,
        _room: room,
      },
      position: {
        x: centreX + distance * Math.cos(angle),
        y: centreY + distance * Math.sin(angle),
      },
      classes: "room",
    };
  });
  return [anchor, ...roomNodes];
}

function buildChipElements(rooms: ConciergeRoom[], allNodes: NodeData[]) {
  const chipNodes: NodeData[] = [];
  const chipEdges: { data: Record<string, string>; classes: string }[] = [];
  for (const room of rooms) {
    const rn = allNodes.find((n) => n.data.id === room.room_id);
    if (!rn || !room.domains.length) continue;
    const chipR = sizeFromSignalCount(room.signal_count) / 2 + 8;
    const domSlice = room.domains.slice(0, 6);
    domSlice.forEach((domain, di) => {
      const a = (di / domSlice.length) * 2 * Math.PI - Math.PI / 2;
      const cid = `chip-${room.room_id}-${domain}`;
      chipNodes.push({
        data: { id: cid, label: "", node_type: "chip", signal_count: 0, highest_severity: "low", urgency_score: 0, domains: [domain] },
        position: { x: rn.position.x + chipR * Math.cos(a), y: rn.position.y + chipR * Math.sin(a) },
        locked: true,
        classes: "chip",
      });
      chipEdges.push({ data: { id: `ce-${cid}`, source: room.room_id, target: cid }, classes: "chip-edge" });
    });
  }
  return { chipNodes, chipEdges };
}

// eslint-disable-next-line @typescript-eslint/no-explicit-any
function getCyStylesheet(): any[] {
  return [
    {
      selector: "node",
      style: {
        label: "",
        "font-family": "'DM Mono', 'JetBrains Mono', monospace",
        "font-size": 8,
        color: "#a0a0a0",
        "text-valign": "bottom",
        "text-halign": "center",
        "text-margin-y": 8,
        "min-zoomed-font-size": 6,
      },
    },
    {
      selector: "node.anchor",
      style: {
        shape: "hexagon",
        width: 72, height: 72,
        "background-color": "#0d1f3c",
        "border-width": 2.5, "border-color": "#3B82F6",
        label: "data(label)", color: "#e6edf3",
        "font-size": 10, "font-weight": 600,
        "text-valign": "center", "text-halign": "center", "text-margin-y": 0,
        "z-index": 10,
        "shadow-blur": 25, "shadow-color": "#3B82F6", "shadow-opacity": 0.4,
        "shadow-offset-x": 0, "shadow-offset-y": 0,
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
        label: "data(label)",
        "z-index": 5,
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        "shadow-blur": (ele: any) => 8 + ele.data("urgency_score") * 20,
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        "shadow-color": (ele: any) => colorFromSeverity(ele.data("highest_severity")),
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        "shadow-opacity": (ele: any) => glowOpacity(ele.data("urgency_score")),
        "shadow-offset-x": 0, "shadow-offset-y": 0,
      },
    },
    {
      selector: "node.chip",
      style: {
        width: 8, height: 8,
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        "background-color": (ele: any) => DOMAIN_COLORS[ele.data("domains")?.[0]] || "#8b7fd4",
        "border-width": 0, label: "", "z-index": 3,
      },
    },
    {
      selector: "edge.gravity-edge",
      style: { width: 0.5, "line-color": "rgba(59,130,246,0.08)", "line-style": "dotted", "curve-style": "straight" },
    },
    {
      selector: "edge.chip-edge",
      style: { width: 0, opacity: 0, "curve-style": "straight" },
    },
  ];
}

// ---- Loading / Error / Empty states ----

function MapPlaceholder({ children }: { children: React.ReactNode }) {
  return (
    <div className="h-full flex items-center justify-center" style={{ background: "#0d1117" }}>
      {children}
    </div>
  );
}

// ---- Cytoscape hook ----

function useConciergeGraph(
  containerRef: React.RefObject<HTMLDivElement | null>,
  rooms: ConciergeRoom[],
  onRoomSelect: (room: ConciergeRoom) => void,
) {
  const cyRef = useRef<Core | null>(null);

  useEffect(() => {
    if (!containerRef.current || rooms.length === 0) return;
    const el = containerRef.current;
    const w = el.clientWidth || 800;
    const h = el.clientHeight || 600;
    const dims: CanvasDims = { centreX: w / 2, centreY: h / 2, maxRadius: Math.min(w, h) / 2 - 60 };

    const nodes = buildRoomNodes(rooms, dims);
    const gravEdges = rooms.map((r) => ({ data: { id: `e-${r.room_id}`, source: "__centre__", target: r.room_id }, classes: "gravity-edge" }));
    const { chipNodes, chipEdges } = buildChipElements(rooms, nodes);

    if (cyRef.current) cyRef.current.destroy();

    const cy = cytoscape({
      container: el,
      elements: [
        ...nodes.map((n) => ({ group: "nodes" as const, ...n })),
        ...chipNodes.map((n) => ({ group: "nodes" as const, ...n })),
        ...gravEdges.map((e) => ({ group: "edges" as const, ...e })),
        ...chipEdges.map((e) => ({ group: "edges" as const, ...e })),
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

    cy.on("tap", "node.room", (evt) => {
      const rd = evt.target.data("_room") as ConciergeRoom | undefined;
      if (rd) onRoomSelect(rd);
    });
    cy.on("mouseover", "node.room", (evt) => { evt.target.style("border-width", 3); evt.target.style("z-index", 20); });
    cy.on("mouseout", "node.room", (evt) => { evt.target.style("border-width", 2); evt.target.style("z-index", 5); });
    cy.fit(undefined, 40);

    return () => { cy.destroy(); cyRef.current = null; };
  }, [rooms, onRoomSelect, containerRef]);
}

// ---- Main component ----

export function ConciergeMap({ siteId, onRoomSelect }: ConciergeMapProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [rooms, setRooms] = useState<ConciergeRoom[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchRooms = useCallback(async () => {
    try {
      const data = await conciergeApi.getRooms(siteId);
      setRooms(data.rooms || []);
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

  useConciergeGraph(containerRef, rooms, onRoomSelect);

  if (loading) {
    return (
      <MapPlaceholder>
        <div className="text-center">
          <div className="w-8 h-8 border-2 border-blue-500 border-t-transparent rounded-full animate-spin mx-auto mb-3" />
          <p className="text-xs text-gray-500">Loading concierge map...</p>
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
    return (
      <MapPlaceholder>
        <p className="text-xs text-gray-500">No rooms with active signals</p>
      </MapPlaceholder>
    );
  }

  return <div ref={containerRef} className="w-full h-full" style={{ background: "#0d1117" }} />;
}
