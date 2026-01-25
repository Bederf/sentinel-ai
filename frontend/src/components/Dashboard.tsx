/**
 * Dashboard Component - SENTINEL Risk Dashboard
 *
 * Features:
 * - Top row: 5 KPI stat panels
 * - Left column: Site protection overview grid
 * - Right column: Risk alert feed
 * - Middle: Energy consumption chart with filters
 * - Bottom: AI Risk Predictions
 *
 * Follows SENTINEL dark theme design.
 */

import { useState, useEffect } from "react";
import {
  Building2,
  AlertTriangle,
  Cpu,
  Shield,
  Bell,
  DollarSign,
  RefreshCw,
} from "lucide-react";
import api from "../lib/api";
import type { DashboardStats, Site, Prediction, EnergyDataPoint } from "../lib/api";
import { KPICard } from "./KPICard";
import { SiteCard } from "./SiteCard";
import { AlertFeed } from "./AlertFeed";
import { EnergyChart } from "./EnergyChart";
import { PredictionCard } from "./PredictionCard";
import { PredictionDetail } from "./PredictionDetail";

// Time period options for energy chart
const TIME_PERIODS = [7, 30, 90] as const;
type TimePeriod = (typeof TIME_PERIODS)[number];

export function Dashboard() {
  const [stats, setStats] = useState<DashboardStats | null>(null);
  const [sites, setSites] = useState<Site[]>([]);
  const [predictions, setPredictions] = useState<Prediction[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Prediction detail modal state
  const [selectedPrediction, setSelectedPrediction] = useState<Prediction | null>(null);
  const [isPredictionDetailOpen, setIsPredictionDetailOpen] = useState(false);

  // Energy chart state
  const [energyData, setEnergyData] = useState<EnergyDataPoint[]>([]);
  const [energyLoading, setEnergyLoading] = useState(false);
  const [selectedSiteId, setSelectedSiteId] = useState<string | null>(null);
  const [selectedDays, setSelectedDays] = useState<TimePeriod>(30);

  useEffect(() => {
    const loadDashboardData = async () => {
      try {
        setLoading(true);
        const [statsData, sitesData, predictionsData] = await Promise.all([
          api.getStats(),
          api.getSites(),
          api.getPredictions(),
        ]);
        setStats(statsData);
        setSites(sitesData);
        setPredictions(predictionsData.predictions);
        setError(null);
      } catch (err) {
        console.error("Failed to load dashboard data:", err);
        setError("Failed to load dashboard data");
      } finally {
        setLoading(false);
      }
    };

    loadDashboardData();
  }, []);

  // Load energy data when filters change
  useEffect(() => {
    const loadEnergyData = async () => {
      try {
        setEnergyLoading(true);
        const response = await api.getEnergy(selectedSiteId, selectedDays);
        setEnergyData(response.data);
      } catch (err) {
        console.error("Failed to load energy data:", err);
        setEnergyData([]);
      } finally {
        setEnergyLoading(false);
      }
    };

    loadEnergyData();
  }, [selectedSiteId, selectedDays]);

  // Calculate site status counts for KPI
  const normalSites = sites.filter((s) => s.status === "normal").length;
  const warningSites = sites.filter((s) => s.status === "warning").length;

  // Calculate total potential savings from all predictions
  const totalPotentialSavings = predictions.reduce((sum, prediction) => {
    if (prediction.financial_impact) {
      return sum + prediction.financial_impact.potential_loss_zar;
    }
    return sum;
  }, 0);

  // Format currency for display
  const formatZAR = (amount: number) =>
    new Intl.NumberFormat("en-ZA", {
      style: "currency",
      currency: "ZAR",
      minimumFractionDigits: 0,
      maximumFractionDigits: 0,
    }).format(amount);

  // Handle site card click
  const handleSiteClick = (site: Site) => {
    console.log("Site clicked:", site.name);
  };

  // Handle prediction card click
  const handlePredictionClick = (prediction: Prediction) => {
    setSelectedPrediction(prediction);
    setIsPredictionDetailOpen(true);
  };

  // Close prediction detail modal
  const closePredictionDetail = () => {
    setIsPredictionDetailOpen(false);
    setSelectedPrediction(null);
  };

  // Loading state
  if (loading) {
    return (
      <div
        className="h-full flex items-center justify-center"
        style={{ background: "var(--color-sentinel-bg-canvas)" }}
      >
        <div className="text-center">
          <RefreshCw
            className="h-8 w-8 animate-spin mx-auto mb-4"
            style={{ color: "var(--color-sentinel-amber)" }}
          />
          <span style={{ color: "var(--color-sentinel-text-secondary)" }}>
            Initializing SENTINEL protection...
          </span>
        </div>
      </div>
    );
  }

  // Error state
  if (error) {
    return (
      <div
        className="h-full flex items-center justify-center"
        style={{ background: "var(--color-sentinel-bg-canvas)" }}
      >
        <div
          className="p-8 rounded-md text-center"
          style={{
            background: "var(--color-sentinel-bg-panel)",
            border: "1px solid var(--color-sentinel-border)",
          }}
        >
          <AlertTriangle
            className="h-12 w-12 mx-auto mb-4"
            style={{ color: "var(--color-sentinel-red)" }}
          />
          <h2
            className="text-lg font-medium mb-2"
            style={{ color: "var(--color-sentinel-text-primary)" }}
          >
            Error Loading Dashboard
          </h2>
          <p style={{ color: "var(--color-sentinel-text-secondary)" }}>{error}</p>
        </div>
      </div>
    );
  }

  return (
    <div
      className="h-full overflow-y-auto p-4 md:p-6"
      style={{ background: "var(--color-sentinel-bg-canvas)" }}
    >
      {/* KPI Row */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-4 mb-6">
        {stats && (
          <>
            <KPICard
              title="Protected Sites"
              value={stats.total_sites}
              icon={<Building2 className="h-5 w-5" />}
              subtitle={`${normalSites} protected, ${warningSites} elevated`}
              accentColor="blue"
            />
            <KPICard
              title="Monitored Assets"
              value={stats.total_equipment}
              icon={<Cpu className="h-5 w-5" />}
              delta={stats.uptime_percent ? stats.uptime_percent - 95 : 0}
              deltaText="vs 95% target"
              accentColor="cyan"
            />
            <KPICard
              title="Active Risks"
              value={stats.active_alerts}
              icon={<Bell className="h-5 w-5" />}
              delta={stats.critical_alerts ? -(stats.critical_alerts * 10) : 0}
              isInverseTrend={true}
              deltaText={`${stats.critical_alerts} critical`}
              accentColor="orange"
            />
            <KPICard
              title="Potential Savings"
              value={formatZAR(totalPotentialSavings)}
              icon={<DollarSign className="h-5 w-5" />}
              subtitle="If all preventive actions taken"
              accentColor="green"
            />
            <KPICard
              title="Risk Predictions"
              value={predictions.length}
              icon={<Shield className="h-5 w-5" />}
              subtitle="AI-detected risk events"
              accentColor="purple"
            />
          </>
        )}
      </div>

      {/* Main Content Grid - Two Columns */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Left Column - Site Protection Overview (2/3 width on large) */}
        <div className="lg:col-span-2">
          <div
            className="rounded-md overflow-hidden"
            style={{
              background: "var(--color-sentinel-bg-panel)",
              border: "1px solid var(--color-sentinel-border)",
            }}
          >
            {/* Panel Header */}
            <div
              className="p-4 flex items-center justify-between"
              style={{ borderBottom: "1px solid var(--color-sentinel-border)" }}
            >
              <div className="flex items-center gap-3">
                <div
                  className="p-2 rounded"
                  style={{ background: "rgba(59, 130, 246, 0.15)" }}
                >
                  <Building2
                    className="h-5 w-5"
                    style={{ color: "var(--color-sentinel-blue)" }}
                  />
                </div>
                <div>
                  <h3
                    className="font-medium text-sm"
                    style={{ color: "var(--color-sentinel-text-primary)" }}
                  >
                    Site Protection Status
                  </h3>
                  <span
                    className="text-xs"
                    style={{ color: "var(--color-sentinel-text-secondary)" }}
                  >
                    {sites.length} sites under protection
                  </span>
                </div>
              </div>
              <span
                className="text-xs px-2 py-1 rounded"
                style={{
                  background: "rgba(16, 185, 129, 0.15)",
                  color: "var(--color-sentinel-green)",
                }}
              >
                {normalSites} protected
              </span>
            </div>

            {/* Sites Grid */}
            <div className="p-4">
              {sites.length === 0 ? (
                <div className="text-center py-8">
                  <Building2
                    className="h-12 w-12 mx-auto mb-2"
                    style={{ color: "var(--color-sentinel-text-disabled)" }}
                  />
                  <span style={{ color: "var(--color-sentinel-text-secondary)" }}>
                    No sites available
                  </span>
                </div>
              ) : (
                <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
                  {sites.map((site) => (
                    <SiteCard key={site.id} site={site} onClick={handleSiteClick} />
                  ))}
                </div>
              )}
            </div>
          </div>
        </div>

        {/* Right Column - Alerts Feed (1/3 width on large) */}
        <div className="lg:col-span-1">
          <AlertFeed limit={10} refreshInterval={30000} />
        </div>
      </div>

      {/* Energy Consumption Section */}
      <div className="mt-6">
        <div
          className="rounded-md overflow-hidden"
          style={{
            background: "var(--color-sentinel-bg-panel)",
            border: "1px solid var(--color-sentinel-border)",
          }}
        >
          {/* Panel Header with Filters */}
          <div
            className="p-4 flex flex-wrap items-center justify-between gap-4"
            style={{ borderBottom: "1px solid var(--color-sentinel-border)" }}
          >
            <h3
              className="font-medium text-sm"
              style={{ color: "var(--color-sentinel-text-primary)" }}
            >
              Energy Analytics
            </h3>

            <div className="flex items-center gap-4">
              {/* Site Filter */}
              <select
                value={selectedSiteId || ""}
                onChange={(e) => setSelectedSiteId(e.target.value || null)}
                className="text-sm rounded px-3 py-1.5"
                style={{
                  background: "var(--color-sentinel-bg-secondary)",
                  border: "1px solid var(--color-sentinel-border)",
                  color: "var(--color-sentinel-text-primary)",
                }}
              >
                <option value="">All Sites</option>
                {sites.map((site) => (
                  <option key={site.id} value={site.id}>
                    {site.name}
                  </option>
                ))}
              </select>

              {/* Time Period Tabs */}
              <div
                className="flex rounded overflow-hidden"
                style={{ border: "1px solid var(--color-sentinel-border)" }}
              >
                {TIME_PERIODS.map((period) => (
                  <button
                    key={period}
                    onClick={() => setSelectedDays(period)}
                    className="px-3 py-1.5 text-xs font-medium transition-colors"
                    style={{
                      background:
                        selectedDays === period
                          ? "var(--color-sentinel-amber)"
                          : "var(--color-sentinel-bg-secondary)",
                      color:
                        selectedDays === period
                          ? "white"
                          : "var(--color-sentinel-text-secondary)",
                    }}
                  >
                    {period}d
                  </button>
                ))}
              </div>
            </div>
          </div>

          {/* Chart Container */}
          <div className="p-4">
            <EnergyChart
              data={energyData}
              loading={energyLoading}
              selectedSiteId={selectedSiteId}
              days={selectedDays}
            />
          </div>
        </div>
      </div>

      {/* AI Risk Predictions Section */}
      <div className="mt-6">
        <div
          className="rounded-md overflow-hidden"
          style={{
            background: "var(--color-sentinel-bg-panel)",
            border: "1px solid var(--color-sentinel-border)",
          }}
        >
          {/* Panel Header */}
          <div
            className="p-4 flex items-center justify-between"
            style={{ borderBottom: "1px solid var(--color-sentinel-border)" }}
          >
            <div className="flex items-center gap-3">
              <div
                className="p-2 rounded"
                style={{ background: "rgba(245, 158, 11, 0.15)" }}
              >
                <Shield
                  className="h-5 w-5"
                  style={{ color: "var(--color-sentinel-amber)" }}
                />
              </div>
              <div>
                <h3
                  className="font-medium text-sm"
                  style={{ color: "var(--color-sentinel-text-primary)" }}
                >
                  Risk Intelligence
                </h3>
                <span
                  className="text-xs"
                  style={{ color: "var(--color-sentinel-text-secondary)" }}
                >
                  AI-powered predictive insights
                </span>
              </div>
            </div>
            {predictions.length > 0 && (
              <div className="flex items-center gap-2">
                <span
                  className="text-xs px-2 py-1 rounded"
                  style={{
                    background: "rgba(245, 158, 11, 0.15)",
                    color: "var(--color-sentinel-amber)",
                  }}
                >
                  {predictions.length} at-risk assets
                </span>
                <span
                  className="text-xs px-2 py-1 rounded"
                  style={{
                    background: "rgba(16, 185, 129, 0.15)",
                    color: "var(--color-sentinel-green)",
                  }}
                >
                  {formatZAR(totalPotentialSavings)} saveable
                </span>
              </div>
            )}
          </div>

          {/* Predictions Grid */}
          <div className="p-4">
            {predictions.length === 0 ? (
              <div className="text-center py-8">
                <Shield
                  className="h-12 w-12 mx-auto mb-2"
                  style={{ color: "var(--color-sentinel-text-disabled)" }}
                />
                <span style={{ color: "var(--color-sentinel-text-secondary)" }}>
                  No risk predictions detected
                </span>
              </div>
            ) : (
              <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
                {predictions.map((prediction) => (
                  <PredictionCard
                    key={prediction.id}
                    prediction={prediction}
                    onClick={() => handlePredictionClick(prediction)}
                  />
                ))}
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Prediction Detail Modal */}
      {selectedPrediction && (
        <PredictionDetail
          prediction={selectedPrediction}
          isOpen={isPredictionDetailOpen}
          onClose={closePredictionDetail}
        />
      )}
    </div>
  );
}

export default Dashboard;
