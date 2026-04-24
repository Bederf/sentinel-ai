/**
 * Space Optimization Page
 *
 * Outlook booking intake, block-booking anomaly alerts, room right-sizing,
 * focus room analytics, and occupancy trend visibility.
 */

import { useState, useEffect, useCallback, useRef } from "react";
import {
  LayoutGrid,
  Mail,
  TrendingDown,
  Focus,
  RefreshCw,
  AlertTriangle,
  CheckCircle2,
  Clock,
  Users,
  XCircle,
  ChevronDown,
  ChevronUp,
  DoorOpen,
  BarChart3,
  Orbit,
} from "lucide-react";
import { gsap } from "gsap";

import { authorizedFetch } from "@/lib/api";
import { ConciergeDashboardPage } from "./intelligence/ConciergeDashboardPage";

interface BlockBookingAlert {
  id: string;
  organiser_email: string;
  organiser_name: string;
  rooms: string[];
  room_count: number;
  overlap_window_start: string;
  overlap_window_end: string;
  detected_at: string;
  notification_sent: boolean;
  dismissed: boolean;
}

interface GhostFinding {
  id: string;
  room_code: string;
  room_name: string;
  booking_id: string;
  organiser_email: string;
  organiser_name: string;
  booking_start: string;
  booking_end: string;
  grace_period_minutes: number;
  detected_at: string;
  status: "open" | "pending_inspection" | "verified_occupied" | "confirmed_empty" | "dismissed";
  notification_sent: boolean;
  email_notified_at: string | null;
  whatsapp_notified_at: string | null;
  whatsapp_message_id: string | null;
  response_text: string | null;
}

interface IngestedBooking {
  id: string;
  organiser_email: string;
  organiser_name: string;
  room_name: string;
  booking_date: string;
  start_time: string;
  end_time: string;
  flagged: boolean;
  ingested_at?: string;
  created_at?: string;
}

interface RightsizingFinding {
  id: string;
  room_code: string;
  room_name: string;
  room_capacity: number;
  booking_id: string;
  organiser_email: string;
  organiser_name: string;
  booking_start: string;
  booking_end: string;
  booking_duration_minutes: number;
  occupied_minutes: number;
  consecutive_vacancy_minutes: number;
  pattern_type: "EARLY_VACATE" | "BRIEF_OCCUPATION" | "SPORADIC_USE";
  detected_at: string;
  status: "open" | "acknowledged" | "dismissed";
  notification_sent: boolean;
}

interface FocusSession {
  session_id: string;
  room_code: string;
  room_type: string;
  sensor_id: string;
  start_time: string;
  end_time: string | null;
  duration_seconds: number;
  duration_minutes: number;
  extended_use: boolean;
  red_light_on: boolean;
  max_allowed_minutes: number;
  red_light_cooldown_seconds?: number;
  red_light_cooldown_remaining_seconds?: number;
  is_active: boolean;
}

interface FocusAnalytics {
  site_id: string;
  total_sessions: number;
  active_sessions: number;
  completed_sessions: number;
  extended_use_sessions: number;
  average_duration_minutes: number;
  peak_hour: number | null;
  sessions_by_room: Record<string, number>;
}

interface HourlyTrend {
  hour: number;
  occupancy_percent: number;
  zone_type: string;
}

type TabId = "intelligence" | "block" | "ghost" | "rightsizing" | "focus" | "trends";

