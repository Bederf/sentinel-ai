import { useEffect, useState, useRef, useCallback, useMemo, Suspense, lazy } from "react";
import { Routes, Route, useParams, useNavigate } from "react-router-dom";
import { Clock, Wifi, WifiOff, Bell, X, LogOut } from "lucide-react";
import { Toaster, toast } from "sonner";
import { formatTime } from "./lib/timeFormat";
import api, { AUTH_EXPIRED_EVENT, isExpectedApiError, type Alert, type AuthUser } from "./lib/api";
import { useRecommendationToasts, RecommendationCard } from "./components/RecommendationToast";
import { useBuildingsList } from "./hooks/useBuildingsList";
import { SITE_SELECTION_CHANGED_EVENT, getStoredSelectedSite } from "./lib/siteSelection";
import { phaseAllows } from "./lib/onboardingPhase";

// Security: Prevent console logging in production (Phase 75-07)
import { initializeSecurityProtections } from "./lib/api/security-utils";
import { Sidebar } from "./components/Sidebar";
import { SplashScreen } from "./components/SplashScreen";
import { EmailEntry } from "./components/EmailEntry";
import { AlertFeed } from "./components/AlertFeed";
import { CalendarPicker } from "./components/CalendarPicker";
import { ModuleProvider } from "./contexts/ModuleContext";
import { useModules } from "./contexts/ModuleHooks";
import { ThemeProvider } from "./contexts/ThemeContext";
import { type View, VIEW_TITLES, ALL_NAV_ITEMS } from "./lib/navigation";
import { canAccessView, getDefaultView } from "./lib/access-control";

const Chat = lazy(() => import("./components/Chat").then(m => ({ default: m.Chat })));
const Dashboard = lazy(() => import("./components/Dashboard").then(m => ({ default: m.Dashboard })));
const ControlAuditTrail = lazy(() => import("./components/ControlAuditTrail").then(m => ({ default: m.ControlAuditTrail })));
const Settings = lazy(() => import("./components/Settings").then(m => ({ default: m.Settings })));
const SystemHealthPage = lazy(() => import("./components/SystemHealthPage"));
const AssetWorkflowDashboard = lazy(() => import("./components/AssetWorkflowDashboard").then(m => ({ default: m.AssetWorkflowDashboard })));
const SimbiotPage = lazy(() => import("./components/SimbiotPage").then(m => ({ default: m.SimbiotPage })));
const FleetInsights = lazy(() => import("./components/FleetInsights").then(m => ({ default: m.FleetInsights })));
const ContractManagementPage = lazy(() => import("./pages/ContractManagementPage").then(m => ({ default: m.ContractManagementPage })));
const SiteDetail = lazy(() => import("./components/SiteDetail").then(m => ({ default: m.SiteDetail })));

interface HealthStatus {
  status: string;
  version: string;
}

/**
 * Route component for /buildings/:siteId — renders SiteDetail at a stable URL.
 * onBack navigates to / (portfolio dashboard).
 */
function BuildingRoute() {
  const { siteId } = useParams<{ siteId: string }>();
  const navigate = useNavigate();
  if (!siteId) return null;
  return (
    <SiteDetail siteId={siteId} onBack={() => navigate("/")} defaultMainTab="overview" />
  );
}

