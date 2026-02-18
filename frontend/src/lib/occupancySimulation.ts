/**
 * OCCUPANCY SIMULATION ENGINE
 *
 * Manages animated people (dots) moving through building zones.
 * Supports multiple persona types with different behavior patterns.
 *
 * Phase 1: Basic zone-level movement
 * Phase 2: Multi-floor pathfinding with elevators/stairs
 * Phase 3: 3D integration
 * Phase 4: Backend sync with Grant scenario
 */

export type PersonaType = 'worker' | 'security' | 'cleaner' | 'visitor';
export type PersonState = 'entering' | 'working' | 'moving' | 'exiting' | 'idle';

export interface Point {
  x: number;
  y: number;
}

export interface Point3D extends Point {
  floor: number;
}

export interface ZoneConfig {
  id: string;
  name: string;
  x: number;
  y: number;
  w: number;
  h: number;
  maxOccupancy: number;
  type: 'office' | 'meeting' | 'common' | 'utility' | 'corridor' | 'entry';
  floor: number;
}

export interface Waypoint extends Point3D {
  action?: 'elevator' | 'stairs' | 'continue';
  waitTime?: number;
}

export interface Person {
  id: string;
  x: number;
  y: number;
  floor: number;
  vx: number; // Velocity x
  vy: number; // Velocity y
  targetX: number;
  targetY: number;
  targetFloor: number;
  zoneId: string;
  persona: PersonaType;
  state: PersonState;
  path: Waypoint[];
  entryTime: Date;
  scheduledExitTime: Date;
  moving: boolean; // For CSS transitions
  waitTimer?: number; // For elevator waits
}

export interface PersonaConfig {
  type: PersonaType;
  arrivalTimes: TimeRange[];
  departureTimes: TimeRange[];
  movementFrequency: number;
  preferredZones: string[];
  speed: number;
  color: string;
}

export interface TimeRange {
  start: string; // "HH:MM"
  end: string;
  peak: string;
}

export interface ZoneTarget {
  zoneId: string;
  targetOccupancy: number;
  maxOccupancy: number;
  personas?: Record<PersonaType, number>;
}

// ─────────────────────────────────────────────────────────────────
// PERSONA CONFIGURATIONS
// ─────────────────────────────────────────────────────────────────

export const PERSONAS: Record<PersonaType, PersonaConfig> = {
  worker: {
    type: 'worker',
    arrivalTimes: [
      { start: '07:00', end: '09:30', peak: '08:00' },
    ],
    departureTimes: [
      { start: '16:30', end: '19:00', peak: '17:00' },
    ],
    movementFrequency: 0.15,
    preferredZones: ['office', 'meeting', 'common'],
    speed: 40,
    color: 'rgba(34, 211, 238, 0.9)', // Cyan
  },
  security: {
    type: 'security',
    arrivalTimes: [
      { start: '06:00', end: '07:00', peak: '06:30' },
      { start: '18:00', end: '19:00', peak: '18:30' },
    ],
    departureTimes: [
      { start: '18:00', end: '19:00', peak: '18:30' },
      { start: '06:00', end: '07:00', peak: '06:30' },
    ],
    movementFrequency: 0.4,
    preferredZones: ['corridor', 'entry', 'utility'],
    speed: 50,
    color: 'rgba(168, 85, 247, 0.9)', // Purple
  },
  cleaner: {
    type: 'cleaner',
    arrivalTimes: [
      { start: '18:00', end: '19:00', peak: '18:30' },
    ],
    departureTimes: [
      { start: '22:00', end: '23:00', peak: '22:30' },
    ],
    movementFrequency: 0.6,
    preferredZones: ['all'],
    speed: 35,
    color: 'rgba(34, 197, 94, 0.9)', // Green
  },
  visitor: {
    type: 'visitor',
    arrivalTimes: [
      { start: '09:00', end: '16:00', peak: '10:00' },
    ],
    departureTimes: [
      { start: '10:00', end: '17:00', peak: '15:00' },
    ],
    movementFrequency: 0.3,
    preferredZones: ['entry', 'meeting', 'common'],
    speed: 30,
    color: 'rgba(245, 158, 11, 0.9)', // Orange
  },
};

