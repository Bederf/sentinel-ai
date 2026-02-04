import { useEffect, useState, useRef, useCallback } from "react";
import { Clock, Wifi, WifiOff, Bell, X, LogOut } from "lucide-react";
import { Toaster, toast } from "sonner";
import { formatTime } from "./lib/timeFormat";
import api, { type Alert, type AuthUser } from "./lib/api";
import { Chat } from "./components/Chat";
import TechnicianChat from "./components/TechnicianChat";
import { Dashboard } from "./components/Dashboard";
import { ControlDashboard } from "./components/ControlDashboard";
import { ControlAuditTrail } from "./components/ControlAuditTrail";
import { OptimizationPage } from "./pages/OptimizationPage";
import { Settings } from "./components/Settings";
import { Sidebar, type View } from "./components/Sidebar";
import { SplashScreen } from "./components/SplashScreen";
import { EmailEntry } from "./components/EmailEntry";
import { AlertFeed } from "./components/AlertFeed";
import { CalendarPicker } from "./components/CalendarPicker";
import { IntegrationMonitoringPage } from "./components/IntegrationMonitoringPage";
import { AssetWorkflowDashboard } from "./components/AssetWorkflowDashboard";
import { OccupancyPanel } from "./components/OccupancyPanel";
import { SecurityDashboard } from "./components/SecurityDashboard";
import { SimbiotPage } from "./components/SimbiotPage";

interface HealthStatus {
  status: string;
  version: string;
}

