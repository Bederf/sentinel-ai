/**
 * Fire Safety Page — Building tab for fire system monitoring
 *
 * Always read-only (no control toggle). Shows fire equipment status,
 * inspection schedules, and NFPA/SABS compliance.
 */

import { FireEquipmentPanel } from '../compliance/FireEquipmentPanel';

export function FireSafetyPage() {
  return (
    <div className="space-y-6">
      <FireEquipmentPanel siteCode="S002" />
    </div>
  );
}
