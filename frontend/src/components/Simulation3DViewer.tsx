/**
 * Simulation 3D Viewer - Real-time 3D occupancy visualization for simulations
 *
 * Displays:
 * - 3D building floors with people
 * - Stair climbing animations
 * - Elevator transitions
 * - Real-time occupancy updates from simulation events
 * - Persona-based coloring (worker, security, cleaner, visitor)
 */

import React, { useEffect, useState } from 'react';
import { Canvas } from '@react-three/fiber';
import { OrbitControls, PerspectiveCamera } from '@react-three/drei';
import { OccupancyMarkers3DEnhanced } from './digital-twin/OccupancyMarkers3D-v2';
import type { LiveEvent } from '@/lib/simulationApi';
import type { Person } from '@/lib/occupancySimulation';

interface Simulation3DViewerProps {
  events: LiveEvent[];
  isRunning: boolean;
  simulatedHour: number;
}

/**
 * Extract occupancy data from simulation events
 */
function extractOccupancyFromEvents(events: LiveEvent[]): Person[] {
  const people: Person[] = [];

  // Look for occupancy events
  for (const event of events) {
    if (event.event_type === 'occupancy_increase' || event.event_type === 'occupancy_decrease') {
      const occupancyPercent = (event.details?.occupancy_percent ?? 0) as number;
      const floor = Math.floor(occupancyPercent / 25); // Distribute across floors

      // Generate person entries based on occupancy
      const personCount = Math.round((occupancyPercent / 100) * 20); // Max 20 people visible

      for (let i = 0; i < personCount; i++) {
        const personas = ['worker', 'security', 'cleaner', 'visitor'] as const;
        const now = new Date();
        people.push({
          id: `person-${occupancyPercent}-${i}`,
          x: Math.random() * 50,
          y: Math.random() * 50,
          floor: floor % 4,
          targetFloor: floor % 4,
          persona: personas[Math.floor(Math.random() * personas.length)],
          path: [],
          vx: 0,
          vy: 0,
          targetX: Math.random() * 50,
          targetY: Math.random() * 50,
          zoneId: `zone-${floor}`,
          state: 'working' as const,
          entryTime: now,
          scheduledExitTime: new Date(now.getTime() + 8 * 60 * 60 * 1000),
          moving: false,
        });
      }
    }
  }

  return people;
}

/**
 * 3D Viewer Component
 */
export function Simulation3DViewer({
  events,
  isRunning,
  simulatedHour: _simulatedHour
}: Simulation3DViewerProps) {
  const [people, setPeople] = useState<Person[]>([]);

  // Update people based on events
  useEffect(() => {
    const newPeople = extractOccupancyFromEvents(events);
    setPeople(newPeople);
  }, [events]);

  if (!isRunning) {
    return (
      <div
        className="w-full h-full flex items-center justify-center rounded-lg"
        style={{
          background: "var(--color-sentinel-bg-primary)",
          border: "1px solid var(--color-sentinel-border)",
          color: "var(--color-sentinel-text-secondary)",
        }}
      >
        <div className="text-center">
          <p className="text-sm font-medium mb-2">Start simulation to see 3D visualization</p>
          <p className="text-xs opacity-75">Buildings, occupancy, and animations will appear here</p>
        </div>
      </div>
    );
  }

  return (
    <div className="w-full h-full rounded-lg overflow-hidden">
      <Canvas
        style={{ background: '#1a1a2e' }}
        dpr={1} // Reduce pixel ratio for better performance
      >
        {/* Camera */}
        <PerspectiveCamera makeDefault position={[20, 15, 30]} fov={60} />

        {/* Lighting */}
        <ambientLight intensity={0.6} />
        <directionalLight position={[10, 20, 10]} intensity={0.8} castShadow />
        <pointLight position={[0, 10, 0]} intensity={0.5} />

        {/* Controls */}
        <OrbitControls
          autoRotate={false}
          autoRotateSpeed={4}
          enableDamping
          dampingFactor={0.05}
          enableZoom
          minDistance={5}
          maxDistance={100}
        />

        {/* Floor grid */}
        <group>
          {[0, 1, 2, 3].map((floor) => (
            <group key={`floor-${floor}`} position={[0, floor * 3.5, 0]}>
              {/* Floor plane */}
              <mesh position={[0, 0, 0]} receiveShadow>
                <planeGeometry args={[60, 60]} />
                <meshStandardMaterial color={floor % 2 === 0 ? '#2a2a3e' : '#333350'} />
              </mesh>

              {/* Grid lines */}
              <gridHelper args={[60, 10, '#555555', '#444455']} position={[0, 0.01, 0]} />

            </group>
          ))}
        </group>

        {/* Occupancy markers */}
        {people.length > 0 && (
          <OccupancyMarkers3DEnhanced
            people={people}
            floorHeight={3.5}
            enableCameraFollow={false}
            onPersonHover={(_personId) => {
              // Optional: handle person hover
            }}
          />
        )}

        {/* Occupancy counter */}
        <Html position={[-25, 5, 0]}>
          <div
            className="px-3 py-2 rounded bg-blue-900 bg-opacity-80 text-white text-sm font-bold"
            style={{ color: '#10b981' }}
          >
            People: {people.length}
          </div>
        </Html>
      </Canvas>
    </div>
  );
}

// Fallback import for Html component
import { Html } from '@react-three/drei';
