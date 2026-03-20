/**
 * IssueIntelligence — Operational Intelligence page.
 *
 * Displays cluster graph for the Fairlands acceptance case.
 * Will later integrate with GET /api/clusters/{id}/graph.
 * For now, loads the frozen JSON fixture.
 */

import { useState, useEffect } from "react";
import { ClusterGraph } from "./ClusterGraph";
import type { ClusterGraphData } from "./ClusterGraph";

// Frozen fixture — loaded until signal bridges emit and /api/clusters/{id}/graph is live
import fairlandsFixture from "../../fixtures/fairlands-cluster-graph.json";

export function IssueIntelligence() {
  const [graphData, setGraphData] = useState<ClusterGraphData | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    // Load fixture data immediately — no API call until signal bridges are active.
    // When /api/clusters/{id}/graph is live, replace this with a real fetch.
    setGraphData(fairlandsFixture as unknown as ClusterGraphData);
    setLoading(false);
  }, []);

  if (loading) {
    return (
      <div className="h-full flex items-center justify-center">
        <p className="text-sm" style={{ color: "var(--color-sentinel-text-secondary)" }}>Loading cluster data...</p>
      </div>
    );
  }

  if (!graphData) {
    return (
      <div className="h-full flex items-center justify-center">
        <p className="text-sm" style={{ color: "var(--color-sentinel-text-secondary)" }}>No cluster data available</p>
      </div>
    );
  }

  return (
    <div className="h-full flex flex-col overflow-hidden">
      {/* Cluster status strip */}
      <div
        className="flex items-center justify-between px-5 py-3 flex-shrink-0"
        style={{
          background: "var(--color-sentinel-bg-primary)",
          borderBottom: "1px solid var(--color-sentinel-border)",
        }}
      >
        <div className="flex items-center gap-4">
          <span
            className="text-[10px] uppercase tracking-wider px-2 py-1 rounded"
            style={{
              background: stateColor(graphData.cluster_state).bg,
              border: `1px solid ${stateColor(graphData.cluster_state).border}`,
              color: stateColor(graphData.cluster_state).text,
            }}
          >
            {graphData.cluster_state}
          </span>
          <StatChip label="Signals" value={String(graphData.signal_count)} />
          <StatChip label="Domains" value={String(graphData.domain_count)} />
          <StatChip label="Confidence" value={graphData.confidence.toFixed(2)} />
          <StatChip label="Duration" value={`${graphData.duration_days}d`} />
        </div>

        {/* Title from cluster node */}
        <div className="text-[11px] tracking-wide" style={{ color: "var(--color-sentinel-text-secondary)" }}>
          {graphData.nodes.find((n) => n.node_type === "cluster")?.label || "Issue Cluster"}
          {" — "}
          {(graphData.nodes.find((n) => n.node_type === "cluster")?.metadata as Record<string, unknown>)?.classifications
            ? ((graphData.nodes.find((n) => n.node_type === "cluster")?.metadata as Record<string, unknown>).classifications as Array<{ domain: string }>)?.[0]?.domain?.replace(/_/g, " ")
            : ""}
        </div>
      </div>

      {/* Graph — absolute fill ensures Cytoscape gets real pixel dimensions */}
      <div className="flex-1 min-h-0 relative">
        <div className="absolute inset-0">
          <ClusterGraph data={graphData} />
        </div>
      </div>
    </div>
  );
}

function StatChip({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-center gap-1.5">
      <span className="text-[9px] uppercase tracking-wider" style={{ color: "var(--color-sentinel-text-secondary)" }}>{label}</span>
      <span className="text-xs font-semibold" style={{ color: "var(--color-sentinel-text-primary)" }}>{value}</span>
    </div>
  );
}

function stateColor(state: string): { bg: string; border: string; text: string } {
  switch (state) {
    case "escalated":
      return { bg: "rgba(220, 38, 38, 0.15)", border: "rgba(220, 38, 38, 0.4)", text: "#DC2626" };
    case "active":
      return { bg: "rgba(245, 158, 11, 0.15)", border: "rgba(245, 158, 11, 0.4)", text: "#F59E0B" };
    case "emerging":
      return { bg: "rgba(59, 130, 246, 0.15)", border: "rgba(59, 130, 246, 0.4)", text: "#3B82F6" };
    case "resolved":
      return { bg: "rgba(16, 185, 129, 0.15)", border: "rgba(16, 185, 129, 0.4)", text: "#10B981" };
    default:
      return { bg: "rgba(139, 148, 158, 0.15)", border: "rgba(139, 148, 158, 0.4)", text: "#8B949E" };
  }
}
