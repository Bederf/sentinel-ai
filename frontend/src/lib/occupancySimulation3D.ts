/**
 * OCCUPANCY SIMULATION 3D ENHANCEMENTS (Phase 5.3)
 *
 * Advanced 3D animation features:
 * - Stair climbing with vertical animation
 * - Elevator cage simulation
 * - Improved humanoid meshes
 * - Camera follow tracking
 * - Performance optimization
 */

export type VerticalTransitionType = 'stairs' | 'elevator' | 'none';
export type MeshType = 'cylinder' | 'humanoid' | 'capsule';

/**
 * Vertical transition configuration
 * (stairs vs elevator with different animation styles)
 */
export interface VerticalTransition {
  id: string;
  type: VerticalTransitionType;
  x: number;
  y: number;
  startFloor: number;
  endFloor: number;
  duration: number; // seconds (time to climb/ride)
  capacity?: number; // for elevators
}

/**
 * Enhanced person with 3D animation properties
 */
export interface Person3D {
  id: string;
  // Position
  x: number;
  y: number;
  floor: number;
  // Vertical movement (0-1, where 1 = completed transition)
  verticalProgress: number;
  verticalStartFloor: number;
  verticalEndFloor: number;
  verticalTransitionType: VerticalTransitionType;
  verticalTransitionDuration: number;
  verticalTransitionStart: number; // timestamp
  // Mesh
  meshType: MeshType;
  scale: number;
  // Animation state
  isClimbing: boolean;
  isInElevator: boolean;
  elevatorId?: string;
}

/**
 * Elevator cage state tracking
 */
export interface ElevatorCage {
  id: string;
  x: number;
  y: number;
  currentFloor: number;
  targetFloor: number;
  occupants: string[]; // person IDs
  maxCapacity: number;
  movingProgress: number; // 0-1
  movingStart: number; // timestamp
  movingDuration: number; // seconds to move between floors
  doors: {
    leftOpen: number; // 0-1, animation progress
    rightOpen: number; // 0-1
  };
}

/**
 * Camera target for follow camera
 */
export interface CameraTarget {
  x: number;
  y: number;
  z: number; // height = floor * floorHeight + offset
  focusX: number;
  focusY: number;
  focusZ: number;
}

/**
 * Stair climbing animation state
 */
export class StairClimber {
  static getVerticalPosition(progress: number): number {
    // Progress goes from 0 to 1 during stair climbing
    // Create a wave-like motion (step, step, step...)
    const step = Math.floor(progress * 4); // 4 steps
    const stepProgress = (progress * 4) - step;
    // Each step goes up 0.25 (1/4 of total height)
    return (step * 0.25) + (Math.sin(stepProgress * Math.PI) * 0.1);
  }

  static getRotationZ(progress: number): number {
    // Slight forward lean while climbing
    return Math.sin(progress * Math.PI) * 0.15; // -0.15 to 0.15 radians
  }
}

/**
 * Elevator cage animation state
 */
export class ElevatorAnimator {
  static getDoorOpenProgress(isOpening: boolean, progress: number): number {
    // progress: 0 = closed, 0.5 = opening/closing, 1 = fully open
    if (isOpening) {
      return Math.min(progress * 2, 1); // Open in first half of time
    } else {
      return Math.max(1 - progress * 2, 0); // Close in first half
    }
  }

  static getCageVerticalPosition(progress: number, startFloor: number, endFloor: number, floorHeight: number): number {
    // Smooth easing: cubic easeInOut
    const t = progress;
    const eased = t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2;
    return startFloor * floorHeight + (endFloor - startFloor) * floorHeight * eased;
  }
}

/**
 * Humanoid mesh builder
 * Creates realistic human-like shapes instead of cylinders
 */
export class HumanoidMeshBuilder {
  static createGeometry() {
    // Returns geometry specs for a humanoid shape:
    // Head: sphere at top
    // Torso: capsule in middle
    // Legs: two capsules at bottom
    return {
      head: {
        type: 'sphere',
        radius: 0.15,
        position: { x: 0, y: 0.65, z: 0 },
      },
      torso: {
        type: 'capsule',
        radius: 0.12,
        height: 0.5,
        position: { x: 0, y: 0.35, z: 0 },
      },
      leftLeg: {
        type: 'capsule',
        radius: 0.08,
        height: 0.4,
        position: { x: -0.08, y: 0.05, z: 0 },
      },
      rightLeg: {
        type: 'capsule',
        radius: 0.08,
        height: 0.4,
        position: { x: 0.08, y: 0.05, z: 0 },
      },
      leftArm: {
        type: 'capsule',
        radius: 0.05,
        height: 0.35,
        position: { x: -0.2, y: 0.45, z: 0 },
      },
      rightArm: {
        type: 'capsule',
        radius: 0.05,
        height: 0.35,
        position: { x: 0.2, y: 0.45, z: 0 },
      },
    };
  }

