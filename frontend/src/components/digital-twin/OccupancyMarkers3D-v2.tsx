/**
 * OCCUPANCY MARKERS 3D - Phase 5.3 Enhanced
 *
 * Advanced 3D visualization with:
 * - Stair climbing animations
 * - Elevator cage simulation
 * - Improved humanoid meshes
 * - Camera follow
 * - Performance optimization (LOD, instancing)
 */

import { useRef, useEffect, useState } from 'react';
import { useFrame, useThree } from '@react-three/fiber';
import * as THREE from 'three';
import type { Person } from '@/lib/occupancySimulation';
import {
  occupancySimulation3D,
  HumanoidMeshBuilder,
  StairClimber,
  ElevatorAnimator,
  CameraFollowSystem,
  type Person3D,
} from '@/lib/occupancySimulation3D';

interface OccupancyMarkers3DEnhancedProps {
  people: Person[];
  floorHeight: number;
  enableCameraFollow: boolean;
  followTargetId?: string;
  onPersonHover?: (personId: string | null) => void;
}

/**
 * Convert Person to Person3D with vertical animation
 */
function toPerson3D(person: Person, currentTime: number = 0): Person3D {
  // Check if person is in vertical transition
  const isClimbing = person.path[0]?.action === 'stairs';
  const isInElevator = person.path[0]?.action === 'elevator';

  let verticalProgress = 0;
  let verticalTransitionStart = 0;
  let verticalTransitionDuration = 4; // seconds

  if (isClimbing || isInElevator) {
    // Calculate progress through vertical transition
    verticalTransitionStart = currentTime;
    verticalTransitionDuration = isClimbing ? 4 : 3; // stairs slower than elevator
    verticalProgress = Math.random(); // In real implementation, track actual time
  }

  return {
    id: person.id,
    x: person.x,
    y: person.y,
    floor: person.floor,
    verticalProgress,
    verticalStartFloor: person.floor,
    verticalEndFloor: person.targetFloor,
    verticalTransitionType: isClimbing ? 'stairs' : isInElevator ? 'elevator' : 'none',
    verticalTransitionDuration,
    verticalTransitionStart,
    meshType: 'humanoid',
    scale: 1.0,
    isClimbing,
    isInElevator,
  };
}

/**
 * Person humanoid mesh component
 */
