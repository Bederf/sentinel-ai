/**
 * Dashboard Component - Grafana-inspired main dashboard view
 *
 * Features:
 * - Top row: 5 KPI stat panels
 * - Left column: Site overview grid
 * - Right column: Alert feed
 * - Middle: Energy consumption chart with filters
 * - Bottom: AI Failure Predictions
 *
 * Follows Grafana dashboard design with dark theme panels.
 */

import { useState, useEffect } from "react";
import {
  Building2,
  AlertTriangle,
  Cpu,
  TrendingUp,
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
        style={{ background: "var(--color-grafana-bg-canvas)" }}
      >
        <div className="text-center">
          <RefreshCw
            className="h-8 w-8 animate-spin mx-auto mb-4"
            style={{ color: "var(--color-grafana-orange)" }}
          />
          <span style={{ color: "var(--color-grafana-text-secondary)" }}>
            Loading dashboard data...
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
        style={{ background: "var(--color-grafana-bg-canvas)" }}
      >
        <div
          className="p-8 rounded text-center"
          style={{
            background: "var(--color-grafana-bg-panel)",
            border: "1px solid var(--color-grafana-border)",
          }}
        >
          <AlertTriangle
            className="h-12 w-12 mx-auto mb-4"
            style={{ color: "var(--color-status-error)" }}
          />
          <h2
            className="text-lg font-medium mb-2"
            style={{ color: "var(--color-grafana-text-primary)" }}
          >
            Error Loading Dashboard
          </h2>
          <p style={{ color: "var(--color-grafana-text-secondary)" }}>{error}</p>
        </div>
      </div>
    );
  }

  return (
    <div
      className="h-full overflow-y-auto p-4 md:p-6"
      style={{ background: "var(--color-grafana-bg-canvas)" }}
    >
      {/* KPI Row */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-4 mb-6">
        {stats && (
          <>
            <KPICard
              title="Total Sites"
              value={stats.total_sites}
              icon={<Building2 className="h-5 w-5" />}
              subtitle={`${normalSites} healthy, ${warningSites} warning`}
              accentColor="blue"
            />
            <KPICard
              title="Equipment"
              value={stats.total_equipment}
              icon={<Cpu className="h-5 w-5" />}
              delta={stats.uptime_percent ? stats.uptime_percent - 95 : 0}
              deltaText="vs 95% target"
              accentColor="cyan"
            />
            <KPICard
              title="Active Alerts"
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
              title="AI Predictions"
              value={predictions.length}
              icon={<TrendingUp className="h-5 w-5" />}
              subtitle="Failure predictions detected"
              accentColor="purple"
            />
          </>
        )}
      </div>

      {/* Main Content Grid - Two Columns */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Left Column - Site Overview Grid (2/3 width on large) */}
        <div className="lg:col-span-2">
          <div
            className="rounded overflow-hidden"
            style={{
              background: "var(--color-grafana-bg-panel)",
              border: "1px solid var(--color-grafana-border)",
            }}
          >
            {/* Panel Header */}
            <div
              className="p-4 flex items-center justify-between"
              style={{ borderBottom: "1px solid var(--color-grafana-border)" }}
            >
              <div className="flex items-center gap-3">
                <div
                  className="p-2 rounded"
                  style={{ background: "rgba(50, 116, 217, 0.15)" }}
                >
                  <Building2
                    className="h-5 w-5"
                    style={{ color: "var(--color-grafana-blue)" }}
                  />
                </div>
                <div>
                  <h3
                    className="font-medium text-sm"
                    style={{ color: "var(--color-grafana-text-primary)" }}
                  >
                    Site Overview
                  </h3>
                  <span
                    className="text-xs"
                    style={{ color: "var(--color-grafana-text-secondary)" }}
                  >
                    {sites.length} sites monitored
                  </span>
                </div>
              </div>
              <span
                className="text-xs px-2 py-1 rounded"
                style={{
                  background: "rgba(115, 191, 105, 0.15)",
                  color: "var(--color-status-success)",
                }}
              >
                {normalSites} healthy
              </span>
            </div>

            {/* Sites Grid */}
            <div className="p-4">
              {sites.length === 0 ? (
                <div className="text-center py-8">
                  <Building2
                    className="h-12 w-12 mx-auto mb-2"
                    style={{ color: "var(--color-grafana-text-disabled)" }}
                  />
                  <span style={{ color: "var(--color-grafana-text-secondary)" }}>
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
          className="rounded overflow-hidden"
          style={{
            background: "var(--color-grafana-bg-panel)",
            border: "1px solid var(--color-grafana-border)",
          }}
        >
          {/* Panel Header with Filters */}
          <div
            className="p-4 flex flex-wrap items-center justify-between gap-4"
            style={{ borderBottom: "1px solid var(--color-grafana-border)" }}
          >
            <h3
              className="font-medium text-sm"
              style={{ color: "var(--color-grafana-text-primary)" }}
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
                  background: "var(--color-grafana-bg-secondary)",
                  border: "1px solid var(--color-grafana-border)",
                  color: "var(--color-grafana-text-primary)",
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
                style={{ border: "1px solid var(--color-grafana-border)" }}
              >
                {TIME_PERIODS.map((period) => (
                  <button
                    key={period}
                    onClick={() => setSelectedDays(period)}
                    className="px-3 py-1.5 text-xs font-medium transition-colors"
                    style={{
                      background:
                        selectedDays === period
                          ? "var(--color-grafana-orange)"
                          : "var(--color-grafana-bg-secondary)",
                      color:
                        selectedDays === period
                          ? "white"
                          : "var(--color-grafana-text-secondary)",
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

      {/* AI Failure Predictions Section */}
      <div className="mt-6">
        <div
          className="rounded overflow-hidden"
          style={{
            background: "var(--color-grafana-bg-panel)",
            border: "1px solid var(--color-grafana-border)",
          }}
        >
          {/* Panel Header */}
          <div
            className="p-4 flex items-center justify-between"
            style={{ borderBottom: "1px solid var(--color-grafana-border)" }}
          >
            <div className="flex items-center gap-3">
              <div
                className="p-2 rounded"
                style={{ background: "rgba(184, 119, 217, 0.15)" }}
              >
                <TrendingUp
                  className="h-5 w-5"
                  style={{ color: "var(--color-grafana-purple)" }}
                />
              </div>
              <div>
                <h3
                  className="font-medium text-sm"
                  style={{ color: "var(--color-grafana-text-primary)" }}
                >
                  AI Failure Predictions
                </h3>
                <span
                  className="text-xs"
                  style={{ color: "var(--color-grafana-text-secondary)" }}
                >
                  Predictive maintenance insights
                </span>
              </div>
            </div>
            {predictions.length > 0 && (
              <div className="flex items-center gap-2">
                <span
                  className="text-xs px-2 py-1 rounded"
                  style={{
                    background: "rgba(184, 119, 217, 0.15)",
                    color: "var(--color-grafana-purple)",
                  }}
                >
                  {predictions.length} at-risk
                </span>
                <span
                  className="text-xs px-2 py-1 rounded"
                  style={{
                    background: "rgba(115, 191, 105, 0.15)",
                    color: "var(--color-status-success)",
                  }}
                >
                  {formatZAR(totalPotentialSavings)} savings
                </span>
              </div>
            )}
          </div>

          {/* Predictions Grid */}
          <div className="p-4">
            {predictions.length === 0 ? (
              <div className="text-center py-8">
                <TrendingUp
                  className="h-12 w-12 mx-auto mb-2"
                  style={{ color: "var(--color-grafana-text-disabled)" }}
                />
                <span style={{ color: "var(--color-grafana-text-secondary)" }}>
                  No failure predictions
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