function App() {
  const [showSplash, setShowSplash] = useState(true);
  const [currentUser, setCurrentUser] = useState<AuthUser | null>(() => {
    // Check for stored user on mount
    const storedUser = localStorage.getItem("sentinel_user");
    return storedUser ? JSON.parse(storedUser) : null;
  });
  const [health, setHealth] = useState<HealthStatus | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [currentView, setCurrentView] = useState<View>("chat");
  const [viewRefreshKey, setViewRefreshKey] = useState(0);
  const [showCardLibrary, setShowCardLibrary] = useState(false);
  const [currentTime, setCurrentTime] = useState(new Date());
  const [showAlertsPanel, setShowAlertsPanel] = useState(false);
  const [showCalendar, setShowCalendar] = useState(false);
  const [unreadAlertCount, setUnreadAlertCount] = useState(0);
  const [lastViewedAlertTime, setLastViewedAlertTime] = useState<Date | null>(null);
  const alertsPanelRef = useRef<HTMLDivElement | null>(null);
  const calendarButtonRef = useRef<HTMLDivElement | null>(null);
  const audioRef = useRef<HTMLAudioElement | null>(null);

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

  // Fetch and count unread alerts
  useEffect(() => {
    const fetchUnreadCount = async () => {
      try {
        const alerts = await api.getAlerts();
        // Count unread alerts (not acknowledged or created after last viewed time)
        const unread = alerts.filter((alert) => {
          if (!alert.acknowledged) return true;
          if (lastViewedAlertTime && new Date(alert.created_at) > lastViewedAlertTime) {
            return true;
          }
          return false;
        });
        setUnreadAlertCount(unread.length);
      } catch (err) {
        console.error("Failed to fetch alert count:", err);
      }
    };

    fetchUnreadCount();
    // Refresh every 30 seconds
    const interval = setInterval(fetchUnreadCount, 30000);
    return () => clearInterval(interval);
  }, [lastViewedAlertTime]);

  // Mark alerts as viewed when panel opens
  const handleAlertsPanelOpen = () => {
    setShowAlertsPanel(true);
    setLastViewedAlertTime(new Date());
    // Don't reset count immediately - let individual alert clicks handle it
  };

  // Handle when an individual alert is marked as read
  const handleAlertRead = (_alertId: string) => {
    setUnreadAlertCount((prev) => Math.max(0, prev - 1));
  };

  // Handle when all alerts are cleared
  const handleClearAllAlerts = () => {
    setUnreadAlertCount(0);
  };

  // Handle alert click - navigate to equipment in control dashboard
  const handleAlertClick = (alert: Alert) => {
    // Store selection in sessionStorage for ControlDashboard to pick up
    // Use device_id if available (maps to mock_devices.json), fallback to equipment_id
    const deviceId = alert.device_id || alert.equipment_id;
    if (deviceId && alert.site_id) {
      sessionStorage.setItem("sentinel_selected_equipment", deviceId);
      sessionStorage.setItem("sentinel_selected_site", alert.site_id);
      // Store alert details for context display
      sessionStorage.setItem("sentinel_alert_context", JSON.stringify({
        message: alert.message,
        severity: alert.severity,
        equipment_name: alert.equipment_name,
        created_at: alert.created_at,
        title: alert.title,
        type: alert.type,
      }));
    }

    // Close alerts panel
    setShowAlertsPanel(false);

    // Navigate to control dashboard
    handleViewChange("control");
  };

  const formatDate = (date: Date) => {
    return date.toLocaleDateString("en-ZA", {
      year: "numeric",
      month: "short",
      day: "numeric",
    });
  };

  const handleSentinelLogoClick = () => {
    // Create audio element if it doesn't exist
    if (!audioRef.current) {
      audioRef.current = new Audio('/audio/sentinel-logo.mp3');
    }

    // Play audio
    audioRef.current.play().catch((error) => {
      console.error('Error playing audio:', error);
    });
  };

  const handleLogout = async () => {
    try {
      await api.logout();
    } catch (err) {
      console.error('Logout error:', err);
    } finally {
      // Clear local storage
      localStorage.removeItem("sentinel_token");
      localStorage.removeItem("sentinel_user");
      setCurrentUser(null);
      toast.success("Logged out successfully");
    }
  };

  // Handle view changes - scroll to top and refresh when re-clicking same view
  const handleViewChange = useCallback((view: View) => {
    if (view === currentView) {
      // Same view re-clicked: scroll to top and bump refresh key
      const main = document.querySelector('main');
      if (main) {
        const scrollable = main.firstElementChild as HTMLElement | null;
        scrollable?.scrollTo({ top: 0, behavior: 'smooth' });
      }
      setViewRefreshKey(k => k + 1);
    } else {
      setCurrentView(view);
    }
  }, [currentView]);

  // Close alerts panel when clicking outside
  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (
        alertsPanelRef.current &&
        !alertsPanelRef.current.contains(event.target as Node) &&
        !(event.target as HTMLElement).closest('button[aria-label="View alerts"]')
      ) {
        setShowAlertsPanel(false);
      }
    };

    if (showAlertsPanel) {
      document.addEventListener('mousedown', handleClickOutside);
      return () => {
        document.removeEventListener('mousedown', handleClickOutside);
      };
    }
  }, [showAlertsPanel]);

  // Show splash screen on initial load
  if (showSplash) {
    console.log('Showing splash screen');
    return <SplashScreen onComplete={() => {
      console.log('Splash complete, setting showSplash to false');
      setShowSplash(false);
    }} />;
  }

  // Show email entry if not authenticated
  if (!currentUser) {
    console.log('Showing email entry (user =', currentUser, ')');
    return <EmailEntry onSuccess={(user, token) => {
      console.log('Login success:', user);
      setCurrentUser(user);
    }} />;
  }

  return (
    <div
      className="h-screen flex"
      style={{ background: "var(--color-sentinel-bg-canvas)" }}
    >
      {/* Sidebar Navigation */}
      <Sidebar
        currentView={currentView}
        onViewChange={handleViewChange}
        version={health?.version || "13.0"}
        onCustomizeDashboard={() => setShowCardLibrary(true)}
      />

      {/* Main Content Area */}
      <div className="flex-1 flex flex-col min-w-0">
        {/* Header - SENTINEL style */}
        <header
          className="flex-none h-14 px-4 flex items-center justify-between"
          style={{
            background: "var(--color-sentinel-bg-primary)",
            borderBottom: "1px solid var(--color-sentinel-border)",
          }}
        >
          {/* Left side - Page title and breadcrumb */}
          <div className="flex items-center gap-4 ml-12 md:ml-0">
            <div className="flex items-center gap-2">
              {/* Sentinel Logo - Copied from Sidebar */}
              <div
                className="w-9 h-9 rounded-lg flex items-center justify-center sentinel-shield sentinel-shield-active cursor-pointer"
                onClick={handleSentinelLogoClick}
              >
                <img
                  src="/images/sentinel-logo.png"
                  alt="Sentinel Shield"
                  className="h-5 w-5 pulse-slow"
                  style={{
                    animation: 'pulse-slow 2s ease-in-out infinite',
                  }}
                />
              </div>
              <h1
                className="text-base font-medium"
                style={{ color: "var(--color-sentinel-text-primary)" }}
              >
                {currentView === "dashboard" ? "Dashboard" :
                 currentView === "control" ? "Control Dashboard" :
                 currentView === "control-audit" ? "Control Audit Trail" :
                 currentView === "optimization" ? "Load Shedding Optimization" :
                 currentView === "settings" ? "Settings" :
                 currentView === "technician" ? "Technician Chat" :
                 currentView === "integrations" ? "Integration Monitoring" :
                 currentView === "occupancy" ? "DALI Occupancy" :
                 currentView === "security" ? "Security" :
                 currentView === "simbiot" ? "SIMBIOT" :
                 "AI Assistant"}
              </h1>
            </div>
            <span
              className="hidden sm:inline-block text-xs px-2 py-0.5 rounded"
              style={{
                background: "var(--color-sentinel-bg-secondary)",
                color: "var(--color-sentinel-text-secondary)",
              }}
            >
              Intelligent Asset Protection
            </span>
          </div>

          {/* Right side - Status and time */}
          <div className="flex items-center gap-4 relative">
            {/* Alerts Button */}
            <button
              onClick={handleAlertsPanelOpen}
              className="relative p-2 rounded-md transition-colors hover:brightness-110"
              style={{
                background: showAlertsPanel ? "var(--color-sentinel-bg-secondary)" : "transparent",
                border: "1px solid var(--color-sentinel-border)",
              }}
              aria-label={`View alerts${unreadAlertCount > 0 ? ` (${unreadAlertCount} unread)` : ""}`}
            >
              <Bell
                className="h-5 w-5"
                style={{ color: "var(--color-sentinel-text-primary)" }}
              />
              {unreadAlertCount > 0 && (
                <span
                  className="absolute -top-1 -right-1 min-w-[18px] h-[18px] flex items-center justify-center px-1 rounded-full text-[10px] font-bold"
                  style={{
                    background: "var(--color-sentinel-red)",
                    color: "white",
                    border: "2px solid var(--color-sentinel-bg-primary)",
                  }}
                >
                  {unreadAlertCount > 99 ? "99+" : unreadAlertCount}
                </span>
              )}
            </button>

            {/* Alerts Panel Dropdown */}
            {showAlertsPanel && (
              <div
                ref={alertsPanelRef}
                className="absolute top-full right-0 mt-2 w-96 max-h-[600px] overflow-hidden rounded-md shadow-lg z-50"
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
                  <h3
                    className="font-medium text-sm"
                    style={{ color: "var(--color-sentinel-text-primary)" }}
                  >
                    Recent Alerts
                  </h3>
                  <button
                    onClick={() => setShowAlertsPanel(false)}
                    className="p-1 rounded hover:brightness-110 transition-colors"
                    style={{
                      background: "var(--color-sentinel-bg-secondary)",
                    }}
                    aria-label="Close alerts panel"
                  >
                    <X
                      className="h-4 w-4"
                      style={{ color: "var(--color-sentinel-text-secondary)" }}
                    />
                  </button>
                </div>

                {/* Alert Feed Content */}
                <div className="overflow-y-auto max-h-[500px]">
                  <AlertFeed
                    limit={20}
                    refreshInterval={30000}
                    onAlertRead={handleAlertRead}
                    onClearAll={handleClearAllAlerts}
                    onAlertClick={handleAlertClick}
                  />
                </div>
              </div>
            )}

            {/* Protection status indicator */}
            <div className="hidden sm:flex items-center gap-2">
              <div
                className="w-2 h-2 rounded-full pulse-live"
                style={{ background: "var(--color-sentinel-green)" }}
              />
              <span
                className="text-xs uppercase tracking-wide"
                style={{ color: "var(--color-sentinel-text-secondary)" }}
              >
                Protected
              </span>
            </div>

            {/* Connection status */}
            <div
              className="flex items-center gap-2 px-2 py-1 rounded"
              style={{
                background: error
                  ? "rgba(220, 38, 38, 0.15)"
                  : loading
                    ? "rgba(142, 142, 142, 0.15)"
                    : "rgba(16, 185, 129, 0.15)",
                border: `1px solid ${
                  error
                    ? "rgba(220, 38, 38, 0.3)"
                    : loading
                      ? "rgba(142, 142, 142, 0.3)"
                      : "rgba(16, 185, 129, 0.3)"
                }`,
              }}
            >
              {loading ? (
                <>
                  <div className="w-3 h-3 rounded-full border-2 border-gray-400 border-t-transparent animate-spin" />
                  <span
                    className="text-xs hidden sm:inline"
                    style={{ color: "var(--color-sentinel-text-secondary)" }}
                  >
                    Connecting...
                  </span>
                </>
              ) : error ? (
                <>
                  <WifiOff
                    className="h-3.5 w-3.5"
                    style={{ color: "var(--color-sentinel-red)" }}
                  />
                  <span
                    className="text-xs hidden sm:inline"
                    style={{ color: "var(--color-sentinel-red)" }}
                  >
                    Offline
                  </span>
                </>
              ) : (
                <>
                  <Wifi
                    className="h-3.5 w-3.5"
                    style={{ color: "var(--color-sentinel-green)" }}
                  />
                  <span
                    className="text-xs hidden sm:inline"
                    style={{ color: "var(--color-sentinel-green)" }}
                  >
                    v{health?.version}
                  </span>
                </>
              )}
            </div>

            {/* Time display - Clickable Calendar */}
            <div className="hidden md:block relative" ref={calendarButtonRef}>
              <button
                onClick={() => setShowCalendar(!showCalendar)}
                className="flex items-center gap-2 px-3 py-1 rounded transition-colors hover:brightness-110 cursor-pointer"
                style={{
                  background: showCalendar
                    ? "var(--color-sentinel-bg-panel)"
                    : "var(--color-sentinel-bg-secondary)",
                  border: "1px solid var(--color-sentinel-border)",
                }}
                aria-label="Open calendar"
              >
                <Clock
                  className="h-3.5 w-3.5"
                  style={{ color: "var(--color-sentinel-text-secondary)" }}
                />
                <div className="flex flex-col items-end">
                  <span
                    className="text-xs font-mono"
                    style={{ color: "var(--color-sentinel-text-primary)" }}
                  >
                    {formatTime(currentTime)}
                  </span>
                  <span
                    className="text-xs"
                    style={{ color: "var(--color-sentinel-text-disabled)" }}
                  >
                    {formatDate(currentTime)}
                  </span>
                </div>
              </button>

              {/* Calendar Picker */}
              {showCalendar && (
                <CalendarPicker
                  selectedDate={currentTime}
                  onDateSelect={(date) => {
                    // Update time but keep the current time of day
                    const newDate = new Date(date);
                    newDate.setHours(currentTime.getHours());
                    newDate.setMinutes(currentTime.getMinutes());
                    newDate.setSeconds(currentTime.getSeconds());
                    setCurrentTime(newDate);
                  }}
                  onClose={() => setShowCalendar(false)}
                />
              )}
            </div>

            {/* User info and logout */}
            {currentUser && (
              <div className="hidden md:flex items-center gap-2 pl-2 border-l" style={{ borderColor: "var(--color-sentinel-border)" }}>
                <div className="text-right">
                  <div
                    className="text-xs font-medium"
                    style={{ color: "var(--color-sentinel-text-primary)" }}
                  >
                    {currentUser.full_name}
                  </div>
                  <div
                    className="text-xs"
                    style={{ color: "var(--color-sentinel-text-disabled)" }}
                  >
                    {currentUser.role}
                  </div>
                </div>
                <button
                  onClick={handleLogout}
                  className="p-2 rounded-md transition-colors hover:brightness-110"
                  style={{
                    background: "var(--color-sentinel-bg-secondary)",
                    border: "1px solid var(--color-sentinel-border)",
                  }}
                  aria-label="Logout"
                  title="Logout"
                >
                  <LogOut className="h-4 w-4" style={{ color: "var(--color-sentinel-text-secondary)" }} />
                </button>
              </div>
            )}
          </div>
        </header>

        {/* Main content - Takes remaining space */}
        <main
          className="flex-1 overflow-hidden"
          style={{ background: "var(--color-sentinel-bg-canvas)" }}
        >
          {currentView === "dashboard" ? (
            <Dashboard
              key={viewRefreshKey}
              onViewChange={handleViewChange}
              openCardLibrary={showCardLibrary}
              onCardLibraryClose={() => setShowCardLibrary(false)}
            />
          ) : currentView === "control" ? (
            <ControlDashboard onError={(error) => setError(error)} />
          ) : currentView === "control-audit" ? (
            <ControlAuditTrail
              onError={(error) => setError(error)}
              onViewDevice={(deviceId) => {
                sessionStorage.setItem("sentinel_selected_equipment", deviceId);
                sessionStorage.setItem("sentinel_selected_site", "site-002");
                handleViewChange("control");
              }}
            />
          ) : currentView === "optimization" ? (
            <OptimizationPage onError={(error) => setError(error)} />
          ) : currentView === "settings" ? (
            <Settings onError={(error) => setError(error)} />
          ) : currentView === "technician" ? (
            <div className="h-full">
              <TechnicianChat />
            </div>
          ) : currentView === "integrations" ? (
            <IntegrationMonitoringPage />
          ) : currentView === "occupancy" ? (
            <div className="h-full overflow-y-auto p-4 md:p-6">
              <OccupancyPanel compact={false} />
            </div>
          ) : currentView === "workflow" ? (
            <div className="h-full overflow-y-auto">
              <AssetWorkflowDashboard />
            </div>
          ) : currentView === "security" ? (
            <SecurityDashboard />
          ) : currentView === "simbiot" ? (
            <SimbiotPage />
          ) : (
            <div className="h-full p-4 md:p-6">
              <div className="h-full max-w-4xl mx-auto">
                <Chat />
              </div>
            </div>
          )}
        </main>
      </div>

      {/* Toast notifications */}
      <Toaster
        position="top-right"
        toastOptions={{
          style: {
            background: "var(--color-sentinel-bg-panel)",
            border: "1px solid var(--color-sentinel-border)",
            color: "var(--color-sentinel-text-primary)",
          },
        }}
        theme="dark"
      />
    </div>
  );
}

export default App;
