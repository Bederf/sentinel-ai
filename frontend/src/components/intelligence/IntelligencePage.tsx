/**
 * IntelligencePage — Tab container for intelligence sub-views.
 *
 * Tabs: "Issue Clusters" (existing ClusterGraph) | "Concierge Map" (new).
 *
 * Phase 161-04 — Concierge Intelligence Dashboard.
 */

import { useState } from "react";
import { IssueIntelligence } from "./IssueIntelligence";
import { ConciergeDashboardPage } from "./ConciergeDashboardPage";

type IntelligenceTab = "clusters" | "concierge";

const TABS: { id: IntelligenceTab; label: string }[] = [
  { id: "clusters", label: "Issue Clusters" },
  { id: "concierge", label: "Concierge Map" },
];

export function IntelligencePage() {
  const [activeTab, setActiveTab] = useState<IntelligenceTab>("clusters");

  return (
    <div className="h-full flex flex-col overflow-hidden">
      {/* Tab bar */}
      <div
        className="flex items-center gap-1 px-5 flex-shrink-0"
        style={{
          background: "var(--color-sentinel-bg-primary, #0d1117)",
          borderBottom: "1px solid var(--color-sentinel-border, rgba(255,255,255,0.08))",
        }}
      >
        {TABS.map((tab) => (
          <button
            key={tab.id}
            onClick={() => setActiveTab(tab.id)}
            className="px-3 py-2.5 text-xs font-medium transition-colors relative"
            style={{
              color: activeTab === tab.id ? "#e6edf3" : "#8B949E",
            }}
          >
            {tab.label}
            {activeTab === tab.id && (
              <div
                className="absolute bottom-0 left-1 right-1 h-[2px] rounded-full"
                style={{ background: "#3B82F6" }}
              />
            )}
          </button>
        ))}
      </div>

      {/* Active tab content */}
      <div className="flex-1 min-h-0">
        {activeTab === "clusters" ? (
          <IssueIntelligence />
        ) : (
          <ConciergeDashboardPage />
        )}
      </div>
    </div>
  );
}
