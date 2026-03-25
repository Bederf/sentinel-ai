import { useEffect, useState } from "react";
import api from '@/lib/api';
import type { RiskThresholds } from '@/lib/api';

const DEFAULT_RISK_THRESHOLDS: RiskThresholds = {
  medium: 31,
  high: 61,
  critical: 81,
};

export function useRiskThresholds() {
  const [thresholds, setThresholds] = useState<RiskThresholds>(DEFAULT_RISK_THRESHOLDS);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const fetchThresholds = async () => {
      try {
        const data = await api.getRiskThresholds();
        setThresholds(data);
        setError(null);
      } catch (err) {
        console.error("Failed to fetch risk thresholds:", err);
        setError("Failed to load risk thresholds");
      } finally {
        setLoading(false);
      }
    };

    fetchThresholds();
  }, []);

  const updateThresholds = async (newThresholds: RiskThresholds) => {
    try {
      const updated = await api.updateRiskThresholds(newThresholds);
      setThresholds(updated);
      setError(null);
      return true;
    } catch (err: any) {
      console.error("Failed to update risk thresholds:", err);
      setError(err.message || "Failed to update risk thresholds");
      return false;
    }
  };

  return { thresholds, loading, error, updateThresholds };
}
