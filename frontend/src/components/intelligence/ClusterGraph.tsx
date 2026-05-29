/**
 * ClusterGraph — Cytoscape.js relationship graph for issue clusters.
 *
 * Renders the case map from GET /api/clusters/{id}/graph data.
 * Centre cluster node pinned by default, click opens detail panel,
 * hover highlights neighbourhood.
 *
 * Follows the frozen UI contract from OPERATIONAL_INTELLIGENCE_UI.md.
 */

import { useEffect, useRef, useCallback, useState } from "react";
import cytoscape from "cytoscape";
import type { Core, EventObject, NodeSingular } from "cytoscape";

// ---- Types matching API contract ----

export interface GraphNode {
  id: string;
  node_type: "cluster" | "signal" | "entity";
  signal_type: string | null;
  domain: string;
  label: string;
  severity: string | null;
  confidence: number | null;
  is_collapsed_summary_node: boolean;
  entity_type?: string;
  badge?: string;
  metadata: Record<string, unknown>;
}

export interface GraphEdge {
  id: string;
  source: string;
  target: string;
  edge_type: "evidenced_by" | "affects" | "involves" | "escalated_to" | "related_to" | "owned_by";
  weight: number;
  confidence: number;
  metadata?: Record<string, unknown>;
}

export interface ClusterGraphData {
  cluster_id: string;
  cluster_state: string;
  signal_count: number;
  domain_count: number;
  confidence: number;
  duration_days: number;
  nodes: GraphNode[];
  edges: GraphEdge[];
}

// ---- Domain colours (SENTINEL design system) ----

const DOMAIN_COLORS_RAW: Record<string, string> = {
  cluster: "var(--color-sentinel-blue)",
  email: "var(--color-sentinel-blue)",
  space_optimisation: "var(--color-sentinel-amber)",
  occupancy: "var(--color-sentinel-green)",
  hvac: "var(--color-sentinel-red)",
  maintenance: "var(--color-sentinel-amber)",
  security: "var(--color-sentinel-teal)",
  energy: "var(--color-sentinel-purple)",
  entity: "var(--color-sentinel-purple)",
};

const DOMAIN_LABELS: Record<string, string> = {
  cluster: "Issue Cluster",
  email: "Email Signal",
  space_optimisation: "Space Signal",
  occupancy: "Occupancy Signal",
  hvac: "HVAC Signal",
  maintenance: "Maintenance Signal",
  entity: "Entity",
};

interface ClusterGraphProps {
  data: ClusterGraphData;
  className?: string;
  onNodeSelect?: (node: GraphNode | null) => void;
}