  static getLegAnimationRotation(progress: number, isWalking: boolean): number {
    // Swing legs while walking
    if (!isWalking) return 0;
    return Math.sin(progress * Math.PI * 2) * 0.3; // ±0.3 radians swing
  }

  static getArmAnimationRotation(progress: number, isWalking: boolean): number {
    // Swing arms in opposite direction to legs
    if (!isWalking) return 0;
    return Math.sin(progress * Math.PI * 2 + Math.PI) * 0.25; // ±0.25 radians (opposite)
  }
}

/**
 * Camera follow system for 3D view
 */
export class CameraFollowSystem {
  private targetPersonId: string | null = null;
  private cameraDistance: number = 5;
  private cameraHeight: number = 2;

  setFollowTarget(personId: string | null): void {
    this.targetPersonId = personId;
  }

  getCameraTarget(person: Person3D, floorHeight: number = 3.5): CameraTarget {
    const personZ = person.floor * floorHeight + person.verticalProgress * floorHeight;

    return {
      // Camera position (behind and above the person)
      x: person.x - this.cameraDistance * 0.7,
      y: person.y - this.cameraDistance * 0.7,
      z: personZ + this.cameraHeight,
      // Focus on the person
      focusX: person.x,
      focusY: person.y,
      focusZ: personZ + 0.8, // Focus on person's head area
    };
  }

  interpolateCamera(current: CameraTarget, target: CameraTarget, speed: number = 0.1): CameraTarget {
    // Smooth camera interpolation
    return {
      x: current.x + (target.x - current.x) * speed,
      y: current.y + (target.y - current.y) * speed,
      z: current.z + (target.z - current.z) * speed,
      focusX: current.focusX + (target.focusX - current.focusX) * speed,
      focusY: current.focusY + (target.focusY - current.focusY) * speed,
      focusZ: current.focusZ + (target.focusZ - current.focusZ) * speed,
    };
  }
}

/**
 * Performance optimization: Instance management
 */
export class PersonInstanceManager {
  private maxInstances: number;
  private activePersonCount: number = 0;

  constructor(maxInstances: number = 100) {
    this.maxInstances = maxInstances;
  }

  /**
   * Determine if person should be rendered at full quality
   * (LOD = Level of Detail)
   */
  getLOD(personIndex: number, cameraDistance: number): 'high' | 'medium' | 'low' {
    // Priority: people close to camera and early in list
    const distanceLOD = cameraDistance < 3 ? 'high' : cameraDistance < 8 ? 'medium' : 'low';
    const priorityLOD = personIndex < 20 ? 'high' : personIndex < 50 ? 'medium' : 'low';

    // Use worse LOD of the two
    const lods = ['high', 'medium', 'low'] as const;
    return lods[Math.max(lods.indexOf(distanceLOD), lods.indexOf(priorityLOD))];
  }

  /**
   * Instance count for THREE.js InstancedMesh
   */
  getInstanceCapacity(): number {
    return this.maxInstances;
  }

  setActivePersonCount(count: number): void {
    this.activePersonCount = Math.min(count, this.maxInstances);
  }

  getActivePersonCount(): number {
    return this.activePersonCount;
  }

  /**
   * Check if we've hit capacity
   */
  isFull(): boolean {
    return this.activePersonCount >= this.maxInstances;
  }
}

/**
 * Occupancy Simulation 3D Extensions
 *
 * Extend OccupancySimulation with 3D features:
 * - Track vertical transitions
 * - Manage elevators
 * - Calculate camera targets
 * - Optimize rendering
 */
export class OccupancySimulation3D {
  private elevatorCages: Map<string, ElevatorCage> = new Map();
  private stairTransitions: Map<string, VerticalTransition> = new Map();
  private cameraFollowSystem: CameraFollowSystem = new CameraFollowSystem();
  private instanceManager: PersonInstanceManager = new PersonInstanceManager(100);

  constructor() {
    this.initializeDefaultElevators();
    this.initializeDefaultStairs();
  }

  private initializeDefaultElevators(): void {
    // 2 elevators in the building
    this.elevatorCages.set('elevator-1', {
      id: 'elevator-1',
      x: 230,
      y: 170,
      currentFloor: 0,
      targetFloor: 0,
      occupants: [],
      maxCapacity: 8,
      movingProgress: 0,
      movingStart: 0,
      movingDuration: 3, // 3 seconds per floor
      doors: { leftOpen: 1, rightOpen: 1 }, // Start open at ground
    });

    this.elevatorCages.set('elevator-2', {
      id: 'elevator-2',
      x: 510,
      y: 170,
      currentFloor: 0,
      targetFloor: 0,
      occupants: [],
      maxCapacity: 8,
      movingProgress: 0,
      movingStart: 0,
      movingDuration: 3,
      doors: { leftOpen: 1, rightOpen: 1 },
    });
  }

