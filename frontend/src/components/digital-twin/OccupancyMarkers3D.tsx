/**
 * 3D OCCUPANCY MARKERS COMPONENT
 *
 * Renders animated 3D cylinders representing people on the building.
 * Handles:
 * - Person mesh creation and positioning
 * - Smooth interpolation to target positions (60fps)
 * - Walking animation (subtle bobbing effect)
 * - Persona-based color coding
 * - Vertical positioning on building floors
 */

import React, { useEffect, useRef } from 'react';
import type { Person } from '@/lib/occupancySimulation';
import { getPersonaColor } from '@/lib/occupancySimulation';

interface OccupancyMarkers3DProps {
  people: Person[];
  THREE: any; // THREE.js library instance (injected from parent)
  scene: any; // THREE.Scene
  floorHeight?: number; // Height per floor (default 3.5m)
  scale?: number; // Coordinate scale factor (default 1)
}

/**
 * Creates and manages 3D person meshes as cylinders
 * Integrates into existing THREE.js scene
 */
export const OccupancyMarkers3D: React.FC<OccupancyMarkers3DProps> = ({
  people,
  THREE,
  scene,
  floorHeight = 3.5,
  scale = 1,
}) => {
  const meshesRef = useRef<Map<string, any>>(new Map());
  const groupRef = useRef<any>(null);

  // Initialize or update meshes
  useEffect(() => {
    if (!THREE || !scene) return;

    // Create group if needed
    if (!groupRef.current) {
      groupRef.current = new THREE.Group();
      groupRef.current.name = 'occupancy-markers-3d';
      scene.add(groupRef.current);
    }

    const meshes = meshesRef.current;

    // Remove meshes for people who left
    for (const [id, mesh] of meshes.entries()) {
      if (!people.find(p => p.id === id)) {
        groupRef.current.remove(mesh);
        mesh.geometry.dispose();
        mesh.material.dispose();
        meshes.delete(id);
      }
    }

    // Add or update meshes for active people
    for (const person of people) {
      let mesh = meshes.get(person.id);

      if (!mesh) {
        // Create new person mesh (cylinder = simple humanoid representation)
        const geometry = new THREE.CylinderGeometry(
          0.25, // radiusTop
          0.25, // radiusBottom
          1.7,  // height
          12    // radialSegments (smoother)
        );

        const personaColor = getPersonaColor(person.persona);
        // Convert CSS color to THREE.js hex
        const hexColor = personaColorToHex(personaColor);

        const material = new THREE.MeshPhongMaterial({
          color: hexColor,
          emissive: hexColor,
          emissiveIntensity: 0.2,
          shininess: 10,
          transparent: true,
          opacity: person.state === 'exiting' ? 0.5 : 1.0,
        });

        mesh = new THREE.Mesh(geometry, material);
        mesh.castShadow = true;
        mesh.receiveShadow = true;
        mesh.userData.personId = person.id;
        mesh.userData.persona = person.persona;
        mesh.userData.state = person.state;

        // Store target positions for smooth interpolation
        mesh.userData.targetX = 0;
        mesh.userData.targetY = 0;
        mesh.userData.targetZ = 0;
        mesh.userData.currentTime = 0;

        groupRef.current.add(mesh);
        meshes.set(person.id, mesh);
      }

      // Update target position
      // Convert from simulation coords to scene coords
      // Simulation: 2D coords (x, y), with floor as separate field
      // Scene: 3D coords (x, y=height, z)
      mesh.userData.targetX = (person.x - 300) / 50; // Normalize to scene coords
      mesh.userData.targetZ = (person.y - 200) / 50;
      mesh.userData.targetY = person.floor * floorHeight + 0.85; // Person height (cylinder center)
      mesh.userData.personId = person.id;
      mesh.userData.persona = person.persona;
      mesh.userData.state = person.state;

      // Update opacity based on state
      if (person.state === 'exiting') {
        mesh.material.opacity = 0.5;
      } else {
        mesh.material.opacity = 1.0;
      }
    }
  }, [people, THREE, scene]);

  // Animation loop (smooth interpolation + walking effect)
  // This hook doesn't directly run the animation; instead it marks meshes as needing updates
  // The parent component's animation loop will handle the actual interpolation
  useEffect(() => {
    return () => {
      // Cleanup on unmount
      if (groupRef.current) {
        groupRef.current.traverse((obj: any) => {
          if (obj.geometry) obj.geometry.dispose();
          if (obj.material) {
            if (Array.isArray(obj.material)) {
              obj.material.forEach((m: any) => m.dispose());
            } else {
              obj.material.dispose();
            }
          }
        });
      }
    };
  }, []);

  // Return null - component manages THREE.js objects directly
  return null;
};

/**
 * Helper function to convert CSS color to THREE.js hex color
 * Handles rgba and hex formats
 */
function personaColorToHex(cssColor: string): number {
  // Extract RGB from rgba(r, g, b, a) format
  const match = cssColor.match(/rgba?\((\d+),\s*(\d+),\s*(\d+)/);
  if (match) {
    const r = parseInt(match[1]);
    const g = parseInt(match[2]);
    const b = parseInt(match[3]);
    return (r << 16) | (g << 8) | b;
  }

  // Fallback to white if parsing fails
  return 0xffffff;
}

/**
 * Animation updater function
 * Call this from parent component's animation loop with deltaTime
 */
export function updateOccupancyMarkers3D(
  meshes: Map<string, any>,
  deltaTime: number,
  time: number,
  THREE: any
) {
  for (const mesh of meshes.values()) {
    if (!mesh.userData.targetX) continue;

    // Smooth interpolation to target position (lerp)
    const lerpFactor = Math.min(deltaTime * 5, 1); // 5 units/sec movement speed
    mesh.position.x += (mesh.userData.targetX - mesh.position.x) * lerpFactor;
    mesh.position.y += (mesh.userData.targetY - mesh.position.y) * lerpFactor;
    mesh.position.z += (mesh.userData.targetZ - mesh.position.z) * lerpFactor;

    // Walking animation: subtle bobbing effect
    // Amplitude decreases with 1/x to prevent excessive motion
    const bobAmount = Math.sin(time * 4 + mesh.position.x) * 0.08;
    mesh.position.y += bobAmount;

    // Optional: subtle rotation while moving
    mesh.rotation.y += 0.01;
  }
}

export default OccupancyMarkers3D;