function RouteLoading() {
  return (
    <div className="h-full flex items-center justify-center">
      <div className="text-sm" style={{ color: "var(--color-sentinel-text-secondary)" }}>
        Loading view...
      </div>
    </div>
  );
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
    // Simulation is now a building tab, not a sidebar view
  }, [currentView, isModuleActive, loading, siteId, userRole, onRedirect]);

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

  // Resolve primary site from registered buildings (no hardcoded site ID)
  const { data: buildings = [] } = useBuildingsList({ enabled: !!currentUser });
  const primarySiteId = useMemo(() => buildings[0]?.id || null, [buildings]);
  const primarySiteName = useMemo(() => buildings[0]?.name || null, [buildings]);
  const [selectedSiteId, setSelectedSiteId] = useState<string | null>(() => getStoredSelectedSite());
  const selectedSite = useMemo(
    () => buildings.find((building) => building.id === selectedSiteId) || null,
    [buildings, selectedSiteId]
  );
  // Only use a selected site if it is present in the currently accessible buildings.
  const effectiveSiteId = selectedSite?.id || primarySiteId || "";
  const effectiveSiteName = selectedSite?.name || primarySiteName || undefined;
  // Auto-landing: if user only has one site with space module, go straight there
  const [autoSelectSiteId, setAutoSelectSiteId] = useState<string | null>(null);
  const [defaultBuildingTab, setDefaultBuildingTab] = useState<import("./lib/navigation").BuildingTabId | undefined>(undefined);

  useEffect(() => {
    if (!currentUser?.email || buildings.length === 0) return;
    const token = localStorage.getItem("sentinel_token");
    if (!token) return;
    const headers = { Authorization: `Bearer ${token}` };

    // Check user's site access — if they have exactly one site, auto-select it
    fetch("/api/user-access/me/sites", { headers })
      .then(res => res.ok ? res.json() : null)
      .then(data => {
        const sites = data?.sites || [];
        if (sites.length === 1) {
          setAutoSelectSiteId(sites[0].site_id);
          // Check if they only have space module for this site
          fetch(`/api/user-access/me/modules?site_code=${encodeURIComponent(sites[0].site_code)}`, { headers })
            .then(res => res.ok ? res.json() : null)
            .then(modData => {
              const modules: string[] = modData?.effective_modules || [];
              if (modules.includes("space_optimization") && modules.length <= 2) {
                setDefaultBuildingTab("space");
              }
            })
            .catch(() => {});
        }
      })
      .catch(() => {});
  }, [currentUser?.email, buildings.length]);

  useEffect(() => {
    if (buildings.length === 0) return;

    const storedSiteId = getStoredSelectedSite();
    // Reject site-001 — it is a future/inactive site
    const preferredSiteId = (storedSiteId && storedSiteId !== "site-001") ? storedSiteId : selectedSiteId;
    const validSiteId = preferredSiteId && buildings.some((building) => building.id === preferredSiteId)
      ? preferredSiteId
      : buildings.find(b => b.id !== "site-001")?.id || null;

    if (validSiteId !== selectedSiteId) {
      setSelectedSiteId(validSiteId);
    }
  }, [buildings, selectedSiteId]);

  useEffect(() => {
    const handleSiteSelectionChanged = (event: Event) => {
      const customEvent = event as CustomEvent<{ siteId?: string | null }>;
      const nextSiteId = customEvent.detail?.siteId || getStoredSelectedSite();
      // Reject site-001 — it is a future/inactive site
      if (nextSiteId === "site-001") return;
      setSelectedSiteId(nextSiteId || null);
    };

    window.addEventListener(SITE_SELECTION_CHANGED_EVENT, handleSiteSelectionChanged as EventListener);
    return () => {
      window.removeEventListener(SITE_SELECTION_CHANGED_EVENT, handleSiteSelectionChanged as EventListener);
    };
  }, []);

  const [health, setHealth] = useState<HealthStatus | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [currentView, setCurrentView] = useState<View>("dashboard");
  const [viewRefreshKey, setViewRefreshKey] = useState(0);
  const [chatKey, setChatKey] = useState(0);
  // Card library removed — dashboard now shows only portfolio-level sections
  const [currentTime, setCurrentTime] = useState(new Date());
  const [showAlertsPanel, setShowAlertsPanel] = useState(false);
  const [showCalendar, setShowCalendar] = useState(false);
  const [unreadAlertCount, setUnreadAlertCount] = useState(0);
  const [lastViewedAlertTime, setLastViewedAlertTime] = useState<Date | null>(null);
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

  // AI Recommendation card state
  // eslint-disable-next-line @typescript-eslint/no-explicit-any -- RecommendationData type not exported from RecommendationToast
  const [selectedRec, setSelectedRec] = useState<any>(null);
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const handleShowRecCard = useCallback((rec: any) => setSelectedRec(rec), []);
  const handleApproveRec = useCallback(async (id: string) => {
    try {
      const token = localStorage.getItem('sentinel_token');
      await fetch(`/api/approvals/recommendations/${id}/approve`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${token || ''}`,
        },
        body: JSON.stringify({ approved_by: 'dashboard' }),
      });
    } catch (_e) { /* silent */ }
    setSelectedRec(null);
  }, []);

  // Use recommendation toasts hook when logged in — only in advisory+ (sentry_notifications gate)
  const siteId = currentUser ? effectiveSiteId : '';
  const showToasts = currentUser && phaseAllows(selectedSite?.onboarding_phase, "sentry_notifications");
  useRecommendationToasts(showToasts ? siteId : '', handleShowRecCard);

  // Initialize devices from the connected site on login
  useEffect(() => {
    if (!currentUser) return;

    const initializeDevices = async () => {
      try {
        const token = localStorage.getItem('sentinel_token');
        if (!token) return;

        const apiUrl = import.meta.env.VITE_API_URL || '';
        const response = await fetch(`${apiUrl}/api/devices/init`, {
          method: 'POST',
          headers: {
            'Authorization': `Bearer ${token}`,
            'Content-Type': 'application/json',
          },
        });

        if (response.ok) {
          await response.json();
        }
      } catch (_error) {
        // Device initialization skipped silently
      }
    };

    initializeDevices();
  }, [currentUser]);

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

  // Handle alert click - navigate to equipment on dashboard
  const handleAlertClick = (alert: Alert) => {
    // Store alert context so the dashboard can highlight the relevant equipment
    const deviceId = alert.device_id || alert.equipment_id;
    if (deviceId && alert.site_id) {
      sessionStorage.setItem("sentinel_selected_equipment", deviceId);
      // Only persist site if it's active (not site-001 which is a future/inactive site)
      if (alert.site_id !== "site-001") {
        sessionStorage.setItem("sentinel_selected_site", alert.site_id);
      }
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

    // Navigate to dashboard (site detail with building tabs)
    handleViewChange("dashboard");
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

    // Reset to start so re-clicks always play
    audioRef.current.currentTime = 0;

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
        toast.warning(`Access to ${view} is not available in your assigned access profile`);
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
      if (view === "ai-chat") setChatKey(k => k + 1);
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

  const handleEmailEntrySuccess = useCallback((user: AuthUser, _token: string) => {
    setCurrentUser(user);
  }, []);

  // Show splash screen on initial load
  if (showSplash) {
    return <SplashScreen onComplete={handleSplashComplete} />;
  }

  // Show email entry if not authenticated
  if (!currentUser) {
    return <EmailEntry onSuccess={handleEmailEntrySuccess} />;
  }

  return (
    <ThemeProvider>
    <ModuleProvider initialSiteId={effectiveSiteId || undefined} initialSiteName={effectiveSiteName}>
    <Routes>
      <Route path="/buildings/:siteId" element={<Suspense fallback={<RouteLoading />}><BuildingRoute /></Suspense>} />
      <Route path="*" element={
    <div
      className="h-screen flex"
      style={{ background: "var(--color-sentinel-bg-canvas)" }}
    >
      {/* Sidebar Navigation */}
      <Sidebar
        currentView={currentView}
        onViewChange={handleViewChange}
        version={health?.version || "13.0"}
        userRole={currentUser?.role}
        userEmail={currentUser?.email}
      />

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
          className="flex-1 min-h-0 overflow-hidden"
          style={{ background: "var(--color-sentinel-bg-canvas)" }}
        >
          <ViewGuard currentView={currentView} userRole={currentUser?.role} onRedirect={handleViewChange}>
          <Suspense fallback={<RouteLoading />}>
          {currentView === "dashboard" ? (
            <Dashboard
              key={viewRefreshKey}
              onViewChange={handleViewChange}
              autoSelectSiteId={autoSelectSiteId}
              defaultBuildingTab={defaultBuildingTab}
            />
          ) : currentView === "ai-chat" ? (
            <div className="h-full">
              <Chat key={chatKey} />
            </div>
          ) : currentView === "integrations" ? (
            <div className="h-full overflow-y-auto">
              <SystemHealthPage />
            </div>
          ) : currentView === "logs" ? (
            <ControlAuditTrail
              onError={(error) => setError(error)}
              onViewDevice={(deviceId) => {
                sessionStorage.setItem("sentinel_selected_equipment", deviceId);
                if (primarySiteId) sessionStorage.setItem("sentinel_selected_site", primarySiteId);
                handleViewChange("dashboard");
              }}
            />
          ) : currentView === "simbiot" ? (
            <SimbiotPage />
          ) : currentView === "settings" ? (
            <Settings siteId={effectiveSiteId || undefined} onError={setError} onNavigate={handleViewChange} />
          ) : currentView === "maintenance" ? (
            <div className="h-full overflow-y-auto">
              <AssetWorkflowDashboard />
            </div>
          ) : currentView === "financial" ? (
            <ContractManagementPage />
          ) : currentView === "fleet-ml" ? (
            <FleetInsights />
          ) : (
            <div className="h-full flex items-center justify-center">
              <div className="text-center">
                <p className="text-gray-400">View not found</p>
              </div>
            </div>
          )}
          </Suspense>
          </ViewGuard>
        </main>
      </div>

      {/* AI Recommendation detail card */}
      {selectedRec && (
        <RecommendationCard
          recommendation={selectedRec}
          onClose={() => setSelectedRec(null)}
          onApprove={handleApproveRec}
          sitePhase={selectedSite?.onboarding_phase}
        />
      )}

      {/* Toast notifications */}
      <Toaster
        position="bottom-right"
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
      } />
    </Routes>
    </ModuleProvider>
    </ThemeProvider>
  );
}

export default App;
