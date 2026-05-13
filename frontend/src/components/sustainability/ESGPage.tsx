import React from 'react';
import { Leaf } from 'lucide-react';
import { SustainabilityDashboard } from './SustainabilityDashboard';

interface ESGPageProps {
  selectedBuilding?: {
    id: string;
    name: string;
    code: string;
  };
}

export function ESGPage({ selectedBuilding }: ESGPageProps) {
  const siteId = selectedBuilding?.id || '';
  const siteName = selectedBuilding?.name || 'Building';

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-900 via-slate-800 to-slate-900 p-6">
      <div className="mb-8">
        <div className="flex items-center gap-3 mb-2">
          <Leaf className="w-8 h-8 text-emerald-400" />
          <h1 className="text-3xl font-bold text-white">ESG & Sustainability</h1>
        </div>
        <p className="text-slate-400">{siteName} • Carbon Emissions & ESG Metrics</p>
      </div>

      <SustainabilityDashboard siteId={siteId} />

      <div className="mt-8 rounded-lg p-4" style={{ background: "var(--sentinel-bg-panel)", border: "1px solid var(--sentinel-border)" }}>
        <div className="flex gap-8">
          <div>
            <span style={{ color: "var(--sentinel-text-secondary)" }}>ESG Compliance Framework</span>
            <h3 className="text-sm font-medium mt-1" style={{ color: "var(--sentinel-text-primary)" }}>Green Star SA 5.1</h3>
            <span className="text-sm mt-2 block" style={{ color: "var(--sentinel-text-secondary)" }}>
              Tracking progress toward Green Star certification with real-time carbon emissions monitoring
            </span>
          </div>
          <div>
            <span style={{ color: "var(--sentinel-text-secondary)" }}>Data Sources</span>
            <h3 className="text-sm font-medium mt-1" style={{ color: "var(--sentinel-text-primary)" }}>Energy • Water • Waste</h3>
            <span className="text-sm mt-2 block" style={{ color: "var(--sentinel-text-secondary)" }}>
              Real-time monitoring of building operations with Scope 1/2/3 emissions tracking
            </span>
          </div>
          <div>
            <span style={{ color: "var(--sentinel-text-secondary)" }}>Benchmark Target</span>
            <h3 className="text-sm font-medium mt-1" style={{ color: "var(--sentinel-text-primary)" }}>10% Reduction/Year</h3>
            <span className="text-sm mt-2 block" style={{ color: "var(--sentinel-text-secondary)" }}>
              On track for carbon neutrality by 2030 with AI-optimized building controls
            </span>
          </div>
        </div>
      </div>
    </div>
  );
}

export default ESGPage;
