/**
 * HealthConfigEditor - Engineer-configurable health calculation parameters
 *
 * Features:
 * - Edit health weights per equipment type
 * - Adjust thresholds for warnings/critical
 * - Configure fault weights
 * - Reset to defaults
 */

import { useState, useEffect } from "react";
import { Card, Title, Text, Badge, Flex, Grid, Button, Tab, TabGroup, TabList, TabPanel, TabPanels } from "@tremor/react";
import { Save, RotateCcw, AlertTriangle, CheckCircle, Info } from "lucide-react";
import { healthConfigApi, type EquipmentHealthConfig, type HealthWeights, type HealthThresholds } from "../../lib/hvacApi";

interface HealthConfigEditorProps {
  onConfigChange?: (equipmentType: string, config: EquipmentHealthConfig) => void;
}

export function HealthConfigEditor({ onConfigChange }: HealthConfigEditorProps) {
  const [configs, setConfigs] = useState<Record<string, EquipmentHealthConfig>>({});
  const [selectedType, setSelectedType] = useState<string>("chiller");
  const [editedConfig, setEditedConfig] = useState<Partial<EquipmentHealthConfig> | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);

  useEffect(() => {
    loadConfigs();
  }, []);

  useEffect(() => {
    if (configs[selectedType]) {
      setEditedConfig({ ...configs[selectedType] });
    }
  }, [selectedType, configs]);

  async function loadConfigs() {
    try {
      const response = await healthConfigApi.list();
      setConfigs(response.configs);
      setLoading(false);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load health configs");
      setLoading(false);
    }
  }

  async function handleSave() {
    if (!editedConfig) return;

    setSaving(true);
    setError(null);
    setSuccessMessage(null);

    try {
      const result = await healthConfigApi.update(selectedType, {
        expected_life_years: editedConfig.expected_life_years,
        service_interval_days: editedConfig.service_interval_days,
        weights: editedConfig.weights,
        thresholds: editedConfig.thresholds,
        fault_weights: editedConfig.fault_weights,
      });

      setConfigs((prev) => ({
        ...prev,
        [selectedType]: result.config,
      }));
      setSuccessMessage(`Configuration saved for ${selectedType}`);
      onConfigChange?.(selectedType, result.config);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to save configuration");
    } finally {
      setSaving(false);
    }
  }

  async function handleReset() {
    setSaving(true);
    setError(null);
    setSuccessMessage(null);

    try {
      const result = await healthConfigApi.reset(selectedType);
      setConfigs((prev) => ({
        ...prev,
        [selectedType]: result.config,
      }));
      setEditedConfig({ ...result.config });
      setSuccessMessage(`Configuration reset to defaults for ${selectedType}`);
      onConfigChange?.(selectedType, result.config);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to reset configuration");
    } finally {
      setSaving(false);
    }
  }

  function updateWeight(key: keyof HealthWeights, value: number) {
    if (!editedConfig) return;
    setEditedConfig({
      ...editedConfig,
      weights: {
        ...editedConfig.weights!,
        [key]: value,
      },
    });
  }

  function updateThreshold(key: keyof HealthThresholds, value: number) {
    if (!editedConfig) return;
    setEditedConfig({
      ...editedConfig,
      thresholds: {
        ...editedConfig.thresholds!,
        [key]: value,
      },
    });
  }

  function updateFaultWeight(key: string, value: number) {
    if (!editedConfig) return;
    setEditedConfig({
      ...editedConfig,
      fault_weights: {
        ...editedConfig.fault_weights,
        [key]: value,
      },
    });
  }

  // Calculate if weights sum to 1
  function validateWeights(): boolean {
    if (!editedConfig?.weights) return true;
    const sum = Object.values(editedConfig.weights).reduce((a, b) => a + b, 0);
    return Math.abs(sum - 1) < 0.01;
  }

  function validateFaultWeights(): boolean {
    if (!editedConfig?.fault_weights) return true;
    const sum = Object.values(editedConfig.fault_weights).reduce((a, b) => a + b, 0);
    return Math.abs(sum - 1) < 0.01;
  }

  if (loading) {
    return (
      <Card>
        <Title>Health Calculation Configuration</Title>
        <div className="animate-pulse space-y-4 mt-4">
          <div className="h-32 bg-gray-200 rounded" />
          <div className="h-32 bg-gray-200 rounded" />
        </div>
      </Card>
    );
  }

  const equipmentTypes = Object.keys(configs);
  const typeLabels: Record<string, string> = {
    chiller: "Chillers",
    ahu: "AHUs",
    fcu: "FCUs",
    vav: "VAV Boxes",
    cooling_tower: "Cooling Towers",
    pump: "Pumps",
  };

  const weightsValid = validateWeights();
  const faultWeightsValid = validateFaultWeights();

  return (
    <div className="space-y-4">
      <Flex justifyContent="between" alignItems="center">
        <div>
          <Title>Health Calculation Configuration</Title>
          <Text>Configure how health scores are calculated for each equipment type</Text>
        </div>
        <div className="flex gap-2">
          <Button
            size="sm"
            variant="secondary"
            icon={RotateCcw}
            onClick={handleReset}
            disabled={saving}
          >
            Reset to Defaults
          </Button>
          <Button
            size="sm"
            icon={Save}
            onClick={handleSave}
            disabled={saving || !weightsValid || !faultWeightsValid}
          >
            {saving ? "Saving..." : "Save Changes"}
          </Button>
        </div>
      </Flex>

      {/* Messages */}
      {error && (
        <Card className="bg-red-900/20 border-red-500/30">
          <Flex alignItems="center" className="gap-2">
            <AlertTriangle className="w-5 h-5 text-red-400" />
            <Text className="text-red-300">{error}</Text>
          </Flex>
        </Card>
      )}

      {successMessage && (
        <Card className="bg-green-900/20 border-green-500/30">
          <Flex alignItems="center" className="gap-2">
            <CheckCircle className="w-5 h-5 text-green-400" />
            <Text className="text-green-300">{successMessage}</Text>
          </Flex>
        </Card>
      )}

      {/* Equipment Type Selector */}
      <Card>
        <Text className="font-medium mb-3">Equipment Type</Text>
        <Flex className="gap-2 flex-wrap">
          {equipmentTypes.map((type) => (
            <Button
              key={type}
              size="xs"
              variant={selectedType === type ? "primary" : "secondary"}
              onClick={() => setSelectedType(type)}
            >
              {typeLabels[type] || type}
            </Button>
          ))}
        </Flex>
      </Card>

      {editedConfig && (
        <TabGroup>
          <TabList className="mb-4 overflow-x-auto">
            <Tab>General</Tab>
            <Tab>Weights</Tab>
            <Tab>Thresholds</Tab>
            <Tab>Faults</Tab>
          </TabList>

          <TabPanels>
            {/* General Settings */}
            <TabPanel>
              <Card>
                <Grid className="grid grid-cols-2 gap-6">
                  <div>
                    <label className="block text-sm font-medium mb-2">
                      Expected Life (Years)
                    </label>
                    <input
                      type="number"
                      value={editedConfig.expected_life_years || 20}
                      onChange={(e) =>
                        setEditedConfig({
                          ...editedConfig,
                          expected_life_years: parseInt(e.target.value) || 20,
                        })
                      }
                      min={1}
                      max={100}
                      className="w-full px-3 py-2 rounded-md"
                      style={{
                        background: "var(--color-sentinel-bg-secondary)",
                        border: "1px solid var(--color-sentinel-border)",
                        color: "var(--color-sentinel-text-primary)",
                      }}
                    />
                    <Text className="text-xs text-gray-400 mt-1">
                      Typical lifespan for this equipment type
                    </Text>
                  </div>
                  <div>
                    <label className="block text-sm font-medium mb-2">
                      Service Interval (Days)
                    </label>
                    <input
                      type="number"
                      value={editedConfig.service_interval_days || 90}
                      onChange={(e) =>
                        setEditedConfig({
                          ...editedConfig,
                          service_interval_days: parseInt(e.target.value) || 90,
                        })
                      }
                      min={1}
                      max={365}
                      className="w-full px-3 py-2 rounded-md"
                      style={{
                        background: "var(--color-sentinel-bg-secondary)",
                        border: "1px solid var(--color-sentinel-border)",
                        color: "var(--color-sentinel-text-primary)",
                      }}
                    />
                    <Text className="text-xs text-gray-400 mt-1">
                      Recommended service frequency
                    </Text>
                  </div>
                </Grid>
              </Card>
            </TabPanel>

            {/* Health Weights */}
            <TabPanel>
              <Card>
                <Flex justifyContent="between" alignItems="center" className="mb-4">
                  <Text className="font-medium">Weight Distribution</Text>
                  <Badge color={weightsValid ? "green" : "red"}>
                    Sum: {editedConfig.weights
                      ? Object.values(editedConfig.weights).reduce((a, b) => a + b, 0).toFixed(2)
                      : "0"}{" "}
                    {weightsValid ? "✓" : "(must equal 1.0)"}
                  </Badge>
                </Flex>

                <div className="space-y-4">
                  {editedConfig.weights &&
                    Object.entries(editedConfig.weights).map(([key, value]) => (
                      <div key={key}>
                        <Flex justifyContent="between" className="mb-1">
                          <label className="text-sm capitalize">
                            {key.replace(/_/g, " ")}
                          </label>
                          <span className="text-sm font-medium">{(value * 100).toFixed(0)}%</span>
                        </Flex>
                        <input
                          type="range"
                          min={0}
                          max={100}
                          value={value * 100}
                          onChange={(e) =>
                            updateWeight(key as keyof HealthWeights, parseInt(e.target.value) / 100)
                          }
                          className="w-full h-2 rounded-full appearance-none cursor-pointer"
                          style={{
                            background: `linear-gradient(to right, var(--color-sentinel-blue) 0%, var(--color-sentinel-blue) ${value * 100}%, var(--color-sentinel-border) ${value * 100}%, var(--color-sentinel-border) 100%)`,
                          }}
                        />
                      </div>
                    ))}
                </div>

                <Flex alignItems="start" className="gap-2 mt-4 p-3 rounded bg-blue-900/20 border border-blue-500/30">
                  <Info className="w-4 h-4 text-blue-400 flex-shrink-0 mt-0.5" />
                  <Text className="text-xs text-blue-300">
                    Weights determine how much each factor contributes to the overall health score.
                    They must sum to 100%.
                  </Text>
                </Flex>
              </Card>
            </TabPanel>

            {/* Thresholds */}
            <TabPanel>
              <Card>
                <Text className="font-medium mb-4">Warning & Critical Thresholds</Text>

                <Grid className="grid grid-cols-2 gap-6">
                  {editedConfig.thresholds &&
                    Object.entries(editedConfig.thresholds).map(([key, value]) => {
                      const isWarning = key.includes("warning");
                      const label = key
                        .replace(/_/g, " ")
                        .replace("warning", "(Warning)")
                        .replace("critical", "(Critical)");

                      return (
                        <div key={key}>
                          <label className="block text-sm font-medium mb-2 capitalize">
                            {label}
                          </label>
                          <input
                            type="number"
                            value={value}
                            onChange={(e) =>
                              updateThreshold(
                                key as keyof HealthThresholds,
                                parseInt(e.target.value) || 0
                              )
                            }
                            min={0}
                            className="w-full px-3 py-2 rounded-md"
                            style={{
                              background: "var(--color-sentinel-bg-secondary)",
                              border: `1px solid ${isWarning ? "var(--color-sentinel-amber)" : "var(--color-sentinel-red)"}`,
                              color: "var(--color-sentinel-text-primary)",
                            }}
                          />
                        </div>
                      );
                    })}
                </Grid>
              </Card>
            </TabPanel>

            {/* Fault Weights */}
            <TabPanel>
              <Card>
                <Flex justifyContent="between" alignItems="center" className="mb-4">
                  <Text className="font-medium">Fault Type Weights</Text>
                  <Badge color={faultWeightsValid ? "green" : "red"}>
                    Sum:{" "}
                    {editedConfig.fault_weights
                      ? Object.values(editedConfig.fault_weights).reduce((a, b) => a + b, 0).toFixed(2)
                      : "0"}{" "}
                    {faultWeightsValid ? "✓" : "(must equal 1.0)"}
                  </Badge>
                </Flex>

                <div className="space-y-4">
                  {editedConfig.fault_weights &&
                    Object.entries(editedConfig.fault_weights).map(([key, value]) => (
                      <div key={key}>
                        <Flex justifyContent="between" className="mb-1">
                          <label className="text-sm capitalize">
                            {key.replace(/_/g, " ")}
                          </label>
                          <span className="text-sm font-medium">{(value * 100).toFixed(0)}%</span>
                        </Flex>
                        <input
                          type="range"
                          min={0}
                          max={100}
                          value={value * 100}
                          onChange={(e) =>
                            updateFaultWeight(key, parseInt(e.target.value) / 100)
                          }
                          className="w-full h-2 rounded-full appearance-none cursor-pointer"
                          style={{
                            background: `linear-gradient(to right, var(--color-sentinel-amber) 0%, var(--color-sentinel-amber) ${value * 100}%, var(--color-sentinel-border) ${value * 100}%, var(--color-sentinel-border) 100%)`,
                          }}
                        />
                      </div>
                    ))}
                </div>

                <Flex alignItems="start" className="gap-2 mt-4 p-3 rounded bg-amber-900/20 border border-amber-500/30">
                  <Info className="w-4 h-4 text-amber-400 flex-shrink-0 mt-0.5" />
                  <Text className="text-xs text-amber-300">
                    Fault weights determine how different fault types impact the health score.
                    Higher weights mean more severe impact on equipment health.
                  </Text>
                </Flex>
              </Card>
            </TabPanel>
          </TabPanels>
        </TabGroup>
      )}
    </div>
  );
}

export default HealthConfigEditor;