export function SpaceOptimizationPage({ siteId: propSiteId }: { siteId?: string } = {}) {
  const [activeTab, setActiveTab] = useState<TabId>("intelligence");
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [entered, setEntered] = useState(false);

  // GSAP animation refs
  const headerRef = useRef<HTMLDivElement>(null);
  const kpiGridRef = useRef<HTMLDivElement>(null);
  const tabBarRef = useRef<HTMLDivElement>(null);
  const tabContentRef = useRef<HTMLDivElement>(null);
  const tabKeyRef = useRef(activeTab);

  const [blockAlerts, setBlockAlerts] = useState<BlockBookingAlert[]>([]);
  const [ghostFindings, setGhostFindings] = useState<GhostFinding[]>([]);
  const [ingestedBookings, setIngestedBookings] = useState<IngestedBooking[]>([]);
  const [totalIngested, setTotalIngested] = useState(0);
  const [rightsizingFindings, setRightsizingFindings] = useState<RightsizingFinding[]>([]);
  const [focusSessions, setFocusSessions] = useState<FocusSession[]>([]);
  const [focusAnalytics, setFocusAnalytics] = useState<FocusAnalytics | null>(null);
  const [hourlyTrends, setHourlyTrends] = useState<HourlyTrend[]>([]);

  const siteId = propSiteId || (() => {
    try {
      return sessionStorage.getItem("sentinel_selected_site") || "site-002";
    } catch {
      return "site-002";
    }
  })();

  const fetchData = useCallback(async (showRefreshing = false) => {
    try {
      if (showRefreshing) setRefreshing(true);
      else setLoading(true);

      const headers = { "x-site-id": siteId };
      const trendsUrl = `/api/occupancy/analytics/hourly-trend?site_id=${encodeURIComponent(siteId)}&days=7`;

      const sq = `site_id=${encodeURIComponent(siteId)}`;
      const [alertsRes, ghostRes, bookingsRes, rightsizingRes, focusRes, analyticsRes, trendsRes] = await Promise.all([
        authorizedFetch(`/api/block-bookings/alerts?${sq}`, { headers }),
        authorizedFetch(`/api/space/ghost-findings?${sq}`, { headers }),
        authorizedFetch(`/api/block-bookings/bookings?${sq}`, { headers }),
        authorizedFetch(`/api/space/rightsizing-findings?${sq}`, { headers }),
        authorizedFetch(`/api/space/focus-sessions?${sq}`, { headers }),
        authorizedFetch(`/api/space/focus-analytics?${sq}`, { headers }),
        authorizedFetch(trendsUrl, { headers }),
      ]);
      const apiErrors: string[] = [];

      const readApiError = async (label: string, response: Response) => {
        let detail = response.statusText || `HTTP ${response.status}`;
        try {
          const body = await response.json() as { detail?: string; message?: string };
          detail = body.detail || body.message || detail;
        } catch {
          // ignore JSON parse issues
        }
        apiErrors.push(`${label}: ${detail}`);
      };

      if (alertsRes.ok) {
        const data = await alertsRes.json();
        setBlockAlerts(data.alerts || []);
      } else {
        await readApiError("block booking alerts", alertsRes);
      }
      if (ghostRes.ok) {
        const data = await ghostRes.json();
        setGhostFindings(data.findings || []);
      } else {
        await readApiError("ghost rooms", ghostRes);
      }
      if (bookingsRes.ok) {
        const data = await bookingsRes.json();
        setIngestedBookings(data.bookings || []);
        setTotalIngested(data.total_ingested ?? data.bookings?.length ?? 0);
      } else {
        await readApiError("bookings", bookingsRes);
      }
      if (rightsizingRes.ok) {
        const data = await rightsizingRes.json();
        setRightsizingFindings(data.findings || []);
      } else {
        await readApiError("right-sizing", rightsizingRes);
      }
      if (focusRes.ok) {
        const data = await focusRes.json();
        setFocusSessions(data.sessions || []);
      } else {
        await readApiError("focus rooms", focusRes);
      }
      if (analyticsRes.ok) {
        setFocusAnalytics(await analyticsRes.json());
      } else {
        await readApiError("focus analytics", analyticsRes);
      }
      if (trendsRes.ok) {
        const data = await trendsRes.json();
        setHourlyTrends(transformHourlyTrendData(data));
      } else {
        await readApiError("occupancy trends", trendsRes);
      }

      setError(apiErrors.length > 0 ? `Failed to load: ${apiErrors.join("; ")}` : null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load space optimization data");
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, [siteId]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  useEffect(() => {
    const interval = setInterval(() => fetchData(true), 30000);
    return () => clearInterval(interval);
  }, [fetchData]);

  // GSAP entrance animations
  useEffect(() => {
    if (!entered || loading) return;
    const prefersReduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    if (prefersReduced) { setEntered(true); return; }

    const ctx = gsap.context(() => {
      // Header: slide in from top + fade
      gsap.fromTo(headerRef.current,
        { y: -24, opacity: 0 },
        { y: 0, opacity: 1, duration: 0.55, ease: "power3.out" }
      );

      // KPI cards: staggered cascade
      const kpiCards = kpiGridRef.current?.querySelectorAll(".kpi-card");
      if (kpiCards?.length) {
        gsap.fromTo(kpiCards,
          { y: 28, opacity: 0 },
          {
            y: 0, opacity: 1,
            duration: 0.45,
            ease: "power3.out",
            stagger: 0.07,
            delay: 0.15,
          }
        );
      }

      // Tab bar
      gsap.fromTo(tabBarRef.current,
        { y: 12, opacity: 0 },
        { y: 0, opacity: 1, duration: 0.4, ease: "power3.out", delay: 0.3 }
      );

      // Initial tab content
      gsap.fromTo(tabContentRef.current,
        { opacity: 0, y: 10 },
        { opacity: 1, y: 0, duration: 0.35, ease: "power3.out", delay: 0.4 }
      );
    });
    return () => ctx.revert();
  }, [entered, loading]);

  // Animate tab content on tab change
  useEffect(() => {
    if (!entered) return;
    const prefersReduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    if (prefersReduced) return;

    if (tabKeyRef.current !== activeTab) {
      tabKeyRef.current = activeTab;
      gsap.to(tabContentRef.current, {
        opacity: 0,
        y: 8,
        duration: 0.18,
        ease: "power2.in",
        onComplete: () => {
          gsap.fromTo(tabContentRef.current,
            { opacity: 0, y: 10 },
            { opacity: 1, y: 0, duration: 0.3, ease: "power3.out" }
          );
        },
      });
    }
  }, [activeTab, entered]);

  // Mark entered on first data load
  useEffect(() => {
    if (!loading) {
      setEntered(true);
    }
  }, [loading]);

  const handleDismissBlockAlert = async (alertId: string) => {
    try {
      const res = await authorizedFetch(`/api/block-bookings/alerts/${alertId}/dismiss`, {
        method: "POST",
        headers: { "Content-Type": "application/json", "x-site-id": siteId },
        body: JSON.stringify({ dismissed_by: "admin" }),
      });
      if (res.ok) {
        setBlockAlerts((prev) => prev.filter((alert) => alert.id !== alertId));
      }
    } catch {
      // silent for now
    }
  };

  const handleDismissSpaceFinding = async (findingId: string) => {
    try {
      const res = await authorizedFetch(`/api/space/findings/${findingId}/dismiss`, {
        method: "POST",
        headers: { "Content-Type": "application/json", "x-site-id": siteId },
        body: JSON.stringify({ dismissed_by: "admin" }),
      });
      if (res.ok) {
        setRightsizingFindings((prev) => prev.filter((finding) => finding.id !== findingId));
      }
    } catch {
      // silent for now
    }
  };

  const handleGhostOutcome = async (findingId: string, occupied: boolean) => {
    try {
      const res = await authorizedFetch(`/api/space/findings/${findingId}/inspection-outcome`, {
        method: "POST",
        headers: { "Content-Type": "application/json", "x-site-id": siteId },
        body: JSON.stringify({ confirmed_by: "dashboard", occupied }),
      });
      if (res.ok) {
        setGhostFindings((prev) =>
          prev.map((finding) =>
            finding.id === findingId
              ? { ...finding, status: occupied ? "verified_occupied" : "confirmed_empty", response_text: occupied ? "yes" : "no" }
              : finding,
          ),
        );
      }
    } catch {
      // silent for now
    }
  };

  const openBlockAlerts = blockAlerts.filter((alert) => !alert.dismissed).length;
  const openGhostFindings = ghostFindings.filter((finding) => ["open", "pending_inspection"].includes(finding.status)).length;
  const openRightsizing = rightsizingFindings.filter((finding) => finding.status === "open").length;
  const activeFocusSessions = focusSessions.filter((session) => session.is_active).length;
  const flaggedBookings = ingestedBookings.filter((booking) => booking.flagged).length;

  const tabs: { id: TabId; label: string; count?: number }[] = [
    { id: "intelligence", label: "Meeting Room Intelligence" },
    { id: "block", label: "Block Bookings" },
    { id: "ghost", label: "Ghost Rooms" },
    { id: "rightsizing", label: "Right-Sizing" },
    { id: "focus", label: "Focus Rooms" },
    { id: "trends", label: "Occupancy Trends" },
  ];

  if (loading) {
    return (
      <div
        className="h-full flex items-center justify-center"
        style={{ background: "var(--color-sentinel-bg-canvas)" }}
      >
        <div className="text-center">
          <div
            className="animate-spin h-8 w-8 border-2 rounded-full mx-auto mb-3"
            style={{ borderColor: "var(--color-sentinel-blue)", borderTopColor: "transparent" }}
          />
          <p className="text-sm" style={{ color: "var(--color-sentinel-text-secondary)" }}>
            Loading space optimization...
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="p-4 md:p-6 max-w-7xl mx-auto space-y-6" style={{ background: "var(--color-sentinel-bg-canvas)" }}>
      <div ref={headerRef} className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4 opacity-0">
        <div className="flex items-center gap-3">
          <div className="p-2 rounded" style={{ background: "rgba(13, 148, 136, 0.15)" }}>
            <LayoutGrid className="h-6 w-6" style={{ color: "var(--color-sentinel-teal)" }} />
          </div>
          <div>
            <h1 className="text-2xl font-bold" style={{ color: "var(--color-sentinel-text-primary)" }}>
              Space Optimization
            </h1>
            <p className="text-sm" style={{ color: "var(--color-sentinel-text-secondary)" }}>
              Outlook booking intake, block-booking anomalies, ghost-room inspections, right-sizing, and focus-room analytics
            </p>
          </div>
        </div>
        <button
          onClick={() => fetchData(true)}
          disabled={refreshing}
          className="flex items-center gap-2 px-3 py-1.5 rounded text-sm font-medium transition-colors"
          style={{
            background: "var(--color-sentinel-bg-secondary)",
            color: "var(--color-sentinel-text-primary)",
            border: "1px solid var(--color-sentinel-border)",
          }}
        >
          <RefreshCw className={`h-4 w-4 ${refreshing ? "animate-spin" : ""}`} />
          Refresh
        </button>
      </div>

      {error && (
        <div
          className="rounded-md p-4 flex items-center gap-3"
          style={{ background: "rgba(220, 38, 38, 0.1)", border: "1px solid rgba(220, 38, 38, 0.3)" }}
        >
          <AlertTriangle className="h-5 w-5" style={{ color: "var(--color-sentinel-red)" }} />
          <span style={{ color: "var(--color-sentinel-red)" }}>{error}</span>
        </div>
      )}

      <div ref={kpiGridRef} className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-5 gap-4">
        <KpiCard
          icon={<Orbit className="h-5 w-5" />}
          label="Meeting Room Intelligence"
          value={openBlockAlerts + openGhostFindings}
          color="#3b82f6"
          bgColor="rgba(59, 130, 246, 0.15)"
          subtitle="room signals for this building"
        />
        <KpiCard
          icon={<Mail className="h-5 w-5" />}
          label="Block Booking Alerts"
          value={openBlockAlerts}
          total={blockAlerts.length}
          color={openBlockAlerts > 0 ? "var(--color-sentinel-red)" : "var(--color-sentinel-green)"}
          bgColor={openBlockAlerts > 0 ? "rgba(220, 38, 38, 0.15)" : "rgba(16, 185, 129, 0.15)"}
          subtitle={openBlockAlerts > 0 ? "concierge follow-up required" : "all clear"}
        />
        <KpiCard
          icon={<AlertTriangle className="h-5 w-5" />}
          label="Ghost Rooms"
          value={openGhostFindings}
          total={ghostFindings.length}
          color={openGhostFindings > 0 ? "var(--color-sentinel-red)" : "var(--color-sentinel-green)"}
          bgColor={openGhostFindings > 0 ? "rgba(220, 38, 38, 0.15)" : "rgba(16, 185, 129, 0.15)"}
          subtitle={openGhostFindings > 0 ? "inspection in progress" : "no open ghost rooms"}
        />
        <KpiCard
          icon={<TrendingDown className="h-5 w-5" />}
          label="Right-Sizing"
          value={openRightsizing}
          total={rightsizingFindings.length}
          color={openRightsizing > 0 ? "var(--color-sentinel-amber)" : "var(--color-sentinel-green)"}
          bgColor={openRightsizing > 0 ? "rgba(245, 158, 11, 0.15)" : "rgba(16, 185, 129, 0.15)"}
          subtitle={openRightsizing > 0 ? "patterns detected" : "well utilized"}
        />
        <KpiCard
          icon={<Focus className="h-5 w-5" />}
          label="Active Focus Sessions"
          value={activeFocusSessions}
          total={focusSessions.length}
          color="var(--color-sentinel-blue)"
          bgColor="rgba(59, 130, 246, 0.15)"
          subtitle={`${focusSessions.filter((session) => session.extended_use).length} extended`}
        />
        <KpiCard
          icon={<Clock className="h-5 w-5" />}
          label="Booking Emails Ingested"
          value={totalIngested}
          color="var(--color-sentinel-teal)"
          bgColor="rgba(13, 148, 136, 0.15)"
          subtitle={`${flaggedBookings} flagged`}
        />
      </div>

      <div ref={tabBarRef} className="flex gap-1 border-b opacity-0" style={{ borderColor: "var(--color-sentinel-border)" }}>
        {tabs.map((tab) => (
          <button
            key={tab.id}
            onClick={() => setActiveTab(tab.id)}
            className="space-optim-tab px-4 py-2.5 text-sm font-medium border-b-2 transition-colors"
            style={{
              borderColor: activeTab === tab.id ? "var(--color-sentinel-teal)" : "transparent",
              color: activeTab === tab.id ? "var(--color-sentinel-teal)" : "var(--color-sentinel-text-secondary)",
            }}
          >
            {tab.label}
            {tab.count !== undefined && tab.count > 0 && (
              <span
                className="ml-2 text-xs px-1.5 py-0.5 rounded-full"
                style={{
                  background: activeTab === tab.id ? "rgba(13,148,136,0.2)" : "var(--color-sentinel-bg-secondary)",
                  color: activeTab === tab.id ? "var(--color-sentinel-teal)" : "var(--color-sentinel-text-secondary)",
                }}
              >
                {tab.count}
              </span>
            )}
          </button>
        ))}
      </div>

      <div ref={tabContentRef} className="opacity-0">
      {activeTab === "intelligence" && (
        <MeetingRoomIntelligencePanel siteId={siteId} />
      )}
      {activeTab === "block" && (
        <BlockBookingsPanel
          alerts={blockAlerts}
          bookings={ingestedBookings}
          onDismissAlert={handleDismissBlockAlert}
        />
      )}
      {activeTab === "ghost" && (
        <GhostRoomsPanel findings={ghostFindings} onSetOutcome={handleGhostOutcome} />
      )}
      {activeTab === "rightsizing" && (
        <RightsizingPanel findings={rightsizingFindings} onDismiss={handleDismissSpaceFinding} />
      )}
      {activeTab === "focus" && (
        <FocusRoomsPanel sessions={focusSessions} analytics={focusAnalytics} />
      )}
      {activeTab === "trends" && (
        <OccupancyTrendsPanel trends={hourlyTrends} />
      )}
      </div>
    </div>
  );
}

function MeetingRoomIntelligencePanel({ siteId }: { siteId: string }) {
  return (
    <div className="space-y-4">
      <div
        className="rounded-md p-4"
        style={{ background: "var(--color-sentinel-bg-panel)", border: "1px solid var(--color-sentinel-border)" }}
      >
        <p className="text-sm font-medium mb-1" style={{ color: "var(--color-sentinel-text-primary)" }}>
          Concierge room intelligence
        </p>
        <p className="text-xs leading-6" style={{ color: "var(--color-sentinel-text-secondary)" }}>
          Room intelligence here is locked to this building only. Meeting-room issue emails, block bookings, ghost rooms,
          and related concierge signals are grouped by room so the concierge can work directly from the Space tab.
        </p>
      </div>

      <div
        className="rounded-md overflow-hidden"
        style={{ background: "var(--color-sentinel-bg-panel)", border: "1px solid var(--color-sentinel-border)" }}
      >
        <div className="h-[720px] min-h-[540px]">
          <ConciergeDashboardPage siteId={siteId} siteLabel="Sandton City" showHeader={false} />
        </div>
      </div>
    </div>
  );
}

function GhostRoomsPanel({
  findings,
  onSetOutcome,
}: {
  findings: GhostFinding[];
  onSetOutcome: (id: string, occupied: boolean) => void;
}) {
  if (findings.length === 0) {
    return (
      <EmptyState
        icon={<AlertTriangle className="h-8 w-8" />}
        message="No ghost-room findings"
        detail="SENTINEL will flag a room when a booking starts and no presence is detected for 15 minutes."
      />
    );
  }

  const statusStyles: Record<GhostFinding["status"], { label: string; color: string; bg: string }> = {
    open: { label: "Open", color: "var(--color-sentinel-red)", bg: "rgba(220, 38, 38, 0.15)" },
    pending_inspection: { label: "Pending Inspection", color: "var(--color-sentinel-amber)", bg: "rgba(245, 158, 11, 0.15)" },
    verified_occupied: { label: "Verified Occupied", color: "var(--color-sentinel-green)", bg: "rgba(16, 185, 129, 0.15)" },
    confirmed_empty: { label: "Confirmed Empty", color: "var(--color-sentinel-teal)", bg: "rgba(13,148,136,0.15)" },
    dismissed: { label: "Dismissed", color: "var(--color-sentinel-text-disabled)", bg: "rgba(148, 163, 184, 0.12)" },
  };

  return (
    <div className="space-y-3">
      <div
        className="rounded-md p-4"
        style={{ background: "var(--color-sentinel-bg-panel)", border: "1px solid var(--color-sentinel-border)" }}
      >
        <p className="text-sm font-medium mb-1" style={{ color: "var(--color-sentinel-text-primary)" }}>
          Ghost room rule
        </p>
        <p className="text-xs leading-6" style={{ color: "var(--color-sentinel-text-secondary)" }}>
          When a booked meeting room shows no presence after the configured grace period, SENTINEL flags the room,
          sends the concierge an email, and sends a WhatsApp inspection message.
        </p>
      </div>

      {findings.map((finding) => {
        const statusMeta = statusStyles[finding.status];
        const actionable = finding.status === "open" || finding.status === "pending_inspection";

        return (
          <div
            key={finding.id}
            className="rounded-md p-4"
            style={{ background: "var(--color-sentinel-bg-panel)", border: "1px solid var(--color-sentinel-border)" }}
          >
            <div className="flex items-start gap-3">
              <div className="p-2 rounded" style={{ background: statusMeta.bg }}>
                <AlertTriangle className="h-4 w-4" style={{ color: statusMeta.color }} />
              </div>
              <div className="flex-1 min-w-0 space-y-3">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="text-sm font-medium" style={{ color: "var(--color-sentinel-text-primary)" }}>
                    {shortRoom(finding.room_code)}
                  </span>
                  <span className="text-xs px-2 py-0.5 rounded-full" style={{ background: statusMeta.bg, color: statusMeta.color }}>
                    {statusMeta.label}
                  </span>
                  <span
                    className="text-xs px-2 py-0.5 rounded-full"
                    style={{
                      background: finding.notification_sent ? "rgba(16, 185, 129, 0.15)" : "rgba(245, 158, 11, 0.15)",
                      color: finding.notification_sent ? "var(--color-sentinel-green)" : "var(--color-sentinel-amber)",
                    }}
                  >
                    {finding.notification_sent ? "notifications sent" : "notification pending"}
                  </span>
                </div>

                <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 gap-3">
                  <DetailItem label="Organiser" value={finding.organiser_name || finding.organiser_email} />
                  <DetailItem label="Booking" value={`${formatTime(finding.booking_start)} - ${formatTime(finding.booking_end)}`} />
                  <DetailItem label="Detected" value={formatDateTime(finding.detected_at)} />
                  <DetailItem
                    label="Channels"
                    value={[
                      finding.email_notified_at ? "Email" : null,
                      finding.whatsapp_notified_at ? "WhatsApp" : null,
                    ].filter(Boolean).join(" + ") || "Pending"}
                  />
                </div>

                {finding.response_text && (
                  <p className="text-xs" style={{ color: "var(--color-sentinel-text-secondary)" }}>
                    Concierge reply: <span style={{ color: "var(--color-sentinel-text-primary)" }}>{finding.response_text}</span>
                  </p>
                )}

                {actionable && (
                  <div className="flex flex-wrap gap-2 pt-1">
                    <button
                      onClick={() => onSetOutcome(finding.id, true)}
                      className="flex items-center gap-1.5 px-3 py-1.5 rounded text-xs font-medium transition-colors"
                      style={{
                        background: "rgba(16, 185, 129, 0.15)",
                        color: "var(--color-sentinel-green)",
                        border: "1px solid rgba(16, 185, 129, 0.25)",
                      }}
                    >
                      <CheckCircle2 className="h-3.5 w-3.5" />
                      Mark Occupied
                    </button>
                    <button
                      onClick={() => onSetOutcome(finding.id, false)}
                      className="flex items-center gap-1.5 px-3 py-1.5 rounded text-xs font-medium transition-colors"
                      style={{
                        background: "rgba(220, 38, 38, 0.15)",
                        color: "var(--color-sentinel-red)",
                        border: "1px solid rgba(220, 38, 38, 0.25)",
                      }}
                    >
                      <XCircle className="h-3.5 w-3.5" />
                      Mark Empty
                    </button>
                  </div>
                )}
              </div>
              <span className="text-xs whitespace-nowrap" style={{ color: "var(--color-sentinel-text-disabled)" }}>
                {timeAgo(finding.detected_at)}
              </span>
            </div>
          </div>
        );
      })}
    </div>
  );
}

function KpiCard({
  icon,
  label,
  value,
  total,
  color,
  bgColor,
  subtitle,
}: {
  icon: React.ReactNode;
  label: string;
  value: number;
  total?: number;
  color: string;
  bgColor: string;
  subtitle: string;
}) {
  return (
    <div
      className="kpi-card rounded-md p-4 opacity-0"
      style={{ background: "var(--color-sentinel-bg-panel)", border: "1px solid var(--color-sentinel-border)" }}
    >
      <div className="flex items-center gap-2 mb-3">
        <div className="p-2 rounded" style={{ background: bgColor, color }}>
          {icon}
        </div>
        <span className="text-xs font-medium uppercase" style={{ color: "var(--color-sentinel-text-secondary)" }}>
          {label}
        </span>
      </div>
      <div>
        <span className="text-3xl font-bold" style={{ color }}>
          {value}
          {total !== undefined && (
            <span className="text-sm font-normal" style={{ color: "var(--color-sentinel-text-disabled)" }}>
              /{total}
            </span>
          )}
        </span>
        <p className="text-xs mt-1" style={{ color: "var(--color-sentinel-text-secondary)" }}>
          {subtitle}
        </p>
      </div>
    </div>
  );
}

function BlockBookingsPanel({
  alerts,
  bookings,
  onDismissAlert,
}: {
  alerts: BlockBookingAlert[];
  bookings: IngestedBooking[];
  onDismissAlert: (id: string) => void;
}) {
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const recentBookings = [...bookings]
    .sort((a, b) => {
      const aTime = new Date(a.ingested_at || a.created_at || a.start_time).getTime();
      const bTime = new Date(b.ingested_at || b.created_at || b.start_time).getTime();
      return bTime - aTime;
    })
    .slice(0, 8);

  return (
    <div className="space-y-6">
      <div
        className="rounded-md p-4"
        style={{ background: "var(--color-sentinel-bg-panel)", border: "1px solid var(--color-sentinel-border)" }}
      >
        <p className="text-sm font-medium mb-1" style={{ color: "var(--color-sentinel-text-primary)" }}>
          Block booking rule
        </p>
        <p className="text-xs leading-6" style={{ color: "var(--color-sentinel-text-secondary)" }}>
          SENTINEL flags an anomaly when the same organiser holds three or more rooms in the same building, on the same
          day, for the exact same time window. The concierge is notified by email to contact the organiser for more
          information. SENTINEL does not cancel or modify any bookings.
        </p>
      </div>

      {alerts.length === 0 ? (
        <EmptyState
          icon={<Mail className="h-8 w-8" />}
          message="No block booking anomalies detected"
          detail="SENTINEL is analysing incoming Outlook room confirmation emails and will notify the concierge when one organiser holds 3 or more rooms for the same slot."
        />
      ) : (
        <div className="space-y-3">
          {alerts.map((alert) => {
            const expanded = expandedId === alert.id;
            return (
              <div
                key={alert.id}
                className="rounded-md overflow-hidden"
                style={{ background: "var(--color-sentinel-bg-panel)", border: "1px solid var(--color-sentinel-border)" }}
              >
                <button
                  onClick={() => setExpandedId(expanded ? null : alert.id)}
                  className="w-full flex items-center gap-3 p-4 text-left"
                >
                  <div className="p-2 rounded" style={{ background: "rgba(220, 38, 38, 0.15)" }}>
                    <Mail className="h-4 w-4" style={{ color: "var(--color-sentinel-red)" }} />
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2">
                      <span className="font-medium text-sm" style={{ color: "var(--color-sentinel-text-primary)" }}>
                        {alert.organiser_name || alert.organiser_email}
                      </span>
                      <span
                        className="text-xs px-2 py-0.5 rounded-full"
                        style={{ background: "rgba(220, 38, 38, 0.15)", color: "var(--color-sentinel-red)" }}
                      >
                        {alert.room_count} rooms
                      </span>
                      <span
                        className="text-xs px-2 py-0.5 rounded-full"
                        style={{
                          background: alert.notification_sent ? "rgba(16, 185, 129, 0.15)" : "rgba(245, 158, 11, 0.15)",
                          color: alert.notification_sent ? "var(--color-sentinel-green)" : "var(--color-sentinel-amber)",
                        }}
                      >
                        {alert.notification_sent ? "email sent" : "notification pending"}
                      </span>
                    </div>
                    <p className="text-xs truncate" style={{ color: "var(--color-sentinel-text-secondary)" }}>
                      {formatDay(alert.overlap_window_start)} · {formatTime(alert.overlap_window_start)} - {formatTime(alert.overlap_window_end)}
                    </p>
                  </div>
                  <div className="flex items-center gap-2">
                    <span className="text-xs" style={{ color: "var(--color-sentinel-text-disabled)" }}>
                      {timeAgo(alert.detected_at)}
                    </span>
                    {expanded ? (
                      <ChevronUp className="h-4 w-4" style={{ color: "var(--color-sentinel-text-disabled)" }} />
                    ) : (
                      <ChevronDown className="h-4 w-4" style={{ color: "var(--color-sentinel-text-disabled)" }} />
                    )}
                  </div>
                </button>
                {expanded && (
                  <div className="px-4 pb-4 pt-0 space-y-3" style={{ borderTop: "1px solid var(--color-sentinel-border)" }}>
                    <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 pt-3">
                      <DetailItem label="Organiser" value={alert.organiser_email} />
                      <DetailItem label="Room Count" value={String(alert.room_count)} />
                      <DetailItem label="Detected" value={formatDateTime(alert.detected_at)} />
                      <DetailItem label="Notification" value={alert.notification_sent ? "Email sent" : "Pending"} />
                    </div>
                    <div>
                      <p className="text-xs mb-2" style={{ color: "var(--color-sentinel-text-disabled)" }}>
                        Rooms in the flagged slot
                      </p>
                      <div className="flex flex-wrap gap-2">
                        {alert.rooms.map((room) => (
                          <span
                            key={room}
                            className="text-xs px-2 py-1 rounded"
                            style={{ background: "var(--color-sentinel-bg-secondary)", color: "var(--color-sentinel-text-primary)" }}
                          >
                            {room}
                          </span>
                        ))}
                      </div>
                    </div>
                    <div className="flex gap-2 pt-2">
                      <button
                        onClick={() => onDismissAlert(alert.id)}
                        className="flex items-center gap-1.5 px-3 py-1.5 rounded text-xs font-medium transition-colors"
                        style={{
                          background: "var(--color-sentinel-bg-secondary)",
                          color: "var(--color-sentinel-text-primary)",
                          border: "1px solid var(--color-sentinel-border)",
                        }}
                      >
                        <XCircle className="h-3.5 w-3.5" />
                        Mark Handled
                      </button>
                    </div>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}

      <div
        className="rounded-md p-4"
        style={{ background: "var(--color-sentinel-bg-panel)", border: "1px solid var(--color-sentinel-border)" }}
      >
        <div className="flex items-center justify-between gap-3 mb-3">
          <h3 className="text-sm font-medium" style={{ color: "var(--color-sentinel-text-primary)" }}>
            Recent Booking Emails
          </h3>
          <span className="text-xs" style={{ color: "var(--color-sentinel-text-secondary)" }}>
            {bookings.length} ingested
          </span>
        </div>

        {recentBookings.length === 0 ? (
          <p className="text-xs" style={{ color: "var(--color-sentinel-text-secondary)" }}>
            No booking confirmation emails have been ingested for this site yet.
          </p>
        ) : (
          <div className="space-y-2">
            {recentBookings.map((booking) => (
              <div
                key={booking.id}
                className="rounded p-3 cursor-pointer transition-colors"
                style={{ background: "var(--color-sentinel-bg-secondary)" }}
                onClick={() => setExpandedId(expandedId === booking.id ? null : booking.id)}
              >
                <div className="flex flex-col sm:flex-row sm:items-center gap-2 sm:gap-3">
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2">
                      <span className="text-sm font-medium truncate" style={{ color: "var(--color-sentinel-text-primary)" }}>
                        {booking.room_name}
                      </span>
                      {booking.flagged && (
                        <span
                          className="text-[10px] px-1.5 py-0.5 rounded-full"
                          style={{ background: "rgba(220, 38, 38, 0.15)", color: "var(--color-sentinel-red)" }}
                        >
                          flagged
                        </span>
                      )}
                    </div>
                    <p className="text-xs truncate" style={{ color: "var(--color-sentinel-text-secondary)" }}>
                      {booking.organiser_name || booking.organiser_email} · {formatDay(booking.start_time)} · {formatTime(booking.start_time)} - {formatTime(booking.end_time)}
                    </p>
                  </div>
                  <span className="text-xs" style={{ color: "var(--color-sentinel-text-secondary)" }}>
                    {expandedId === booking.id ? "\u25B2" : "\u25BC"}
                  </span>
                </div>
                {expandedId === booking.id && (
                  <div className="mt-3 pt-3 space-y-1.5" style={{ borderTop: "1px solid var(--color-sentinel-border)" }}>
                    <div className="grid grid-cols-2 gap-x-4 gap-y-1 text-xs">
                      <span style={{ color: "var(--color-sentinel-text-secondary)" }}>Organiser</span>
                      <span style={{ color: "var(--color-sentinel-text-primary)" }}>{booking.organiser_name || "—"}</span>
                      <span style={{ color: "var(--color-sentinel-text-secondary)" }}>Email</span>
                      <span style={{ color: "var(--color-sentinel-text-primary)" }}>{booking.organiser_email}</span>
                      <span style={{ color: "var(--color-sentinel-text-secondary)" }}>Date</span>
                      <span style={{ color: "var(--color-sentinel-text-primary)" }}>{formatDay(booking.start_time)}</span>
                      <span style={{ color: "var(--color-sentinel-text-secondary)" }}>Time</span>
                      <span style={{ color: "var(--color-sentinel-text-primary)" }}>{formatTime(booking.start_time)} - {formatTime(booking.end_time)}</span>
                      <span style={{ color: "var(--color-sentinel-text-secondary)" }}>Room</span>
                      <span style={{ color: "var(--color-sentinel-text-primary)" }}>{booking.room_name}</span>
                      {booking.ingested_at && (
                        <>
                          <span style={{ color: "var(--color-sentinel-text-secondary)" }}>Ingested</span>
                          <span style={{ color: "var(--color-sentinel-text-primary)" }}>{formatDateTime(booking.ingested_at)}</span>
                        </>
                      )}
                    </div>
                  </div>
                )}
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

function RightsizingPanel({
  findings,
  onDismiss,
}: {
  findings: RightsizingFinding[];
  onDismiss: (id: string) => void;
}) {
  const patternMeta: Record<string, { icon: React.ReactNode; label: string; color: string }> = {
    EARLY_VACATE: { icon: <DoorOpen className="h-4 w-4" />, label: "Early Vacate", color: "var(--color-sentinel-amber)" },
    BRIEF_OCCUPATION: { icon: <Clock className="h-4 w-4" />, label: "Brief Occupation", color: "var(--color-sentinel-red)" },
    SPORADIC_USE: { icon: <BarChart3 className="h-4 w-4" />, label: "Sporadic Use", color: "#a855f7" },
  };

  if (findings.length === 0) {
    return (
      <EmptyState
        icon={<TrendingDown className="h-8 w-8" />}
        message="No right-sizing patterns detected"
        detail="Meeting rooms are being used efficiently."
      />
    );
  }

  return (
    <div className="space-y-3">
      {findings.map((finding) => {
        const meta = patternMeta[finding.pattern_type] || patternMeta.EARLY_VACATE;
        const utilPct = finding.booking_duration_minutes > 0
          ? Math.round((finding.occupied_minutes / finding.booking_duration_minutes) * 100)
          : 0;

        return (
          <div
            key={finding.id}
            className="rounded-md p-4"
            style={{ background: "var(--color-sentinel-bg-panel)", border: "1px solid var(--color-sentinel-border)" }}
          >
            <div className="flex items-start gap-3">
              <div className="p-2 rounded" style={{ background: `${meta.color}22` }}>
                <span style={{ color: meta.color }}>{meta.icon}</span>
              </div>
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2 mb-1">
                  <span className="font-medium text-sm" style={{ color: "var(--color-sentinel-text-primary)" }}>
                    {finding.room_name || finding.room_code}
                  </span>
                  <span className="text-xs px-2 py-0.5 rounded-full" style={{ background: `${meta.color}22`, color: meta.color }}>
                    {meta.label}
                  </span>
                </div>
                <p className="text-xs mb-2" style={{ color: "var(--color-sentinel-text-secondary)" }}>
                  {finding.organiser_name || finding.organiser_email} · {formatTime(finding.booking_start)} - {formatTime(finding.booking_end)}
                </p>
                <div className="flex items-center gap-3">
                  <div className="flex-1">
                    <div className="h-2 rounded-full overflow-hidden" style={{ background: "rgba(255,255,255,0.06)" }}>
                      <div
                        className="h-full rounded-full transition-all"
                        style={{
                          width: `${utilPct}%`,
                          background: utilPct < 25 ? "var(--color-sentinel-red)" : utilPct < 50 ? "var(--color-sentinel-amber)" : "var(--color-sentinel-green)",
                        }}
                      />
                    </div>
                  </div>
                  <span className="text-xs font-medium w-10 text-right" style={{ color: "var(--color-sentinel-text-primary)" }}>
                    {utilPct}%
                  </span>
                </div>
                <div className="flex gap-4 mt-1">
                  <span className="text-xs" style={{ color: "var(--color-sentinel-text-disabled)" }}>
                    Used: {finding.occupied_minutes} min / {finding.booking_duration_minutes} min booked
                  </span>
                  {finding.room_capacity > 0 && (
                    <span className="text-xs" style={{ color: "var(--color-sentinel-text-disabled)" }}>
                      Capacity: {finding.room_capacity}
                    </span>
                  )}
                </div>
              </div>
              <div className="flex flex-col items-end gap-2">
                <span className="text-xs" style={{ color: "var(--color-sentinel-text-disabled)" }}>
                  {timeAgo(finding.detected_at)}
                </span>
                {finding.status === "open" && (
                  <button
                    onClick={() => onDismiss(finding.id)}
                    className="flex items-center gap-1 px-2 py-1 rounded text-xs transition-colors"
                    style={{
                      background: "var(--color-sentinel-bg-secondary)",
                      color: "var(--color-sentinel-text-secondary)",
                      border: "1px solid var(--color-sentinel-border)",
                    }}
                  >
                    <XCircle className="h-3 w-3" />
                    Dismiss
                  </button>
                )}
              </div>
            </div>
          </div>
        );
      })}
    </div>
  );
}

function FocusRoomsPanel({
  sessions,
  analytics,
}: {
  sessions: FocusSession[];
  analytics: FocusAnalytics | null;
}) {
  const activeSessions = sessions.filter((session) => session.is_active);
  const recentCompleted = sessions
    .filter((session) => !session.is_active)
    .sort((a, b) => new Date(b.end_time || "").getTime() - new Date(a.end_time || "").getTime())
    .slice(0, 10);

  return (
    <div className="space-y-6">
      {analytics && (
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
          <MiniStat label="Total Sessions" value={analytics.total_sessions} />
          <MiniStat label="Active Now" value={analytics.active_sessions} color="var(--color-sentinel-green)" />
          <MiniStat label="Extended Use" value={analytics.extended_use_sessions} color="var(--color-sentinel-amber)" />
          <MiniStat label="Peak Hour" value={analytics.peak_hour !== null ? `${analytics.peak_hour}:00` : "N/A"} />
        </div>
      )}

      {analytics && Object.keys(analytics.sessions_by_room).length > 0 && (
        <div
          className="rounded-md p-4"
          style={{ background: "var(--color-sentinel-bg-panel)", border: "1px solid var(--color-sentinel-border)" }}
        >
          <h3 className="text-sm font-medium mb-3" style={{ color: "var(--color-sentinel-text-primary)" }}>
            Sessions by Room
          </h3>
          <div className="space-y-2">
            {Object.entries(analytics.sessions_by_room)
              .sort(([, a], [, b]) => b - a)
              .map(([room, count]) => {
                const maxCount = Math.max(...Object.values(analytics.sessions_by_room));
                const pct = maxCount > 0 ? (count / maxCount) * 100 : 0;
                return (
                  <div key={room} className="flex items-center gap-3">
                    <span className="text-xs w-28 truncate" style={{ color: "var(--color-sentinel-text-secondary)" }}>
                      {shortRoom(room)}
                    </span>
                    <div className="flex-1 h-2 rounded-full overflow-hidden" style={{ background: "rgba(255,255,255,0.06)" }}>
                      <div className="h-full rounded-full" style={{ width: `${pct}%`, background: "var(--color-sentinel-teal)" }} />
                    </div>
                    <span className="text-xs w-8 text-right font-medium" style={{ color: "var(--color-sentinel-text-primary)" }}>
                      {count}
                    </span>
                  </div>
                );
              })}
          </div>
        </div>
      )}

      {activeSessions.length > 0 && (
        <div>
          <h3 className="text-sm font-medium mb-3" style={{ color: "var(--color-sentinel-text-primary)" }}>
            Active Sessions
          </h3>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            {activeSessions.map((session) => (
              <SessionCard key={session.session_id} session={session} />
            ))}
          </div>
        </div>
      )}

      {recentCompleted.length > 0 && (
        <div>
          <h3 className="text-sm font-medium mb-3" style={{ color: "var(--color-sentinel-text-primary)" }}>
            Recent Sessions
          </h3>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            {recentCompleted.map((session) => (
              <SessionCard key={session.session_id} session={session} />
            ))}
          </div>
        </div>
      )}

      {sessions.length === 0 && (
        <EmptyState
          icon={<Focus className="h-8 w-8" />}
          message="No focus room sessions"
          detail="Focus room session tracking will appear here when sensors report data."
        />
      )}
    </div>
  );
}

function SessionCard({ session }: { session: FocusSession }) {
  const overLimit = session.red_light_on;
  return (
    <div
      className="rounded-md p-3 flex items-center gap-3"
      style={{ background: "var(--color-sentinel-bg-panel)", border: "1px solid var(--color-sentinel-border)" }}
    >
      <div
        className="p-2 rounded"
        style={{
          background: overLimit
            ? "rgba(239, 68, 68, 0.16)"
            : session.is_active
              ? "rgba(16, 185, 129, 0.15)"
              : "rgba(59, 130, 246, 0.1)",
        }}
      >
        {overLimit ? (
          <AlertTriangle className="h-4 w-4" style={{ color: "var(--color-sentinel-red)" }} />
        ) : session.is_active ? (
          <Users className="h-4 w-4" style={{ color: "var(--color-sentinel-green)" }} />
        ) : (
          <CheckCircle2 className="h-4 w-4" style={{ color: "var(--color-sentinel-blue)" }} />
        )}
      </div>
      <div className="flex-1 min-w-0">
        <span className="text-sm font-medium" style={{ color: "var(--color-sentinel-text-primary)" }}>
          {shortRoom(session.room_code)}
        </span>
        <div className="flex items-center gap-2">
          <span className="text-xs" style={{ color: "var(--color-sentinel-text-secondary)" }}>
            {session.duration_minutes.toFixed(0)} min
          </span>
          <span className="text-xs" style={{ color: "var(--color-sentinel-text-disabled)" }}>
            max {session.max_allowed_minutes} min
          </span>
          {session.red_light_on && (
            <span className="text-xs px-1.5 py-0.5 rounded" style={{ background: "rgba(239, 68, 68, 0.16)", color: "var(--color-sentinel-red)" }}>
              Red Light On
            </span>
          )}
          {session.red_light_on && !session.is_active && (session.red_light_cooldown_remaining_seconds ?? 0) > 0 && (
            <span className="text-xs" style={{ color: "var(--color-sentinel-text-disabled)" }}>
              cooldown {Math.ceil((session.red_light_cooldown_remaining_seconds ?? 0) / 60)} min
            </span>
          )}
          {session.extended_use && (
            <span className="text-xs px-1.5 py-0.5 rounded" style={{ background: "rgba(245, 158, 11, 0.15)", color: "var(--color-sentinel-amber)" }}>
              Extended
            </span>
          )}
          {session.is_active && (
            <span className="text-xs px-1.5 py-0.5 rounded" style={{ background: "rgba(16, 185, 129, 0.15)", color: "var(--color-sentinel-green)" }}>
              Active
            </span>
          )}
        </div>
      </div>
      <span className="text-xs" style={{ color: "var(--color-sentinel-text-disabled)" }}>
        {formatTime(session.start_time)}
      </span>
    </div>
  );
}

function OccupancyTrendsPanel({ trends }: { trends: HourlyTrend[] }) {
  if (trends.length === 0) {
    return (
      <EmptyState
        icon={<BarChart3 className="h-8 w-8" />}
        message="No occupancy trend data"
        detail="Trends will appear after occupancy data is available for at least one day."
      />
    );
  }

  const byZone = trends.reduce<Record<string, HourlyTrend[]>>((acc, trend) => {
    const zone = trend.zone_type || "all";
    if (!acc[zone]) acc[zone] = [];
    acc[zone].push(trend);
    return acc;
  }, {});

  return (
    <div className="space-y-6">
      {Object.entries(byZone).map(([zone, zoneTrends]) => {
        const sorted = [...zoneTrends].sort((a, b) => a.hour - b.hour);
        const maxOcc = Math.max(...sorted.map((trend) => trend.occupancy_percent), 1);

        return (
          <div
            key={zone}
            className="rounded-md p-4"
            style={{ background: "var(--color-sentinel-bg-panel)", border: "1px solid var(--color-sentinel-border)" }}
          >
            <h3 className="text-sm font-medium mb-3 capitalize" style={{ color: "var(--color-sentinel-text-primary)" }}>
              {zone} Occupancy (7-Day Avg)
            </h3>
            <div className="flex items-end gap-1 h-24">
              {sorted.map((trend) => {
                const height = maxOcc > 0 ? (trend.occupancy_percent / maxOcc) * 100 : 0;
                const isPeak = trend.occupancy_percent > 70;
                return (
                  <div
                    key={`${zone}-${trend.hour}`}
                    className="flex-1 flex flex-col items-center justify-end"
                    title={`${trend.hour}:00 - ${trend.occupancy_percent}%`}
                  >
                    <div
                      className="w-full rounded-sm transition-all"
                      style={{
                        height: `${Math.max(height, 2)}%`,
                        background: isPeak ? "var(--color-sentinel-amber)" : "var(--color-sentinel-teal)",
                        opacity: 0.8,
                        minHeight: 2,
                      }}
                    />
                  </div>
                );
              })}
            </div>
            <div className="flex gap-1 mt-1">
              {sorted.map((trend) => (
                <div key={`${zone}-label-${trend.hour}`} className="flex-1 text-center">
                  <span className="text-[9px]" style={{ color: "var(--color-sentinel-text-disabled)" }}>
                    {trend.hour % 3 === 0 ? `${trend.hour}` : ""}
                  </span>
                </div>
              ))}
            </div>
          </div>
        );
      })}
    </div>
  );
}

function MiniStat({ label, value, color }: { label: string; value: string | number; color?: string }) {
  return (
    <div
      className="rounded-md p-3"
      style={{ background: "var(--color-sentinel-bg-panel)", border: "1px solid var(--color-sentinel-border)" }}
    >
      <p className="text-xs mb-1" style={{ color: "var(--color-sentinel-text-secondary)" }}>{label}</p>
      <p className="text-xl font-bold" style={{ color: color || "var(--color-sentinel-text-primary)" }}>{value}</p>
    </div>
  );
}

function DetailItem({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <p className="text-xs" style={{ color: "var(--color-sentinel-text-disabled)" }}>{label}</p>
      <p className="text-sm font-medium break-words" style={{ color: "var(--color-sentinel-text-primary)" }}>{value}</p>
    </div>
  );
}

function EmptyState({ icon, message, detail }: { icon: React.ReactNode; message: string; detail: string }) {
  return (
    <div
      className="rounded-md p-8 text-center"
      style={{ background: "var(--color-sentinel-bg-panel)", border: "1px solid var(--color-sentinel-border)" }}
    >
      <div className="inline-flex p-3 rounded-full mb-3" style={{ background: "rgba(13,148,136,0.1)", color: "var(--color-sentinel-teal)" }}>
        {icon}
      </div>
      <p className="text-sm font-medium mb-1" style={{ color: "var(--color-sentinel-text-primary)" }}>
        {message}
      </p>
      <p className="text-xs" style={{ color: "var(--color-sentinel-text-secondary)" }}>
        {detail}
      </p>
    </div>
  );
}

function transformHourlyTrendData(data: unknown): HourlyTrend[] {
  if (!data || typeof data !== "object") {
    return [];
  }

  const record = data as { zones?: Record<string, number[]> };
  if (!record.zones) {
    return [];
  }

  const trends: HourlyTrend[] = [];
  for (const [zoneType, values] of Object.entries(record.zones)) {
    values.forEach((value, hour) => {
      trends.push({
        hour,
        occupancy_percent: value,
        zone_type: zoneType,
      });
    });
  }
  return trends;
}

const JHB = "Africa/Johannesburg";

function formatTime(iso: string): string {
  try {
    const d = new Date(iso);
    return d.toLocaleTimeString("en-ZA", { hour: "2-digit", minute: "2-digit", timeZone: JHB });
  } catch {
    return iso;
  }
}

function formatDay(iso: string): string {
  try {
    const d = new Date(iso);
    return d.toLocaleDateString("en-ZA", { weekday: "short", day: "2-digit", month: "short", timeZone: JHB });
  } catch {
    return iso;
  }
}

function formatDateTime(iso: string): string {
  try {
    const d = new Date(iso);
    return d.toLocaleString("en-ZA", {
      year: "numeric",
      month: "short",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
      timeZone: JHB,
    });
  } catch {
    return iso;
  }
}

function shortRoom(code: string): string {
  // Strip prefix pattern to get short form: L0-MR01 → MR01, FA2-1Q4-FR25 → FR25
  const parts = code.split("-");
  return parts[parts.length - 1];
}

function timeAgo(iso: string): string {
  try {
    const diff = Date.now() - new Date(iso).getTime();
    const minutes = Math.floor(diff / 60000);
    if (minutes < 1) return "just now";
    if (minutes < 60) return `${minutes}m ago`;
    const hours = Math.floor(minutes / 60);
    if (hours < 24) return `${hours}h ago`;
    const days = Math.floor(hours / 24);
    return `${days}d ago`;
  } catch {
    return "";
  }
}