export function ClusterGraph({ data, className = "", onNodeSelect }: ClusterGraphProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const cyRef = useRef<Core | null>(null);
  const [selectedNode, setSelectedNode] = useState<GraphNode | null>(null);

  // Build Cytoscape elements from API data
  const buildElements = useCallback(() => {
    const nodes = data.nodes.map((n) => ({
      data: {
        id: n.id,
        label: n.label,
        node_type: n.node_type,
        domain: n.domain,
        signal_type: n.signal_type,
        severity: n.severity,
        confidence: n.confidence,
        entity_type: n.entity_type || n.metadata?.entity_type,
        badge: n.badge || null,
        is_collapsed_summary_node: n.is_collapsed_summary_node,
        metadata: n.metadata,
      },
      ...(n.node_type === "cluster" ? { position: { x: 0, y: 0 } } : {}),
    }));

    const edges = data.edges.map((e) => ({
      data: {
        id: e.id,
        source: e.source,
        target: e.target,
        edge_type: e.edge_type,
        weight: e.weight,
        confidence: e.confidence,
      },
    }));

    return { nodes, edges };
  }, [data]);

  useEffect(() => {
    if (!containerRef.current) return;

    const elements = buildElements();

    const cy = cytoscape({
      container: containerRef.current,
      elements,
      style: ([
        // Base node
        {
          selector: "node",
          style: {
            label: "data(label)",
            "font-family": "'JetBrains Mono', monospace",
            "font-size": 9,
            color: "#8B949E",
            "text-valign": "bottom",
            "text-halign": "center",
            "text-margin-y": 5,
            "text-wrap": "wrap",
            "text-max-width": 80,
            "min-zoomed-font-size": 6,
          },
        },
        // Cluster node
        {
          selector: 'node[node_type="cluster"]',
          style: {
            shape: "hexagon",
            width: 86,
            height: 86,
            "background-color": "#0d1f3c",
            "border-width": 2.5,
            "border-color": "#3B82F6",
            color: "#e6edf3",
            "font-size": 10,
            "font-weight": 500,
            "text-valign": "center",
            "text-halign": "center",
            "text-margin-y": 0,
            "text-max-width": 70,
            "z-index": 10,
            "shadow-blur": 30,
            "shadow-color": "#3B82F6",
            "shadow-opacity": 0.5,
            "shadow-offset-x": 0,
            "shadow-offset-y": 0,
          },
        },
        // Email signals
        {
          selector: 'node[domain="email"]',
          style: {
            shape: "ellipse",
            width: 48,
            height: 48,
            "background-color": "#0d1520",
            "border-width": 1.8,
            "border-color": "#3B82F6",
            color: "#7aacdd",
          },
        },
        // Space signals
        {
          selector: 'node[domain="space_optimisation"]',
          style: {
            shape: "ellipse",
            width: 52,
            height: 52,
            "background-color": "#1a1000",
            "border-width": 2,
            "border-color": "#F59E0B",
            color: "#d4800c",
          },
        },
        // Occupancy signals
        {
          selector: 'node[domain="occupancy"]',
          style: {
            shape: "ellipse",
            width: 50,
            height: 50,
            "background-color": "#001510",
            "border-width": 2,
            "border-color": "#10B981",
            color: "#10B981",
          },
        },
        // HVAC signals
        {
          selector: 'node[domain="hvac"]',
          style: {
            shape: "ellipse",
            width: 50,
            height: 50,
            "background-color": "#1a0500",
            "border-width": 2,
            "border-color": "#DC2626",
            color: "#DC2626",
          },
        },
        // Maintenance signals
        {
          selector: 'node[domain="maintenance"]',
          style: {
            shape: "ellipse",
            width: 50,
            height: 50,
            "background-color": "#1a1000",
            "border-width": 2,
            "border-color": "#F59E0B",
            color: "#F59E0B",
          },
        },
        // Entity — person
        {
          selector: 'node[entity_type="person"]',
          style: {
            shape: "ellipse",
            width: 36,
            height: 36,
            "background-color": "#100d1f",
            "border-width": 1.5,
            "border-color": "#8B7FD4",
            color: "#8B7FD4",
            "font-size": 8,
          },
        },
        // Entity — room
        {
          selector: 'node[entity_type="room"]',
          style: {
            shape: "round-rectangle",
            width: 62,
            height: 24,
            "background-color": "#050f1a",
            "border-width": 1.5,
            "border-color": "#2980B9",
            color: "#5a9fd4",
            "font-size": 8,
            "text-valign": "center",
            "text-margin-y": 0,
          },
        },
        // Badge label override
        {
          selector: "node[?badge]",
          style: {
            label: (ele: NodeSingular) => `${ele.data("label")}\n${ele.data("badge")}`,
            "font-size": 8,
            color: "#7a8a9a",
          },
        },
        // Edges — base
        {
          selector: "edge",
          style: {
            "curve-style": "bezier",
            width: 1,
            opacity: 0.6,
            "font-family": "'JetBrains Mono', monospace",
            "font-size": 7,
            color: "#3a4a5a",
            "text-background-color": "#0d1117",
            "text-background-opacity": 0.85,
            "text-background-padding": "2px",
          },
        },
        // evidenced_by
        {
          selector: 'edge[edge_type="evidenced_by"]',
          style: {
            "line-color": "#1a3a5a",
            "target-arrow-color": "#1a3a5a",
            "target-arrow-shape": "triangle",
            width: 1.2,
            opacity: 0.5,
          },
        },
        // affects — always show label
        {
          selector: 'edge[edge_type="affects"]',
          style: {
            "line-color": "#5a3000",
            "target-arrow-color": "#F59E0B",
            "target-arrow-shape": "triangle",
            label: "affects",
            width: 1.8,
            opacity: 0.7,
            color: "#5a3a10",
          },
        },
        // escalated_to — always show label
        {
          selector: 'edge[edge_type="escalated_to"]',
          style: {
            "line-color": "#5a1a10",
            "target-arrow-color": "#DC2626",
            "target-arrow-shape": "triangle",
            "line-style": "dashed",
            "line-dash-pattern": [6, 3] as unknown as string,
            label: "escalated to",
            width: 2,
            opacity: 0.85,
            color: "#8a2a20",
          },
        },
        // owned_by — always show label
        {
          selector: 'edge[edge_type="owned_by"]',
          style: {
            "line-color": "#2a1a4a",
            "target-arrow-color": "#8B7FD4",
            "target-arrow-shape": "triangle",
            label: "owned by",
            width: 2,
            opacity: 0.8,
            color: "#6a5ab4",
          },
        },
        // involves — hover only
        {
          selector: 'edge[edge_type="involves"]',
          style: {
            "line-color": "#2a1a4a",
            "target-arrow-shape": "none",
            width: 1,
            opacity: 0.45,
          },
        },
        // related_to — hover only
        {
          selector: 'edge[edge_type="related_to"]',
          style: {
            "line-color": "#1a2030",
            "target-arrow-shape": "none",
            width: 0.8,
            opacity: 0.3,
            "line-style": "dotted",
          },
        },
        // Hover states
        {
          selector: "node.highlighted",
          style: { "border-width": 3, opacity: 1, "z-index": 5 },
        },
        {
          selector: "node.dimmed",
          style: { opacity: 0.1 },
        },
        {
          selector: "edge.dimmed",
          style: { opacity: 0.05 },
        },
        {
          selector: "edge.highlighted",
          style: { opacity: 1, width: 2.5 },
        },
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      ] as any),
      layout: {
        name: "cose",
        animate: true,
        animationDuration: 900,
        animationEasing: "ease-out-cubic",
        randomize: false,
        componentSpacing: 80,
        nodeRepulsion: () => 6000,
        idealEdgeLength: () => 110,
        edgeElasticity: () => 0.45,
        gravity: 0.25,
        numIter: 2000,
        initialTemp: 1000,
        coolingFactor: 0.99,
        minTemp: 1,
      } as cytoscape.LayoutOptions,
      wheelSensitivity: 0.3,
      boxSelectionEnabled: false,
      userPanningEnabled: true,
      userZoomingEnabled: true,
    });

    cyRef.current = cy;

    // Pin cluster node after layout settles
    setTimeout(() => {
      const clusterNode = cy.nodes('[node_type="cluster"]');
      if (clusterNode.length) clusterNode.lock();
    }, 1000);

    // Hover: highlight neighbourhood
    cy.on("mouseover", "node", (evt: EventObject) => {
      const node = evt.target;
      const neighborhood = node.closedNeighborhood();
      cy.elements().not(neighborhood).addClass("dimmed");
      neighborhood.removeClass("dimmed").addClass("highlighted");
      neighborhood.connectedEdges().addClass("highlighted").removeClass("dimmed");
    });

    cy.on("mouseout", "node", () => {
      cy.elements().removeClass("dimmed highlighted");
    });

    // Click: select node
    cy.on("tap", "node", (evt: EventObject) => {
      const nodeData = evt.target.data() as GraphNode;
      setSelectedNode(nodeData);
      onNodeSelect?.(nodeData);
    });

    cy.on("tap", (evt: EventObject) => {
      if (evt.target === cy) {
        setSelectedNode(null);
        onNodeSelect?.(null);
      }
    });

    return () => {
      cy.destroy();
      cyRef.current = null;
    };
  }, [buildElements, onNodeSelect]);

  const handleFit = useCallback(() => {
    cyRef.current?.fit(undefined, 40);
  }, []);

  const handleZoomIn = useCallback(() => {
    const cy = cyRef.current;
    if (cy) cy.zoom({ level: cy.zoom() * 1.25, renderedPosition: { x: cy.width() / 2, y: cy.height() / 2 } });
  }, []);

  const handleZoomOut = useCallback(() => {
    const cy = cyRef.current;
    if (cy) cy.zoom({ level: cy.zoom() * 0.8, renderedPosition: { x: cy.width() / 2, y: cy.height() / 2 } });
  }, []);

  return (
    <div className={`relative w-full h-full ${className}`}>
      {/* Graph container */}
      <div
        ref={containerRef}
        className="w-full h-full"
        style={{ background: "radial-gradient(ellipse at 50% 40%, #0d1520 0%, var(--color-sentinel-bg-canvas, #0d1117) 65%, #030507 100%)" }}
      />

      {/* Hint */}
      <div
        className="absolute top-3 left-1/2 -translate-x-1/2 text-[9px] pointer-events-none opacity-70"
        style={{ color: "var(--color-sentinel-text-secondary)" }}
      >
        Click any node to inspect · Hover to highlight connections · Scroll to zoom
      </div>

      {/* Legend */}
      <div
        className="absolute bottom-5 left-5 rounded-md p-3 text-[9px]"
        style={{
          background: "rgba(13, 17, 23, 0.92)",
          border: "1px solid var(--color-sentinel-border)",
          backdropFilter: "blur(8px)",
        }}
      >
        <div className="uppercase tracking-widest mb-2" style={{ color: "var(--color-sentinel-text-secondary)" }}>
          Domain
        </div>
        <div className="flex flex-col gap-1.5">
          {[
            { color: "var(--color-sentinel-blue)", label: "Email signal" },
            { color: "var(--color-sentinel-amber)", label: "Space / booking" },
            { color: "var(--color-sentinel-green)", label: "Occupancy" },
            { color: "var(--color-sentinel-red)", label: "HVAC" },
            { color: "var(--color-sentinel-purple)", label: "Person" },
            { color: "var(--color-sentinel-blue)", label: "Room / location" },
          ].map((item) => (
            <div key={item.label} className="flex items-center gap-2" style={{ color: "var(--color-sentinel-text-secondary)" }}>
              <div className="w-2 h-2 rounded-full flex-shrink-0" style={{ background: item.color }} />
              {item.label}
            </div>
          ))}
        </div>
      </div>

      {/* Controls */}
      <div className="absolute bottom-5 right-5 flex flex-col gap-1.5">
        {/* eslint-disable-next-line react-hooks/refs */}
        {[
          { label: "Fit", icon: "\u229E", onClick: handleFit },
          { label: "Zoom in", icon: "+", onClick: handleZoomIn },
          { label: "Zoom out", icon: "\u2212", onClick: handleZoomOut },
        ].map((btn) => (
          <button
            key={btn.label}
            type="button"
            onClick={btn.onClick}
            title={btn.label}
            className="w-8 h-8 flex items-center justify-center rounded text-sm transition-colors"
            style={{
              background: "rgba(13, 17, 23, 0.92)",
              border: "1px solid var(--color-sentinel-border)",
              color: "var(--color-sentinel-text-secondary)",
              backdropFilter: "blur(8px)",
            }}
          >
            {btn.icon}
          </button>
        ))}
      </div>

      {/* Detail panel */}
      {selectedNode && (
        <div
          className="absolute top-0 right-0 h-full w-[300px] flex flex-col overflow-hidden"
          style={{
            background: "var(--color-sentinel-bg-primary, #161b22)",
            borderLeft: "1px solid var(--color-sentinel-border)",
          }}
        >
          <div className="p-3.5 flex items-start justify-between gap-2" style={{ borderBottom: "1px solid var(--color-sentinel-border)" }}>
            <div className="flex-1">
              <span
                className="text-[9px] uppercase tracking-widest px-1.5 py-0.5 rounded inline-block mb-1.5"
                style={{
                  background: `${DOMAIN_COLORS_RAW[selectedNode.domain] || "#3B82F6"}18`,
                  border: `1px solid ${DOMAIN_COLORS_RAW[selectedNode.domain] || "#3B82F6"}44`,
                  color: DOMAIN_COLORS_RAW[selectedNode.domain] || "#3B82F6",
                }}
              >
                {(DOMAIN_LABELS[selectedNode.domain] || selectedNode.domain).toUpperCase()}
              </span>
              <div className="text-[13px] font-semibold" style={{ color: "var(--color-sentinel-text-primary)" }}>
                {selectedNode.label}
              </div>
            </div>
            <button
              type="button"
              onClick={() => { setSelectedNode(null); onNodeSelect?.(null); }}
              className="text-base p-0.5"
              style={{ color: "var(--color-sentinel-text-secondary)" }}
            >
              &#x2715;
            </button>
          </div>
          <div className="flex-1 overflow-y-auto p-3.5">
            <NodeDetail node={selectedNode} />
          </div>
        </div>
      )}
    </div>
  );
}

