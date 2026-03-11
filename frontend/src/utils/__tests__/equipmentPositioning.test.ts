import { describe, expect, it } from 'vitest';

import {
  buildZoneKey,
  distributeEquipmentInZone,
  generateSyntheticZoneBounds,
  extractZoneNumber,
} from '@/utils/equipmentPositioning';
import type { Equipment } from '@/lib/api/sites';

function makeEquipment(code: string): Equipment {
  return {
    id: code,
    code,
    name: code,
    equipment_type: 'lighting',
    health_score: 100,
    status: 'online',
  };
}

describe('equipmentPositioning', () => {
  it('maps S002 equipment codes to five floor zones using the trailing zone digit', () => {
    expect(extractZoneNumber('S002-FCU-101')).toBe(1);
    expect(extractZoneNumber('S002-VAV-204')).toBe(4);
    expect(extractZoneNumber('S002-DALI-105')).toBe(5);
    expect(extractZoneNumber('S002-FCU-200')).toBe(5);
  });

  it('uses a shared plant zone for basement and roof equipment', () => {
    expect(buildZoneKey('S002-CHILLER-B1-001')).toBe('Zone-B1-plant');
    expect(buildZoneKey('S002-INV-R-002')).toBe('Zone-R-plant');
  });

  it('generates five full-depth zone strips across a standard floor plate', () => {
    const bounds = generateSyntheticZoneBounds('L1');

    expect(Object.keys(bounds)).toEqual([
      'Zone-L1-1',
      'Zone-L1-2',
      'Zone-L1-3',
      'Zone-L1-4',
      'Zone-L1-5',
    ]);

    expect(bounds['Zone-L1-1']).toMatchObject({
      minX: -14,
      maxX: -8.4,
      minZ: -9,
      maxZ: 9,
      width: 5.6,
      depth: 18,
    });

    expect(bounds['Zone-L1-5'].minX).toBeCloseTo(8.4, 6);
    expect(bounds['Zone-L1-5'].maxX).toBeCloseTo(14, 6);
    expect(bounds['Zone-L1-5'].minZ).toBe(-9);
    expect(bounds['Zone-L1-5'].maxZ).toBe(9);
    expect(bounds['Zone-L1-5'].width).toBeCloseTo(5.6, 6);
    expect(bounds['Zone-L1-5'].depth).toBe(18);
  });

  it('uses the full floor area for plant-floor equipment placement', () => {
    const bounds = generateSyntheticZoneBounds('B1');

    expect(bounds).toEqual({
      'Zone-B1-plant': expect.objectContaining({
        minX: -14,
        maxX: 14,
        minZ: -9,
        maxZ: 9,
        width: 28,
        depth: 18,
      }),
    });
  });

  it('distributes equipment across the full zone rectangle instead of clustering in one corner', () => {
    const zone = generateSyntheticZoneBounds('L2')['Zone-L2-3'];
    const equipment = Array.from({ length: 12 }, (_, idx) =>
      makeEquipment(`S002-LTG-203-${String(idx + 1).padStart(2, '0')}`)
    );

    const positions = Array.from(distributeEquipmentInZone(equipment, zone, 9.5).values());
    const xs = positions.map((pos) => pos.x);
    const zs = positions.map((pos) => pos.z);

    expect(Math.max(...xs) - Math.min(...xs)).toBeGreaterThan(zone.width * 0.45);
    expect(Math.max(...zs) - Math.min(...zs)).toBeGreaterThan(zone.depth * 0.6);
    positions.forEach((pos) => {
      expect(pos.x).toBeGreaterThanOrEqual(zone.minX);
      expect(pos.x).toBeLessThanOrEqual(zone.maxX);
      expect(pos.z).toBeGreaterThanOrEqual(zone.minZ);
      expect(pos.z).toBeLessThanOrEqual(zone.maxZ);
    });
  });
});
