import { useCallback, useEffect, useState } from 'react';
import { ChevronDown, ChevronRight, Package, AlertTriangle, RefreshCw } from 'lucide-react';
import { authorizedFetch } from '@/lib/api';

interface SparePart {
  id: string;
  equipment_type: string;
  manufacturer: string | null;
  model: string | null;
  part_name: string;
  part_number: string | null;
  unit_cost_zar: number | null;
  typical_replacement_interval_days: number | null;
  criticality: string;
  source: string;
  spare_parts_inventory: {
    id: string;
    quantity_on_hand: number;
    min_threshold: number;
    location: string | null;
  } | null;
}

interface EquipmentPartsListProps {
  equipmentCode: string;
}

function getCriticalityColor(criticality: string): string {
  switch (criticality) {
    case 'critical':
      return 'var(--color-status-error)';
    case 'essential':
      return 'var(--color-status-warning)';
    default:
      return 'var(--color-grafana-text-secondary)';
  }
}

function getStockStatus(qty: number, min: number): { label: string; color: string } {
  if (qty <= 0) return { label: 'OUT OF STOCK', color: 'var(--color-status-error)' };
  if (qty <= min) return { label: `Low (${qty})`, color: 'var(--color-status-warning)' };
  return { label: `In stock (${qty})`, color: 'var(--color-status-ok)' };
}

export function EquipmentPartsList({ equipmentCode }: EquipmentPartsListProps) {
  const [parts, setParts] = useState<SparePart[]>([]);
  const [loading, setLoading] = useState(true);
  const [expanded, setExpanded] = useState(false);
  const [decrementing, setDecrementing] = useState<string | null>(null);

  const fetchParts = useCallback(async () => {
    setLoading(true);
    try {
      const resp = await authorizedFetch(`/api/parts/equipment/${equipmentCode}`);
      if (resp.ok) {
        const data = await resp.json();
        setParts(Array.isArray(data) ? data : []);
      }
    } catch {
      setParts([]);
    } finally {
      setLoading(false);
    }
  }, [equipmentCode]);

  useEffect(() => {
    if (expanded) {
      fetchParts();
    }
  }, [expanded, fetchParts]);

  async function handleDecrement(partId: string) {
    setDecrementing(partId);
    try {
      await authorizedFetch(`/api/parts/${partId}/decrement`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ quantity: 1 }),
      });
      await fetchParts();
    } catch {
      // silently fail
    } finally {
      setDecrementing(null);
    }
  }

  if (parts.length === 0 && !loading) {
    return null;
  }

  const criticalParts = parts.filter(p => p.criticality === 'critical');
  const lowStock = parts.filter(
    p => p.spare_parts_inventory && p.spare_parts_inventory.quantity_on_hand <= p.spare_parts_inventory.min_threshold
  );
  const hasWarnings = criticalParts.length > 0 || lowStock.length > 0;

  return (
    <div>
      <button
        onClick={() => setExpanded(!expanded)}
        className="flex items-center gap-2 w-full text-left py-2 px-1 rounded transition-colors hover:bg-white/5"
        style={{ color: 'var(--color-grafana-text-primary)' }}
      >
        {expanded ? <ChevronDown size={16} /> : <ChevronRight size={16} />}
        <Package size={16} />
        <span className="text-sm font-semibold">Spare Parts</span>
        <span className="text-xs ml-1" style={{ color: 'var(--color-grafana-text-secondary)' }}>
          ({parts.length})
        </span>
        {hasWarnings && (
          <AlertTriangle size={14} style={{ color: 'var(--color-status-warning)' }} />
        )}
      </button>

      {expanded && (
        <div className="ml-6 space-y-1.5">
          {loading ? (
            <div className="flex items-center gap-2 py-2">
              <RefreshCw size={14} className="animate-spin" />
              <span className="text-xs" style={{ color: 'var(--color-grafana-text-secondary)' }}>Loading parts...</span>
            </div>
          ) : (
            parts.map(part => {
              const inv = part.spare_parts_inventory;
              const qty = inv?.quantity_on_hand ?? 0;
              const min = inv?.min_threshold ?? 2;
              const stock = getStockStatus(qty, min);

              return (
                <div
                  key={part.id}
                  className="flex items-center justify-between py-1.5 px-2 rounded text-xs"
                  style={{ background: 'var(--color-grafana-bg-secondary, #1a1a2e)' }}
                >
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2">
                      <span className="font-medium truncate">{part.part_name}</span>
                      {part.part_number && (
                        <code className="text-[10px] px-1 py-0.5 rounded font-mono"
                          style={{ background: 'var(--color-grafana-bg-primary, #0f0f23)', color: 'var(--color-grafana-text-secondary)' }}>
                          {part.part_number}
                        </code>
                      )}
                      <span
                        className="text-[10px] px-1 py-0.5 rounded uppercase font-semibold"
                        style={{
                          background: `${getCriticalityColor(part.criticality)}20`,
                          color: getCriticalityColor(part.criticality),
                        }}
                      >
                        {part.criticality}
                      </span>
                    </div>
                  </div>

                  <div className="flex items-center gap-3 ml-3 shrink-0">
                    <span style={{ color: stock.color }} className="text-[11px] font-medium">
                      {stock.label}
                    </span>

                    {part.unit_cost_zar && (
                      <span style={{ color: 'var(--color-grafana-text-secondary)' }} className="text-[11px]">
                        R{part.unit_cost_zar.toLocaleString()}
                      </span>
                    )}

                    {qty > 0 && (
                      <button
                        onClick={() => handleDecrement(part.id)}
                        disabled={decrementing === part.id}
                        className="text-[10px] px-1.5 py-0.5 rounded hover:bg-white/10 disabled:opacity-40"
                        style={{ color: 'var(--color-grafana-text-secondary)' }}
                        title="Mark one as used"
                      >
                        {decrementing === part.id ? '...' : '-1'}
                      </button>
                    )}

                    <span className="text-[10px]" style={{ color: 'var(--color-grafana-text-secondary)' }}>
                      {part.source}
                    </span>
                  </div>
                </div>
              );
            })
          )}
        </div>
      )}
    </div>
  );
}
