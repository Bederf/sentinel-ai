// Asset Onboarding Step - Major Mechanical Asset Baseline Eligibility and Seeding
//
// Phase 186 Wave 4: Simbiot Wizard Step 5 - Major Mechanical Asset Onboarding
// Scans major mechanical assets, checks baseline eligibility, and seeds baselines.

import { useState, useEffect } from "react";
import {
  CheckCircle,
  AlertTriangle,
  XCircle,
  Loader2,
  ArrowRight,
  ChevronRight,
  Wrench,
  Activity,
} from "lucide-react";
import { authorizedFetch } from "@/lib/api/client";

export interface AssetOnboardingStepProps {
  siteId: string;
  onComplete: () => void;
  onSkip: () => void;
}

type Phase = "scanning" | "scan_complete" | "seeding" | "done" | "error";

interface EligibilityResult {
  equipment_id: string;
  equipment_code: string;
  equipment_name: string;
  equipment_type: string;
  status: string;
  health_score: number | null;
  telemetry_hours: number | null;
  has_active_alerts: boolean;
  is_anomaly_flagged: boolean;
  has_existing_baseline: boolean;
  eligibility_status: string;
  eligibility_reason: string;
}

interface ScanResponse {
  site_id: string;
  total_equipment: number;
  eligible_count: number;
  results: EligibilityResult[];
}

interface SeedResult {
  equipment_id: string;
  equipment_code: string;
  status: "seeded" | "skipped" | "error";
  baseline_id: string | null;
  message: string;
}

interface SeedResponse {
  site_id: string;
  total_requested: number;
  seeded_count: number;
  skipped_count: number;
  error_count: number;
  results: SeedResult[];
}

// Category grouping for scan results
interface CategoryGroup {
  label: string;
  count: number;
  items: EligibilityResult[];
}

const ELIGIBILITY_CATEGORIES = [
  { key: "eligible", label: "Eligible", color: "var(--color-sentinel-green)" },
  { key: "degraded", label: "Degraded", color: "var(--color-sentinel-amber)" },
  { key: "insufficient_data", label: "Insufficient Data", color: "var(--color-sentinel-text-muted)" },
  { key: "active_fault", label: "Active Fault", color: "var(--color-sentinel-red)" },
  { key: "already_baselined", label: "Already Baselined", color: "var(--color-sentinel-blue)" },
  { key: "not_applicable", label: "Not Applicable", color: "var(--color-sentinel-border)" },
] as const;

function groupByCategory(results: EligibilityResult[]): CategoryGroup[] {
  return ELIGIBILITY_CATEGORIES.map(({ key, label }) => ({
    label,
    count: results.filter((r) => r.eligibility_status === key).length,
    items: results.filter((r) => r.eligibility_status === key),
  })).filter((g) => g.count > 0);
}

