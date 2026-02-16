import { useEffect, useState, useRef, useCallback } from "react";
import { Clock, Wifi, WifiOff, Bell, X, LogOut } from "lucide-react";
import { Toaster, toast } from "sonner";
import { formatTime } from "./lib/timeFormat";
import api, { AUTH_EXPIRED_EVENT, isExpectedApiError, type Alert, type AuthUser } from "./lib/api";
import { SimulationTimeIndicator } from "./components/SimulationTimeIndicator";
import { useRecommendationToasts } from "./components/RecommendationToast";

// Security: Prevent console logging in production (Phase 75-07)
import { initializeSecurityProtections } from "./lib/api/security-utils";
import { Chat } from "./components/Chat";
import TechnicianChat from "./components/TechnicianChat";
import { Dashboard } from "./components/Dashboard";
import { DigitalTwin } from "./components/digital-twin";
import { ControlDashboard } from "./components/ControlDashboard";
import { ControlAuditTrail } from "./components/ControlAuditTrail";
import { OptimizationPage } from "./pages/OptimizationPage";
import { Settings } from "./components/Settings";
import { Sidebar } from "./components/Sidebar";
import { SplashScreen } from "./components/SplashScreen";
import { EmailEntry } from "./components/EmailEntry";
import { AlertFeed } from "./components/AlertFeed";
import { CalendarPicker } from "./components/CalendarPicker";
import SystemHealthPage from "./components/SystemHealthPage";
import { AssetWorkflowDashboard } from "./components/AssetWorkflowDashboard";
import { OccupancyPanel } from "./components/OccupancyPanel";
import { LightingPage } from "./components/lighting/LightingPage";
import { SecurityDashboard } from "./components/SecurityDashboard";
import { SimbiotPage } from "./components/SimbiotPage";
import { SimulationDashboard } from "./components/SimulationDashboard";
import { FleetInsights } from "./components/FleetInsights";
import { MLMetrics } from "./components/MLMetrics";
import { ESGPage } from "./components/sustainability/ESGPage";
import { SolarDashboard } from "./components/solar/SolarDashboard";
import { WaterPanel } from "./components/water";
import { ContractManagementPage } from "./pages/ContractManagementPage";
import { BudgetReportPage } from "./pages/BudgetReportPage";
import { ProfitabilityDashboardPage } from "./pages/ProfitabilityDashboardPage";
import { ModularDashboard } from "./components/modules/ModularDashboard";
import { SolarConfigWizard } from "./components/wizards/SolarConfigWizard";
import { ModuleProvider } from "./contexts/ModuleContext";
import { useModules } from "./contexts/ModuleHooks";
import { ThemeProvider } from "./contexts/ThemeContext";
import { type View, VIEW_TITLES, ALL_NAV_ITEMS } from "./lib/navigation";
import { canAccessView, getDefaultView } from "./lib/access-control";

interface HealthStatus {
  status: string;
  version: string;
}

/**
 * Guard component that checks module access for gated views.
 * Must be rendered inside ModuleProvider.
 */
function ViewGuard({
  currentView,
  userRole,
  onRedirect,
  children,
}: {
  currentView: View;
  userRole?: string;
  onRedirect: (view: View) => void;
  children: React.ReactNode;
}) {
  const { isModuleActive, loading, siteId } = useModules();

  useEffect(() => {
    const currentNavItem = ALL_NAV_ITEMS.find((item) => item.id === currentView);
    if (!loading && siteId && currentNavItem?.requiredModule) {
      const requiredModule = currentNavItem.requiredModule;
      if (requiredModule && !isModuleActive(requiredModule)) {
        toast.info(`The "${VIEW_TITLES[currentView]}" module is not active for this site.`);
        onRedirect("dashboard");
      }
    }
    // Check internal views (simulation requires admin)
    if (currentView === "simulation" && userRole !== "admin") {
      toast.info("Simulation is only available to administrators.");
      onRedirect("dashboard");
    }
  }, [currentView, isModuleActive, userRole, onRedirect]);

  return <>{children}</>;
}

