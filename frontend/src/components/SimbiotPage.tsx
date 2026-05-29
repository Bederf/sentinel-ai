/**
 * SIMBIOT Page — Site Connection Wizard + Data Source Control
 *
 * Admin-only page with two sub-tabs:
 * 1. Connection Wizard — onboard new site data sources through SIMBIOT
 * 2. Data Source — local source controls for non-production instances
 */

import { useEffect, useState } from "react";
import api, { type Site } from '@/lib/api';
import { BMSConnectionWizard } from "./BMSConnectionWizard";
import { Loader2, Plug } from "lucide-react";

type SimbiotTab = "wizard";

export function SimbiotPage() {
  const [sites, setSites] = useState<Site[]>([]);
  const [selectedSiteId, setSelectedSiteId] = useState<string>("");
  const [wizardKey, setWizardKey] = useState(0);
  const [loading, setLoading] = useState(true);
  const [activeTab, setActiveTab] = useState<SimbiotTab>("wizard");

  useEffect(() => {
    api
      .getSites()
      .then((data) => {
        setSites(data);
        if (data.length > 0) {
          const preferredSite =
            data.find((site) => site.id === "site-002")
            ?? data.find((site) => /sandton city office tower/i.test(site.name))
            ?? data[0];
          setSelectedSiteId(preferredSite.id);
        }
        setLoading(false);
      })
      .catch(() => setLoading(false));
  }, []);

  if (loading) {
    return (
      <div className="h-full flex items-center justify-center">
        <Loader2
          className="w-8 h-8 animate-spin"
          style={{ color: "var(--color-sentinel-text-secondary)" }}
        />
      </div>
    );
  }

  const tabs: { id: SimbiotTab; label: string; icon: typeof Plug }[] = [
    { id: "wizard", label: "Connection Wizard", icon: Plug },
  ];

  return (
    <div
      className="h-full overflow-y-auto"
      style={{ background: "var(--color-sentinel-bg-canvas)" }}
    >
      <div className="p-4 md:p-6 lg:p-8 space-y-6">
        {/* Sub-tab navigation */}
        <div
          className="flex overflow-x-auto scrollbar-hide gap-1 rounded-lg p-1"
          style={{
            background: "var(--color-sentinel-bg-secondary)",
            border: "1px solid var(--color-sentinel-border)",
          }}
        >
          {tabs.map((tab) => {
            const Icon = tab.icon;
            const isActive = activeTab === tab.id;
            return (
              <button
                key={tab.id}
                onClick={() => setActiveTab(tab.id)}
                className="flex items-center gap-2 px-4 py-2 rounded text-sm font-medium transition-colors flex-shrink-0"
                style={{
                  background: isActive ? "var(--color-sentinel-bg-panel)" : "transparent",
                  color: isActive ? "var(--color-sentinel-text-primary)" : "var(--color-sentinel-text-secondary)",
                  border: isActive ? "1px solid var(--color-sentinel-border)" : "1px solid transparent",
                }}
              >
                <Icon className="h-4 w-4" />
                {tab.label}
              </button>
            );
          })}
        </div>

        {/* Tab content */}
        {activeTab === "wizard" && (
          <BMSConnectionWizard
            key={wizardKey}
            siteId=""
            sites={sites}
            onClose={() => setWizardKey((k) => k + 1)}
            onComplete={() => setWizardKey((k) => k + 1)}
          />
        )}

      </div>
    </div>
  );
}
