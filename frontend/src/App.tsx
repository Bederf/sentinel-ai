import { useEffect, useState } from "react";
import { Badge } from "@tremor/react";
import { Building2, Activity } from "lucide-react";
import api from "./lib/api";
import { Chat } from "./components/Chat";
import { Dashboard } from "./components/Dashboard";
import { Sidebar, type View } from "./components/Sidebar";

interface HealthStatus {
  status: string;
  version: string;
}

function App() {
  const [health, setHealth] = useState<HealthStatus | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [currentView, setCurrentView] = useState<View>("dashboard"); // Default to Dashboard for demo

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
    <div className="h-screen flex bg-gray-50">
      {/* Sidebar Navigation */}
      <Sidebar currentView={currentView} onViewChange={setCurrentView} />

      {/* Main Content Area */}
      <div className="flex-1 flex flex-col min-w-0">
        {/* Header - Fixed height */}
        <header className="flex-none bg-white border-b border-gray-200 px-6 py-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3 ml-12 md:ml-0">
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

        {/* Main content - Takes remaining space */}
        <main className="flex-1 overflow-hidden">
          {currentView === "dashboard" ? (
            <Dashboard />
          ) : (
            <div className="h-full p-4 md:p-6">
              <div className="h-full max-w-4xl mx-auto">
                <Chat />
              </div>
            </div>
          )}
        </main>
      </div>
    </div>
  );
}

export default App;