function App() {
  const [showSplash, setShowSplash] = useState(true);
  const [currentUser, setCurrentUser] = useState<AuthUser | null>(() => {
    // Check for stored user on mount
    const storedUser = localStorage.getItem("sentinel_user");
    const storedToken = localStorage.getItem("sentinel_token");
    if (!storedUser || !storedToken) return null;
    return JSON.parse(storedUser);
  });
  const [health, setHealth] = useState<HealthStatus | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [currentView, setCurrentView] = useState<View>("dashboard");
  const [viewRefreshKey, setViewRefreshKey] = useState(0);
  const [showCardLibrary, setShowCardLibrary] = useState(false);
  const [currentTime, setCurrentTime] = useState(new Date());
  const [showAlertsPanel, setShowAlertsPanel] = useState(false);
  const [showCalendar, setShowCalendar] = useState(false);
  const [unreadAlertCount, setUnreadAlertCount] = useState(0);
  const [lastViewedAlertTime, setLastViewedAlertTime] = useState<Date | null>(null);
  const [simulationRunning, setSimulationRunning] = useState(false);
  const alertsPanelRef = useRef<HTMLDivElement | null>(null);
  const calendarButtonRef = useRef<HTMLDivElement | null>(null);
  const audioRef = useRef<HTMLAudioElement | null>(null);

  // Security: Initialize protections on app startup (Phase 75-07)
  useEffect(() => {
    initializeSecurityProtections();
  }, []);

  // Update time every second for Grafana-like time display
  useEffect(() => {
    const timer = setInterval(() => setCurrentTime(new Date()), 1000);
    return () => clearInterval(timer);
  }, []);

  // Monitor simulation status
  useEffect(() => {
    const checkSimulationStatus = async () => {
      try {
        const response = await fetch('/api/lifecycle/status/site-002');
        const data = await response.json();
        setSimulationRunning(data.running === true);
      } catch (error) {
        // Fail silently - simulation might not be running
        setSimulationRunning(false);
      }
    };

    // Check on mount and every 5 seconds
    checkSimulationStatus();
    const interval = setInterval(checkSimulationStatus, 5000);
    return () => clearInterval(interval);
  }, []);

  // Use recommendation toasts hook when logged in
  const siteId = currentUser ? 'site-002' : '';
  useRecommendationToasts(siteId);

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
    let failureCount = 0;
    let timeoutId: number | null = null;

    const fetchUnreadCount = async () => {
      const token = localStorage.getItem("sentinel_token");
      if (!token) return;
      if (document.hidden) {
        timeoutId = window.setTimeout(fetchUnreadCount, 60000);
        return;
      }
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
        failureCount = 0;
      } catch (err) {
        failureCount += 1;
        if (!isExpectedApiError(err)) {
          console.error("Failed to fetch alert count:", err);
        }
      }

      const baseIntervalMs = 60000;
      const backoffIntervalMs = Math.min(300000, baseIntervalMs * (2 ** failureCount));
      timeoutId = window.setTimeout(fetchUnreadCount, backoffIntervalMs);
    };

    fetchUnreadCount();
    return () => {
      if (timeoutId !== null) {
        window.clearTimeout(timeoutId);
      }
    };
  }, [lastViewedAlertTime]);

  // Mark alerts as viewed when panel opens
  const handleAlertsPanelOpen = () => {
    setShowAlertsPanel(true);
    setLastViewedAlertTime(new Date());
    // Don't reset count immediately - let individual alert clicks handle it
  };

  // Handle when an individual alert is marked as read
  const handleAlertRead = () => {
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
      localStorage.removeItem("sentinel_refresh_token");
      localStorage.removeItem("sentinel_user");
      setCurrentUser(null);
      toast.success("Logged out successfully");
    }
  };

  // Force logout when API layer reports auth expiry/invalid refresh.
  useEffect(() => {
    const onAuthExpired = () => {
      setCurrentUser(null);
      toast.error("Session expired. Please sign in again.");
    };
    window.addEventListener(AUTH_EXPIRED_EVENT, onAuthExpired);
    return () => window.removeEventListener(AUTH_EXPIRED_EVENT, onAuthExpired);
  }, []);

  // Handle view changes - scroll to top and refresh when re-clicking same view
  const handleViewChange = useCallback((view: View) => {
    // Check access control - redirect to allowed view if not permitted
    if (currentUser?.email) {
      const allViewIds = ALL_NAV_ITEMS.map(item => item.id);
      if (!canAccessView(currentUser.email, view, allViewIds)) {
        const defaultView = getDefaultView(currentUser.email);
        toast.warning(`Access to ${view} is not available in your demo configuration`);
        if (view !== defaultView) {
          setCurrentView(defaultView);
        }
        return;
      }
    }

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
  }, [currentView, currentUser?.email]);

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

  // Memoize callbacks to prevent SplashScreen/EmailEntry remounting
  const handleSplashComplete = useCallback(() => {
    setShowSplash(false);
  }, []);

  const handleEmailEntrySuccess = useCallback((user: AuthUser) => {
    console.log('Login success:', user);
    setCurrentUser(user);

    // Auto-start demo simulation for demo users
    if ((user as any).demo_auto_start === true) {
      console.log('Auto-starting demo scenario:', (user as any).demo_scenario);
      toast.success(`Demo scenario started: ${(user as any).demo_scenario}`);
      
      // Start the lifecycle simulator in the background
      fetch('/api/lifecycle/start', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ scenario: (user as any).demo_scenario })
      }).catch(err => console.error('Failed to start demo scenario:', err));
    }
  }, []);

  // Show splash screen on initial load
  if (showSplash) {
    return <SplashScreen onComplete={handleSplashComplete} />;
  }

  // Show email entry if not authenticated
  if (!currentUser) {
    console.log('Showing email entry (user =', currentUser, ')');
    return <EmailEntry onSuccess={handleEmailEntrySuccess} />;
  }

  return (
    <ThemeProvider>
    <ModuleProvider initialSiteId="site-002" initialSiteName="Sandton City Office Tower">
    <div
      className="h-screen flex"
      style={{ background: "var(--color-sentinel-bg-canvas)" }}
    >
      {/* Sidebar Navigation */}
      <Sidebar
        currentView={currentView}
        onViewChange={handleViewChange}
        version={health?.version || "13.0"}
        onCustomizeDashboard={() => {
          setShowCardLibrary(true);
          // Navigate to dashboard if not already there (CardLibrary only works on dashboard)
          if (currentView !== "dashboard") {
            setCurrentView("dashboard");
          }
        }}
        userRole={currentUser?.role}
        userEmail={currentUser?.email}
      />

      {/* Simulation Time Indicator - Shows when simulation is running */}
      <SimulationTimeIndicator simulationRunning={simulationRunning} siteId="site-002" />

      {/* Main Content Area */}
      <div className="flex-1 flex flex-col min-w-0">
        {/* Header - SENTINEL style */}
        <header
          className="flex-none h-14 px-4 flex items-center justify-between sticky top-0 z-40"
          style={{
            background: "var(--glass-bg)",
            backdropFilter: "blur(var(--glass-blur)) saturate(180%)",
            WebkitBackdropFilter: "blur(var(--glass-blur)) saturate(180%)",
            borderBottom: "1px solid var(--glass-border)",
            borderRadius: 0,
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
                {VIEW_TITLES[currentView] || "AI Assistant"}
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
          <ViewGuard currentView={currentView} userRole={currentUser?.role} onRedirect={handleViewChange}>
          {currentView === "dashboard" ? (
            <Dashboard
              key={viewRefreshKey}
              onViewChange={handleViewChange}
              openCardLibrary={showCardLibrary}
              onCardLibraryClose={() => setShowCardLibrary(false)}
              userEmail={currentUser?.email}
            />
          ) : currentView === "digital-twin" ? (
            <div className="h-full overflow-hidden">
              <DigitalTwin />
            </div>
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
          ) : currentView === "ai-chat" ? (
            <div className="h-full">
              <Chat />
            </div>
          ) : currentView === "technician" ? (
            <div className="h-full">
              <TechnicianChat />
            </div>
          ) : currentView === "integrations" ? (
            <div className="h-full overflow-y-auto">
              <SystemHealthPage />
            </div>
          ) : currentView === "occupancy" ? (
            <div className="h-full overflow-y-auto p-4 md:p-6">
              <OccupancyPanel compact={false} />
            </div>
          ) : currentView === "lighting" ? (
            <LightingPage />
          ) : currentView === "workflow" ? (
            <div className="h-full overflow-y-auto">
              <AssetWorkflowDashboard />
            </div>
          ) : currentView === "security" ? (
            <SecurityDashboard />
          ) : currentView === "simbiot" ? (
            <SimbiotPage />
          ) : currentView === "simulation" ? (
            <div className="h-full overflow-y-auto">
              <SimulationDashboard />
            </div>
          ) : currentView === "sustainability" ? (
            <div className="h-full overflow-y-auto">
              <ESGPage selectedBuilding={undefined} />
            </div>
          ) : currentView === "fleet" ? (
            <FleetInsights />
          ) : currentView === "mlops" ? (
            <MLMetrics />
          ) : currentView === "solar" ? (
            <SolarDashboard />
          ) : currentView === "water" ? (
            <WaterPanel />
          ) : currentView === "contracts" ? (
            <ContractManagementPage />
          ) : currentView === "profitability" ? (
            <ProfitabilityDashboardPage />
          ) : currentView === "budget-report" ? (
            <BudgetReportPage />
          ) : currentView === "solar-config" ? (
            <div className="h-full overflow-y-auto p-4 md:p-6">
              <SolarConfigWizard />
            </div>
          ) : currentView === "modules" ? (
            <ModularDashboard />
          ) : (
            // Fallback: should never reach here due to View type constraints
            <div className="h-full flex items-center justify-center">
              <div className="text-center">
                <p className="text-gray-400">View not found</p>
              </div>
            </div>
          )}
          </ViewGuard>
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
    </ModuleProvider>
    </ThemeProvider>
  );
}

export default App;
