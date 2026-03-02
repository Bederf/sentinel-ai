/**
 * Fire Safety Page — Building tab for fire system monitoring
 *
 * Always read-only (no control toggle). Shows fire equipment status,
 * inspection schedules, and NFPA/SABS compliance.
 */

import { Flame } from 'lucide-react';
import { FireEquipmentPanel } from '../compliance/FireEquipmentPanel';
import { SentinelValueCard } from '../SentinelValueCard';

export function FireSafetyPage() {
  return (
    <div className="h-full overflow-y-auto p-4 md:p-6">
      {/* Page Header — matches Lighting tab pattern */}
      <div className="mb-6">
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-3">
            <div className="p-2 rounded" style={{ background: "rgba(239, 68, 68, 0.15)" }}>
              <Flame className="h-6 w-6" style={{ color: "#EF4444" }} />
            </div>
            <div>
              <h1 className="text-2xl font-bold" style={{ color: "var(--color-sentinel-text-primary)" }}>
                Fire Safety
              </h1>
              <p className="text-sm" style={{ color: "var(--color-sentinel-text-secondary)" }}>
                Equipment Compliance &amp; Readiness
              </p>
            </div>
          </div>
        </div>
      </div>

      <div className="space-y-6">
      <SentinelValueCard
        title="Fire Safety Intelligence Impact"
        icon={Flame}
        baseline={{ label: "", value: 0, unit: "incidents" }}
        sentinel={{ label: "", value: 0, unit: "incidents" }}
        savingsPercent={0}
        period="Monthly"
        collecting
      />
      <FireEquipmentPanel siteCode="S002" />
      </div>
    </div>
  );
}
