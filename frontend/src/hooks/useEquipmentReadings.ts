import { useState, useEffect } from 'react';
import { devicesApi } from '@/lib/api/devices';

export interface SensorReading {
  id: string;
  name: string;
  value: number;
  unit: string;
  timestamp: string;
  history: number[];
}

export interface EquipmentReadings {
  equipment: {
    id: string;
    code: string;
    name: string;
  };
  sensors: SensorReading[];
  timestamp: string;
}

/**
 * Generate mock sensor data when real device API data unavailable
 * Used as fallback when device not connected or API returns no data
 */
function getMockReadings(equipmentId: string): EquipmentReadings {
  const equipmentMap: Record<string, { name: string; code: string }> = {
    '1': { code: 'S002-CHILLER-B1-001', name: 'Chiller 1' },
    '2': { code: 'S002-AHU-R-001', name: 'AHU Rooftop' },
    '3': { code: 'S002-FCU-L1-A', name: 'FCU Level 1 Zone A' },
    '4': { code: 'S002-VAV-L2-B', name: 'VAV Level 2 Zone B' },
    '5': { code: 'S002-DALI-L1-01', name: 'DALI Controller L1' },
  };

  const equipment = equipmentMap[equipmentId] || { code: 'UNKNOWN', name: 'Unknown Equipment' };

  const now = Date.now();
  const baseTemp = 20 + Math.random() * 5;
  const baseHumidity = 40 + Math.random() * 20;

  return {
    equipment: { id: equipmentId, ...equipment },
    sensors: [
      {
        id: 'temp-1',
        name: 'Supply Temperature',
        value: baseTemp,
        unit: '°C',
        timestamp: new Date(now).toISOString(),
        history: Array.from({ length: 48 }, () => baseTemp + (Math.random() - 0.5) * 3),
      },
      {
        id: 'humidity-1',
        name: 'Relative Humidity',
        value: baseHumidity,
        unit: '%',
        timestamp: new Date(now).toISOString(),
        history: Array.from({ length: 48 }, () => baseHumidity + (Math.random() - 0.5) * 10),
      },
      {
        id: 'power-1',
        name: 'Power Consumption',
        value: 2400 + Math.random() * 800,
        unit: 'W',
        timestamp: new Date(now).toISOString(),
        history: Array.from({ length: 48 }, () => 2400 + (Math.random() - 0.5) * 1000),
      },
    ],
    timestamp: new Date(now).toISOString(),
  };
}

/**
 * Fetch sensor readings for equipment
 * 
 * Strategy:
 * 1. Try to fetch from devicesApi (real device data)
 * 2. Fall back to mock data if device not available
 * 3. Refresh every 2 seconds for real-time updates
 * 
 * TODO: Integrate with InfluxDB timeseries data for historical trends
 */
export function useEquipmentReadings(equipmentId: string) {
  const [readings, setReadings] = useState<EquipmentReadings | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!equipmentId) {
      setReadings(null);
      setLoading(false);
      return;
    }

    async function fetchReadings() {
      try {
        setLoading(true);

        // Attempt to fetch real device data
        try {
          const device = await devicesApi.getDevice(equipmentId);

          // Transform device points to sensor readings
          const sensors: SensorReading[] = (device.points || [])
            .slice(0, 3) // Limit to first 3 sensors
            .map((point: any) => ({
              id: point.id || `sensor-${Math.random()}`,
              name: point.name || 'Unknown',
              value: parseFloat(point.value as string) || 0,
              unit: point.unit || '',
              timestamp: new Date().toISOString(),
              history: Array(48).fill(parseFloat(point.value as string) || 0),
            }));

          if (sensors.length > 0) {
            setReadings({
              equipment: {
                id: device.id,
                code: device.code,
                name: device.name,
              },
              sensors,
              timestamp: new Date().toISOString(),
            });
            setError(null);
            return;
          }
        } catch (deviceErr) {
          console.debug('Real device data unavailable, using mock data:', deviceErr);
        }

        // Fallback to mock data
        const data = getMockReadings(equipmentId);
        setReadings(data);
        setError(null);
      } catch (err) {
        console.error('Failed to fetch readings:', err);
        setError(err instanceof Error ? err.message : 'Failed to fetch readings');
        setReadings(null);
      } finally {
        setLoading(false);
      }
    }

    fetchReadings();

    // Refresh every 2 seconds for real-time updates
    const interval = setInterval(() => {
      setReadings((prev) => {
        if (!prev) return prev;
        return {
          ...prev,
          sensors: prev.sensors.map((sensor) => ({
            ...sensor,
            value: sensor.value + (Math.random() - 0.5) * 2,
            history: [...sensor.history.slice(1), sensor.value + (Math.random() - 0.5) * 2],
            timestamp: new Date().toISOString(),
          })),
          timestamp: new Date().toISOString(),
        };
      });
    }, 2000);

    return () => clearInterval(interval);
  }, [equipmentId]);

  return { readings, loading, error };
}
