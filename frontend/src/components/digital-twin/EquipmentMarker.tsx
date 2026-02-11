import { Html } from '@react-three/drei';
import { useRef } from 'react';
import type { Equipment } from '@/lib/api/sites';

interface EquipmentMarkerProps {
  equipment: Equipment;
  position: [number, number, number];
  onClick: () => void;
}

// Equipment type to icon/emoji mapping
const EQUIPMENT_ICONS: Record<string, string> = {
  'chiller': '❄️',
  'ahu': '🌬️',
  'fcu': '💨',
  'vav': '🎚️',
  'cooling_tower': '🌊',
  'ct': '🌊',
  'generator': '⚡',
  'gen': '⚡',
  'ups': '🔋',
  'transformer': '⚙️',
  'tx': '⚙️',
  'ats': '🔀',
  'dali': '💡',
  'luminaire': '💡',
  'lum': '💡',
  'meter': '📊',
  'mtr': '📊',
  'fire': '🔥',
  'sprinkler': '💧',
  'cctv': '📹',
  'access': '🔐',
  'acc': '🔐',
  'sensor': '📡',
  'pump': '🔵',
  'boiler': '🟠',
  'hvac_zone': '🎛️',
};

// Equipment type to size mapping for visual differentiation
const EQUIPMENT_SIZES: Record<string, number> = {
  'chiller': 0.8,      // Large - critical equipment
  'ahu': 0.7,
  'generator': 0.7,
  'gen': 0.7,
  'transformer': 0.6,
  'tx': 0.6,
  'ups': 0.6,
  'fcu': 0.4,          // Small
  'vav': 0.35,
  'dali': 0.3,
  'luminaire': 0.25,
  'lum': 0.25,
  'meter': 0.35,
  'default': 0.5,
};

export function EquipmentMarker({ equipment, position, onClick }: EquipmentMarkerProps) {
  const meshRef = useRef<any>(null);
  const equipmentType = ((equipment as any).equipment_type || (equipment as any).type || '').toLowerCase();

  // Determine status color based on health or status field
  const getStatusColor = (equipment: Equipment) => {
    const status = equipment.status?.toLowerCase() || 'offline';
    const health = (equipment as any).health_score || 0;

    if (status === 'fault' || health < 30) return '#ef4444';  // red
    if (status === 'warning' || health < 60) return '#f59e0b'; // yellow
    if (status === 'online' || health >= 60) return '#10b981';  // green
    return '#6b7280';  // gray
  };

  const getEquipmentIcon = (type: string): string => {
    return EQUIPMENT_ICONS[type] || '🏗️'; // Default icon
  };

  const getEquipmentSize = (type: string): number => {
    return EQUIPMENT_SIZES[type] || EQUIPMENT_SIZES['default'];
  };

  const color = getStatusColor(equipment);
  const icon = getEquipmentIcon(equipmentType);
  const size = getEquipmentSize(equipmentType);

  const handleClick = () => {
    if (meshRef.current) {
      meshRef.current.scale.set(1.3, 1.3, 1.3);
      setTimeout(() => {
        if (meshRef.current) {
          meshRef.current.scale.set(1, 1, 1);
        }
      }, 100);
    }
    onClick();
  };

  return (
    <group position={position} onClick={handleClick}>
      {/* Type-specific base shape - size varies by equipment type */}
      <mesh ref={meshRef}>
        <cylinderGeometry args={[size, size, size * 0.6, 16]} />
        <meshStandardMaterial
          color={color}
          emissive={color}
          emissiveIntensity={0.3}
          metalness={0.4}
          roughness={0.6}
        />
      </mesh>

      {/* Status ring with size proportional to equipment */}
      <mesh position={[0, size * 0.4, 0]} rotation={[Math.PI / 2, 0, 0]}>
        <torusGeometry args={[size * 1.2, size * 0.1, 8, 32]} />
        <meshBasicMaterial color={color} />
      </mesh>

      {/* Pulsing effect for faults */}
      {color === '#ef4444' && (
        <mesh position={[0, size * 0.3, 0]}>
          <sphereGeometry args={[size * 1.4, 8, 8]} />
          <meshBasicMaterial color={color} transparent opacity={0.2} />
        </mesh>
      )}

      {/* Equipment type icon and label */}
      <Html distanceFactor={10} position={[0, size + 0.8, 0]}>
        <div
          className="flex flex-col items-center gap-1 pointer-events-none select-none"
          style={{
            filter: 'drop-shadow(0 2px 4px rgba(0,0,0,0.5))',
          }}
        >
          {/* Equipment type icon */}
          <div
            className="text-2xl"
            style={{
              textShadow: '0 1px 2px rgba(0,0,0,0.8)',
            }}
          >
            {icon}
          </div>
          {/* Equipment name */}
          <div
            className="text-xs px-2 py-0.5 rounded font-medium whitespace-nowrap"
            style={{
              background: 'rgba(0, 0, 0, 0.8)',
              color: 'white',
              border: `1px solid ${color}`,
            }}
          >
            {equipment.name || (equipment as any).code || 'Unknown'}
          </div>
          {/* Equipment type label */}
          <div
            className="text-xs px-1.5 py-0.5 rounded font-medium whitespace-nowrap"
            style={{
              background: color,
              color: 'white',
              opacity: 0.9,
              fontSize: '0.65rem',
            }}
          >
            {equipmentType.toUpperCase()}
          </div>
        </div>
      </Html>
    </group>
  );
}
