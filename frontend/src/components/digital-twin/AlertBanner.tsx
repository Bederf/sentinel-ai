import { AlertTriangle } from 'lucide-react';
import { useState } from 'react';
import type { Equipment } from '@/lib/api/sites';

interface AlertBannerProps {
  equipment: Equipment[];
}

export function AlertBanner({ equipment }: AlertBannerProps) {
  const [dismissed, setDismissed] = useState(false);

  // Find equipment with faults
  const faultedEquipment = equipment.filter((e) => {
    const status = e.status?.toLowerCase() || 'offline';
    const health = (e as any).health_score || 0;
    return status === 'fault' || health < 30;
  });

  if (dismissed || faultedEquipment.length === 0) {
    return null;
  }

  const primary = faultedEquipment[0];

  return (
    <div
      className="flex-none px-4 py-3 flex items-center justify-between gap-4 matrix-alert"
      style={{
        background: 'rgba(239, 68, 68, 0.12)',
        borderBottom: '2px solid rgba(239, 68, 68, 0.6)',
        borderLeft: '3px solid rgba(239, 68, 68, 0.8)',
      }}
    >
      <div className="flex items-center gap-3">
        <AlertTriangle className="h-5 w-5 flex-none text-red-500" />
        <div>
          <div className="text-sm font-bold text-red-500">
            {faultedEquipment.length} Equipment
            {faultedEquipment.length > 1 ? ' Issues' : ' Issue'} Detected
          </div>
          <div className="text-xs" style={{ color: 'var(--color-sentinel-text-secondary)' }}>
            {primary.name || (primary as any).code || primary.id}: {primary.status || 'Offline'}
            {faultedEquipment.length > 1 && ` + ${faultedEquipment.length - 1} more`}
          </div>
        </div>
      </div>
      <button
        onClick={() => setDismissed(true)}
        className="px-2 py-1 flex-none text-xs font-bold transition-colors"
        style={{
          background: 'rgba(239, 68, 68, 0.2)',
          color: '#EF4444',
          border: '1px solid rgba(239, 68, 68, 0.5)',
          borderRadius: 0,
          fontSize: '14px',
        }}
        aria-label="Dismiss alert"
      >
        ✕
      </button>
    </div>
  );
}