export function AssetOnboardingStep({ siteId, onComplete, onSkip }: AssetOnboardingStepProps) {
  const [phase, setPhase] = useState<Phase>("scanning");
  const [scanResults, setScanResults] = useState<ScanResponse | null>(null);
  const [seedResults, setSeedResults] = useState<SeedResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [eligibleToSeed, setEligibleToSeed] = useState<string[]>([]);

  // On mount, scan for baseline eligibility
  useEffect(() => {
    let cancelled = false;
    async function scan() {
      try {
        const response = await authorizedFetch(
          `/api/onboarding/baseline-eligibility?site_id=${encodeURIComponent(siteId)}`
        );
        if (cancelled) return;
        const data: ScanResponse = await response.json();
        setScanResults(data);
        setEligibleToSeed(data.results.filter((r) => r.eligibility_status === "eligible").map((r) => r.equipment_id));
        setPhase("scan_complete");
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : "Failed to scan equipment");
          setPhase("error");
        }
      }
    }
    scan();
    return () => { cancelled = true; };
  }, [siteId]);

  // Handle seeding
  const handleSeed = async () => {
    if (eligibleToSeed.length === 0) return;
    setPhase("seeding");
    try {
      const response = await authorizedFetch("/api/onboarding/seed-baselines", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ site_id: siteId, equipment_ids: eligibleToSeed }),
      });
      const data: SeedResponse = await response.json();
      setSeedResults(data);
      setPhase("done");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to seed baselines");
      setPhase("error");
    }
  };

  // Render scanning phase
  if (phase === "scanning") {
    return (
      <div className="space-y-6">
        <div className="flex items-center justify-center py-12">
          <div className="flex flex-col items-center gap-4">
            <Loader2 className="w-10 h-10 animate-spin" style={{ color: "var(--color-sentinel-blue)" }} />
            <p className="text-sm" style={{ color: "var(--color-sentinel-text-secondary)" }}>
              Scanning major mechanical assets...
            </p>
          </div>
        </div>
      </div>
    );
  }

  // Render error phase
  if (phase === "error") {
    return (
      <div className="space-y-6">
        <div className="flex items-start gap-4 p-4 rounded-lg" style={{ background: "rgba(239,68,68,0.1)", border: "1px solid var(--color-sentinel-red)" }}>
          <XCircle className="w-5 h-5 mt-0.5 flex-shrink-0" style={{ color: "var(--color-sentinel-red)" }} />
          <div>
            <p className="font-medium" style={{ color: "var(--color-sentinel-red)" }}>Scan Failed</p>
            <p className="text-sm mt-1" style={{ color: "var(--color-sentinel-text-secondary)" }}>{error}</p>
          </div>
        </div>
        <div className="flex justify-between">
          <button onClick={onSkip} className="px-4 py-2 rounded text-sm font-medium" style={{ background: "var(--color-sentinel-bg-secondary)", border: "1px solid var(--color-sentinel-border)", color: "var(--color-sentinel-text-primary)" }}>
            Skip
          </button>
          <button onClick={() => setPhase("scanning")} className="px-4 py-2 rounded text-sm font-medium" style={{ background: "var(--color-sentinel-blue)", color: "#fff" }}>
            Retry
          </button>
        </div>
      </div>
    );
  }

  // Render scan complete phase
  if (phase === "scan_complete" && scanResults) {
    const groups = groupByCategory(scanResults.results);
    const eligibleGroup = groups.find((g) => g.label === "Eligible");
    const hasEligible = eligibleGroup && eligibleGroup.count > 0;

    return (
      <div className="space-y-6">
        {/* Header */}
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-full flex items-center justify-center" style={{ background: "var(--color-sentinel-blue)", color: "#fff" }}>
            <Activity className="w-5 h-5" />
          </div>
          <div>
            <h3 className="font-semibold" style={{ color: "var(--color-sentinel-text-primary)" }}>Major Mechanical Assets</h3>
            <p className="text-sm" style={{ color: "var(--color-sentinel-text-secondary)" }}>
              {scanResults.total_equipment} equipment scanned &middot; {eligibleGroup?.count || 0} eligible for baseline
            </p>
          </div>
        </div>

        {/* Category list */}
        <div className="space-y-3">
          {groups.map((group) => {
            const catDef = ELIGIBILITY_CATEGORIES.find((c) => c.label === group.label);
            return (
              <div key={group.label} className="rounded-lg border" style={{ borderColor: "var(--color-sentinel-border)", background: "var(--color-sentinel-bg-secondary)" }}>
                <div className="flex items-center justify-between px-4 py-3">
                  <div className="flex items-center gap-2">
                    <div className="w-2 h-2 rounded-full" style={{ background: catDef?.color || "var(--color-sentinel-border)" }} />
                    <span className="text-sm font-medium" style={{ color: "var(--color-sentinel-text-primary)" }}>{group.label}</span>
                  </div>
                  <span className="text-sm font-semibold" style={{ color: "var(--color-sentinel-text-secondary)" }}>{group.count}</span>
                </div>
                {group.items.slice(0, 3).map((item) => (
                  <div key={item.equipment_id} className="px-4 py-2 text-xs" style={{ borderTop: "1px solid var(--color-sentinel-border)" }}>
                    <span style={{ color: "var(--color-sentinel-text-primary)" }}>{item.equipment_name}</span>
                    <span className="mx-2" style={{ color: "var(--color-sentinel-text-muted)" }}>&middot;</span>
                    <span style={{ color: "var(--color-sentinel-text-muted)" }}>{item.equipment_type}</span>
                    <span className="mx-2" style={{ color: "var(--color-sentinel-text-muted)" }}>&middot;</span>
                    <span style={{ color: "var(--color-sentinel-text-muted)" }}>{item.eligibility_reason}</span>
                  </div>
                ))}
                {group.items.length > 3 && (
                  <div className="px-4 py-2 text-xs" style={{ borderTop: "1px solid var(--color-sentinel-border)", color: "var(--color-sentinel-text-muted)" }}>
                    +{group.items.length - 3} more
                  </div>
                )}
              </div>
            );
          })}
        </div>

        {/* Empty state */}
        {!hasEligible && scanResults.total_equipment === 0 && (
          <div className="flex flex-col items-center py-8 text-center">
            <Wrench className="w-8 h-8 mb-3" style={{ color: "var(--color-sentinel-text-muted)" }} />
            <p className="text-sm font-medium" style={{ color: "var(--color-sentinel-text-secondary)" }}>No Major Mechanical Assets Found</p>
            <p className="text-xs mt-1" style={{ color: "var(--color-sentinel-text-muted)" }}>
              No AHU, chiller, cooling tower, pump, BESS, or generator equipment detected at this site.
            </p>
          </div>
        )}

        {/* Actions */}
        <div className="flex justify-between pt-2">
          <button onClick={onSkip} className="px-4 py-2 rounded text-sm font-medium" style={{ background: "var(--color-sentinel-bg-secondary)", border: "1px solid var(--color-sentinel-border)", color: "var(--color-sentinel-text-primary)" }}>
            Skip
          </button>
          {hasEligible && (
            <button onClick={handleSeed} className="flex items-center gap-2 px-4 py-2 rounded text-sm font-medium" style={{ background: "var(--color-sentinel-green)", color: "#fff" }}>
              Seed Baselines ({eligibleGroup.count})
              <ArrowRight className="w-4 h-4" />
            </button>
          )}
        </div>
      </div>
    );
  }

  // Render seeding phase
  if (phase === "seeding") {
    return (
      <div className="space-y-6">
        <div className="flex flex-col items-center py-12 gap-4">
          <Loader2 className="w-10 h-10 animate-spin" style={{ color: "var(--color-sentinel-blue)" }} />
          <div className="text-center">
            <p className="font-medium" style={{ color: "var(--color-sentinel-text-primary)" }}>Seeding Baselines</p>
            <p className="text-sm mt-1" style={{ color: "var(--color-sentinel-text-secondary)" }}>
              Creating initial baselines for {eligibleToSeed.length} equipment...
            </p>
          </div>
        </div>
      </div>
    );
  }

  // Render done phase
  if (phase === "done" && seedResults) {
    const hasErrors = seedResults.error_count > 0;
    return (
      <div className="space-y-6">
        {/* Summary */}
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-full flex items-center justify-center" style={{ background: hasErrors ? "var(--color-sentinel-amber)" : "var(--color-sentinel-green)", color: "#fff" }}>
            {hasErrors ? <AlertTriangle className="w-5 h-5" /> : <CheckCircle className="w-5 h-5" />}
          </div>
          <div>
            <h3 className="font-semibold" style={{ color: "var(--color-sentinel-text-primary)" }}>Baseline Seeding Complete</h3>
            <p className="text-sm" style={{ color: "var(--color-sentinel-text-secondary)" }}>
              {seedResults.seeded_count} seeded &middot; {seedResults.skipped_count} skipped &middot; {seedResults.error_count} errors
            </p>
          </div>
        </div>

        {/* Result list */}
        <div className="space-y-2 max-h-64 overflow-y-auto">
          {seedResults.results.map((result) => (
            <div key={result.equipment_id} className="flex items-center gap-3 px-4 py-2 rounded" style={{ background: "var(--color-sentinel-bg-secondary)", border: "1px solid var(--color-sentinel-border)" }}>
              {result.status === "seeded" && <CheckCircle className="w-4 h-4 flex-shrink-0" style={{ color: "var(--color-sentinel-green)" }} />}
              {result.status === "skipped" && <ChevronRight className="w-4 h-4 flex-shrink-0" style={{ color: "var(--color-sentinel-text-muted)" }} />}
              {result.status === "error" && <XCircle className="w-4 h-4 flex-shrink-0" style={{ color: "var(--color-sentinel-red)" }} />}
              <div className="flex-1 min-w-0">
                <p className="text-sm font-medium truncate" style={{ color: "var(--color-sentinel-text-primary)" }}>
                  {result.equipment_code || result.equipment_id}
                </p>
                <p className="text-xs truncate" style={{ color: "var(--color-sentinel-text-muted)" }}>{result.message}</p>
              </div>
              <span className="text-xs font-medium" style={{ color: result.status === "seeded" ? "var(--color-sentinel-green)" : result.status === "error" ? "var(--color-sentinel-red)" : "var(--color-sentinel-text-muted)" }}>
                {result.status}
              </span>
            </div>
          ))}
        </div>

        {/* Error warning */}
        {hasErrors && (
          <div className="flex items-start gap-3 p-3 rounded-lg" style={{ background: "rgba(245,158,11,0.1)", border: "1px solid var(--color-sentinel-amber)" }}>
            <AlertTriangle className="w-4 h-4 mt-0.5 flex-shrink-0" style={{ color: "var(--color-sentinel-amber)" }} />
            <p className="text-sm" style={{ color: "var(--color-sentinel-text-secondary)" }}>
              {seedResults.error_count} equipment failed to seed. You can retry or continue with partial coverage.
            </p>
          </div>
        )}

        {/* Actions */}
        <div className="flex justify-between">
          <button onClick={onSkip} className="px-4 py-2 rounded text-sm font-medium" style={{ background: "var(--color-sentinel-bg-secondary)", border: "1px solid var(--color-sentinel-border)", color: "var(--color-sentinel-text-primary)" }}>
            Skip
          </button>
          <div className="flex gap-2">
            {hasErrors && (
              <button onClick={handleSeed} className="px-4 py-2 rounded text-sm font-medium" style={{ background: "var(--color-sentinel-bg-secondary)", border: "1px solid var(--color-sentinel-border)", color: "var(--color-sentinel-text-primary)" }}>
                Retry Failed
              </button>
            )}
            <button onClick={onComplete} className="flex items-center gap-2 px-4 py-2 rounded text-sm font-medium" style={{ background: "var(--color-sentinel-blue)", color: "#fff" }}>
              Complete Onboarding
              <ArrowRight className="w-4 h-4" />
            </button>
          </div>
        </div>
      </div>
    );
  }

  return null;
}