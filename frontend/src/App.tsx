import { useEffect, useState } from "react";
import { Badge } from "@tremor/react";
import { Building2, Activity } from "lucide-react";
import api from "./lib/api";
import { Chat } from "./components/Chat";

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
    <div className="h-screen flex flex-col bg-gray-50">
      {/* Header - Fixed height */}
      <header className="flex-none bg-white border-b border-gray-200 px-6 py-4">
        <div className="flex items-center justify-between max-w-7xl mx-auto">
          <div className="flex items-center gap-3">
            <Building2 className="h-8 w-8 text-bidvest-blue-600" />
            <div>
              <h1 className="text-xl font-bold text-gray-900">
                BMS Intelligence
              </h1>
              <p className="text-sm text-gray-500">
                FM Assistant
              </p>
            </div>
          </div>

          {/* Status indicator */}
          <div className="flex items-center gap-2">
            <Activity className="h-4 w-4 text-gray-400" />
            {loading ? (
              <Badge color="gray" size="sm">Checking...</Badge>
            ) : error ? (
              <Badge color="red" size="sm">Offline</Badge>
            ) : (
              <Badge color="green" size="sm">
                {health?.status} v{health?.version}
              </Badge>
            )}
          </div>
        </div>
      </header>

      {/* Chat area - Takes remaining space */}
      <main className="flex-1 overflow-hidden p-4 md:p-6">
        <div className="h-full max-w-4xl mx-auto">
          <Chat />
        </div>
      </main>
    </div>
  );
}

export default App;
