/**
 * Dashboard Component - Main dashboard view with grid layout
 *
 * Features:
 * - Top row: 4 KPI cards (sites, equipment, alerts, anomalies)
 * - Left column: Site grid using SiteCard components
 * - Right column: AlertFeed with auto-refresh
 * - Middle: Energy consumption charts with site and time period selection
 * - Bottom: AI Predictions & Anomalies section
 *
 * Requirements:
 * - DASH-01: Multi-site overview with all 15 sites
 * - DASH-02: Alert feed with severity colors
 * - DASH-03: Energy consumption charts
 * - DASH-04: KPI cards with trend indicators
 */

import { useState, useEffect } from "react";
import {
  Card,
  Title,
  Text,
  Grid,
  Col,
  Badge,
  Flex,
  TabGroup,
  TabList,
  Tab,
} from "@tremor/react";
import {
  Building2,
  AlertTriangle,
  Cpu,
  TrendingUp,
  Bell,
} from "lucide-react";
import api from "../lib/api";
import type { DashboardStats, Site, Prediction, EnergyDataPoint } from "../lib/api";
import { KPICard } from "./KPICard";
import { SiteCard } from "./SiteCard";
import { AlertFeed } from "./AlertFeed";
import { SiteSelector } from "./SiteSelector";
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
        // Load stats, sites, and predictions in parallel
        // AlertFeed fetches its own data
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

  // Handle site card click (placeholder for future navigation)
  const handleSiteClick = (site: Site) => {
    console.log("Site clicked:", site.name);
    // Future: navigate to site details page
  };

  // Handle prediction card click - open detail modal
  const handlePredictionClick = (prediction: Prediction) => {
    setSelectedPrediction(prediction);
    setIsPredictionDetailOpen(true);
  };

  // Close prediction detail modal
  const closePredictionDetail = () => {
    setIsPredictionDetailOpen(false);
    setSelectedPrediction(null);
  };

  if (loading) {
    return (
      <div className="h-full flex items-center justify-center">
        <div className="text-center">
          <div className="animate-spin h-8 w-8 border-4 border-bidvest-blue-600 border-t-transparent rounded-full mx-auto mb-4" />
          <Text>Loading dashboard data...</Text>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="h-full flex items-center justify-center">
        <Card className="p-8 text-center">
          <AlertTriangle className="h-12 w-12 text-red-500 mx-auto mb-4" />
          <Title>Error Loading Dashboard</Title>
          <Text className="text-gray-500">{error}</Text>
        </Card>
      </div>
    );
  }

  return (
    <div className="h-full overflow-y-auto p-6">
      {/* Header */}
      <div className="mb-6">
        <Title className="text-2xl font-bold text-gray-900">Dashboard</Title>
        <Text className="text-gray-500">
          Facilities Management Overview - Real-time monitoring
        </Text>
      </div>

      {/* KPI Row - DASH-04 */}
      <Grid numItems={1} numItemsSm={2} numItemsLg={4} className="gap-4 mb-6">
        <Col>
          <KPICard
            title="Total Sites"
            value={stats?.total_sites ?? 0}
            icon={<Building2 className="h-6 w-6 text-bidvest-blue-600" />}
            subtitle={`${normalSites} healthy, ${warningSites} warning`}
          />
        </Col>
        <Col>
          <KPICard
            title="Equipment"
            value={stats?.total_equipment ?? 0}
            icon={<Cpu className="h-6 w-6 text-bidvest-blue-600" />}
            delta={stats?.uptime_percent ? stats.uptime_percent - 95 : 0}
            deltaText="vs 95% target"
          />
        </Col>
        <Col>
          <KPICard
            title="Active Alerts"
            value={stats?.active_alerts ?? 0}
            icon={<Bell className="h-6 w-6 text-amber-500" />}
            delta={stats?.critical_alerts ? -(stats.critical_alerts * 10) : 0}
            isInverseTrend={true}
            deltaText={`${stats?.critical_alerts ?? 0} critical`}
          />
        </Col>
        <Col>
          <KPICard
            title="AI Predictions"
            value={predictions.length}
            icon={<TrendingUp className="h-6 w-6 text-purple-500" />}
            subtitle="Failure predictions detected"
          />
        </Col>
      </Grid>

      {/* Main Content Grid - Two Columns */}
      <Grid numItems={1} numItemsLg={3} className="gap-6">
        {/* Left Column - Site Overview Grid (2/3 width on large) - DASH-01 */}
        <Col numColSpan={1} numColSpanLg={2}>
          <Card className="h-full">
            <Flex justifyContent="between" alignItems="center" className="mb-4">
              <Title>Site Overview</Title>
              <Badge color="blue" size="sm">
                {sites.length} sites
              </Badge>
            </Flex>

            {sites.length === 0 ? (
              <div className="text-center py-8">
                <Building2 className="h-12 w-12 text-gray-300 mx-auto mb-2" />
                <Text className="text-gray-500">No sites available</Text>
              </div>
            ) : (
              <Grid numItems={1} numItemsMd={2} numItemsLg={3} className="gap-4">
                {sites.map((site) => (
                  <Col key={site.id}>
                    <SiteCard site={site} onClick={handleSiteClick} />
                  </Col>
                ))}
              </Grid>
            )}
          </Card>
        </Col>

        {/* Right Column - Alerts Feed (1/3 width on large) - DASH-02 */}
        <Col numColSpan={1} numColSpanLg={1}>
          <AlertFeed
            limit={10}
            refreshInterval={30000}
          />
        </Col>
      </Grid>

      {/* Energy Consumption Section - DASH-03 */}
      <div className="mt-6">
        <Card>
          <Flex
            justifyContent="between"
            alignItems="center"
            className="mb-4 flex-wrap gap-4"
          >
            <Title>Energy Analytics</Title>
            <Flex className="gap-4 flex-wrap">
              {/* Site Filter */}
              <div className="w-48">
                <SiteSelector
                  sites={sites}
                  selectedSiteId={selectedSiteId}
                  onSiteChange={setSelectedSiteId}
                />
              </div>
              {/* Time Period Tabs */}
              <TabGroup
                index={TIME_PERIODS.indexOf(selectedDays)}
                onIndexChange={(index) => setSelectedDays(TIME_PERIODS[index])}
              >
                <TabList variant="solid">
                  <Tab>7 Days</Tab>
                  <Tab>30 Days</Tab>
                  <Tab>90 Days</Tab>
                </TabList>
              </TabGroup>
            </Flex>
          </Flex>
          <EnergyChart
            data={energyData}
            loading={energyLoading}
            selectedSiteId={selectedSiteId}
            days={selectedDays}
          />
        </Card>
      </div>

      {/* Bottom Area - AI Failure Predictions */}
      <div className="mt-6">
        <Card>
          <Flex justifyContent="between" alignItems="center" className="mb-4">
            <Title>AI Failure Predictions</Title>
            {predictions.length > 0 && (
              <Badge color="purple" size="sm">
                {predictions.length} predictions
              </Badge>
            )}
          </Flex>
          <div>
            {predictions.length === 0 ? (
              <div className="text-center py-8">
                <TrendingUp className="h-12 w-12 text-gray-300 mx-auto mb-2" />
                <Text className="text-gray-500">No failure predictions</Text>
              </div>
            ) : (
              <Grid numItems={1} numItemsMd={2} numItemsLg={3} className="gap-4">
                {predictions.map((prediction) => (
                  <Col key={prediction.id}>
                    <PredictionCard
                      prediction={prediction}
                      onClick={() => handlePredictionClick(prediction)}
                    />
                  </Col>
                ))}
              </Grid>
            )}
          </div>
        </Card>
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
