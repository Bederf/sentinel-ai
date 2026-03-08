import { useRef, useMemo, useState } from 'react';
import { useFrame } from '@react-three/fiber';
import { Html } from '@react-three/drei';
import * as THREE from 'three';
import type { Equipment } from '@/lib/api/sites';

interface EquipmentMarkerProps {
  equipment: Equipment;
  position: [number, number, number];
  onClick: () => void;
}

// ─── Matrix Cyberpunk Color Palette ──────────────────────────────────────
// eslint-disable-next-line react-refresh/only-export-components
export const TYPE_COLORS: Record<string, string> = {
  // HVAC - Various green shades
  ahu: '#00A541', vav: '#008B37', fcu: '#00712D', fcuventilation: '#00712D',
  // Power/Electrical - Bright green/emerald
  mcc: '#00C852', db: '#00E676', distribution_board: '#00E676',
  ups: '#1DE9B6', dali: '#00FF41', luminaire: '#00FF41', lum: '#00FF41',
  sensor: '#69F0AE', solar: '#00C853', bess: '#00E676',
  chiller: '#00897B', cooling_tower: '#00897B', ct: '#00897B',
  pump: '#009688', fire_panel: '#DC2626', fire: '#EF4444', sprinkler: '#EF4444',
  cctv: '#424242', access: '#7C3AED', acc: '#7C3AED',
  generator: '#00C853', gen: '#00C853',
  transformer: '#00A541', tx: '#00A541', ats: '#00A541',
  meter: '#00897B', mtr: '#00897B', switch: '#00E676',
  boiler: '#FF5722', hvac_zone: '#009688',
};

const STATUS_COLORS: Record<string, string> = {
  online: '#22C55E', normal: '#22C55E', running: '#22C55E',
  warning: '#F59E0B', offline: '#6B7280',
  standby: '#6366F1', idle: '#6366F1',
  fault: '#EF4444', critical: '#EF4444',
};

// ─── Type-specific geometry (matches landing page switch statement) ───
function useEquipmentGeometry(type: string) {
  return useMemo(() => {
    switch (type) {
      // Panels: tall box (MCC, DB, UPS)
      case 'mcc': case 'db': case 'distribution_board':
      case 'ups': case 'ats':
        return new THREE.BoxGeometry(0.5, 1.0, 0.35);
      // Large HVAC: wide box (AHU, Chiller)
      case 'ahu': case 'chiller': case 'cooling_tower': case 'ct':
        return new THREE.BoxGeometry(1.2, 0.7, 0.8);
      // Small HVAC: cylinder (VAV, FCU)
      case 'vav': case 'fcu': case 'fcuventilation':
        return new THREE.CylinderGeometry(0.25, 0.25, 0.4, 8);
      // Lighting: flat slab
      case 'dali': case 'luminaire': case 'lum':
        return new THREE.BoxGeometry(0.6, 0.06, 0.6);
      // Sensor: tiny sphere
      case 'sensor':
        return new THREE.SphereGeometry(0.12, 10, 7);
      // Solar: large flat panel
      case 'solar':
        return new THREE.BoxGeometry(2.5, 0.06, 1.8);
      // Battery: medium box
      case 'bess':
        return new THREE.BoxGeometry(1.0, 0.7, 0.5);
      // Pump: cylinder
      case 'pump':
        return new THREE.CylinderGeometry(0.3, 0.3, 0.5, 8);
      // Wall-mount panels: small flat box (Fire, Access, CCTV)
      case 'fire_panel': case 'fire': case 'sprinkler':
      case 'access': case 'acc': case 'cctv':
        return new THREE.BoxGeometry(0.3, 0.4, 0.15);
      // Generators: large box
      case 'generator': case 'gen':
        return new THREE.BoxGeometry(1.0, 0.8, 0.6);
      // Transformer
      case 'transformer': case 'tx':
        return new THREE.BoxGeometry(0.8, 0.7, 0.5);
      // Meter: small box
      case 'meter': case 'mtr':
        return new THREE.BoxGeometry(0.3, 0.4, 0.2);
      // Boiler
      case 'boiler':
        return new THREE.CylinderGeometry(0.35, 0.35, 0.6, 8);
      default:
        return new THREE.BoxGeometry(0.3, 0.3, 0.3);
    }
  }, [type]);
}

// ─── Status helpers ──────────────────────────────────────────────────
function getStatusColor(equipment: Equipment): string {
  const status = (equipment.status || '').toLowerCase();
  const health = (equipment as any).health_score ?? 100;
  if (status === 'fault' || status === 'critical' || health < 30) return STATUS_COLORS.fault;
  if (status === 'warning' || health < 60) return STATUS_COLORS.warning;
  if (status === 'offline') return STATUS_COLORS.offline;
  if (status === 'standby' || status === 'idle') return STATUS_COLORS.standby;
  return STATUS_COLORS.online;
}

