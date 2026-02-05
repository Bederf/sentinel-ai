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
    <div
      className="h-full overflow-y-auto"
      style={{ background: "var(--color-sentinel-bg-canvas)" }}
    >
      <div className="p-4 md:p-6 lg:p-8">
        <BMSConnectionWizard
          key={wizardKey}
          siteId={selectedSiteId}
          sites={sites}
          onClose={() => setWizardKey((k) => k + 1)}
          onComplete={() => setWizardKey((k) => k + 1)}
        />
      </div>
    </div>
  );
}
