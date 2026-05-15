import { useState, useEffect, useCallback } from 'react';

import { energyCentreApi } from '../../lib/energyCentreApi';
import type { PowerMeter } from '../../lib/energyCentreApi';

interface PowerMeteringCardProps {
  siteId: string;
  compact?: boolean;
}

const touColors: Record<string, string> = {
  peak: 'var(--color-sentinel-red)',
  standard: 'var(--color-sentinel-amber)',
  'off-peak': 'var(--color-sentinel-green)',
};

const getTouColor = (period?: string): string => touColors[period || 'standard'] || 'var(--color-sentinel-text-secondary)';

export function PowerMeteringCard({ siteId, compact = false }: PowerMeteringCardProps) {
  const [meter, setMeter] = useState<PowerMeter | null>(null);
  const [loading, setLoading] = useState(true);

  const loadData = useCallback(async () => {
    try {
      const meters = await energyCentreApi.getMeters(siteId, 'main');
      if (meters.length > 0) {
        setMeter(meters[0]);
      }
      setLoading(false);
    } catch (_err) {
      setLoading(false);
    }
  }, [siteId]);

  useEffect(() => {
    loadData();
    const interval = setInterval(loadData, 5000);
    return () => clearInterval(interval);
  }, [loadData]);

  if (loading) {
    return (
      <div style={{background:'var(--color-sentinel-bg-panel)', border:'1px solid var(--color-sentinel-border)', borderRadius:8}}>
        <h3 className="text-sm font-semibold" style={{color:'var(--color-sentinel-text-primary)'}}>Power Metering</h3>
        <div className="animate-pulse h-32 bg-gray-100 rounded mt-4" />
      </div>
    );
  }

  if (!meter) {
    return (
      <div style={{background:'var(--color-sentinel-bg-panel)', border:'1px solid var(--color-sentinel-border)', borderRadius:8}}>
        <h3 className="text-sm font-semibold" style={{color:'var(--color-sentinel-text-primary)'}}>Power Metering</h3>
        <p className="text-sm" style={{color:'var(--color-sentinel-text-secondary)'}}>No meter data available</p>
      </div>
    );
  }

  if (compact) {
    return (
      <div style={{background:'var(--color-sentinel-bg-panel)', border:'1px solid var(--color-sentinel-border)', borderRadius:8, borderTop:'3px solid ' + getTouColor(meter.tou_period)}}>
        <div className="flex justify-between items-start">
          <div>
            <p className="text-sm" style={{color:'var(--color-sentinel-text-secondary)'}}>Power</p>
            <div className="text-3xl font-semibold tabular-nums">{meter.active_power_kw.toFixed(0)} kW</div>
          </div>
          <div className="text-right">
            <p className="text-sm" style={{color:'var(--color-sentinel-text-secondary)'}}>PF</p>
            <div className={`text-3xl font-semibold tabular-nums ${meter.power_factor < 0.9 ? 'text-amber-500' : ''}`}>
              {meter.power_factor.toFixed(2)}
            </div>
          </div>
        </div>
        {meter.tou_period && (
          <span className="inline-flex items-center px-2 py-1 text-xs font-medium rounded-full mt-2" style={{background:'color-mix(in srgb, ' + getTouColor(meter.tou_period) + ' 15%, transparent)', color: getTouColor(meter.tou_period)}}>
            {meter.tariff_type} - {meter.tou_period.toUpperCase()}
          </span>
        )}
      </div>
    );
  }

  return (
    <div style={{background:'var(--color-sentinel-bg-panel)', border:'1px solid var(--color-sentinel-border)', borderRadius:8}}>
      <div className="flex justify-between items-start">
        <div>
          <h3 className="text-sm font-semibold" style={{color:'var(--color-sentinel-text-primary)'}}>Main Incomer</h3>
          <p className="text-xs" style={{color:'var(--color-sentinel-text-secondary)'}}>{meter.manufacturer} {meter.model}</p>
        </div>
        {meter.tou_period && (
          <span className="inline-flex items-center px-2 py-1 text-xs font-medium rounded-full" style={{background:'color-mix(in srgb, ' + getTouColor(meter.tou_period) + ' 15%, transparent)', color: getTouColor(meter.tou_period)}}>
            {meter.tariff_type} - {meter.tou_period.toUpperCase()}
          </span>
        )}
      </div>

      <div className="grid grid-cols-4 gap-4 mt-4">
        <div style={{background:'var(--color-sentinel-bg-panel)', border:'1px solid var(--color-sentinel-border)', borderRadius:8, borderTop:'3px solid var(--color-sentinel-blue)'}}>
          <p className="text-sm" style={{color:'var(--color-sentinel-text-secondary)'}}>Active Power</p>
          <div className="text-3xl font-semibold tabular-nums">{meter.active_power_kw.toFixed(0)}</div>
          <p className="text-xs" style={{color:'var(--color-sentinel-text-secondary)'}}>kW</p>
        </div>
        <div style={{background:'var(--color-sentinel-bg-panel)', border:'1px solid var(--color-sentinel-border)', borderRadius:8, borderTop:'3px solid #a855f7'}}>
          <p className="text-sm" style={{color:'var(--color-sentinel-text-secondary)'}}>Apparent Power</p>
          <div className="text-3xl font-semibold tabular-nums">{meter.apparent_power_kva.toFixed(0)}</div>
          <p className="text-xs" style={{color:'var(--color-sentinel-text-secondary)'}}>kVA</p>
        </div>
        <div style={{background:'var(--color-sentinel-bg-panel)', border:'1px solid var(--color-sentinel-border)', borderRadius:8, borderTop:'3px solid ' + (meter.power_factor < 0.9 ? 'var(--color-sentinel-amber)' : 'var(--color-sentinel-green)')}}>
          <p className="text-sm" style={{color:'var(--color-sentinel-text-secondary)'}}>Power Factor</p>
          <div className="text-3xl font-semibold tabular-nums">{meter.power_factor.toFixed(2)}</div>
          <p className="text-xs" style={{color:'var(--color-sentinel-text-secondary)'}}>target 0.95</p>
        </div>
        <div style={{background:'var(--color-sentinel-bg-panel)', border:'1px solid var(--color-sentinel-border)', borderRadius:8, borderTop:'3px solid var(--color-sentinel-blue)'}}>
          <p className="text-sm" style={{color:'var(--color-sentinel-text-secondary)'}}>Frequency</p>
          <div className="text-3xl font-semibold tabular-nums">{meter.frequency_hz.toFixed(1)}</div>
          <p className="text-xs" style={{color:'var(--color-sentinel-text-secondary)'}}>Hz</p>
        </div>
      </div>

      {/* Voltage & Current */}
      <div className="mt-4 grid grid-cols-3 gap-2 text-center">
        <div>
          <p className="text-xs" style={{color:'var(--color-sentinel-text-secondary)'}}>L1</p>
          <p className="text-sm" style={{color:'var(--color-sentinel-text-primary)'}}>{meter.voltage_l1_n.toFixed(0)}V / {meter.current_l1.toFixed(0)}A</p>
        </div>
        <div>
          <p className="text-xs" style={{color:'var(--color-sentinel-text-secondary)'}}>L2</p>
          <p className="text-sm" style={{color:'var(--color-sentinel-text-primary)'}}>{meter.voltage_l2_n.toFixed(0)}V / {meter.current_l2.toFixed(0)}A</p>
        </div>
        <div>
          <p className="text-xs" style={{color:'var(--color-sentinel-text-secondary)'}}>L3</p>
          <p className="text-sm" style={{color:'var(--color-sentinel-text-primary)'}}>{meter.voltage_l3_n.toFixed(0)}V / {meter.current_l3.toFixed(0)}A</p>
        </div>
      </div>

      {/* Energy totals */}
      <div className="mt-4 pt-4 border-t" style={{borderColor:'var(--color-sentinel-border)'}}>
        <div className="flex justify-between">
          <div>
            <p className="text-xs" style={{color:'var(--color-sentinel-text-secondary)'}}>Total Import</p>
            <p className="font-bold" style={{color:'var(--color-sentinel-text-primary)'}}>{(meter.kwh_import / 1000).toFixed(1)} MWh</p>
          </div>
          <div className="text-right">
            <p className="text-xs" style={{color:'var(--color-sentinel-text-secondary)'}}>Max Demand</p>
            <p className="font-bold" style={{color:'var(--color-sentinel-text-primary)'}}>{meter.max_demand_kw.toFixed(0)} kW</p>
          </div>
        </div>
      </div>

      {/* Power Quality */}
      {(meter.thd_voltage_pct || meter.thd_current_pct) && (
        <div className="mt-4 pt-4 border-t" style={{borderColor:'var(--color-sentinel-border)'}}>
          <p className="text-xs mb-2" style={{color:'var(--color-sentinel-text-secondary)'}}>Power Quality</p>
          <div className="grid grid-cols-3 gap-2">
            {meter.thd_voltage_pct !== undefined && (
              <div>
                <p className="text-xs" style={{color:'var(--color-sentinel-text-secondary)'}}>THD-V</p>
                <p className="text-sm" style={{color: meter.thd_voltage_pct > 5 ? 'var(--color-sentinel-amber)' : 'var(--color-sentinel-text-primary)'}}>
                  {meter.thd_voltage_pct.toFixed(1)}%
                </p>
              </div>
            )}
            {meter.thd_current_pct !== undefined && (
              <div>
                <p className="text-xs" style={{color:'var(--color-sentinel-text-secondary)'}}>THD-I</p>
                <p className="text-sm" style={{color: meter.thd_current_pct > 15 ? 'var(--color-sentinel-amber)' : 'var(--color-sentinel-text-primary)'}}>
                  {meter.thd_current_pct.toFixed(1)}%
                </p>
              </div>
            )}
            {meter.voltage_unbalance_pct !== undefined && (
              <div>
                <p className="text-xs" style={{color:'var(--color-sentinel-text-secondary)'}}>Unbalance</p>
                <p className="text-sm" style={{color: meter.voltage_unbalance_pct > 2 ? 'var(--color-sentinel-amber)' : 'var(--color-sentinel-text-primary)'}}>
                  {meter.voltage_unbalance_pct.toFixed(1)}%
                </p>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

export default PowerMeteringCard;