  private initializeDefaultStairs(): void {
    // 2 stairwells in the building
    this.stairTransitions.set('stairs-1', {
      id: 'stairs-1',
      type: 'stairs',
      x: 220,
      y: 290,
      startFloor: 0,
      endFloor: 1,
      duration: 4, // 4 seconds to climb one floor
    });

    this.stairTransitions.set('stairs-1-up', {
      id: 'stairs-1-up',
      type: 'stairs',
      x: 220,
      y: 290,
      startFloor: 1,
      endFloor: 2,
      duration: 4,
    });

    this.stairTransitions.set('stairs-2', {
      id: 'stairs-2',
      type: 'stairs',
      x: 500,
      y: 360,
      startFloor: 0,
      endFloor: 1,
      duration: 4,
    });

    this.stairTransitions.set('stairs-2-up', {
      id: 'stairs-2-up',
      type: 'stairs',
      x: 500,
      y: 360,
      startFloor: 1,
      endFloor: 2,
      duration: 4,
    });
  }

  /**
   * Call person to use elevator
   */
  callElevator(personId: string, targetFloor: number): string | null {
    // Find nearest elevator
    let nearestId: string | null = null;
    let nearestDist = Infinity;

    for (const elevator of this.elevatorCages.values()) {
      const dist = Math.abs(elevator.currentFloor - targetFloor);
      if (dist < nearestDist && elevator.occupants.length < elevator.maxCapacity) {
        nearestDist = dist;
        nearestId = elevator.id;
      }
    }

    if (nearestId) {
      const elevator = this.elevatorCages.get(nearestId)!;
      elevator.occupants.push(personId);
      elevator.targetFloor = targetFloor;
    }

    return nearestId;
  }

  /**
   * Update elevator animations
   */
  updateElevators(deltaTime: number, currentTime: number): void {
    for (const elevator of this.elevatorCages.values()) {
      // If moving
      if (elevator.currentFloor !== elevator.targetFloor) {
        if (elevator.movingStart === 0) {
          elevator.movingStart = currentTime;
        }

        const elapsed = currentTime - elevator.movingStart;
        const totalDuration = Math.abs(elevator.targetFloor - elevator.currentFloor) * elevator.movingDuration;

        if (elapsed >= totalDuration) {
          // Finished moving
          elevator.currentFloor = elevator.targetFloor;
          elevator.movingProgress = 0;
          elevator.movingStart = 0;
          // Open doors
          elevator.doors.leftOpen = 1;
          elevator.doors.rightOpen = 1;
        } else {
          // Still moving
          elevator.movingProgress = elapsed / totalDuration;
          // Close doors while moving
          elevator.doors.leftOpen = 0;
          elevator.doors.rightOpen = 0;
        }
      } else {
        // Open doors at destination
        if (elevator.doors.leftOpen < 1) {
          elevator.doors.leftOpen = Math.min(elevator.doors.leftOpen + deltaTime * 1.5, 1);
          elevator.doors.rightOpen = Math.min(elevator.doors.rightOpen + deltaTime * 1.5, 1);
        }
      }
    }
  }

  /**
   * Get elevator cage for rendering
   */
  getElevatorCage(id: string): ElevatorCage | undefined {
    return this.elevatorCages.get(id);
  }

  getAllElevatorCages(): ElevatorCage[] {
    return Array.from(this.elevatorCages.values());
  }

  /**
   * Get stair for rendering
   */
  getStairTransition(id: string): VerticalTransition | undefined {
    return this.stairTransitions.get(id);
  }

  getAllStairs(): VerticalTransition[] {
    return Array.from(this.stairTransitions.values());
  }

  /**
   * Set camera follow target
   */
  setFollowTarget(personId: string | null): void {
    this.cameraFollowSystem.setFollowTarget(personId);
  }

  /**
   * Get camera target for person
   */
  getCameraTarget(person: Person3D): CameraTarget {
    return this.cameraFollowSystem.getCameraTarget(person);
  }

  /**
   * Get LOD for rendering
   */
  getLOD(personIndex: number, cameraDistance: number): 'high' | 'medium' | 'low' {
    return this.instanceManager.getLOD(personIndex, cameraDistance);
  }

  /**
   * Update active person count for instancing
   */
  setActivePersonCount(count: number): void {
    this.instanceManager.setActivePersonCount(count);
  }

  getActivePersonCount(): number {
    return this.instanceManager.getActivePersonCount();
  }

  getInstanceCapacity(): number {
    return this.instanceManager.getInstanceCapacity();
  }
}

export const occupancySimulation3D = new OccupancySimulation3D();