function HumanoidPerson({
  person3D,
  persona,
  isSelected,
  lod,
}: {
  person3D: Person3D;
  persona: string;
  isSelected: boolean;
  lod: 'high' | 'medium' | 'low';
}) {
  const groupRef = useRef<THREE.Group>(null);
  const meshes = useRef<Record<string, THREE.Mesh>>({});

  // Get persona color
  const personaColors: Record<string, number> = {
    worker: 0x22d3ee,
    security: 0xa855f7,
    cleaner: 0x22c55e,
    visitor: 0xf59e0b,
  };
  const color = personaColors[persona] || 0xffffff;

  // Create humanoid geometry on mount
  useEffect(() => {
    if (!groupRef.current) return;
    if (lod === 'low') return; // Don't render humanoid for low LOD

    const specs = HumanoidMeshBuilder.createGeometry();
    const geometry: Record<string, THREE.BufferGeometry> = {
      sphere: new THREE.SphereGeometry(1, 8, 8),
      capsule: new THREE.CapsuleGeometry(1, 1, 4, 8),
    };

    // Head
    const headMesh = new THREE.Mesh(
      geometry.sphere,
      new THREE.MeshPhongMaterial({ color, emissiveIntensity: isSelected ? 0.8 : 0.3 })
    );
    headMesh.scale.set(specs.head.radius, specs.head.radius, specs.head.radius);
    headMesh.position.set(specs.head.position.x, specs.head.position.y, specs.head.position.z);
    headMesh.castShadow = true;
    groupRef.current.add(headMesh);
    meshes.current.head = headMesh;

    // Torso
    const torsoMesh = new THREE.Mesh(
      geometry.capsule,
      new THREE.MeshPhongMaterial({ color, emissiveIntensity: isSelected ? 0.8 : 0.3 })
    );
    torsoMesh.scale.set(specs.torso.radius, specs.torso.height / 2, specs.torso.radius);
    torsoMesh.position.set(specs.torso.position.x, specs.torso.position.y, specs.torso.position.z);
    torsoMesh.castShadow = true;
    groupRef.current.add(torsoMesh);
    meshes.current.torso = torsoMesh;

    // Legs and arms for high LOD only
    if (lod === 'high') {
      // Left leg
      const leftLegMesh = new THREE.Mesh(geometry.capsule, new THREE.MeshPhongMaterial({ color }));
      leftLegMesh.scale.set(specs.leftLeg.radius, specs.leftLeg.height / 2, specs.leftLeg.radius);
      leftLegMesh.position.set(specs.leftLeg.position.x, specs.leftLeg.position.y, specs.leftLeg.position.z);
      leftLegMesh.castShadow = true;
      groupRef.current.add(leftLegMesh);
      meshes.current.leftLeg = leftLegMesh;

      // Right leg
      const rightLegMesh = new THREE.Mesh(geometry.capsule, new THREE.MeshPhongMaterial({ color }));
      rightLegMesh.scale.set(specs.rightLeg.radius, specs.rightLeg.height / 2, specs.rightLeg.radius);
      rightLegMesh.position.set(specs.rightLeg.position.x, specs.rightLeg.position.y, specs.rightLeg.position.z);
      rightLegMesh.castShadow = true;
      groupRef.current.add(rightLegMesh);
      meshes.current.rightLeg = rightLegMesh;
    }
  }, [lod, isSelected, color]);

  // Animate vertical movement
  useFrame((state, delta) => {
    if (!groupRef.current) return;

    const baseY = person3D.floor * person3D.scale;

    if (person3D.isClimbing) {
      // Stair climbing animation
      const verticalOffset = StairClimber.getVerticalPosition(person3D.verticalProgress);
      groupRef.current.position.y = baseY + verticalOffset;

      // Lean forward while climbing
      groupRef.current.rotation.z = StairClimber.getRotationZ(person3D.verticalProgress);
    } else if (person3D.isInElevator) {
      // Elevator animation (smooth vertical movement)
      const progress = person3D.verticalProgress;
      const startZ = person3D.verticalStartFloor * person3D.scale;
      const endZ = person3D.verticalEndFloor * person3D.scale;
      const easeProgress = progress < 0.5 ? 2 * progress * progress : -1 + (4 - 2 * progress) * progress;
      groupRef.current.position.y = startZ + (endZ - startZ) * easeProgress;
    } else {
      // Normal position
      groupRef.current.position.y = baseY;
      groupRef.current.rotation.z = 0;
    }

    // Subtle bobbing animation
    if (!person3D.isClimbing && !person3D.isInElevator) {
      groupRef.current.position.y += Math.sin(state.clock.elapsedTime * 4 + groupRef.current.position.x) * 0.02;
    }
  });

  if (lod === 'low') {
    // Low LOD: simple sphere
    return (
      <mesh position={[person3D.x, 0, person3D.y]}>
        <sphereGeometry args={[0.3, 6, 6]} />
        <meshPhongMaterial color={color} emissiveIntensity={isSelected ? 0.8 : 0.3} />
      </mesh>
    );
  }

  return <group ref={groupRef} position={[person3D.x, 0, person3D.y]} />;
}

/**
 * Elevator cage renderer
 */
function ElevatorCage({ elevatorId }: { elevatorId: string }) {
  const groupRef = useRef<THREE.Group>(null);
  const leftDoorRef = useRef<THREE.Group>(null);
  const rightDoorRef = useRef<THREE.Group>(null);

  useEffect(() => {
    if (!groupRef.current) return;

    const elevator = occupancySimulation3D.getElevatorCage(elevatorId);
    if (!elevator) return;

    // Elevator cage frame (wire frame)
    const frame = new THREE.Group();
    const material = new THREE.LineBasicMaterial({ color: 0x888888 });

    // Create elevator outline
    const points = [
      new THREE.Vector3(0, 0, 0),
      new THREE.Vector3(1, 0, 0),
      new THREE.Vector3(1, 2, 0),
      new THREE.Vector3(0, 2, 0),
      new THREE.Vector3(0, 0, 0),
    ];
    const geometry = new THREE.BufferGeometry().setFromPoints(points);
    const line = new THREE.LineSegments(geometry, material);
    frame.add(line);
    groupRef.current.add(frame);

    // Create doors
    const doorMaterial = new THREE.MeshBasicMaterial({ color: 0x444444 });

    // Left door
    const leftDoor = new THREE.Group();
    const leftDoorMesh = new THREE.Mesh(new THREE.PlaneGeometry(0.4, 2), doorMaterial);
    leftDoorMesh.position.x = -0.2;
    leftDoor.add(leftDoorMesh);
    groupRef.current.add(leftDoor);
    (leftDoorRef as any).current = leftDoor;

    // Right door
    const rightDoor = new THREE.Group();
    const rightDoorMesh = new THREE.Mesh(new THREE.PlaneGeometry(0.4, 2), doorMaterial);
    rightDoorMesh.position.x = 0.2;
    rightDoor.add(rightDoorMesh);
    groupRef.current.add(rightDoor);
    (rightDoorRef as any).current = rightDoor;
  }, [elevatorId]);

  // Animate doors
  useFrame(() => {
    const elevator = occupancySimulation3D.getElevatorCage(elevatorId);
    if (!elevator || !leftDoorRef.current) return;

    // Open/close doors
    leftDoorRef.current.position.x = -elevator.doors.leftOpen * 0.3;
    if (rightDoorRef.current) {
      rightDoorRef.current.position.x = elevator.doors.rightOpen * 0.3;
    }
  });

  const elevator = occupancySimulation3D.getElevatorCage(elevatorId);
  if (!elevator) return null;

  const floorHeight = 3.5;
  const elevatorY = elevator.currentFloor * floorHeight + (elevator.targetFloor - elevator.currentFloor) * floorHeight * elevator.movingProgress;

  return <group ref={groupRef} position={[elevator.x / 50, elevatorY, elevator.y / 50]} />;
}

