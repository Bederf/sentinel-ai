import type { Equipment } from '@/lib/api/sites';

interface BottomStatusBarProps {
  equipment: Equipment[];
}

export function BottomStatusBar({ equipment }: BottomStatusBarProps) {
  // Calculate stats from equipment data
  const onlineCount = equipment.filter((e) => {
    const status = (e.status || '').toLowerCase();
    return status !== 'offline' && status !== 'fault' && status !== 'critical';
  }).length;

  const faultCount = equipment.filter((e) => {
    const status = (e.status || '').toLowerCase();
    const health = (e as any).health_score ?? 100;
    return status === 'fault' || status === 'critical' || health < 30;
  }).length;

  const warningCount = equipment.filter((e) => {
    const status = (e.status || '').toLowerCase();
    const health = (e as any).health_score ?? 100;
    return (status === 'warning' || (health >= 30 && health < 60)) && status !== 'fault' && status !== 'critical';
  }).length;

  // Estimate load from equipment data (sum of capacity where available, or use operating data)
  const totalLoadKw = equipment.reduce((sum, eq) => {
    const opData = (eq as any).operating_data;
    if (opData?.power_kw) return sum + opData.power_kw;
    if (opData?.current_power_kw) return sum + opData.current_power_kw;
    return sum;
  }, 0);

  // Solar generation from solar/inverter equipment
  const solarKw = equipment
    .filter((eq) => {
      const type = ((eq as any).equipment_type || (eq as any).type || '').toLowerCase();
      return type === 'solar' || type === 'inv' || type === 'inverter';
    })
    .reduce((sum, eq) => {
      const opData = (eq as any).operating_data;
      if (opData?.power_kw) return sum + opData.power_kw;
      if (opData?.current_power_kw) return sum + opData.current_power_kw;
      return sum;
    }, 0);

  return (
    <div
      className="absolute bottom-0 left-0 right-0 z-10 flex items-center justify-center gap-8 py-3 px-6"
      style={{
        background: 'linear-gradient(to top, rgba(6, 14, 24, 0.95), rgba(6, 14, 24, 0.7))',
        borderTop: '1px solid rgba(0, 255, 65, 0.15)',
      }}
    >
      {/* Online */}
      <div className="flex flex-col items-center">
        <span
          className="text-lg font-bold"
          style={{
            color: '#00FF41',
            fontFamily: 'Orbitron, monospace',
            textShadow: '0 0 10px rgba(0, 255, 65, 0.4)',
          }}
        >
          {onlineCount}/{equipment.length}
        </span>
        <span
          style={{
            color: 'rgba(255, 255, 255, 0.5)',
            fontFamily: 'Share Tech Mono, monospace',
            fontSize: '10px',
            letterSpacing: '0.1em',
          }}
        >
          ONLINE
        </span>
      </div>

      {/* Faults */}
      <div className="flex flex-col items-center">
        <span
          className="text-lg font-bold"
          style={{
            color: faultCount > 0 ? '#EF4444' : '#22C55E',
            fontFamily: 'Orbitron, monospace',
            textShadow: faultCount > 0 ? '0 0 10px rgba(239, 68, 68, 0.4)' : undefined,
          }}
        >
          {faultCount}
        </span>
        <span
          style={{
            color: 'rgba(255, 255, 255, 0.5)',
            fontFamily: 'Share Tech Mono, monospace',
            fontSize: '10px',
            letterSpacing: '0.1em',
          }}
        >
          FAULTS
        </span>
      </div>

      {/* Warnings */}
      <div className="flex flex-col items-center">
        <span
          className="text-lg font-bold"
          style={{
            color: warningCount > 0 ? '#F59E0B' : '#22C55E',
            fontFamily: 'Orbitron, monospace',
            textShadow: warningCount > 0 ? '0 0 10px rgba(245, 158, 11, 0.4)' : undefined,
          }}
        >
          {warningCount}
        </span>
        <span
          style={{
            color: 'rgba(255, 255, 255, 0.5)',
            fontFamily: 'Share Tech Mono, monospace',
            fontSize: '10px',
            letterSpacing: '0.1em',
          }}
        >
          WARNINGS
        </span>
      </div>

      {/* Load */}
      <div className="flex flex-col items-center">
        <span
          className="text-lg font-bold"
          style={{
            color: '#00BCD4',
            fontFamily: 'Orbitron, monospace',
            textShadow: '0 0 10px rgba(0, 188, 212, 0.4)',
          }}
        >
          {totalLoadKw > 0 ? `${Math.round(totalLoadKw)} kW` : '— kW'}
        </span>
        <span
          style={{
            color: 'rgba(255, 255, 255, 0.5)',
            fontFamily: 'Share Tech Mono, monospace',
            fontSize: '10px',
            letterSpacing: '0.1em',
          }}
        >
          LOAD
        </span>
      </div>

      {/* Solar */}
      <div className="flex flex-col items-center">
        <span
          className="text-lg font-bold"
          style={{
            color: '#FF9800',
            fontFamily: 'Orbitron, monospace',
            textShadow: '0 0 10px rgba(255, 152, 0, 0.4)',
          }}
        >
          {solarKw > 0 ? `${Math.round(solarKw * 10) / 10} kW` : '— kW'}
        </span>
        <span
          style={{
            color: 'rgba(255, 255, 255, 0.5)',
            fontFamily: 'Share Tech Mono, monospace',
            fontSize: '10px',
            letterSpacing: '0.1em',
          }}
        >
          SOLAR
        </span>
      </div>
    </div>
  );
}
