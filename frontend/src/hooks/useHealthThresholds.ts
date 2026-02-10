import { useState, useEffect } from "react";
import api from '@/lib/api';

export interface HealthThresholds {
  healthy: number;
  warning: number;
  critical: number;
}

export function useHealthThresholds() {
  const [thresholds, setThresholds] = useState<HealthThresholds>({
    healthy: 90,
    warning: 70,
    critical: 0,
  });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const fetchThresholds = async () => {
      try {
        const data = await api.getHealthThresholds();
        setThresholds(data);
        setError(null);
      } catch (err) {
        console.error("Failed to fetch health thresholds:", err);
        setError("Failed to load health thresholds");
      } finally {
        setLoading(false);
      }
    };

    fetchThresholds();
  }, []);

  const updateThresholds = async (newThresholds: HealthThresholds) => {
    try {
      const updated = await api.updateHealthThresholds(newThresholds);
      setThresholds(updated);
      setError(null);
      return true;
    } catch (err: any) {
      console.error("Failed to update health thresholds:", err);
      setError(err.message || "Failed to update health thresholds");
      return false;
    }
  };

  return { thresholds, loading, error, updateThresholds };
}