/**
 * Stair renderer
 */
function Stair({ stairId }: { stairId: string }) {
  const groupRef = useRef<THREE.Group>(null);

  useEffect(() => {
    if (!groupRef.current) return;

    const stair = occupancySimulation3D.getStairTransition(stairId);
    if (!stair) return;

    // Draw stair steps
    const stepHeight = 0.15;
    const stepCount = 4;
    const stepWidth = 0.3;

    for (let i = 0; i < stepCount; i++) {
      const stepMesh = new THREE.Mesh(
        new THREE.BoxGeometry(stepWidth, stepHeight, stepWidth),
        new THREE.MeshPhongMaterial({ color: 0xcccccc })
      );
      stepMesh.position.y = i * stepHeight;
      stepMesh.castShadow = true;
      groupRef.current.add(stepMesh);
    }
  }, [stairId]);

  const stair = occupancySimulation3D.getStairTransition(stairId);
  if (!stair) return null;

  const floorHeight = 3.5;
  const stairY = (stair.startFloor + stair.endFloor) * floorHeight * 0.5;

  return <group ref={groupRef} position={[stair.x / 50, stairY, stair.y / 50]} />;
}

/**
 * Enhanced 3D Occupancy Markers (Phase 5.3)
 */
export function OccupancyMarkers3DEnhanced({
  people,
  floorHeight,
  enableCameraFollow,
  followTargetId,
  onPersonHover,
}: OccupancyMarkers3DEnhancedProps) {
  const groupRef = useRef<THREE.Group>(null);
  const { camera } = useThree();
  const cameraFollowSystem = useRef(new CameraFollowSystem());
  const [hoveredPersonId, setHoveredPersonId] = useState<string | null>(null);

  // Update active person count for LOD
  useEffect(() => {
    occupancySimulation3D.setActivePersonCount(people.length);
  }, [people.length]);

  // Animate camera follow
  useFrame((state) => {
    if (!enableCameraFollow || !followTargetId || people.length === 0) return;

    const targetPerson = people.find(p => p.id === followTargetId);
    if (!targetPerson) return;

    const person3D = toPerson3D(targetPerson, state.clock.getElapsedTime());
    const cameraTarget = occupancySimulation3D.getCameraTarget(person3D);

    // Smooth camera interpolation
    const speed = 0.1;
    camera.position.x += (cameraTarget.x - camera.position.x) * speed;
    camera.position.y += (cameraTarget.z - camera.position.y) * speed;
    camera.position.z += (cameraTarget.y - camera.position.z) * speed;

    const focusPoint = new THREE.Vector3(cameraTarget.focusX, cameraTarget.focusZ, cameraTarget.focusY);
    const currentLook = new THREE.Vector3();
    camera.getWorldDirection(currentLook);
    const targetDirection = focusPoint.sub(camera.position).normalize();

    currentLook.lerp(targetDirection, speed);
    camera.lookAt(camera.position.clone().add(currentLook));
  });

  return (
    <group ref={groupRef}>
      {/* Render elevator cages */}
      {occupancySimulation3D.getAllElevatorCages().map(elevator => (
        <ElevatorCage key={elevator.id} elevatorId={elevator.id} />
      ))}

      {/* Render stairs */}
      {occupancySimulation3D.getAllStairs().map(stair => (
        <Stair key={stair.id} stairId={stair.id} />
      ))}

      {/* Render people */}
      {people.map((person, idx) => {
        const person3D = toPerson3D(person);
        const lod = occupancySimulation3D.getLOD(idx, 5); // TODO: calculate actual camera distance

        return (
          <HumanoidPerson
            key={person.id}
            person3D={person3D}
            persona={person.persona}
            isSelected={hoveredPersonId === person.id || followTargetId === person.id}
            lod={lod}
          />
        );
      })}
    </group>
  );
}

export default OccupancyMarkers3DEnhanced;