// ─────────────────────────────────────────────────────────────────
// OCCUPANCY SIMULATION ENGINE
// ─────────────────────────────────────────────────────────────────

export class OccupancySimulation {
  private people: Map<string, Person> = new Map();
  private zones: Map<string, ZoneConfig> = new Map();
  private personas: Record<PersonaType, PersonaConfig>;
  private currentTime: Date = new Date();
  private nextPersonId: number = 0;
  private zoneTargets: Map<string, ZoneTarget> = new Map();
  private zonesArray: ZoneConfig[] = []; // For quick access by index

  constructor(zoneConfigs: ZoneConfig[], personas?: Record<PersonaType, PersonaConfig>) {
    this.personas = personas || PERSONAS;
    this.zonesArray = zoneConfigs;

    // Index zones by ID for quick lookup
    for (const zone of zoneConfigs) {
      this.zones.set(zone.id, zone);
    }
  }

  /**
   * Update simulation time (for backend sync)
   */
  setTime(time: Date): void {
    this.currentTime = new Date(time);
  }

  /**
   * Update target occupancy for a zone
   */
  updateZoneTarget(target: ZoneTarget): void {
    this.zoneTargets.set(target.zoneId, target);
    this.reconcileOccupancy(target);
  }

  /**
   * Reconcile current occupancy with target
   * Spawn or despawn people as needed
   */
  private reconcileOccupancy(target: ZoneTarget): void {
    const zone = this.zones.get(target.zoneId);
    if (!zone) return;

    const currentInZone = Array.from(this.people.values()).filter(
      p => p.zoneId === target.zoneId && p.state !== 'exiting'
    ).length;

    // Spawn new people if under target
    while (currentInZone + (this.people.size - Array.from(this.people.values()).filter(p => p.zoneId === target.zoneId).length) < target.targetOccupancy) {
      const persona = this.selectPersonaByTargets(target.personas);
      this.spawnPersonInZone(persona, target.zoneId);
    }

    // Mark people for exit if over target
    if (currentInZone > target.targetOccupancy) {
      const excess = currentInZone - target.targetOccupancy;
      let removed = 0;
      for (const person of this.people.values()) {
        if (person.zoneId === target.zoneId && person.state !== 'exiting' && removed < excess) {
          this.exitPerson(person);
          removed++;
        }
      }
    }
  }

  /**
   * Select persona based on target distribution
   */
  private selectPersonaByTargets(personas?: Record<PersonaType, number>): PersonaType {
    // If personas is empty or undefined, default to 'worker'
    const validPersonas = personas && Object.keys(personas).length > 0 ? personas : { worker: 1, security: 0, cleaner: 0, visitor: 0 };

    const rand = Math.random();
    let cumulative = 0;

    for (const [type, ratio] of Object.entries(validPersonas)) {
      cumulative += ratio;
      if (rand <= cumulative) return type as PersonaType;
    }

    return 'worker';
  }

  /**
   * Spawn person in zone
   */
  private spawnPersonInZone(persona: PersonaType, zoneId: string): Person {
    const zone = this.zones.get(zoneId);
    if (!zone) throw new Error(`Zone ${zoneId} not found`);

    const id = `person-${this.nextPersonId++}`;
    const margin = 14;
    const x = zone.x + margin + Math.random() * (zone.w - margin * 2);
    const y = zone.y + margin + Math.random() * (zone.h - margin * 2);

    const personaConfig = this.personas[persona];
    const exitTime = new Date(this.currentTime);
    const exitHour = this.parseTime(personaConfig.departureTimes[0]?.start || '17:00');
    exitTime.setHours(exitHour[0], exitHour[1]);

    const person: Person = {
      id,
      x,
      y,
      floor: zone.floor,
      vx: 0,
      vy: 0,
      targetX: x,
      targetY: y,
      targetFloor: zone.floor,
      zoneId,
      persona,
      state: 'idle',
      path: [],
      entryTime: new Date(this.currentTime),
      scheduledExitTime: exitTime,
      moving: false,
    };

    this.people.set(id, person);
    return person;
  }

  /**
   * Trigger person to leave building
   */
  private exitPerson(person: Person): void {
    person.state = 'exiting';
    person.scheduledExitTime = new Date(); // Exit immediately
  }

