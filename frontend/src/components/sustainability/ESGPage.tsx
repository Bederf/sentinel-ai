/**
 * ESG Page - Sustainability Dashboard
 *
 * Displays carbon emissions tracking, ESG metrics, and Green Star progress
 * for facilities teams to track building sustainability performance.
 */

import React from 'react';
import { Leaf } from 'lucide-react';
import { Card, Title, Text } from '@tremor/react';
import { SustainabilityDashboard } from './SustainabilityDashboard';

interface ESGPageProps {
  selectedBuilding?: {
    id: string;
    name: string;
    code: string;
  };
}

export function ESGPage({ selectedBuilding }: ESGPageProps) {
  const buildingId = selectedBuilding?.id || 'site-002';
  const buildingName = selectedBuilding?.name || 'Sandton City Office Tower';

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-900 via-slate-800 to-slate-900 p-6">
      {/* Header */}
      <div className="mb-8">
        <div className="flex items-center gap-3 mb-2">
          <Leaf className="w-8 h-8 text-emerald-400" />
          <h1 className="text-3xl font-bold text-white">ESG & Sustainability</h1>
        </div>
        <p className="text-slate-400">{buildingName} • Carbon Emissions & ESG Metrics</p>
      </div>

      {/* Main Dashboard */}
      <SustainabilityDashboard siteId={buildingId} />

      {/* Footer Info */}
      <Card className="mt-8 bg-slate-800/40 border border-slate-700">
        <div className="flex gap-8">
          <div>
            <Text className="text-slate-400">ESG Compliance Framework</Text>
            <Title className="text-white">Green Star SA 5.1</Title>
            <Text className="text-slate-400 text-sm mt-2">
              Tracking progress toward Green Star certification with real-time carbon emissions monitoring
            </Text>
          </div>
          <div>
            <Text className="text-slate-400">Data Sources</Text>
            <Title className="text-white">Energy • Water • Waste</Title>
            <Text className="text-slate-400 text-sm mt-2">
              Real-time monitoring of building operations with Scope 1/2/3 emissions tracking
            </Text>
          </div>
          <div>
            <Text className="text-slate-400">Benchmark Target</Text>
            <Title className="text-white">10% Reduction/Year</Title>
            <Text className="text-slate-400 text-sm mt-2">
              On track for carbon neutrality by 2030 with AI-optimized building controls
            </Text>
          </div>
        </div>
      </Card>
    </div>
  );
}

export default ESGPage;
