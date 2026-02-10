import { Html } from '@react-three/drei';
import { useRef } from 'react';
import type { Equipment } from '@/lib/api/sites';

interface EquipmentMarkerProps {
  equipment: Equipment;
  position: [number, number, number];
  onClick: () => void;
}

export function EquipmentMarker({ equipment, position, onClick }: EquipmentMarkerProps) {
  const meshRef = useRef<any>(null);

  // Determine status color based on health or status field
  const getStatusColor = (equipment: Equipment) => {
    const status = equipment.status?.toLowerCase() || 'offline';
    const health = (equipment as any).health_score || 0;

    if (status === 'fault' || health < 30) return '#ef4444';  // red
    if (status === 'warning' || health < 60) return '#f59e0b'; // yellow
    if (status === 'online' || health >= 60) return '#10b981';  // green
    return '#6b7280';  // gray
  };

  const color = getStatusColor(equipment);

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
      {/* Equipment cylinder marker */}
      <mesh ref={meshRef}>
        <cylinderGeometry args={[0.5, 0.5, 0.3, 16]} />
        <meshStandardMaterial
          color={color}
          emissive={color}
          emissiveIntensity={0.3}
          metalness={0.4}
          roughness={0.6}
        />
      </mesh>

      {/* Status ring */}
      <mesh position={[0, 0.2, 0]} rotation={[Math.PI / 2, 0, 0]}>
        <torusGeometry args={[0.6, 0.05, 8, 32]} />
        <meshBasicMaterial color={color} />
      </mesh>

      {/* Pulsing effect for faults */}
      {color === '#ef4444' && (
        <mesh position={[0, 0.15, 0]}>
          <sphereGeometry args={[0.7, 8, 8]} />
          <meshBasicMaterial color={color} transparent opacity={0.2} />
        </mesh>
      )}

      {/* Equipment label */}
      <Html distanceFactor={10} position={[0, 1.2, 0]}>
        <div
          className="text-xs px-2 py-1 rounded whitespace-nowrap pointer-events-none select-none font-medium"
          style={{
            background: 'rgba(0, 0, 0, 0.8)',
            color: 'white',
            textShadow: '0 1px 2px rgba(0,0,0,0.5)',
            border: `1px solid ${color}`,
          }}
        >
          {equipment.name || (equipment as any).code || 'Unknown'}
        </div>
      </Html>
    </group>
  );
}
