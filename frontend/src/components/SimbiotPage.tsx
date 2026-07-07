/**
 * SIMBIOT Page — Site Connection Wizard + Data Source Control
 *
 * Admin-only page with two sub-tabs:
 * 1. Connection Wizard — onboard new site data sources through SIMBIOT
 * 2. Data Source — local source controls for non-production instances
 */

import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import api, { type Site } from '@/lib/api';
import { BMSConnectionWizard } from "./BMSConnectionWizard";
import { CheckCircle, ExternalLink, Loader2, Plug } from "lucide-react";

type SimbiotTab = "wizard";

export function SimbiotPage() {
  const navigate = useNavigate();
  const [sites, setSites] = useState<Site[]>([]);
  const [selectedSiteId, setSelectedSiteId] = useState<string>("");
  const [wizardKey, setWizardKey] = useState(0);
  const [loading, setLoading] = useState(true);
  const [activeTab, setActiveTab] = useState<SimbiotTab>("wizard");
  const [completedSiteId, setCompletedSiteId] = useState<string | null>(null);

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
  const targetSiteId = new URLSearchParams(window.location.search).get("site_id")
    ?? new URLSearchParams(window.location.search).get("site_code")
    ?? new URLSearchParams(window.location.search).get("siteId")
    ?? "";

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
        {activeTab === "wizard" && completedSiteId ? (
          <div
            className="max-w-3xl mx-auto rounded-lg p-6 space-y-5"
            style={{
              background: "var(--color-sentinel-bg-secondary)",
              border: "1px solid var(--color-sentinel-border)",
            }}
          >
            <div className="flex items-start gap-3">
              <CheckCircle className="w-7 h-7 shrink-0" style={{ color: "var(--color-sentinel-green)" }} />
              <div>
                <h2 className="text-xl font-semibold" style={{ color: "var(--color-sentinel-text-primary)" }}>
                  SIMBIOT onboarding complete
                </h2>
                <p className="mt-1 text-sm" style={{ color: "var(--color-sentinel-text-secondary)" }}>
                  {completedSiteId} is connected in shadow read-only mode. Telemetry onboarding is complete; control, maintenance workflows, and tenant sharing remain gated.
                </p>
              </div>
            </div>

            <div className="grid gap-2 text-sm">
              {[
                "Bridge telemetry boundary recorded",
                "Equipment mappings approved",
                "Control/write tools remain disabled",
                "Tenant key still requires separate admin deployment",
              ].map((item) => (
                <div key={item} className="flex items-center gap-2">
                  <CheckCircle className="w-4 h-4 shrink-0" style={{ color: "var(--color-sentinel-green)" }} />
                  <span style={{ color: "var(--color-sentinel-text-primary)" }}>{item}</span>
                </div>
              ))}
            </div>

            <div className="flex flex-wrap gap-3 pt-2">
              <button
                type="button"
                onClick={() => {
                  navigate(`/buildings/${encodeURIComponent(completedSiteId)}`);
                }}
                className="flex items-center gap-2 px-4 py-2 rounded text-sm font-semibold"
                style={{ background: "var(--color-sentinel-green)", color: "#fff" }}
              >
                Open Site Dashboard
                <ExternalLink className="w-4 h-4" />
              </button>
              <button
                type="button"
                onClick={() => {
                  setCompletedSiteId(null);
                  setWizardKey((k) => k + 1);
                }}
                className="px-4 py-2 rounded text-sm font-medium"
                style={{
                  background: "var(--color-sentinel-bg-primary)",
                  border: "1px solid var(--color-sentinel-border)",
                  color: "var(--color-sentinel-text-primary)",
                }}
              >
                Onboard Another Site
              </button>
            </div>
          </div>
        ) : activeTab === "wizard" && (
          <BMSConnectionWizard
            key={wizardKey}
            siteId=""
            requestedSiteId={targetSiteId}
            sites={sites}
            onClose={() => {
              setCompletedSiteId(null);
              setWizardKey((k) => k + 1);
            }}
            onComplete={(siteId) => {
              setCompletedSiteId(siteId || targetSiteId || selectedSiteId || "site-005");
            }}
          />
        )}

      </div>
    </div>
  );
}
