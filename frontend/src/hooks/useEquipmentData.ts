import { useState, useEffect } from 'react';
import type { Equipment } from '@/lib/api/sites';

// Mock equipment data for demo
const MOCK_EQUIPMENT: Equipment[] = [
  { id: '1', code: 'S002-CHILLER-B1-001', name: 'Chiller 1', equipment_type: 'CHILLER', health_score: 85, status: 'online', model: 'Trane' },
  { id: '2', code: 'S002-AHU-R-001', name: 'AHU Rooftop', equipment_type: 'AHU', health_score: 75, status: 'online', model: 'Carrier' },
  { id: '3', code: 'S002-FCU-L1-A', name: 'FCU Level 1 Zone A', equipment_type: 'FCU', health_score: 90, status: 'online', model: 'Daikin' },
  { id: '4', code: 'S002-VAV-L2-B', name: 'VAV Level 2 Zone B', equipment_type: 'VAV', health_score: 65, status: 'warning', model: 'Johnson' },
  { id: '5', code: 'S002-DALI-L1-01', name: 'DALI Controller L1', equipment_type: 'DALI', health_score: 95, status: 'online', model: 'Philips' },
];

export function useEquipmentData(siteId: string) {
  const [equipment, setEquipment] = useState<Equipment[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    // Use mock data for now - can be replaced with real API calls later
    setLoading(false);
    setEquipment(MOCK_EQUIPMENT);
    setError(null);

    // Refresh every 5 seconds for real-time updates
    const interval = setInterval(() => {
      // Simulate health score changes
      setEquipment((prev) =>
        prev.map((eq) => ({
          ...eq,
          health_score: Math.max(20, Math.min(100, eq.health_score + (Math.random() - 0.5) * 5)),
        }))
      );
    }, 5000);
    return () => clearInterval(interval);
  }, [siteId]);

  return { equipment, loading, error };
}