// ─── Component ───────────────────────────────────────────────────────
export function EquipmentMarker({ equipment, position, onClick }: EquipmentMarkerProps) {
  const meshRef = useRef<THREE.Mesh>(null);
  const pulseRef = useRef<THREE.Mesh>(null);
  const [hovered, setHovered] = useState(false);

  const eqType = ((equipment as any).equipment_type || (equipment as any).type || '').toLowerCase();
  const typeColor = TYPE_COLORS[eqType] || '#666666';
  const statusColor = getStatusColor(equipment);
  const isFault = statusColor === STATUS_COLORS.fault;
  const isWarning = statusColor === STATUS_COLORS.warning;
  const isOnline = statusColor === STATUS_COLORS.online;

  const geometry = useEquipmentGeometry(eqType);

  // Material (Matrix Cyberpunk: Enhanced glow effect)
  const material = useMemo(() => {
    return new THREE.MeshPhongMaterial({
      color: new THREE.Color(typeColor),
      emissive: new THREE.Color(statusColor),
      emissiveIntensity: isFault ? 0.8 : isWarning ? 0.6 : 0.4,
      transparent: true,
      opacity: 0.85,
    });
  }, [typeColor, statusColor, isFault, isWarning]);

  // Animate: pulse for fault/warning, subtle bob for online
  useFrame((_, delta) => {
    if (!meshRef.current) return;
    const time = performance.now() * 0.001;

    // Fault/warning pulse on child sphere
    if (pulseRef.current) {
      const s = 1 + Math.sin(time * 4) * 0.3;
      pulseRef.current.scale.set(s, s, s);
      (pulseRef.current.material as THREE.MeshBasicMaterial).opacity =
        0.08 + Math.sin(time * 4) * 0.06;
    }

    // Subtle bob for online equipment (matches landing page)
    if (isOnline && !isFault) {
      meshRef.current.position.y = Math.sin(time * 1.5) * 0.02;
    }

    // Hover scale
    const target = hovered ? 1.15 : 1;
    const curr = meshRef.current.scale.x;
    const lerped = curr + (target - curr) * delta * 8;
    meshRef.current.scale.setScalar(lerped);
  });

  return (
    <group
      position={position}
      onClick={(e) => { e.stopPropagation(); onClick(); }}
      onPointerEnter={(e) => { e.stopPropagation(); setHovered(true); document.body.style.cursor = 'pointer'; }}
      onPointerLeave={() => { setHovered(false); document.body.style.cursor = 'auto'; }}
    >
      {/* Main equipment mesh */}
      <mesh ref={meshRef} geometry={geometry} material={material} castShadow />

      {/* Equipment ID Label - Matrix Cyberpunk Style */}
      <Html position={[0, 0.6, 0]} scale={0.3} distanceFactor={8}>
        <div
          onClick={(e) => { e.stopPropagation(); onClick(); }}
          className="matrix-label px-2 py-1 text-xs whitespace-nowrap font-mono"
          style={{
            pointerEvents: 'auto',
            cursor: 'pointer',
            background: 'rgba(0, 255, 65, 0.15)',
            border: '1px solid rgba(0, 255, 65, 0.4)',
            boxShadow: '0 0 10px rgba(0, 255, 65, 0.3)',
            color: '#00FF41',
          }}
        >
          {(equipment as any).code || equipment.id}
        </div>
      </Html>

      {/* Online status ring (flat ring below equipment) */}
      {isOnline && !isFault && !isWarning && (
        <mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, -0.25, 0]}>
          <ringGeometry args={[0.2, 0.28, 16]} />
          <meshBasicMaterial
            color={statusColor}
            transparent
            opacity={0.2}
            side={THREE.DoubleSide}
          />
        </mesh>
      )}

      {/* Fault pulse sphere */}
      {isFault && (
        <mesh ref={pulseRef}>
          <sphereGeometry args={[0.5, 8, 6]} />
          <meshBasicMaterial color={0xef4444} transparent opacity={0.12} />
        </mesh>
      )}

      {/* Warning pulse sphere */}
      {isWarning && (
        <mesh ref={!isFault ? pulseRef : undefined}>
          <sphereGeometry args={[0.35, 8, 6]} />
          <meshBasicMaterial color={0xf59e0b} transparent opacity={0.08} />
        </mesh>
      )}
    </group>
  );
}
