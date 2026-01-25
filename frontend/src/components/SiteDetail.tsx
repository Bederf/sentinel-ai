/**
 * Site Detail Component - Detailed view of a single site
 *
 * Features:
 * - Site information header with key metrics
 * - Equipment list with health indicators
 * - Site-specific alerts
 * - Energy consumption for this site
 * - Work order history (from CSV data)
 * - AI predictions for this site
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
  ProgressBar,
  Table,
  TableHead,
  TableRow,
  TableHeaderCell,
  TableBody,
  TableCell,
  TabGroup,
  TabList,
  Tab,
  TabPanels,
  TabPanel,
} from "@tremor/react";
import {
  ArrowLeft,
  Building2,
  MapPin,
  Phone,
  Mail,
  Clock,
  Cpu,
  AlertTriangle,
  Zap,
  Calendar,
  TrendingUp,
  CheckCircle,
  XCircle,
  AlertCircle,
} from "lucide-react";
import api from "../lib/api";
import type { Alert, Prediction, EnergyDataPoint } from "../lib/api";
import { EnergyChart } from "./EnergyChart";
import { PredictionCard } from "./PredictionCard";
import { PredictionDetail } from "./PredictionDetail";

interface SiteDetailProps {
  siteId: string;
  onBack: () => void;
}

interface SiteDetailData {
  id: string;
  name: string;
  address: string;
  region: string;
  type: string;
  sqm: number;
  floors: number;
  year_built: number;
  operating_hours: { start: string; end: string };
  occupancy_pattern: string;
  contact_email: string;
  contact_phone: string;
  equipment_count: number;
  active_alerts: number;
}

interface Equipment {
  id: string;
  name: string;
  type: string;
  site_id: string;
  model?: string;
  manufacturer?: string;
  install_date?: string;
  health_score: number;
  status: string;
  last_maintenance?: string;
  next_maintenance?: string;
}

export function SiteDetail({ siteId, onBack }: SiteDetailProps) {
  const [site, setSite] = useState<SiteDetailData | null>(null);
  const [equipment, setEquipment] = useState<Equipment[]>([]);
  const [alerts, setAlerts] = useState<Alert[]>([]);
  const [predictions, setPredictions] = useState<Prediction[]>([]);
  const [energyData, setEnergyData] = useState<EnergyDataPoint[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Prediction detail modal
  const [selectedPrediction, setSelectedPrediction] = useState<Prediction | null>(null);
  const [isPredictionDetailOpen, setIsPredictionDetailOpen] = useState(false);

  useEffect(() => {
    const loadSiteData = async () => {
      try {
        setLoading(true);

        // Fetch site details
        const siteResponse = await fetch(`http://localhost:9095/api/sites/${siteId}`);
        if (!siteResponse.ok) throw new Error("Failed to load site");
        const siteData = await siteResponse.json();
        setSite(siteData);

        // Fetch equipment for this site
        const equipmentResponse = await fetch(`http://localhost:9095/api/equipment?site_id=${siteId}`);
        if (equipmentResponse.ok) {
          const equipmentData = await equipmentResponse.json();
          setEquipment(equipmentData.equipment || []);
        }

        // Fetch alerts for this site
        const allAlerts = await api.getAlerts();
        setAlerts(allAlerts.filter((a) => a.site_id === siteId));

        // Fetch predictions for this site
        const predictionsData = await api.getPredictions(siteId);
        setPredictions(predictionsData.predictions || []);

        // Fetch energy data for this site
        const energyResponse = await api.getEnergy(siteId, 30);
        setEnergyData(energyResponse.data || []);

        setError(null);
      } catch (err) {
        console.error("Failed to load site data:", err);
        setError("Failed to load site details");
      } finally {
        setLoading(false);
      }
    };

    loadSiteData();
  }, [siteId]);

  const handlePredictionClick = (prediction: Prediction) => {
    setSelectedPrediction(prediction);
    setIsPredictionDetailOpen(true);
  };

  const getHealthColor = (score: number) => {
    if (score >= 90) return "emerald";
    if (score >= 70) return "yellow";
    return "red";
  };

  const getStatusIcon = (status: string) => {
    switch (status) {
      case "online":
        return <CheckCircle className="h-4 w-4 text-emerald-500" />;
      case "warning":
        return <AlertCircle className="h-4 w-4 text-yellow-500" />;
      case "offline":
      case "critical":
        return <XCircle className="h-4 w-4 text-red-500" />;
      default:
        return <Cpu className="h-4 w-4 text-gray-400" />;
    }
  };

  const getSeverityColor = (severity: string) => {
    switch (severity) {
      case "critical":
        return "red";
      case "high":
        return "orange";
      case "medium":
        return "yellow";
      default:
        return "blue";
    }
  };

  const formatDate = (dateStr: string | undefined) => {
    if (!dateStr) return "N/A";
    return new Date(dateStr).toLocaleDateString("en-ZA", {
      year: "numeric",
      month: "short",
      day: "numeric",
    });
  };

  if (loading) {
    return (
      <div className="h-full flex items-center justify-center">
        <div className="text-center">
          <div className="animate-spin h-8 w-8 border-4 border-bidvest-blue-600 border-t-transparent rounded-full mx-auto mb-4" />
          <Text>Loading site details...</Text>
        </div>
      </div>
    );
  }

  if (error || !site) {
    return (
      <div className="h-full flex items-center justify-center">
        <Card className="p-8 text-center">
          <AlertTriangle className="h-12 w-12 text-red-500 mx-auto mb-4" />
          <Title>Error Loading Site</Title>
          <Text className="text-gray-500">{error}</Text>
          <button
            onClick={onBack}
            className="mt-4 px-4 py-2 bg-bidvest-blue-600 text-white rounded-lg hover:bg-bidvest-blue-700"
          >
            Back to Dashboard
          </button>
        </Card>
      </div>
    );
  }

  // Calculate summary stats
  const healthyEquipment = equipment.filter((e) => e.health_score >= 90).length;
  const warningEquipment = equipment.filter((e) => e.health_score >= 70 && e.health_score < 90).length;
  const criticalEquipment = equipment.filter((e) => e.health_score < 70).length;
  const avgHealth = equipment.length > 0
    ? Math.round(equipment.reduce((sum, e) => sum + e.health_score, 0) / equipment.length)
    : 0;

  return (
    <div className="h-full overflow-y-auto p-6">
      {/* Back Button & Header */}
      <div className="mb-6">
        <button
          onClick={onBack}
          className="flex items-center gap-2 text-gray-600 hover:text-gray-900 mb-4 transition-colors"
        >
          <ArrowLeft className="h-5 w-5" />
          <span>Back to Dashboard</span>
        </button>

        <Flex justifyContent="between" alignItems="start" className="flex-wrap gap-4">
          <div>
            <Flex alignItems="center" className="gap-3 mb-2">
              <Building2 className="h-8 w-8 text-bidvest-blue-600" />
              <Title className="text-2xl">{site.name}</Title>
              <Badge color={site.type === "data_center" ? "purple" : site.type === "regional_office" ? "blue" : "gray"}>
                {site.type.replace("_", " ")}
              </Badge>
            </Flex>
            <Flex className="gap-4 text-gray-500 flex-wrap">
              <Flex className="gap-1">
                <MapPin className="h-4 w-4" />
                <Text>{site.address}</Text>
              </Flex>
              <Flex className="gap-1">
                <Clock className="h-4 w-4" />
                <Text>{site.operating_hours.start} - {site.operating_hours.end}</Text>
              </Flex>
            </Flex>
          </div>

          <div className="text-right">
            <Flex className="gap-4 flex-wrap justify-end">
              <div className="text-center">
                <Text className="text-gray-500 text-xs">Equipment</Text>
                <Text className="text-2xl font-bold text-gray-900">{equipment.length}</Text>
              </div>
              <div className="text-center">
                <Text className="text-gray-500 text-xs">Active Alerts</Text>
                <Text className="text-2xl font-bold text-amber-600">{alerts.length}</Text>
              </div>
              <div className="text-center">
                <Text className="text-gray-500 text-xs">Avg Health</Text>
                <Text className={`text-2xl font-bold ${avgHealth >= 90 ? "text-emerald-600" : avgHealth >= 70 ? "text-yellow-600" : "text-red-600"}`}>
                  {avgHealth}%
                </Text>
              </div>
            </Flex>
          </div>
        </Flex>
      </div>

      {/* Site Info Cards */}
      <Grid numItems={1} numItemsMd={2} numItemsLg={4} className="gap-4 mb-6">
        <Col>
          <Card>
            <Flex alignItems="center" className="gap-3">
              <div className="p-2 bg-blue-100 rounded-lg">
                <Building2 className="h-5 w-5 text-blue-600" />
              </div>
              <div>
                <Text className="text-gray-500 text-sm">Building Size</Text>
                <Text className="font-semibold">{site.sqm.toLocaleString()} sqm</Text>
              </div>
            </Flex>
          </Card>
        </Col>
        <Col>
          <Card>
            <Flex alignItems="center" className="gap-3">
              <div className="p-2 bg-purple-100 rounded-lg">
                <Calendar className="h-5 w-5 text-purple-600" />
              </div>
              <div>
                <Text className="text-gray-500 text-sm">Year Built</Text>
                <Text className="font-semibold">{site.year_built}</Text>
              </div>
            </Flex>
          </Card>
        </Col>
        <Col>
          <Card>
            <Flex alignItems="center" className="gap-3">
              <div className="p-2 bg-green-100 rounded-lg">
                <Phone className="h-5 w-5 text-green-600" />
              </div>
              <div>
                <Text className="text-gray-500 text-sm">Contact</Text>
                <Text className="font-semibold">{site.contact_phone}</Text>
              </div>
            </Flex>
          </Card>
        </Col>
        <Col>
          <Card>
            <Flex alignItems="center" className="gap-3">
              <div className="p-2 bg-amber-100 rounded-lg">
                <Mail className="h-5 w-5 text-amber-600" />
              </div>
              <div>
                <Text className="text-gray-500 text-sm">Email</Text>
                <Text className="font-semibold text-sm">{site.contact_email}</Text>
              </div>
            </Flex>
          </Card>
        </Col>
      </Grid>

      {/* Tabbed Content */}
      <TabGroup>
        <TabList>
          <Tab icon={Cpu}>Equipment ({equipment.length})</Tab>
          <Tab icon={AlertTriangle}>Alerts ({alerts.length})</Tab>
          <Tab icon={Zap}>Energy</Tab>
          <Tab icon={TrendingUp}>Predictions ({predictions.length})</Tab>
        </TabList>

        <TabPanels>
          {/* Equipment Tab */}
          <TabPanel>
            <Card className="mt-4">
              <Flex justifyContent="between" className="mb-4">
                <Title>Equipment</Title>
                <Flex className="gap-4">
                  <Badge color="emerald">{healthyEquipment} Healthy</Badge>
                  <Badge color="yellow">{warningEquipment} Warning</Badge>
                  <Badge color="red">{criticalEquipment} Critical</Badge>
                </Flex>
              </Flex>

              {equipment.length === 0 ? (
                <div className="text-center py-8">
                  <Cpu className="h-12 w-12 text-gray-300 mx-auto mb-2" />
                  <Text className="text-gray-500">No equipment found for this site</Text>
                </div>
              ) : (
                <Table>
                  <TableHead>
                    <TableRow>
                      <TableHeaderCell>Equipment</TableHeaderCell>
                      <TableHeaderCell>Type</TableHeaderCell>
                      <TableHeaderCell>Status</TableHeaderCell>
                      <TableHeaderCell>Health</TableHeaderCell>
                      <TableHeaderCell>Last Maintenance</TableHeaderCell>
                    </TableRow>
                  </TableHead>
                  <TableBody>
                    {equipment.map((item) => (
                      <TableRow key={item.id}>
                        <TableCell>
                          <Flex alignItems="center" className="gap-2">
                            {getStatusIcon(item.status)}
                            <div>
                              <Text className="font-medium">{item.name}</Text>
                              <Text className="text-xs text-gray-500">{item.manufacturer} {item.model}</Text>
                            </div>
                          </Flex>
                        </TableCell>
                        <TableCell>
                          <Badge color="gray">{item.type.replace("_", " ")}</Badge>
                        </TableCell>
                        <TableCell>
                          <Badge color={item.status === "online" ? "emerald" : item.status === "warning" ? "yellow" : "red"}>
                            {item.status}
                          </Badge>
                        </TableCell>
                        <TableCell>
                          <Flex alignItems="center" className="gap-2">
                            <ProgressBar
                              value={item.health_score}
                              color={getHealthColor(item.health_score)}
                              className="w-20"
                            />
                            <Text className="text-sm">{item.health_score}%</Text>
                          </Flex>
                        </TableCell>
                        <TableCell>
                          <Text className="text-sm">{formatDate(item.last_maintenance)}</Text>
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              )}
            </Card>
          </TabPanel>

          {/* Alerts Tab */}
          <TabPanel>
            <Card className="mt-4">
              <Title className="mb-4">Active Alerts</Title>

              {alerts.length === 0 ? (
                <div className="text-center py-8">
                  <CheckCircle className="h-12 w-12 text-emerald-300 mx-auto mb-2" />
                  <Text className="text-gray-500">No active alerts for this site</Text>
                </div>
              ) : (
                <div className="space-y-3">
                  {alerts.map((alert) => (
                    <Card key={alert.id} className="bg-gray-50">
                      <Flex alignItems="start" className="gap-3">
                        <div className={`p-2 rounded-lg ${
                          alert.severity === "critical" ? "bg-red-100" :
                          alert.severity === "high" ? "bg-orange-100" :
                          alert.severity === "medium" ? "bg-yellow-100" : "bg-blue-100"
                        }`}>
                          <AlertTriangle className={`h-5 w-5 ${
                            alert.severity === "critical" ? "text-red-600" :
                            alert.severity === "high" ? "text-orange-600" :
                            alert.severity === "medium" ? "text-yellow-600" : "text-blue-600"
                          }`} />
                        </div>
                        <div className="flex-1">
                          <Flex justifyContent="between" alignItems="start">
                            <div>
                              <Text className="font-medium">{alert.message}</Text>
                              <Text className="text-sm text-gray-500">{alert.equipment_name}</Text>
                            </div>
                            <Badge color={getSeverityColor(alert.severity)}>{alert.severity}</Badge>
                          </Flex>
                          <Text className="text-xs text-gray-400 mt-1">
                            {new Date(alert.created_at).toLocaleString("en-ZA")}
                          </Text>
                        </div>
                      </Flex>
                    </Card>
                  ))}
                </div>
              )}
            </Card>
          </TabPanel>

          {/* Energy Tab */}
          <TabPanel>
            <Card className="mt-4">
              <Title className="mb-4">Energy Consumption - Last 30 Days</Title>
              <EnergyChart
                data={energyData}
                loading={false}
                selectedSiteId={siteId}
                days={30}
              />
            </Card>
          </TabPanel>

          {/* Predictions Tab */}
          <TabPanel>
            <Card className="mt-4">
              <Title className="mb-4">AI Failure Predictions</Title>

              {predictions.length === 0 ? (
                <div className="text-center py-8">
                  <TrendingUp className="h-12 w-12 text-gray-300 mx-auto mb-2" />
                  <Text className="text-gray-500">No predictions for this site</Text>
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
            </Card>
          </TabPanel>
        </TabPanels>
      </TabGroup>

      {/* Prediction Detail Modal */}
      {selectedPrediction && (
        <PredictionDetail
          prediction={selectedPrediction}
          isOpen={isPredictionDetailOpen}
          onClose={() => {
            setIsPredictionDetailOpen(false);
            setSelectedPrediction(null);
          }}
        />
      )}
    </div>
  );
}

export default SiteDetail;
