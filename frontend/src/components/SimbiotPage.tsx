import { useEffect, useState } from "react";
import api, { type Site } from "../lib/api";
import { BMSConnectionWizard } from "./BMSConnectionWizard";
import { Loader2 } from "lucide-react";

export function SimbiotPage() {
  const [sites, setSites] = useState<Site[]>([]);
  const [selectedSiteId, setSelectedSiteId] = useState<string>("");
  const [wizardKey, setWizardKey] = useState(0);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api
      .getSites()
      .then((data) => {
        setSites(data);
        if (data.length > 0) setSelectedSiteId(data[0].id);
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

  return (
    <div className="h-full overflow-y-auto flex items-center justify-center p-4 md:p-6">
      <div
        className="w-full max-w-4xl rounded-lg"
        style={{
          background: "var(--color-sentinel-bg-panel)",
          border: "1px solid var(--color-sentinel-border)",
        }}
      >
        <div className="p-6">
          <BMSConnectionWizard
            key={wizardKey}
            siteId={selectedSiteId}
            sites={sites}
            onClose={() => setWizardKey((k) => k + 1)}
            onComplete={() => setWizardKey((k) => k + 1)}
          />
        </div>
      </div>
    </div>
  );
}
