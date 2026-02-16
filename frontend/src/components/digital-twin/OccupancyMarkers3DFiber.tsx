/**
 * 3D OCCUPANCY MARKERS FOR REACT THREE FIBER
 *
 * Renders animated 3D cylinders representing people on the building
 * using React Three Fiber canvas context.
 * Handles:
 * - Person mesh creation and positioning
 * - Smooth interpolation to target positions (60fps)
 * - Walking animation (subtle bobbing effect)
 * - Persona-based color coding
 * - Vertical positioning on building floors
 */

import React, { useEffect, useRef } from 'react';
import { useFrame } from '@react-three/fiber';
import * as THREE from 'three';
import type { Person } from '@/lib/occupancySimulation';
import { getPersonaColor } from '@/lib/occupancySimulation';

interface OccupancyMarkers3DFiberProps {
  people: Person[];
  buildingWidth?: number;
  buildingDepth?: number;
  floorHeight?: number;
}

// Helper: Convert CSS color to THREE.js hex
function personaColorToHex(cssColor: string): number {
  const match = cssColor.match(/rgba?\((\d+),\s*(\d+),\s*(\d+)/);
  if (match) {
    const r = parseInt(match[1]);
    const g = parseInt(match[2]);
    const b = parseInt(match[3]);
    return (r << 16) | (g << 8) | b;
  }
  return 0xffffff;
}

/**
 * Component that renders occupancy markers as 3D cylinders in React Three Fiber
 */
export const OccupancyMarkers3DFiber: React.FC<OccupancyMarkers3DFiberProps> = ({
  people,
  buildingWidth = 12,
  buildingDepth = 8,
  floorHeight = 3.5,
}) => {
  const groupRef = useRef<THREE.Group>(null);
  const meshesRef = useRef<Map<string, any>>(new Map());
  const timeRef = useRef<number>(0);

  // Create or update meshes for people
  useEffect(() => {
    const meshes = meshesRef.current;

    // Remove meshes for people who left
    for (const [id, mesh] of meshes.entries()) {
      if (!people.find(p => p.id === id)) {
        if (groupRef.current) {
          groupRef.current.remove(mesh);
        }
        mesh.geometry?.dispose();
        mesh.material?.dispose();
        meshes.delete(id);
      }
    }

    // Add or update meshes for active people
    for (const person of people) {
      let mesh = meshes.get(person.id);

      if (!mesh) {
        // Create new person mesh (cylinder)
        const geometry = new THREE.CylinderGeometry(0.25, 0.25, 1.7, 12);
        const hexColor = personaColorToHex(getPersonaColor(person.persona));

        const material = new THREE.MeshPhongMaterial({
          color: hexColor,
          emissive: hexColor,
          emissiveIntensity: 0.2,
          shininess: 10,
          transparent: true,
          opacity: 1.0,
        });

        mesh = new THREE.Mesh(geometry, material);
        mesh.castShadow = true;
        mesh.receiveShadow = true;
        mesh.userData.personId = person.id;
        mesh.userData.persona = person.persona;

        if (groupRef.current) {
          groupRef.current.add(mesh);
        }
        meshes.set(person.id, mesh);
      }

      // Update target position
      // Convert from simulation coords to scene coords
      mesh.userData.targetX = (person.x - 300) / 50;
      mesh.userData.targetZ = (person.y - 200) / 50;
      mesh.userData.targetY = person.floor * floorHeight + 0.85;

      // Update opacity based on state
      if (person.state === 'exiting') {
        mesh.material.opacity = 0.5;
      } else {
        mesh.material.opacity = 1.0;
      }
    }
  }, [people]);

  // Animation loop: smooth interpolation + walking effect
  useFrame((state, delta) => {
    timeRef.current += delta;
    const meshes = meshesRef.current;

    for (const mesh of meshes.values()) {
      if (!mesh.userData.targetX) continue;

      // Smooth interpolation to target position (lerp)
      const lerpFactor = Math.min(delta * 5, 1); // 5 units/sec movement speed
      mesh.position.x += (mesh.userData.targetX - mesh.position.x) * lerpFactor;
      mesh.position.y += (mesh.userData.targetY - mesh.position.y) * lerpFactor;
      mesh.position.z += (mesh.userData.targetZ - mesh.position.z) * lerpFactor;

      // Walking animation: subtle bobbing effect
      const bobAmount = Math.sin(timeRef.current * 4 + mesh.position.x) * 0.08;
      mesh.position.y += bobAmount;

      // Optional: subtle rotation while moving
      mesh.rotation.y += 0.01;
    }
  });

  // Return mesh group that will be added to the scene
  return <group ref={groupRef} name="occupancy-markers-3d-fiber" />;
};

export default OccupancyMarkers3DFiber;
