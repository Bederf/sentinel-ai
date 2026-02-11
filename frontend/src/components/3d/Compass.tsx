import { Html } from '@react-three/drei';

/**
 * 3D Compass - Displays cardinal directions (N/S/E/W) in 3D space
 * Positioned at world origin, scales with camera distance
 */
export function Compass() {
  const compassSize = 2;
  const tickLength = 0.3;
  const ringRadius = 1.2;

  return (
    <group position={[18, 3, 0]}>
      {/* Compass ring outline */}
      <mesh>
        <cylinderGeometry args={[ringRadius, ringRadius, 0.1, 64]} />
        <meshStandardMaterial
          color="#1a1a2e"
          metalness={0.6}
          roughness={0.4}
          emissive="#0066ff"
          emissiveIntensity={0.3}
        />
      </mesh>

      {/* Cardinal directions (N/S/E/W) */}
      {[
        { angle: 0, label: 'N', color: '#ff3333' },    // North - Red
        { angle: Math.PI / 2, label: 'E', color: '#33ff33' }, // East - Green
        { angle: Math.PI, label: 'S', color: '#3333ff' }, // South - Blue
        { angle: (3 * Math.PI) / 2, label: 'W', color: '#ffff33' }, // West - Yellow
      ].map((dir, i) => {
        const x = Math.sin(dir.angle) * ringRadius;
        const z = Math.cos(dir.angle) * ringRadius;

        return (
          <group key={i}>
            {/* Cardinal direction marker */}
            <mesh position={[x, 0, z]}>
              <sphereGeometry args={[0.15, 16, 16]} />
              <meshStandardMaterial
                color={dir.color}
                emissive={dir.color}
                emissiveIntensity={0.6}
              />
            </mesh>

            {/* Text label */}
            <Html
              position={[x * 1.35, 0.2, z * 1.35]}
              scale={0.5}
              distanceFactor={15}
            >
              <div className="font-bold text-lg" style={{ color: dir.color }}>
                {dir.label}
              </div>
            </Html>
          </group>
        );
      })}

      {/* Center circle */}
      <mesh position={[0, 0.05, 0]}>
        <cylinderGeometry args={[0.2, 0.2, 0.15, 32]} />
        <meshStandardMaterial color="#ffffff" emissive="#00ffff" emissiveIntensity={0.8} />
      </mesh>

      {/* Tick marks for minor directions */}
      {Array.from({ length: 32 }).map((_, i) => {
        const angle = (i * Math.PI) / 16;
        const innerR = ringRadius * 0.9;
        const outerR = ringRadius;

        const x1 = Math.sin(angle) * innerR;
        const z1 = Math.cos(angle) * innerR;
        const x2 = Math.sin(angle) * outerR;
        const z2 = Math.cos(angle) * outerR;

        return (
          <line key={`tick-${i}`}>
            <bufferGeometry>
              <bufferAttribute
                attach="attributes-position"
                count={2}
                array={new Float32Array([x1, 0.05, z1, x2, 0.05, z2])}
                itemSize={3}
              />
            </bufferGeometry>
            <lineBasicMaterial color="#00ffff" linewidth={1} fog={false} />
          </line>
        );
      })}
    </group>
  );
}