  /**
   * Parse time string "HH:MM" to [hours, minutes]
   */
  private parseTime(timeStr: string): [number, number] {
    const [h, m] = timeStr.split(':').map(Number);
    return [h, m];
  }

  /**
   * Find multi-floor path between zones on different floors
   * Returns waypoints including elevator/stairs transitions
   */
  private findMultiFloorPath(startZoneId: string, endZoneId: string): Waypoint[] {
    const startZone = this.zones.get(startZoneId);
    const endZone = this.zones.get(endZoneId);

    if (!startZone || !endZone) return [];

    const path: Waypoint[] = [];

    // Same floor: direct path
    if (startZone.floor === endZone.floor) {
      // Simple direct path (Phase 2: within-floor corridor movement)
      path.push({
        x: endZone.x + endZone.w / 2,
        y: endZone.y + endZone.h / 2,
        floor: endZone.floor,
        action: 'continue',
      });
      return path;
    }

    // Different floors: use elevator or stairs
    const verticalTransports = [
      // Elevator
      { id: 'lift-1', x: -2, y: 2, type: 'elevator' as const, waitTime: 15 },
      { id: 'lift-2', x: 2, y: 2, type: 'elevator' as const, waitTime: 15 },
      // Stairs
      { id: 'stairs-1', x: -6, y: 2, type: 'stairs' as const, waitTime: 0 },
      { id: 'stairs-2', x: 6, y: 2, type: 'stairs' as const, waitTime: 0 },
    ];

    // Pick nearest elevator/stairs (slightly prefer elevators for variety)
    const isUsingElevator = Math.random() < 0.6;
    const transport = isUsingElevator
      ? verticalTransports.find(t => t.type === 'elevator') || verticalTransports[0]
      : verticalTransports.find(t => t.type === 'stairs') || verticalTransports[0];

    if (!transport) return [];

    // 1. Move to elevator/stairs on current floor
    path.push({
      x: transport.x,
      y: transport.y,
      floor: startZone.floor,
      action: 'continue',
    });

    // 2. Wait for elevator/stairs (with action marker)
    path.push({
      x: transport.x,
      y: transport.y,
      floor: startZone.floor,
      action: transport.type,
      waitTime: transport.waitTime,
    });

    // 3. Exit on destination floor
    path.push({
      x: transport.x,
      y: transport.y,
      floor: endZone.floor,
      action: 'continue',
    });

    // 4. Move to destination zone
    path.push({
      x: endZone.x + endZone.w / 2,
      y: endZone.y + endZone.h / 2,
      floor: endZone.floor,
      action: 'continue',
    });

    return path;
  }

  /**
   * Spawn person at building entrance
   */
  private handleArrival(persona: PersonaType, targetZoneId: string): Person {
    const targetZone = this.zones.get(targetZoneId);
    if (!targetZone) throw new Error(`Target zone ${targetZoneId} not found`);

    const entrance = this.zonesArray[0]; // Use first zone as entrance proxy
    const person = this.spawnPersonInZone(persona, targetZoneId);

    // Set entry state for visual effect
    person.state = 'entering';
    person.x = entrance.x;
    person.y = entrance.y;
    person.floor = entrance.floor;

    // Pathfind from entrance zone to target
    if (entrance.id !== targetZoneId) {
      person.path = this.findMultiFloorPath(entrance.id, targetZoneId);
    }

    return person;
  }

  /**
   * Mark person as departing
   */
  private handleDeparture(person: Person): void {
    person.state = 'exiting';
    // Pathfind to nearest exit
    const exitZone = this.zonesArray.find(z => z.type === 'entry') || this.zonesArray[0];
    if (person.zoneId !== exitZone.id) {
      person.path = this.findMultiFloorPath(person.zoneId, exitZone.id);
    }
    person.scheduledExitTime = new Date(); // Leave immediately
  }

