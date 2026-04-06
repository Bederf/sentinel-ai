import { useState, useEffect, useCallback } from "react";
import { DollarSign } from "lucide-react";
import { authorizedFetch } from "../../lib/api/client";

interface TariffSummary {
  municipality: string;
  tariff_name: string;
  effective_date: string;
  energy_charge_c_kwh?: {
    summer?: { peak?: number; standard?: number; off_peak?: number };
    winter?: { peak?: number; standard?: number; off_peak?: number };
  };
  demand_charge_r_kva?: { summer?: number; winter?: number };
  service_charge_r_month?: number;
}

interface TariffManagerProps {
  siteId?: string;
  onError?: (error: string) => void;
  readOnly?: boolean;
}

export function TariffManager({
  siteId = "site-002",
  onError,
  readOnly: _readOnly = false,
}: TariffManagerProps) {
  const [tariffs, setTariffs] = useState<TariffSummary[]>([]);
  const [loading, setLoading] = useState(true);

  const fetchTariffs = useCallback(async () => {
    setLoading(true);
    try {
      const response = await authorizedFetch(`/api/municipal-billing/tariffs?site_id=${encodeURIComponent(siteId)}`);
      if (!response.ok) throw new Error("Failed to fetch tariffs");
      const data = await response.json();
      // data may be { tariffs: [...] } or direct array
      const list = Array.isArray(data) ? data : (data.tariffs || []);
      setTariffs(list);
    } catch {
      onError?.("Failed to load tariff data");
    } finally {
      setLoading(false);
    }
  }, [onError, siteId]);

  useEffect(() => { fetchTariffs(); }, [fetchTariffs]);

  const formatRate = (cents: number | undefined) => {
    if (cents === undefined || cents === null) return "—";
    return `${(cents / 100).toFixed(2)} R/kWh`;
  };

  const formatMoney = (rands: number | undefined) => {
    if (rands === undefined || rands === null) return "—";
    return `R ${rands.toLocaleString("en-ZA", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
  };

  return (
    <div className="glass-panel overflow-hidden">
      <div className="p-4 border-b" style={{ borderColor: "var(--color-sentinel-border)" }}>
        <div className="flex items-center gap-3">
          <div className="p-2 rounded" style={{ background: "rgba(245, 158, 11, 0.15)", color: "var(--color-sentinel-amber)" }}>
            <DollarSign className="h-5 w-5" />
          </div>
          <div>
            <h2 className="text-lg font-semibold" style={{ color: "var(--color-sentinel-text-primary)" }}>Tariff Configuration</h2>
            <p className="text-sm" style={{ color: "var(--color-sentinel-text-secondary)" }}>
              Active municipal tariff rates and TOU bands
            </p>
          </div>
        </div>
      </div>

      <div className="p-4">
        {loading ? (
          <p className="text-sm" style={{ color: "var(--color-sentinel-text-secondary)" }}>Loading tariff data...</p>
        ) : tariffs.length === 0 ? (
          <div className="text-center py-6">
            <p className="text-sm" style={{ color: "var(--color-sentinel-text-secondary)" }}>No tariffs configured</p>
            <p className="text-xs mt-1" style={{ color: "var(--color-sentinel-text-secondary)" }}>
              Tariffs can be ingested via POST /api/municipal-billing/tariffs/ingest
            </p>
          </div>
        ) : (
          <div className="space-y-4">
            {tariffs.map((tariff, idx) => (
              <div key={idx} className="rounded-lg p-4" style={{ background: "var(--color-sentinel-bg-secondary)", border: "1px solid var(--glass-border)" }}>
                <div className="flex items-center justify-between mb-3">
                  <div>
                    <h3 className="text-sm font-semibold" style={{ color: "var(--color-sentinel-text-primary)" }}>
                      {tariff.tariff_name || "Unknown Tariff"}
                    </h3>
                    <p className="text-xs" style={{ color: "var(--color-sentinel-text-secondary)" }}>
                      {tariff.municipality || "Unknown Municipality"} — Effective: {tariff.effective_date || "N/A"}
                    </p>
                  </div>
                  {tariff.service_charge_r_month && (
                    <div className="text-right">
                      <p className="text-[10px]" style={{ color: "var(--color-sentinel-text-secondary)" }}>Service Charge</p>
                      <p className="text-sm font-semibold" style={{ color: "var(--color-sentinel-amber)" }}>
                        {formatMoney(tariff.service_charge_r_month)}/mo
                      </p>
                    </div>
                  )}
                </div>

                {tariff.energy_charge_c_kwh && (
                  <div className="grid grid-cols-2 gap-3">
                    {/* Summer rates */}
                    {tariff.energy_charge_c_kwh.summer && (
                      <div>
                        <h4 className="text-xs font-medium mb-1.5" style={{ color: "var(--color-sentinel-text-primary)" }}>
                          Summer (Sep-May)
                        </h4>
                        <div className="space-y-1">
                          <div className="flex justify-between text-xs">
                            <span style={{ color: "var(--color-sentinel-red)" }}>Peak</span>
                            <span style={{ color: "var(--color-sentinel-text-primary)" }}>{formatRate(tariff.energy_charge_c_kwh.summer.peak)}</span>
                          </div>
                          <div className="flex justify-between text-xs">
                            <span style={{ color: "var(--color-sentinel-amber)" }}>Standard</span>
                            <span style={{ color: "var(--color-sentinel-text-primary)" }}>{formatRate(tariff.energy_charge_c_kwh.summer.standard)}</span>
                          </div>
                          <div className="flex justify-between text-xs">
                            <span style={{ color: "var(--color-sentinel-green)" }}>Off-peak</span>
                            <span style={{ color: "var(--color-sentinel-text-primary)" }}>{formatRate(tariff.energy_charge_c_kwh.summer.off_peak)}</span>
                          </div>
                        </div>
                      </div>
                    )}

                    {/* Winter rates */}
                    {tariff.energy_charge_c_kwh.winter && (
                      <div>
                        <h4 className="text-xs font-medium mb-1.5" style={{ color: "var(--color-sentinel-text-primary)" }}>
                          Winter (Jun-Aug)
                        </h4>
                        <div className="space-y-1">
                          <div className="flex justify-between text-xs">
                            <span style={{ color: "var(--color-sentinel-red)" }}>Peak</span>
                            <span style={{ color: "var(--color-sentinel-text-primary)" }}>{formatRate(tariff.energy_charge_c_kwh.winter.peak)}</span>
                          </div>
                          <div className="flex justify-between text-xs">
                            <span style={{ color: "var(--color-sentinel-amber)" }}>Standard</span>
                            <span style={{ color: "var(--color-sentinel-text-primary)" }}>{formatRate(tariff.energy_charge_c_kwh.winter.standard)}</span>
                          </div>
                          <div className="flex justify-between text-xs">
                            <span style={{ color: "var(--color-sentinel-green)" }}>Off-peak</span>
                            <span style={{ color: "var(--color-sentinel-text-primary)" }}>{formatRate(tariff.energy_charge_c_kwh.winter.off_peak)}</span>
                          </div>
                        </div>
                      </div>
                    )}
                  </div>
                )}

                {tariff.demand_charge_r_kva && (
                  <div className="mt-3 pt-3" style={{ borderTop: "1px solid var(--glass-border)" }}>
                    <div className="flex gap-4 text-xs">
                      <span style={{ color: "var(--color-sentinel-text-secondary)" }}>Demand Charge:</span>
                      <span style={{ color: "var(--color-sentinel-text-primary)" }}>
                        Summer: R{tariff.demand_charge_r_kva.summer?.toFixed(2)}/kVA
                        {tariff.demand_charge_r_kva.winter && ` | Winter: R${tariff.demand_charge_r_kva.winter.toFixed(2)}/kVA`}
                      </span>
                    </div>
                  </div>
                )}
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
