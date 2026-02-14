import { Zap, AlertTriangle, Activity } from 'lucide-react';
import type { Equipment } from '@/lib/api/sites';

interface StatsBarProps {
  equipment: Equipment[];
  selectedFloors: Set<number>;
}

function getFloorIdFromCode(code: string): number {
  const floorMatch = code.match(/-(B\d|G|L\d+|R)-/);
  const floorCode = floorMatch ? floorMatch[1] : 'G';

  const floorMap: Record<string, number> = {
    'B1': 0,
    'B2': -1,
    'G': 1,
    'L1': 2,
    'L2': 3,
    'R': 4,
  };

  return floorMap[floorCode] ?? 1;
}

export function StatsBar({ equipment, selectedFloors }: StatsBarProps) {
  // Filter equipment to selected floors
  const visibleEquipment = equipment.filter((eq) => {
    const floorId = getFloorIdFromCode((eq as any).code || '');
    return selectedFloors.has(floorId);
  });

  // Calculate stats
  const totalEquipment = visibleEquipment.length;
  const healthyCount = visibleEquipment.filter((e) => {
    const health = (e as any).health_score || 0;
    return health >= 60;
  }).length;
  const warningCount = visibleEquipment.filter((e) => {
    const health = (e as any).health_score || 0;
    return health < 60 && health >= 30;
  }).length;
  const faultCount = visibleEquipment.filter((e) => {
    const health = (e as any).health_score || 0;
    return health < 30;
  }).length;

  const avgHealth = totalEquipment > 0
    ? Math.round(
        visibleEquipment.reduce((sum, e) => sum + ((e as any).health_score || 0), 0) /
          totalEquipment
      )
    : 0;

  return (
    <div
      className="flex-none px-4 py-3 flex items-center gap-4 border-b"
      style={{
        background: 'rgba(6, 14, 24, 0.7)',
        borderColor: 'rgba(0, 255, 65, 0.2)',
      }}
    >
      {/* Total equipment */}
      <div className="flex items-center gap-2">
        <Activity className="h-5 w-5" style={{ color: '#00FF41' }} />
        <div>
          <div className="matrix-label text-xs">UNITS</div>
          <div className="text-lg font-bold" style={{ color: '#00FF41', textShadow: '0 0 8px rgba(0, 255, 65, 0.3)' }}>
            {totalEquipment}
          </div>
        </div>
      </div>

      {/* Average health */}
      <div className="flex items-center gap-2 pl-4" style={{ borderLeft: '1px solid rgba(0, 255, 65, 0.2)' }}>
        <Zap className="h-5 w-5" style={{ color: '#00FF41' }} />
        <div>
          <div className="matrix-label text-xs">SYS HEALTH</div>
          <div className="text-lg font-bold" style={{ color: '#00FF41', textShadow: '0 0 8px rgba(0, 255, 65, 0.3)' }}>
            {avgHealth}%
          </div>
        </div>
      </div>

      {/* Status breakdown */}
      <div className="flex items-center gap-2 pl-4" style={{ borderLeft: '1px solid rgba(0, 255, 65, 0.2)' }}>
        <div
          className="h-5 w-5 rounded flex items-center justify-center text-xs font-bold"
          style={{ background: 'rgba(16, 185, 129, 0.2)', color: '#10b981' }}
        >
          {healthyCount}
        </div>
        <div
          className="h-5 w-5 rounded flex items-center justify-center text-xs font-bold"
          style={{ background: 'rgba(245, 158, 11, 0.2)', color: '#f59e0b' }}
        >
          {warningCount}
        </div>
        <div
          className="h-5 w-5 rounded flex items-center justify-center text-xs font-bold"
          style={{ background: 'rgba(239, 68, 68, 0.2)', color: '#ef4444' }}
        >
          {faultCount}
        </div>
      </div>

      {/* Active alerts */}
      {faultCount > 0 && (
        <div className="flex items-center gap-2 pl-4" style={{ borderLeft: '1px solid rgba(0, 255, 65, 0.2)' }}>
          <AlertTriangle className="h-5 w-5 text-red-500" />
          <div>
            <div className="text-xs" style={{ color: 'var(--color-sentinel-text-disabled)' }}>
              Critical
            </div>
            <div className="text-lg font-bold text-red-500">
              {faultCount}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
