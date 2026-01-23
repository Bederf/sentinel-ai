import { useEffect, useState } from "react";
import { Card, Title, Text, Badge } from "@tremor/react";
import { Building2, Activity } from "lucide-react";
import api from "./lib/api";

interface HealthStatus {
  status: string;
  version: string;
}

function App() {
  const [health, setHealth] = useState<HealthStatus | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const checkHealth = async () => {
      try {
        const response = await api.health();
        setHealth(response);
        setError(null);
      } catch (err) {
        setError("Failed to connect to backend");
        console.error("Health check failed:", err);
      } finally {
        setLoading(false);
      }
    };

    checkHealth();
  }, []);

  return (
    <div className="min-h-screen bg-gray-50 p-8">
      <div className="max-w-4xl mx-auto">
        {/* Header */}
        <div className="flex items-center gap-3 mb-8">
          <Building2 className="h-10 w-10 text-bidvest-blue-600" />
          <div>
            <h1 className="text-3xl font-bold text-gray-900">
              BMS Intelligence
            </h1>
            <p className="text-gray-500">
              Building Management System Intelligence Platform
            </p>
          </div>
        </div>

        {/* Status Card */}
        <Card className="mb-6">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <Activity className="h-5 w-5 text-gray-500" />
              <Title>System Status</Title>
            </div>
            {loading ? (
              <Badge color="gray">Checking...</Badge>
            ) : error ? (
              <Badge color="red">Offline</Badge>
            ) : (
              <Badge color="green">Online</Badge>
            )}
          </div>

          {!loading && (
            <div className="mt-4">
              {error ? (
                <Text className="text-red-600">{error}</Text>
              ) : (
                <div className="space-y-2">
                  <Text>
                    <span className="font-medium">Status:</span>{" "}
                    {health?.status}
                  </Text>
                  <Text>
                    <span className="font-medium">Version:</span>{" "}
                    {health?.version}
                  </Text>
                </div>
              )}
            </div>
          )}
        </Card>

        {/* Placeholder for future content */}
        <Card>
          <Title>Dashboard</Title>
          <Text className="mt-2">
            Building data and AI chat features will be added in subsequent
            phases.
          </Text>
        </Card>
      </div>
    </div>
  );
}

export default App;
