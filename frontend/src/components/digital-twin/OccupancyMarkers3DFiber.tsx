/**
 * 3D OCCUPANCY MARKERS FOR REACT THREE FIBER
 *
 * Renders subtle occupancy dots on building floors.
 * Small semi-transparent cyan spheres that provide background context
 * without competing with equipment markers.
 *
 * Coordinate mapping: simulation canvas (600x400) → building footprint (30x20m)
 * Floor Y: aligned with BuildingModel slab positions (B1=0, L0=3, L1=6, L2=9, R=12)
 */

import React, { useEffect, useRef } from 'react';
import { useFrame } from '@react-three/fiber';
import * as THREE from 'three';
import type { Person } from '@/lib/occupancySimulation';

// Subtle cyan for all occupancy dots — distinct from equipment health colors
const OCCUPANCY_COLOR = 0x00bcd4;

// Building footprint matches BuildingModel.tsx (30m wide, 20m deep)
const BUILDING_HALF_W = 15; // 30m / 2
const BUILDING_HALF_D = 10; // 20m / 2

// Simulation canvas dimensions (from occupancySimulation.ts)
const SIM_W = 600;
const SIM_H = 400;

// Floor Y positions aligned with BuildingModel slabs (+0.3 to sit just above slab)
const FLOOR_Y: Record<number, number> = {
  0: 3.3,  // Ground (L0) slab at Y=3
  1: 6.3,  // L1 slab at Y=6
  2: 9.3,  // L2 slab at Y=9
};

interface OccupancyMarkers3DFiberProps {
  people: Person[];
  buildingWidth?: number;
  buildingDepth?: number;
  floorHeight?: number;
}

/**
 * Renders occupancy as small semi-transparent spheres on floor surfaces
 */
export const OccupancyMarkers3DFiber: React.FC<OccupancyMarkers3DFiberProps> = ({
  people,
}) => {
  const groupRef = useRef<THREE.Group>(null);
  const meshesRef = useRef<Map<string, THREE.Mesh>>(new Map());
  const timeRef = useRef<number>(0);

  // Shared geometry and material (reused across all dots)
  const sharedGeometry = useRef(new THREE.SphereGeometry(0.3, 8, 6));
  const sharedMaterial = useRef(
    new THREE.MeshPhongMaterial({
      color: OCCUPANCY_COLOR,
      emissive: OCCUPANCY_COLOR,
      emissiveIntensity: 0.15,
      transparent: true,
      opacity: 0.5,
      depthWrite: false,
    })
  );

  useEffect(() => {
    const meshes = meshesRef.current;

    // Remove meshes for people who left
    for (const [id, mesh] of meshes.entries()) {
      if (!people.find(p => p.id === id)) {
        groupRef.current?.remove(mesh);
        meshes.delete(id);
      }
    }

    // Add or update meshes for active people
    for (const person of people) {
      let mesh = meshes.get(person.id);

      if (!mesh) {
        mesh = new THREE.Mesh(sharedGeometry.current, sharedMaterial.current);
        mesh.userData.personId = person.id;
        groupRef.current?.add(mesh);
        meshes.set(person.id, mesh);
      }

      // Map simulation coords (0..600, 0..400) to building footprint (-15..15, -10..10)
      mesh.userData.targetX = (person.x / SIM_W) * BUILDING_HALF_W * 2 - BUILDING_HALF_W;
      mesh.userData.targetZ = (person.y / SIM_H) * BUILDING_HALF_D * 2 - BUILDING_HALF_D;
      mesh.userData.targetY = FLOOR_Y[person.floor] ?? 3.3;
    }
  }, [people]);

  // Smooth position interpolation
  useFrame((_state, delta) => {
    timeRef.current += delta;

    for (const mesh of meshesRef.current.values()) {
      if (mesh.userData.targetX == null) continue;

      const lerp = Math.min(delta * 4, 1);
      mesh.position.x += (mesh.userData.targetX - mesh.position.x) * lerp;
      mesh.position.y += (mesh.userData.targetY - mesh.position.y) * lerp;
      mesh.position.z += (mesh.userData.targetZ - mesh.position.z) * lerp;
    }
  });

  return <group ref={groupRef} name="occupancy-markers-3d" />;
};

export default OccupancyMarkers3DFiber;
