/**
 * ML Model Status Panel
 *
 * Shows status of trained ML models, their metrics,
 * and allows training new models.
 */

import { useEffect, useState } from "react";
import {
  Card,
  Title,
  Table,
  TableHead,
  TableHeaderCell,
  TableBody,
  TableRow,
  TableCell,
  Badge,
  Button,
  Flex,
  Text,
  Grid,
  Select,
  SelectItem,
  NumberInput,
} from "@tremor/react";
import {
  PlayIcon,
  CheckCircleIcon,
  ClockIcon,
} from "@heroicons/react/24/outline";
import type { MLModel, TrainResponse } from "../../lib/mlApi";
import { listMLModels, trainModel, activateModel } from "../../lib/mlApi";

interface MLModelStatusProps {
  onModelTrained?: (result: TrainResponse) => void;
}

export function MLModelStatus({ onModelTrained }: MLModelStatusProps) {
  const [models, setModels] = useState<MLModel[]>([]);
  const [loading, setLoading] = useState(true);
  const [training, setTraining] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Training form state
  const [selectedModelType, setSelectedModelType] = useState<"lstm" | "autoencoder">("lstm");
  const [selectedEquipmentType, setSelectedEquipmentType] = useState("chiller");
  const [epochs, setEpochs] = useState(50);

  const equipmentTypes = ["chiller", "ahu", "generator", "fcu", "ups"];

  const fetchModels = async () => {
    try {
      setError(null);
      const modelList = await listMLModels();
      setModels(modelList);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load models");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchModels();
  }, []);

  const handleTrain = async () => {
    setTraining(true);
    setError(null);

    try {
      const result = await trainModel(
        selectedModelType,
        selectedEquipmentType,
        epochs,
        true // use demo data
      );

      // Refresh model list
      await fetchModels();

      if (onModelTrained) {
        onModelTrained(result);
      }

      alert(`Model trained successfully: ${result.model_id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Training failed");
    } finally {
      setTraining(false);
    }
  };

  const handleActivate = async (modelId: string) => {
    try {
      await activateModel(modelId);
      await fetchModels();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to activate model");
    }
  };

  const formatDate = (dateStr: string) => {
    return new Date(dateStr).toLocaleString();
  };

  const formatMetrics = (metrics: Record<string, number>, modelType: string) => {
    if (modelType === "lstm") {
      return `MAE: ${metrics.mae_24h?.toFixed(3) || "N/A"}, R²: ${metrics.r2_24h?.toFixed(3) || "N/A"}`;
    } else {
      return `Threshold: ${metrics.threshold?.toFixed(6) || "N/A"}, F1: ${metrics.f1_score?.toFixed(3) || "N/A"}`;
    }
  };

  if (loading) {
    return (
      <Card>
        <Title>ML Model Status</Title>
        <div className="h-48 flex items-center justify-center">
          <Text>Loading models...</Text>
        </div>
      </Card>
    );
  }

  const lstmModels = models.filter((m) => m.model_type === "lstm");
  const autoencoderModels = models.filter((m) => m.model_type === "autoencoder");

  return (
    <div className="space-y-6">
      {/* Training Panel */}
      <Card>
        <Title>Train New Model</Title>
        <Grid numItems={1} numItemsSm={4} className="gap-4 mt-4">
          <div>
            <Text className="mb-1">Model Type</Text>
            <Select
              value={selectedModelType}
              onValueChange={(v) => setSelectedModelType(v as "lstm" | "autoencoder")}
            >
              <SelectItem value="lstm">LSTM (Forecasting)</SelectItem>
              <SelectItem value="autoencoder">Autoencoder (Anomaly)</SelectItem>
            </Select>
          </div>

          <div>
            <Text className="mb-1">Equipment Type</Text>
            <Select
              value={selectedEquipmentType}
              onValueChange={setSelectedEquipmentType}
            >
              {equipmentTypes.map((eq) => (
                <SelectItem key={eq} value={eq}>
                  {eq.charAt(0).toUpperCase() + eq.slice(1)}
                </SelectItem>
              ))}
            </Select>
          </div>

          <div>
            <Text className="mb-1">Epochs</Text>
            <NumberInput
              value={epochs}
              onValueChange={setEpochs}
              min={10}
              max={200}
              step={10}
            />
          </div>

          <div className="flex items-end">
            <Button
              icon={PlayIcon}
              onClick={handleTrain}
              loading={training}
              disabled={training}
              color="blue"
            >
              {training ? "Training..." : "Train Model"}
            </Button>
          </div>
        </Grid>

        {error && (
          <Text color="red" className="mt-4">
            {error}
          </Text>
        )}
      </Card>

      {/* LSTM Models */}
      <Card>
        <Flex justifyContent="between" alignItems="center">
          <Title>LSTM Forecasting Models</Title>
          <Badge color="blue">{lstmModels.length} models</Badge>
        </Flex>

        {lstmModels.length === 0 ? (
          <Text className="mt-4">No LSTM models trained yet. Train one above!</Text>
        ) : (
          <Table className="mt-4">
            <TableHead>
              <TableRow>
                <TableHeaderCell>Model ID</TableHeaderCell>
                <TableHeaderCell>Equipment</TableHeaderCell>
                <TableHeaderCell>Status</TableHeaderCell>
                <TableHeaderCell>Metrics</TableHeaderCell>
                <TableHeaderCell>Trained</TableHeaderCell>
                <TableHeaderCell>Actions</TableHeaderCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {lstmModels.map((model) => (
                <TableRow key={model.model_id}>
                  <TableCell>
                    <Text className="font-mono text-xs">{model.model_id}</Text>
                  </TableCell>
                  <TableCell>{model.equipment_type}</TableCell>
                  <TableCell>
                    <Badge
                      color={model.status === "active" ? "green" : "gray"}
                      icon={model.status === "active" ? CheckCircleIcon : ClockIcon}
                    >
                      {model.status}
                    </Badge>
                  </TableCell>
                  <TableCell>
                    <Text className="text-sm">
                      {formatMetrics(model.metrics, "lstm")}
                    </Text>
                  </TableCell>
                  <TableCell>
                    <Text className="text-sm">{formatDate(model.registered_at)}</Text>
                  </TableCell>
                  <TableCell>
                    {model.status !== "active" && (
                      <Button
                        size="xs"
                        variant="secondary"
                        onClick={() => handleActivate(model.model_id)}
                      >
                        Activate
                      </Button>
                    )}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </Card>

      {/* Autoencoder Models */}
      <Card>
        <Flex justifyContent="between" alignItems="center">
          <Title>Autoencoder Anomaly Models</Title>
          <Badge color="orange">{autoencoderModels.length} models</Badge>
        </Flex>

        {autoencoderModels.length === 0 ? (
          <Text className="mt-4">No autoencoder models trained yet. Train one above!</Text>
        ) : (
          <Table className="mt-4">
            <TableHead>
              <TableRow>
                <TableHeaderCell>Model ID</TableHeaderCell>
                <TableHeaderCell>Equipment</TableHeaderCell>
                <TableHeaderCell>Status</TableHeaderCell>
                <TableHeaderCell>Metrics</TableHeaderCell>
                <TableHeaderCell>Trained</TableHeaderCell>
                <TableHeaderCell>Actions</TableHeaderCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {autoencoderModels.map((model) => (
                <TableRow key={model.model_id}>
                  <TableCell>
                    <Text className="font-mono text-xs">{model.model_id}</Text>
                  </TableCell>
                  <TableCell>{model.equipment_type}</TableCell>
                  <TableCell>
                    <Badge
                      color={model.status === "active" ? "green" : "gray"}
                      icon={model.status === "active" ? CheckCircleIcon : ClockIcon}
                    >
                      {model.status}
                    </Badge>
                  </TableCell>
                  <TableCell>
                    <Text className="text-sm">
                      {formatMetrics(model.metrics, "autoencoder")}
                    </Text>
                  </TableCell>
                  <TableCell>
                    <Text className="text-sm">{formatDate(model.registered_at)}</Text>
                  </TableCell>
                  <TableCell>
                    {model.status !== "active" && (
                      <Button
                        size="xs"
                        variant="secondary"
                        onClick={() => handleActivate(model.model_id)}
                      >
                        Activate
                      </Button>
                    )}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </Card>
    </div>
  );
}

export default MLModelStatus;
