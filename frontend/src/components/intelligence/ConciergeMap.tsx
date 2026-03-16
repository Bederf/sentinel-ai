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

// ---- Severity → colour mapping ----

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

// ---- Domain → colour chips ----

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

function colorFromSeverity(severity: string): string {
  return SEVERITY_COLORS[severity] || SEVERITY_COLORS.low;
}

function bgFromSeverity(severity: string): string {
  return SEVERITY_BG[severity] || SEVERITY_BG.low;
}

function glowOpacity(urgency: number): number {
  // 0 urgency = 0.15 glow, 1.0 urgency = 0.7 glow
  return 0.15 + urgency * 0.55;
}

// ---- Props ----

interface ConciergeMapProps {
  siteId: string;
  onRoomSelect: (room: ConciergeRoom) => void;
}

const REFRESH_INTERVAL_MS = 5 * 60 * 1000; // 5 minutes

export function ConciergeMap({ siteId, onRoomSelect }: ConciergeMapProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const cyRef = useRef<Core | null>(null);
  const [rooms, setRooms] = useState<ConciergeRoom[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Fetch rooms
  const fetchRooms = useCallback(async () => {
    try {
      const data = await conciergeApi.getRooms(siteId);
      setRooms(data.rooms || []);
      setError(null);
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Failed to load rooms";
      setError(msg);
    } finally {
      setLoading(false);
    }
  }, [siteId]);

  useEffect(() => {
    fetchRooms();
    const interval = setInterval(fetchRooms, REFRESH_INTERVAL_MS);
    return () => clearInterval(interval);
  }, [fetchRooms]);

  // Build & render Cytoscape graph
  useEffect(() => {
    if (!containerRef.current || rooms.length === 0) return;

    const container = containerRef.current;
    const width = container.clientWidth || 800;
    const height = container.clientHeight || 600;
    const centreX = width / 2;
    const centreY = height / 2;
    const maxRadius = Math.min(width, height) / 2 - 60;

    // Build node elements
    const nodes = [
      // Centre anchor
      {
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
      },
      // Room nodes
      ...rooms.map((room, index) => {
        const distance = maxRadius * (1 - room.urgency_score);
        const angle = (index / rooms.length) * 2 * Math.PI - Math.PI / 2;
        const x = centreX + distance * Math.cos(angle);
        const y = centreY + distance * Math.sin(angle);

        return {
          data: {
            id: room.room_id,
            label: room.friendly_name || room.room_id,
            node_type: "room",
            signal_count: room.signal_count,
            highest_severity: room.highest_severity,
            urgency_score: room.urgency_score,
            domains: room.domains,
            // Store full room data for tap handler
            _room: room,
          },
          position: { x, y },
          classes: "room",
        };
      }),
    ];

    // Build edge elements — connect each room to centre with invisible edge (for layout structure)
    const edges = rooms.map((room) => ({
      data: {
        id: `edge-${room.room_id}`,
        source: "__centre__",
        target: room.room_id,
      },
      classes: "gravity-edge",
    }));

    // Domain chip nodes — small dots around room perimeter
    const chipNodes: typeof nodes = [];
    const chipEdges: typeof edges = [];
    rooms.forEach((room) => {
      const roomNode = nodes.find((n) => n.data.id === room.room_id);
      if (!roomNode || !room.domains.length) return;

      const roomSize = sizeFromSignalCount(room.signal_count);
      const chipRadius = roomSize / 2 + 8;

      room.domains.slice(0, 6).forEach((domain, di) => {
        const chipAngle = (di / Math.min(room.domains.length, 6)) * 2 * Math.PI - Math.PI / 2;
        const chipId = `chip-${room.room_id}-${domain}`;
        chipNodes.push({
          data: {
            id: chipId,
            label: "",
            node_type: "chip",
            signal_count: 0,
            highest_severity: "low",
            urgency_score: 0,
            domains: [domain],
          },
          position: {
            x: roomNode.position.x + chipRadius * Math.cos(chipAngle),
            y: roomNode.position.y + chipRadius * Math.sin(chipAngle),
          },
          locked: true,
          classes: "chip",
        });
        chipEdges.push({
          data: {
            id: `chipedge-${chipId}`,
            source: room.room_id,
            target: chipId,
          },
          classes: "chip-edge",
        });
      });
    });

    // Create or update Cytoscape instance
    if (cyRef.current) {
      cyRef.current.destroy();
    }

    const cy = cytoscape({
      container,
      elements: [
        ...nodes.map((n) => ({ group: "nodes" as const, ...n })),
        ...chipNodes.map((n) => ({ group: "nodes" as const, ...n })),
        ...edges.map((e) => ({ group: "edges" as const, ...e })),
        ...chipEdges.map((e) => ({ group: "edges" as const, ...e })),
      ],
      style: [
        // Base node — hidden label by default
        {
          selector: "node",
          style: {
            label: "",
            "font-family": "'DM Mono', 'JetBrains Mono', monospace",
            "font-size": 8,
            color: "#a0a0a0",
            "text-valign": "bottom" as const,
            "text-halign": "center" as const,
            "text-margin-y": 8,
            "min-zoomed-font-size": 6,
          },
        },
        // Centre anchor — hexagon
        {
          selector: "node.anchor",
          style: {
            shape: "hexagon" as const,
            width: 72,
            height: 72,
            "background-color": "#0d1f3c",
            "border-width": 2.5,
            "border-color": "#3B82F6",
            label: "data(label)",
            color: "#e6edf3",
            "font-size": 10,
            "font-weight": 600,
            "text-valign": "center" as const,
            "text-halign": "center" as const,
            "text-margin-y": 0,
            "z-index": 10,
            "shadow-blur": 25,
            "shadow-color": "#3B82F6",
            "shadow-opacity": 0.4,
            "shadow-offset-x": 0,
            "shadow-offset-y": 0,
          },
        },
        // Room nodes — sized by signal count, coloured by severity
        {
          selector: "node.room",
          style: {
            shape: "ellipse" as const,
            width: (ele: { data: (k: string) => number }) =>
              sizeFromSignalCount(ele.data("signal_count")),
            height: (ele: { data: (k: string) => number }) =>
              sizeFromSignalCount(ele.data("signal_count")),
            "background-color": (ele: { data: (k: string) => string }) =>
              bgFromSeverity(ele.data("highest_severity")),
            "border-width": 2,
            "border-color": (ele: { data: (k: string) => string }) =>
              colorFromSeverity(ele.data("highest_severity")),
            label: "data(label)",
            "z-index": 5,
            "shadow-blur": (ele: { data: (k: string) => number }) =>
              8 + ele.data("urgency_score") * 20,
            "shadow-color": (ele: { data: (k: string) => string }) =>
              colorFromSeverity(ele.data("highest_severity")),
            "shadow-opacity": (ele: { data: (k: string) => number }) =>
              glowOpacity(ele.data("urgency_score")),
            "shadow-offset-x": 0,
            "shadow-offset-y": 0,
          },
        },
        // Domain chip nodes
        {
          selector: "node.chip",
          style: {
            width: 8,
            height: 8,
            "background-color": (ele: { data: (k: string) => string[] }) => {
              const domains = ele.data("domains");
              return DOMAIN_COLORS[domains?.[0]] || "#8b7fd4";
            },
            "border-width": 0,
            label: "",
            "z-index": 3,
          },
        },
        // Gravity edges — invisible structural
        {
          selector: "edge.gravity-edge",
          style: {
            width: 0.5,
            "line-color": "rgba(59, 130, 246, 0.08)",
            "line-style": "dotted" as const,
            "curve-style": "straight" as const,
          },
        },
        // Chip edges — invisible
        {
          selector: "edge.chip-edge",
          style: {
            width: 0,
            opacity: 0,
            "curve-style": "straight" as const,
          },
        },
      ],
      layout: { name: "preset" },
      userZoomingEnabled: true,
      userPanningEnabled: true,
      boxSelectionEnabled: false,
      minZoom: 0.3,
      maxZoom: 3,
    });

    cyRef.current = cy;

    // Tap handler for room nodes
    cy.on("tap", "node.room", (evt) => {
      const roomData = evt.target.data("_room") as ConciergeRoom | undefined;
      if (roomData) {
        onRoomSelect(roomData);
      }
    });

    // Hover highlight — brighten border on hover
    cy.on("mouseover", "node.room", (evt) => {
      evt.target.style("border-width", 3);
      evt.target.style("z-index", 20);
      containerRef.current?.classList.add("cursor-pointer");
    });
    cy.on("mouseout", "node.room", (evt) => {
      evt.target.style("border-width", 2);
      evt.target.style("z-index", 5);
      containerRef.current?.classList.remove("cursor-pointer");
    });

    // Fit to viewport with padding
    cy.fit(undefined, 40);

    return () => {
      cy.destroy();
      cyRef.current = null;
    };
  }, [rooms, onRoomSelect]);

  if (loading) {
    return (
      <div className="h-full flex items-center justify-center" style={{ background: "#0d1117" }}>
        <div className="text-center">
          <div className="w-8 h-8 border-2 border-blue-500 border-t-transparent rounded-full animate-spin mx-auto mb-3" />
          <p className="text-xs text-gray-500">Loading concierge map...</p>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="h-full flex items-center justify-center" style={{ background: "#0d1117" }}>
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
      </div>
    );
  }

  if (rooms.length === 0) {
    return (
      <div className="h-full flex items-center justify-center" style={{ background: "#0d1117" }}>
        <p className="text-xs text-gray-500">No rooms with active signals</p>
      </div>
    );
  }

  return (
    <div
      ref={containerRef}
      className="w-full h-full"
      style={{ background: "#0d1117" }}
    />
  );
}
