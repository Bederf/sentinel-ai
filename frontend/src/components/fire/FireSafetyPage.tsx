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
  );
}
