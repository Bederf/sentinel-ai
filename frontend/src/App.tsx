import { useEffect, useState } from "react";
import { Activity, Clock, Wifi, WifiOff } from "lucide-react";
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
  const [currentView, setCurrentView] = useState<View>("dashboard");
  const [currentTime, setCurrentTime] = useState(new Date());

  // Update time every second for Grafana-like time display
  useEffect(() => {
    const timer = setInterval(() => setCurrentTime(new Date()), 1000);
    return () => clearInterval(timer);
  }, []);

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
    // Periodic health check every 30 seconds
    const healthInterval = setInterval(checkHealth, 30000);
    return () => clearInterval(healthInterval);
  }, []);

  const formatTime = (date: Date) => {
    return date.toLocaleTimeString("en-ZA", {
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
      hour12: false,
    });
  };

  const formatDate = (date: Date) => {
    return date.toLocaleDateString("en-ZA", {
      year: "numeric",
      month: "short",
      day: "numeric",
    });
  };

  return (
    <div
      className="h-screen flex"
      style={{ background: "var(--color-grafana-bg-canvas)" }}
    >
      {/* Sidebar Navigation */}
      <Sidebar currentView={currentView} onViewChange={setCurrentView} />

      {/* Main Content Area */}
      <div className="flex-1 flex flex-col min-w-0">
        {/* Header - Grafana style */}
        <header
          className="flex-none h-14 px-4 flex items-center justify-between"
          style={{
            background: "var(--color-grafana-bg-primary)",
            borderBottom: "1px solid var(--color-grafana-border)",
          }}
        >
          {/* Left side - Page title and breadcrumb */}
          <div className="flex items-center gap-4 ml-12 md:ml-0">
            <div className="flex items-center gap-2">
              <Activity
                className="h-5 w-5"
                style={{ color: "var(--color-grafana-orange)" }}
              />
              <h1
                className="text-base font-medium"
                style={{ color: "var(--color-grafana-text-primary)" }}
              >
                {currentView === "dashboard" ? "Dashboard" : "Chat Assistant"}
              </h1>
            </div>
            <span
              className="hidden sm:inline-block text-xs px-2 py-0.5 rounded"
              style={{
                background: "var(--color-grafana-bg-secondary)",
                color: "var(--color-grafana-text-secondary)",
              }}
            >
              Facilities Management
            </span>
          </div>

          {/* Right side - Status and time */}
          <div className="flex items-center gap-4">
            {/* Live indicator */}
            <div className="hidden sm:flex items-center gap-2">
              <div
                className="w-2 h-2 rounded-full pulse-live"
                style={{ background: "var(--color-status-success)" }}
              />
              <span
                className="text-xs uppercase tracking-wide"
                style={{ color: "var(--color-grafana-text-secondary)" }}
              >
                Live
              </span>
            </div>

            {/* Connection status */}
            <div
              className="flex items-center gap-2 px-2 py-1 rounded"
              style={{
                background: error
                  ? "rgba(242, 73, 92, 0.15)"
                  : loading
                    ? "rgba(142, 142, 142, 0.15)"
                    : "rgba(115, 191, 105, 0.15)",
                border: `1px solid ${
                  error
                    ? "rgba(242, 73, 92, 0.3)"
                    : loading
                      ? "rgba(142, 142, 142, 0.3)"
                      : "rgba(115, 191, 105, 0.3)"
                }`,
              }}
            >
              {loading ? (
                <>
                  <div className="w-3 h-3 rounded-full border-2 border-gray-400 border-t-transparent animate-spin" />
                  <span
                    className="text-xs hidden sm:inline"
                    style={{ color: "var(--color-grafana-text-secondary)" }}
                  >
                    Connecting...
                  </span>
                </>
              ) : error ? (
                <>
                  <WifiOff
                    className="h-3.5 w-3.5"
                    style={{ color: "var(--color-status-error)" }}
                  />
                  <span
                    className="text-xs hidden sm:inline"
                    style={{ color: "var(--color-status-error)" }}
                  >
                    Offline
                  </span>
                </>
              ) : (
                <>
                  <Wifi
                    className="h-3.5 w-3.5"
                    style={{ color: "var(--color-status-success)" }}
                  />
                  <span
                    className="text-xs hidden sm:inline"
                    style={{ color: "var(--color-status-success)" }}
                  >
                    v{health?.version}
                  </span>
                </>
              )}
            </div>

            {/* Time display - Grafana style */}
            <div
              className="hidden md:flex items-center gap-2 px-3 py-1 rounded"
              style={{
                background: "var(--color-grafana-bg-secondary)",
                border: "1px solid var(--color-grafana-border)",
              }}
            >
              <Clock
                className="h-3.5 w-3.5"
                style={{ color: "var(--color-grafana-text-secondary)" }}
              />
              <div className="flex flex-col items-end">
                <span
                  className="text-xs font-mono"
                  style={{ color: "var(--color-grafana-text-primary)" }}
                >
                  {formatTime(currentTime)}
                </span>
                <span
                  className="text-xs"
                  style={{ color: "var(--color-grafana-text-disabled)" }}
                >
                  {formatDate(currentTime)}
                </span>
              </div>
            </div>
          </div>
        </header>

        {/* Main content - Takes remaining space */}
        <main
          className="flex-1 overflow-hidden"
          style={{ background: "var(--color-grafana-bg-canvas)" }}
        >
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
