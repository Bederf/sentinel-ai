import { useState, useEffect, useRef, useCallback } from 'react';
import { Download, Loader2, Building2, AlertTriangle } from 'lucide-react';
import { api } from '@/lib/api';
import type { Equipment } from '@/lib/api';

interface GroupedEquipment {
  [floor: string]: {
    [zone: string]: Equipment[];
  };
}

function parseLocation(location: string | undefined): { floor: string; zone: string } {
  if (!location) return { floor: "Unknown", zone: "Unknown" };

  const loc = location.trim();

  const floorMatch = loc.match(/[Ff]loor\s+(\S+)/);
  const floor = floorMatch ? floorMatch[1] : "Unknown";

  const zoneMatch = loc.match(/[Zz]one\s+(\S+)/);
  const zone = zoneMatch ? zoneMatch[1] : "General";

  if (floor === "Unknown") {
    const parts = loc.split(/[,/,-]/).map(s => s.trim()).filter(Boolean);
    if (parts.length >= 2) {
      return { floor: parts[0], zone: parts[1] };
    }
    return { floor: parts[0] || "Unknown", zone: "General" };
  }

  return { floor, zone };
}

function buildMermaidDefinition(siteName: string, grouped: GroupedEquipment): string {
  const lines: string[] = ['graph TD'];
  const siteNode = 'SITE';

  lines.push(`    ${siteNode}["${escapeLabel(siteName)}"]`);

  let floorIdx = 0;
  for (const [floor, zones] of Object.entries(grouped)) {
    const floorNode = `F${floorIdx}`;
    lines.push(`    subgraph ${floorNode}["${escapeLabel(`Floor ${floor}`)}"]`);

    let zoneIdx = 0;
    for (const [zone, devices] of Object.entries(zones)) {
      const zoneNode = `Z${floorIdx}_${zoneIdx}`;
      lines.push(`        subgraph ${zoneNode}["${escapeLabel(`Zone ${zone}`)}"]`);

      devices.forEach((device, di) => {
        const devNode = `D${floorIdx}_${zoneIdx}_${di}`;
        const deviceLabel = device.name || device.id;
        const deviceType = device.type ? ` (${device.type})` : '';
        const statusIcon = device.status === 'online' || device.status === 'normal' ? '✅' :
                          device.status === 'warning' || device.status === 'needs_attention' ? '⚠️' :
                          device.status === 'critical' || device.status === 'offline' ? '❌' : '⚪';
        lines.push(`            ${devNode}["${statusIcon} ${escapeLabel(deviceLabel)}${escapeLabel(deviceType)}"]`);
      });

      lines.push('        end');
      zoneIdx++;
    }

    lines.push('    end');
    floorIdx++;
  }

  return lines.join('\n');
}