// ---- Node detail rendering ----

function NodeDetail({ node }: { node: GraphNode }) {
  if (node.node_type === "cluster") return <ClusterDetail node={node} />;
  if (node.node_type === "signal") return <SignalDetail node={node} />;
  return <EntityDetail node={node} />;
}

function MetricRow({ label, value, valueColor }: { label: string; value: string; valueColor?: string }) {
  return (
    <div className="flex justify-between items-center py-1.5 text-[10px]" style={{ borderBottom: "1px solid rgba(30, 45, 61, 0.5)" }}>
      <span style={{ color: "var(--color-sentinel-text-secondary)" }}>{label}</span>
      <span style={{ color: valueColor || "var(--color-sentinel-text-primary)" }}>{value}</span>
    </div>
  );
}

function SectionTitle({ children }: { children: React.ReactNode }) {
  return (
    <div className="text-[9px] uppercase tracking-widest mb-2 mt-4" style={{ color: "var(--color-sentinel-text-secondary)" }}>
      {children}
    </div>
  );
}

function ConfidenceBar({ value, color }: { value: number; color?: string }) {
  return (
    <div className="h-[3px] rounded-full overflow-hidden mt-1" style={{ background: "var(--color-sentinel-border)" }}>
      <div className="h-full w-full origin-left rounded-full transition-transform will-change-transform" style={{ transform: `scaleX(${value})`, background: color || "var(--color-sentinel-blue)" }} />
    </div>
  );
}