  /**
   * Main animation tick (called at 60fps)
   * Handles zone movement, multi-floor pathfinding, and departures
   */
  tick(deltaTime: number): Person[] {
    const toRemove: string[] = [];

    for (const [id, person] of this.people.entries()) {
      // Check if person should exit
      if (new Date() >= person.scheduledExitTime && person.state !== 'exiting') {
        this.handleDeparture(person);
      }

      // Remove person if exiting and reached final destination
      if (person.state === 'exiting' && person.path.length === 0) {
        toRemove.push(id);
        continue;
      }

      // Handle waypoint-based movement (multi-floor paths)
      if (person.path.length > 0) {
        const currentWaypoint = person.path[0];

        // Handle elevator/stairs transitions
        if (currentWaypoint.action === 'elevator' || currentWaypoint.action === 'stairs') {
          // Start waiting at transport
          person.waitTimer = (person.waitTimer || 0) + deltaTime;

          // Set position to elevator/stairs
          person.x = currentWaypoint.x;
          person.y = currentWaypoint.y;

          // Wait time elapsed: transition to destination floor
          if (person.waitTimer >= (currentWaypoint.waitTime || 0)) {
            person.floor = currentWaypoint.floor; // Change floor instantly
            person.waitTimer = 0;
            person.path.shift(); // Move to next waypoint
            person.moving = false;
          } else {
            person.moving = false; // Frozen while waiting
          }
          continue;
        }

        // Regular waypoint movement
        const dx = currentWaypoint.x - person.x;
        const dy = currentWaypoint.y - person.y;
        const dist = Math.sqrt(dx * dx + dy * dy);

        if (dist < 2) {
          // Reached waypoint
          person.path.shift();
          if (person.path.length === 0) {
            // Reached final destination
            const zone = this.zones.get(person.zoneId);
            if (zone && person.state === 'entering') {
              person.state = 'idle';
            }
          }
          person.moving = false;
        } else {
          // Move toward waypoint
          const personaConfig = this.personas[person.persona];
          const speed = personaConfig.speed * deltaTime;
          person.x += (dx / dist) * speed;
          person.y += (dy / dist) * speed;
          person.floor = currentWaypoint.floor; // Update floor during movement
          person.moving = true;
        }
        continue;
      }

      // Zone idle: move around within zone randomly
      if (person.state === 'idle') {
        if (person.targetX !== person.x || person.targetY !== person.y) {
          const dx = person.targetX - person.x;
          const dy = person.targetY - person.y;
          const dist = Math.sqrt(dx * dx + dy * dy);

          if (dist > 2) {
            const personaConfig = this.personas[person.persona];
            const speed = personaConfig.speed * deltaTime;
            person.x += (dx / dist) * speed;
            person.y += (dy / dist) * speed;
            person.moving = true;
          } else {
            // Reached target, pick new random destination
            if (Math.random() < 0.01) {
              const zone = this.zones.get(person.zoneId);
              if (zone) {
                const margin = 14;
                person.targetX = zone.x + margin + Math.random() * (zone.w - margin * 2);
                person.targetY = zone.y + margin + Math.random() * (zone.h - margin * 2);
              }
            }
            person.moving = false;
          }
        } else {
          person.moving = false;
        }
      }
    }

    // Remove people who exited
    for (const id of toRemove) {
      this.people.delete(id);
    }

    return Array.from(this.people.values());
  }

  /**
   * Get all people
   */
  getPeople(): Person[] {
    return Array.from(this.people.values());
  }

  /**
   * Spawn person in specific zone (public method for initialization)
   */
  spawnPerson(persona: PersonaType, zoneId: string): Person {
    return this.spawnPersonInZone(persona, zoneId);
  }

  /**
   * Get people on specific floor
   */
  getPeopleOnFloor(floor: number): Person[] {
    return Array.from(this.people.values()).filter(p => p.floor === floor);
  }

  /**
   * Reset simulation
   */
  reset(): void {
    this.people.clear();
    this.nextPersonId = 0;
    this.zoneTargets.clear();
  }
}

/**
 * Utility to get persona color
 */
export function getPersonaColor(persona: PersonaType): string {
  return PERSONAS[persona]?.color || 'rgba(255, 255, 255, 0.9)';
}

/**
 * Utility to get persona label
 */
export function getPersonaLabel(persona: PersonaType): string {
  const labels: Record<PersonaType, string> = {
    worker: 'Worker',
    security: 'Security',
    cleaner: 'Cleaner',
    visitor: 'Visitor',
  };
  return labels[persona] || 'Unknown';
}