function escapeLabel(text: string): string {
  return text.replace(/"/g, '#quot;').replace(/\(/g, '#40;').replace(/\)/g, '#41;');
}

interface SiteSchematicViewProps {
  siteId: string;
  siteName?: string;
}

export function SiteSchematicView({ siteId, siteName }: SiteSchematicViewProps) {
  const [equipment, setEquipment] = useState<Equipment[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [exporting, setExporting] = useState(false);
  const [mermaidDef, setMermaidDef] = useState('');
  const mermaidContainerRef = useRef<HTMLDivElement>(null);
  const renderedRef = useRef(false);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);

    api.getSiteEquipment(siteId)
      .then((res) => {
        if (cancelled) return;
        const eqList = res.equipment || [];
        setEquipment(eqList);

        const grouped: GroupedEquipment = {};
        for (const eq of eqList) {
          const { floor, zone } = parseLocation(eq.location);
          if (!grouped[floor]) grouped[floor] = {};
          if (!grouped[floor][zone]) grouped[floor][zone] = [];
          grouped[floor][zone].push(eq);
        }

        const def = buildMermaidDefinition(siteName || siteId, grouped);
        setMermaidDef(def);
        setLoading(false);
      })
      .catch((err) => {
        if (cancelled) return;
        setError(err instanceof Error ? err.message : 'Failed to load equipment');
        setLoading(false);
      });

    return () => { cancelled = true; };
  }, [siteId, siteName]);

  useEffect(() => {
    if (!mermaidDef || !mermaidContainerRef.current || renderedRef.current) return;

    import('mermaid').then((mermaid) => {
      mermaid.default.initialize({
        theme: 'base',
        themeVariables: {
          primaryColor: '#1a1a2e',
          primaryTextColor: '#e0e0e0',
          primaryBorderColor: '#333',
          lineColor: '#555',
          secondaryColor: '#16213e',
          tertiaryColor: '#0f3460',
          fontSize: '13px',
        },
        flowchart: { useMaxWidth: true, htmlLabels: true, curve: 'basis' },
      });

      const el = mermaidContainerRef.current;
      if (!el) return;

      el.innerHTML = '';
      const pre = document.createElement('pre');
      pre.className = 'mermaid';
      pre.textContent = mermaidDef;
      el.appendChild(pre);

      mermaid.default.run({ nodes: [pre] }).then(() => {
        renderedRef.current = true;
      });
    });
  }, [mermaidDef]);

  const handleExport = useCallback(async () => {
    const svgEl = mermaidContainerRef.current?.querySelector('svg');
    if (!svgEl) return;

    setExporting(true);
    try {
      const svgData = new XMLSerializer().serializeToString(svgEl);
      const svgBlob = new Blob([svgData], { type: 'image/svg+xml;charset=utf-8' });
      const url = URL.createObjectURL(svgBlob);

      const img = new Image();
      img.onload = () => {
        const canvas = document.createElement('canvas');
        canvas.width = svgEl.clientWidth * 2;
        canvas.height = svgEl.clientHeight * 2;
        const ctx = canvas.getContext('2d');
        if (!ctx) { setExporting(false); return; }
        ctx.scale(2, 2);
        ctx.drawImage(img, 0, 0);

        canvas.toBlob((blob) => {
          if (!blob) { setExporting(false); return; }
          const a = document.createElement('a');
          a.href = URL.createObjectURL(blob);
          a.download = `${siteName || siteId}-site-schematic.png`;
          a.click();
          URL.revokeObjectURL(a.href);
          setExporting(false);
        }, 'image/png');
      };
      img.src = url;
    } catch {
      setExporting(false);
    }
  }, [siteId, siteName]);

  if (loading) {
    return (
      <div className="flex flex-col items-center justify-center py-16 gap-3">
        <Loader2 className="w-8 h-8 animate-spin" style={{ color: 'var(--color-sentinel-blue)' }} />
        <p className="text-sm" style={{ color: 'var(--color-sentinel-text-secondary)' }}>
          Loading site equipment...
        </p>
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex items-start gap-2 p-4 rounded text-sm" style={{
        background: 'var(--color-sentinel-red)11',
        border: '1px solid var(--color-sentinel-red)',
        color: 'var(--color-sentinel-red)',
      }}>
        <AlertTriangle className="w-4 h-4 mt-0.5 shrink-0" />
        <span>{error}</span>
      </div>
    );
  }

  if (equipment.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center py-16 gap-3">
        <Building2 className="w-12 h-12" style={{ color: 'var(--color-sentinel-text-secondary)' }} />
        <p className="text-sm" style={{ color: 'var(--color-sentinel-text-secondary)' }}>
          No equipment found for this site. Upload a CSV export to build a schematic.
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h3 className="text-lg font-semibold" style={{ color: 'var(--color-sentinel-text-primary)' }}>
            Site Schematic
          </h3>
          <p className="text-xs mt-1" style={{ color: 'var(--color-sentinel-text-secondary)' }}>
            {equipment.length} devices across {Object.keys(equipment.reduce((acc, eq) => {
              const { floor } = parseLocation(eq.location);
              acc[floor] = true;
              return acc;
            }, {} as Record<string, boolean>)).length} floors
          </p>
        </div>
        <button
          onClick={handleExport}
          disabled={exporting}
          className="flex items-center gap-2 px-3 py-2 rounded text-sm font-medium transition-opacity disabled:opacity-50"
          style={{
            background: 'var(--color-sentinel-blue)',
            color: '#fff',
          }}
        >
          {exporting ? (
            <Loader2 className="w-4 h-4 animate-spin" />
          ) : (
            <Download className="w-4 h-4" />
          )}
          Export PNG
        </button>
      </div>

      <div
        className="rounded-lg p-4 overflow-auto"
        style={{
          background: 'var(--color-sentinel-bg-secondary)',
          border: '1px solid var(--color-sentinel-border)',
          minHeight: '400px',
        }}
      >
        <div ref={mermaidContainerRef} className="flex justify-center min-h-[300px]" />
      </div>
    </div>
  );
}