function ClusterDetail({ node }: { node: GraphNode }) {
  const m = node.metadata;
  const classifications = (m.classifications as Array<{ domain: string; confidence: number }>) || [];
  const actions = (m.recommended_actions as string[]) || [];

  return (
    <>
      <SectionTitle>Status</SectionTitle>
      <MetricRow label="State" value={String(m.cluster_state)} valueColor="var(--color-sentinel-red)" />
      <MetricRow label="Severity" value={String(node.severity || "unknown")} />
      <MetricRow label="Open for" value={`${m.duration_days} days`} />
      <MetricRow label="Confidence" value={String(node.confidence || 0)} />

      {classifications.length > 0 && (
        <>
          <SectionTitle>Classifications</SectionTitle>
          {classifications.map((c) => (
            <div key={c.domain} className="mb-2">
              <div className="flex justify-between text-[10px] mb-0.5">
                <span style={{ color: "var(--color-sentinel-text-primary)" }}>{c.domain.replace(/_/g, " ")}</span>
                <span style={{ color: "var(--color-sentinel-text-secondary)" }}>{(c.confidence * 100).toFixed(0)}%</span>
              </div>
              <ConfidenceBar value={c.confidence} color={DOMAIN_COLORS_RAW[c.domain]} />
            </div>
          ))}
        </>
      )}

      {m.likely_root_cause && (
        <>
          <SectionTitle>Likely Root Cause</SectionTitle>
          <div className="text-[10px] leading-relaxed" style={{ color: "var(--color-sentinel-text-secondary)" }}>{String(m.likely_root_cause)}</div>
        </>
      )}

      {actions.length > 0 && (
        <>
          <SectionTitle>Recommended Actions</SectionTitle>
          <ul className="list-none">
            {actions.map((a, i) => (
              <li key={i} className="text-[9px] py-1.5 pl-3 relative" style={{ color: "var(--color-sentinel-text-secondary)", borderBottom: "1px solid rgba(30, 45, 61, 0.4)" }}>
                <span className="absolute left-0" style={{ color: "var(--color-sentinel-blue)" }}>&rarr;</span>
                {a}
              </li>
            ))}
          </ul>
          <div
            className="text-[8px] leading-relaxed mt-3 p-2 rounded"
            style={{
              color: "var(--color-sentinel-text-secondary)",
              background: "rgba(59, 130, 246, 0.05)",
              border: "1px solid rgba(59, 130, 246, 0.15)",
            }}
          >
            These actions are advisory. Human decision required before acting on any booking or policy change.
          </div>
        </>
      )}
    </>
  );
}

