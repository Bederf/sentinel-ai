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

  constructor(zoneConfigs: ZoneConfig[], personas?: Record<PersonaType, PersonaConfig>) {
    this.personas = personas || PERSONAS;

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
   * Main animation tick (called at 60fps)
   */
  tick(deltaTime: number): Person[] {
    // Update people
    const toRemove: string[] = [];

    for (const [id, person] of this.people.entries()) {
      // Check if person should exit
      if (new Date() >= person.scheduledExitTime && person.state !== 'exiting') {
        this.exitPerson(person);
      }

      // Remove person if exiting and path is empty
      if (person.state === 'exiting' && person.path.length === 0) {
        toRemove.push(id);
        continue;
      }

      // Move toward target within zone (Phase 1: no multi-floor yet)
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
          // Reached target, pick new target in zone
          if (person.state === 'idle' && Math.random() < 0.01) {
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