function SignalDetail({ node }: { node: GraphNode }) {
  const m = node.metadata;
  const evidence = (m.evidence_basis as string[]) || [];
  const color = DOMAIN_COLORS_RAW[node.domain] || "#3B82F6";

  return (
    <>
      <SectionTitle>Signal Details</SectionTitle>
      {m.sender && <MetricRow label="Sender" value={String(m.sender)} />}
      {m.sent_at && <MetricRow label="Date" value={String(m.sent_at)} />}
      <MetricRow label="Type" value={(node.signal_type || "").replace(/_/g, " ")} />
      {m.signal_subtype && <MetricRow label="Subtype" value={String(m.signal_subtype)} />}
      <MetricRow label="Severity" value={String(node.severity || "\u2014")} />
      <MetricRow label="Confidence" value={String(node.confidence || "\u2014")} />
      <ConfidenceBar value={node.confidence || 0} color={color} />

      {m.summary && (
        <>
          <SectionTitle>Summary</SectionTitle>
          <div className="text-[10px] leading-relaxed" style={{ color: "var(--color-sentinel-text-secondary)" }}>{String(m.summary)}</div>
        </>
      )}

      {evidence.length > 0 && (
        <>
          <SectionTitle>Evidence Basis</SectionTitle>
          {evidence.map((e, i) => (
            <div
              key={i}
              className="text-[9px] px-2 py-1 rounded mb-1 flex items-center gap-1.5"
              style={{ background: "var(--color-sentinel-bg-secondary)", color: "var(--color-sentinel-text-secondary)" }}
            >
              <div className="w-[5px] h-[5px] rounded-full flex-shrink-0" style={{ background: color }} />
              {e.replace(/_/g, " ")}
            </div>
          ))}
        </>
      )}
    </>
  );
}

function EntityDetail({ node }: { node: GraphNode }) {
  const m = node.metadata;
  return (
    <>
      <SectionTitle>Entity</SectionTitle>
      <MetricRow label="Type" value={String(node.entity_type || m.entity_type || "unknown")} />
      {m.role && <MetricRow label="Role" value={String(m.role)} />}
      {m.department && <MetricRow label="Department" value={String(m.department)} />}
      {m.location_ref && <MetricRow label="Location" value={String(m.location_ref)} />}
      {m.note && (
        <div
          className="text-[8px] leading-relaxed mt-3 p-2 rounded"
          style={{
            color: "var(--color-sentinel-text-secondary)",
            background: "rgba(59, 130, 246, 0.05)",
            border: "1px solid rgba(59, 130, 246, 0.15)",
          }}
        >
          {String(m.note)}
        </div>
      )}
    </>
  );
}
