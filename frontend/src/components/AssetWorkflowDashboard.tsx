import { useState, useEffect, useCallback, createElement } from 'react';
import {
  CheckCircle2,
  AlertTriangle,
  XCircle,
  Clock,
  TrendingUp,
  Activity,
  Calendar,
  Wrench,
  ChevronRight,
  ArrowLeft,
  RefreshCw,
  Building2,
  MessageSquare,
  Package,
} from 'lucide-react';
import {
  api,
  workflowApi,
  type EquipmentMetadata,
  type ServiceRecord,
  type WorkflowEquipmentItem,
  type WorkflowState,
  type WorkflowOnboardAssetRequest,
  type Site,
} from '@/lib/api';
import { useModules } from '@/contexts/ModuleHooks';
import { PageLoading } from "./PageLoading";
import { BuildingSelector } from "./BuildingSelector";
import TechnicianChat from "./TechnicianChat";

// Re-export types from API for local use
type Equipment = WorkflowEquipmentItem;

function getStateColor(state: string) {
  switch (state) {
    case 'healthy': return 'var(--color-sentinel-green)';
    case 'anomaly_detected': return 'var(--color-sentinel-amber)';
    case 'inspection_pending': return 'var(--color-sentinel-amber)';
    case 'deficiency_found': return 'var(--color-sentinel-red)';
    case 'repair_in_progress': return 'var(--color-sentinel-blue)';
    case 'validation_pending': return 'var(--color-sentinel-blue)';
    default: return 'var(--color-sentinel-text-secondary)';
  }
}

function getStateBgColor(state: string) {
  switch (state) {
    case 'healthy': return 'rgba(16, 185, 129, 0.15)';
    case 'anomaly_detected': return 'rgba(245, 158, 11, 0.15)';
    case 'inspection_pending': return 'rgba(245, 158, 11, 0.15)';
    case 'deficiency_found': return 'rgba(220, 38, 38, 0.15)';
    case 'repair_in_progress': return 'rgba(59, 130, 246, 0.15)';
    case 'validation_pending': return 'rgba(59, 130, 246, 0.15)';
    default: return 'rgba(139, 148, 158, 0.15)';
  }
}

function getStateIcon(state: string) {
  switch (state) {
    case 'healthy': return CheckCircle2;
    case 'anomaly_detected': return AlertTriangle;
    case 'inspection_pending': return Clock;
    case 'deficiency_found': return XCircle;
    case 'repair_in_progress': return Wrench;
    case 'validation_pending': return Activity;
    default: return Activity;
  }
}

type MaintenanceTab = 'equipment' | 'tech-chat';

const PRIORITY_EQUIPMENT_KEYWORDS = [
  'GEN',
  'GENERATOR',
  'AHU',
  'FCU',
  'CHILLER',
  'PUMP',
  'UPS',
  'BESS',
  'INVERTER',
  'BOILER',
  'COOLING_TOWER',
  'CT',
];

function isPriorityEquipmentType(type: string): boolean {
  const normalized = type.toUpperCase().replace(/[^A-Z0-9]/g, '');
  return PRIORITY_EQUIPMENT_KEYWORDS.some((keyword) =>
    normalized.includes(keyword.replace(/[^A-Z0-9]/g, ''))
  );
}

export function AssetWorkflowDashboard() {
  const { isModuleActive } = useModules();
  const maintenanceActive = isModuleActive('maintenance');
  const [activeTab, setActiveTab] = useState<MaintenanceTab>('equipment');
  const [equipment, setEquipment] = useState<Equipment[]>([]);
  const [workflowStates, setWorkflowStates] = useState<Record<string, WorkflowState>>({});
  const [selectedEquipment, setSelectedEquipment] = useState<string | null>(null);
  const [workflowState, setWorkflowState] = useState<WorkflowState | null>(null);
  const [equipmentMetadata, setEquipmentMetadata] = useState<EquipmentMetadata | null>(null);
  const [serviceRecords, setServiceRecords] = useState<ServiceRecord[]>([]);
  const [loading, setLoading] = useState(false);
  const [initialLoading, setInitialLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [onboardingOpen, setOnboardingOpen] = useState(false);
  const [onboardingSubmitting, setOnboardingSubmitting] = useState(false);
  const [onboardingError, setOnboardingError] = useState<string | null>(null);
  const [onboardingNotes, setOnboardingNotes] = useState('');
  const [serviceSheetRef, setServiceSheetRef] = useState('');
  const [photoLinks, setPhotoLinks] = useState('');
  const [assetAgeYears, setAssetAgeYears] = useState('');
  const [serialNumber, setSerialNumber] = useState('');
  const [manufacturer, setManufacturer] = useState('');
  const [model, setModel] = useState('');
  const [sites, setSites] = useState<Site[]>([]);
  const [selectedSiteId, setSelectedSiteId] = useState<string>('');
  const [loadingSites, setLoadingSites] = useState(true);
  const selectedSite = sites.find((site) => site.id === selectedSiteId) ?? null;
  const priorityEquipment = equipment.filter((eq) => isPriorityEquipmentType(eq.type));
  const selectedEquipmentItem = selectedEquipment
    ? priorityEquipment.find((eq) => eq.equipment_id === selectedEquipment) ?? null
    : null;

  const handleEquipmentSelect = useCallback(async (equipmentId: string) => {
    setSelectedEquipment(equipmentId);
    setError(null);

    // Fast path: use cached state from dashboard payload.
    const cached = workflowStates[equipmentId];
    if (cached) {
      setWorkflowState(cached);
    }

    // Fetch metadata and service records in parallel
    try {
      setLoading(true);
      const [freshState, metadata, records] = await Promise.all([
        cached ? Promise.resolve(cached) : workflowApi.getWorkflowStatus(equipmentId),
        api.getEquipmentMetadata(equipmentId).then(r => r.equipment).catch(() => null),
        api.getServiceRecords(equipmentId).catch(() => []),
      ]);
      if (!cached) setWorkflowState(freshState);
      setEquipmentMetadata(metadata);
      setServiceRecords(records);
    } catch (err) {
      console.error('Failed to fetch equipment data:', equipmentId, err);
      setWorkflowState(null);
      setError('Failed to load selected equipment data');
    } finally {
      setLoading(false);
    }
  }, [workflowStates]);

  // Fetch equipment list and workflow states from API
  const fetchDashboardData = useCallback(async () => {
    try {
      setError(null);
      const data = await workflowApi.getDashboardEquipment(selectedSiteId || undefined);
      setEquipment(data.equipment);
      setWorkflowStates(data.workflow_states);
    } catch (err) {
      console.error('Failed to fetch workflow dashboard data:', err);
      setError('Failed to load equipment data');
    } finally {
      setInitialLoading(false);
    }
  }, [selectedSiteId]);

  const handleOnboardAsset = useCallback(async () => {
    if (!selectedEquipment || !selectedSiteId || !selectedSite) return;

    try {
      setOnboardingSubmitting(true);
      setOnboardingError(null);

      const storedUser = localStorage.getItem('sentinel_user');
      let capturedBy = 'operator';
      if (storedUser) {
        try {
          const parsed = JSON.parse(storedUser);
          capturedBy = parsed?.full_name || parsed?.email || capturedBy;
        } catch {
          // ignore parse issues and keep fallback
        }
      }

      const payload: WorkflowOnboardAssetRequest = {
        site_id: selectedSiteId,
        site_name: selectedSite.name,
        site_address: (selectedSite as Site & { address?: string }).address || 'N/A',
        captured_by: capturedBy,
        notes: onboardingNotes || undefined,
        equipment: [
          {
            equipment_id: selectedEquipment,
            name: selectedEquipmentItem?.name || selectedEquipment,
            type: selectedEquipmentItem?.type || 'unknown',
            serial_number: serialNumber || null,
            manufacturer: manufacturer || null,
            model: model || null,
            age_years: assetAgeYears ? Number(assetAgeYears) : null,
            service_sheet_ref: serviceSheetRef || null,
            photo_links: photoLinks
              ? photoLinks.split(',').map((item) => item.trim()).filter(Boolean)
              : [],
          },
        ],
      };

      await workflowApi.onboardAsset(payload);
      await fetchDashboardData();
      await handleEquipmentSelect(selectedEquipment);
      setOnboardingOpen(false);
    } catch (err) {
      console.error('Failed to onboard asset:', err);
      setOnboardingError('Failed to onboard asset. Please verify required fields and try again.');
    } finally {
      setOnboardingSubmitting(false);
    }
  }, [
    selectedEquipment,
    selectedEquipmentItem,
    selectedSiteId,
    selectedSite,
    onboardingNotes,
    serialNumber,
    manufacturer,
    model,
    assetAgeYears,
    serviceSheetRef,
    photoLinks,
    fetchDashboardData,
    handleEquipmentSelect,
  ]);

  // Fetch sites on mount
  useEffect(() => {
    const fetchSites = async () => {
      try {
        const sitesData = await api.getSites();
        setSites(sitesData);
        // Prefer Sandton City Office Tower (site-002) as default selection.
        if (sitesData.length > 0) {
          const preferredSite =
            sitesData.find((site) => site.id === 'site-002')
            ?? sitesData.find((site) => /sandton city office tower/i.test(site.name))
            ?? sitesData[0];
          setSelectedSiteId(preferredSite.id);
        }
      } catch (err) {
        console.error('Failed to fetch sites:', err);
      } finally {
        setLoadingSites(false);
      }
    };
    fetchSites();
  }, []);

  // Re-fetch equipment when selected site changes
  useEffect(() => {
    if (!loadingSites) {
      fetchDashboardData();
    }
  }, [selectedSiteId, fetchDashboardData, loadingSites]);

  // Keep selected equipment in sync when dashboard payload refreshes.
  useEffect(() => {
    if (selectedEquipment) {
      const state = workflowStates[selectedEquipment];
      if (state) {
        setWorkflowState(state);
      }
    }
  }, [selectedEquipment, workflowStates]);

  const tabs: { id: MaintenanceTab; label: string; icon: typeof Package }[] = [
    { id: 'equipment', label: 'Equipment', icon: Package },
    { id: 'tech-chat', label: 'Tech Chat', icon: MessageSquare },
  ];

  return (
    <div
      className="h-full flex flex-col"
      style={{ background: 'var(--color-sentinel-bg-canvas)' }}
    >
      {/* Page Header */}
      <div className="px-4 md:px-6 pt-4 md:pt-6">
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-3">
            <div
              className="p-2 rounded"
              style={{ background: 'rgba(59, 130, 246, 0.15)' }}
            >
              <Wrench className="h-5 w-5" style={{ color: 'var(--color-sentinel-blue)' }} />
            </div>
            <div>
              <h1
                className="text-lg font-semibold"
                style={{ color: 'var(--color-sentinel-text-primary)' }}
              >
                Maintenance
              </h1>
              <p
                className="text-sm"
                style={{ color: 'var(--color-sentinel-text-secondary)' }}
              >
                Equipment workflow, work orders & technician support
              </p>
            </div>
          </div>
          {activeTab === 'equipment' && (
            <button
              onClick={fetchDashboardData}
              className="p-2 rounded transition-colors"
              style={{ color: 'var(--color-sentinel-text-secondary)' }}
              onMouseEnter={(e) => e.currentTarget.style.background = 'var(--color-sentinel-bg-secondary)'}
              onMouseLeave={(e) => e.currentTarget.style.background = ''}
              title="Refresh data"
            >
              <RefreshCw className="h-4 w-4" />
            </button>
          )}
        </div>

        {/* Tab Bar */}
        <div
          className="flex gap-1 mb-4"
          style={{ borderBottom: '1px solid var(--color-sentinel-border)' }}
        >
          {tabs.map((tab) => {
            const isActive = activeTab === tab.id;
            const TabIcon = tab.icon;
            return (
              <button
                key={tab.id}
                onClick={() => setActiveTab(tab.id)}
                className="flex items-center gap-2 px-4 py-2.5 text-sm font-medium transition-colors relative"
                style={{
                  color: isActive
                    ? 'var(--color-sentinel-text-primary)'
                    : 'var(--color-sentinel-text-secondary)',
                }}
              >
                <TabIcon className="h-4 w-4" />
                {tab.label}
                {isActive && (
                  <div
                    className="absolute bottom-0 left-0 right-0 h-0.5"
                    style={{ background: 'var(--color-sentinel-blue)' }}
                  />
                )}
              </button>
            );
          })}
        </div>
      </div>

      {/* Tab Content */}
      {activeTab === 'tech-chat' ? (
        <div className="flex-1 min-h-0">
          <TechnicianChat siteId={selectedSiteId || undefined} siteLabel={selectedSite?.name} />
        </div>
      ) : initialLoading ? (
        <PageLoading message="Loading equipment workflow data..." />
      ) : (
      <div className="flex-1 overflow-y-auto px-4 md:px-6 pb-4 md:pb-6">

      {/* Error State */}
      {error && (
        <div
          className="rounded-lg p-4 mb-6 flex items-center gap-3"
          style={{
            background: 'rgba(220, 38, 38, 0.1)',
            border: '1px solid rgba(220, 38, 38, 0.3)',
          }}
        >
          <XCircle className="h-5 w-5" style={{ color: 'var(--color-sentinel-red)' }} />
          <span style={{ color: 'var(--color-sentinel-text-primary)' }}>{error}</span>
        </div>
      )}

      {/* Building Selector */}
      <div
        className="rounded-lg overflow-hidden mb-4"
        style={{
          background: 'var(--color-sentinel-bg-panel)',
          border: '1px solid var(--color-sentinel-border)',
        }}
      >
        <div className="p-4">
          <div className="flex items-center gap-3">
            <Building2
              className="h-5 w-5"
              style={{ color: 'var(--color-sentinel-text-secondary)' }}
            />
            <div className="flex-1">
              <label
                className="text-xs uppercase tracking-wider mb-1.5 block"
                style={{ color: 'var(--color-sentinel-text-secondary)' }}
              >
                Filter by Building
              </label>
              <BuildingSelector
                value={selectedSiteId}
                onChange={setSelectedSiteId}
                sites={sites}
                disabled={loadingSites}
                allowAllOption={true}
              />
            </div>
            <div className="flex items-center gap-2">
              <span
                className="text-xs px-2 py-1 rounded"
                style={{
                  background: 'var(--color-sentinel-bg-secondary)',
                  color: 'var(--color-sentinel-text-secondary)',
                }}
              >
                {priorityEquipment.length} priority equipment
              </span>
            </div>
          </div>
        </div>
      </div>

      {/* Equipment Fleet Panel */}
      {selectedEquipment && !loading && workflowState && (
        <div className="mb-6">
          <EquipmentWorkflowDetail
            workflowState={workflowState}
            metadata={equipmentMetadata}
            serviceRecords={serviceRecords}
            onBack={() => {
              setSelectedEquipment(null);
              setEquipmentMetadata(null);
              setServiceRecords([]);
            }}
            maintenanceActive={maintenanceActive}
          />
        </div>
      )}
      {selectedEquipment && !loading && !workflowState && (
        <div
          className="rounded-lg overflow-hidden p-4 mb-6 flex flex-col gap-4"
          style={{
            background: 'rgba(245, 158, 11, 0.08)',
            border: '1px solid rgba(245, 158, 11, 0.3)',
          }}
        >
          <div className="flex items-start justify-between gap-3">
            <div>
              <h4 className="text-sm font-medium" style={{ color: 'var(--color-sentinel-amber)' }}>
                Equipment not onboarded yet
              </h4>
              <p className="text-xs mt-1" style={{ color: 'var(--color-sentinel-text-secondary)' }}>
                {selectedEquipmentItem?.name || selectedEquipment} exists in BMS telemetry, but has no workflow baseline yet.
                Onboard it to capture asset metadata and initialize health scoring.
              </p>
            </div>
            <div className="flex items-center gap-2">
              <button
                onClick={() => setOnboardingOpen((value) => !value)}
                className="px-3 py-1.5 text-xs rounded transition-colors"
                style={{
                  background: 'rgba(59, 130, 246, 0.2)',
                  border: '1px solid rgba(59, 130, 246, 0.45)',
                  color: 'var(--color-sentinel-blue)',
                }}
              >
                {onboardingOpen ? 'Hide Onboard Form' : 'Onboard Asset'}
              </button>
              <button
                onClick={() => {
                  if (selectedEquipment) void handleEquipmentSelect(selectedEquipment);
                }}
                className="px-3 py-1.5 text-xs rounded transition-colors"
                style={{
                  background: 'var(--color-sentinel-bg-secondary)',
                  border: '1px solid var(--color-sentinel-border)',
                  color: 'var(--color-sentinel-text-primary)',
                }}
              >
                Retry
              </button>
            </div>
          </div>

          {onboardingOpen && (
            <div
              className="rounded-lg p-4 grid grid-cols-1 md:grid-cols-2 gap-3"
              style={{
                background: 'var(--color-sentinel-bg-panel)',
                border: '1px solid var(--color-sentinel-border)',
              }}
            >
              <div>
                <label className="text-xs" style={{ color: 'var(--color-sentinel-text-secondary)' }}>Serial Number</label>
                <input value={serialNumber} onChange={(e) => setSerialNumber(e.target.value)} className="w-full mt-1 rounded-lg px-3 py-2 text-sm" style={{ background: 'var(--color-sentinel-bg-secondary)', border: '1px solid var(--color-sentinel-border)', color: 'var(--color-sentinel-text-primary)' }} />
              </div>
              <div>
                <label className="text-xs" style={{ color: 'var(--color-sentinel-text-secondary)' }}>Asset Age (years)</label>
                <input value={assetAgeYears} onChange={(e) => setAssetAgeYears(e.target.value)} type="number" min="0" className="w-full mt-1 rounded-lg px-3 py-2 text-sm" style={{ background: 'var(--color-sentinel-bg-secondary)', border: '1px solid var(--color-sentinel-border)', color: 'var(--color-sentinel-text-primary)' }} />
              </div>
              <div>
                <label className="text-xs" style={{ color: 'var(--color-sentinel-text-secondary)' }}>Make / Manufacturer</label>
                <input value={manufacturer} onChange={(e) => setManufacturer(e.target.value)} className="w-full mt-1 rounded-lg px-3 py-2 text-sm" style={{ background: 'var(--color-sentinel-bg-secondary)', border: '1px solid var(--color-sentinel-border)', color: 'var(--color-sentinel-text-primary)' }} />
              </div>
              <div>
                <label className="text-xs" style={{ color: 'var(--color-sentinel-text-secondary)' }}>Model</label>
                <input value={model} onChange={(e) => setModel(e.target.value)} className="w-full mt-1 rounded-lg px-3 py-2 text-sm" style={{ background: 'var(--color-sentinel-bg-secondary)', border: '1px solid var(--color-sentinel-border)', color: 'var(--color-sentinel-text-primary)' }} />
              </div>
              <div>
                <label className="text-xs" style={{ color: 'var(--color-sentinel-text-secondary)' }}>Service Sheet Reference / URL</label>
                <input value={serviceSheetRef} onChange={(e) => setServiceSheetRef(e.target.value)} className="w-full mt-1 rounded-lg px-3 py-2 text-sm" style={{ background: 'var(--color-sentinel-bg-secondary)', border: '1px solid var(--color-sentinel-border)', color: 'var(--color-sentinel-text-primary)' }} />
              </div>
              <div>
                <label className="text-xs" style={{ color: 'var(--color-sentinel-text-secondary)' }}>Photos (comma-separated URLs)</label>
                <input value={photoLinks} onChange={(e) => setPhotoLinks(e.target.value)} className="w-full mt-1 rounded-lg px-3 py-2 text-sm" style={{ background: 'var(--color-sentinel-bg-secondary)', border: '1px solid var(--color-sentinel-border)', color: 'var(--color-sentinel-text-primary)' }} />
              </div>
              <div className="md:col-span-2">
                <label className="text-xs" style={{ color: 'var(--color-sentinel-text-secondary)' }}>Notes</label>
                <textarea value={onboardingNotes} onChange={(e) => setOnboardingNotes(e.target.value)} rows={3} className="w-full mt-1 rounded-lg px-3 py-2 text-sm" style={{ background: 'var(--color-sentinel-bg-secondary)', border: '1px solid var(--color-sentinel-border)', color: 'var(--color-sentinel-text-primary)' }} />
              </div>
              {onboardingError && (
                <div className="md:col-span-2 text-xs" style={{ color: 'var(--color-sentinel-red)' }}>
                  {onboardingError}
                </div>
              )}
              <div className="md:col-span-2 flex justify-end gap-2">
                <button
                  onClick={() => setOnboardingOpen(false)}
                  className="px-3 py-2 text-xs rounded-lg transition-colors"
                  style={{
                    background: 'var(--color-sentinel-bg-secondary)',
                    border: '1px solid var(--color-sentinel-border)',
                    color: 'var(--color-sentinel-text-primary)',
                  }}
                >
                  Cancel
                </button>
                <button
                  onClick={() => void handleOnboardAsset()}
                  disabled={onboardingSubmitting}
                  className="px-3 py-2 text-xs rounded-lg transition-colors disabled:opacity-60"
                  style={{
                    background: 'rgba(16, 185, 129, 0.2)',
                    border: '1px solid rgba(16, 185, 129, 0.45)',
                    color: 'var(--color-sentinel-green)',
                  }}
                >
                  {onboardingSubmitting ? 'Onboarding...' : 'Submit Onboarding'}
                </button>
              </div>
            </div>
          )}
        </div>
      )}
      <div
        className="rounded-lg overflow-hidden mb-6"
        style={{
          background: 'var(--color-sentinel-bg-panel)',
          border: '1px solid var(--color-sentinel-border)',
        }}
      >
        {/* Panel Header */}
        <div
          className="p-4 flex items-center justify-between"
          style={{ borderBottom: '1px solid var(--color-sentinel-border)' }}
        >
          <div className="flex items-center gap-3">
            <h3
              className="font-medium text-sm"
              style={{ color: 'var(--color-sentinel-text-primary)' }}
            >
              Equipment Fleet
            </h3>
            <span
              className="text-xs px-2 py-1 rounded"
              style={{
                background: 'var(--color-sentinel-bg-secondary)',
                color: 'var(--color-sentinel-text-secondary)',
              }}
            >
              {priorityEquipment.length} priority
            </span>
          </div>
          <span
            className="text-xs px-2 py-1 rounded"
            style={{
              background: 'rgba(16, 185, 129, 0.15)',
              color: 'var(--color-sentinel-green)',
            }}
          >
            {priorityEquipment.filter(e => e.current_state === 'healthy').length} healthy
          </span>
        </div>

        {/* Equipment Grid */}
        <div className="p-4">
          {priorityEquipment.length === 0 ? (
            <div className="text-center py-8">
              <Activity
                className="h-8 w-8 mx-auto mb-3"
                style={{ color: 'var(--color-sentinel-text-disabled)' }}
              />
              <p style={{ color: 'var(--color-sentinel-text-secondary)' }}>
                No priority plant found for this site yet.
              </p>
            </div>
          ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {priorityEquipment.map((eq) => {
              const StateIcon = getStateIcon(eq.current_state);
              const isSelected = selectedEquipment === eq.equipment_id;
              return (
                <button
                  key={eq.equipment_id}
                  type="button"
                  className="p-4 rounded-lg cursor-pointer transition-all"
                  aria-label={`Open workflow details for ${eq.name} (${eq.equipment_id})`}
                  style={{
                    width: '100%',
                    textAlign: 'left',
                    background: isSelected
                      ? 'var(--color-sentinel-bg-secondary)'
                      : 'var(--color-sentinel-bg-primary)',
                    border: isSelected
                      ? '1px solid var(--color-sentinel-border-strong)'
                      : '1px solid var(--color-sentinel-border)',
                  }}
                  onMouseEnter={(e) => {
                    if (!isSelected) e.currentTarget.style.borderColor = 'var(--color-sentinel-border-strong)';
                  }}
                  onMouseLeave={(e) => {
                    if (!isSelected) e.currentTarget.style.borderColor = '';
                  }}
                  onClick={() => {
                    void handleEquipmentSelect(eq.equipment_id);
                  }}
                >
                  <div className="flex items-center justify-between">
                    <div className="min-w-0">
                      <span
                        className="text-xs uppercase tracking-wider"
                        style={{ color: 'var(--color-sentinel-text-secondary)' }}
                      >
                        {eq.type}
                      </span>
                      <h4
                        className="font-medium text-sm mt-1 truncate"
                        style={{ color: 'var(--color-sentinel-text-primary)' }}
                      >
                        {eq.name}
                      </h4>
                      <span
                        className="text-xs"
                        style={{ color: 'var(--color-sentinel-text-disabled)' }}
                      >
                        {eq.equipment_id}
                      </span>
                    </div>
                    <div className="flex items-center gap-2 ml-3 shrink-0">
                      {isSelected && (
                        <span
                          className="text-[10px] px-2 py-1 rounded-full uppercase tracking-wide"
                          style={{
                            background: 'rgba(59, 130, 246, 0.15)',
                            color: 'var(--color-sentinel-blue)',
                            border: '1px solid rgba(59, 130, 246, 0.35)',
                          }}
                        >
                          Selected
                        </span>
                      )}
                      <span
                        className="text-xs px-2 py-1 rounded-full font-medium flex items-center gap-1.5"
                        style={{
                          background: getStateBgColor(eq.current_state),
                          color: getStateColor(eq.current_state),
                        }}
                      >
                        <StateIcon className="h-3.5 w-3.5" />
                        {eq.current_state.replace(/_/g, ' ')}
                      </span>
                      <ChevronRight
                        className="h-4 w-4"
                        style={{ color: 'var(--color-sentinel-text-disabled)' }}
                      />
                    </div>
                  </div>
                </button>
              );
            })}
          </div>
          )}
        </div>
      </div>

      {/* Loading State */}
      {loading && (
        <div className="flex items-center justify-center py-12">
          <Activity
            className="h-6 w-6 animate-spin"
            style={{ color: 'var(--color-sentinel-amber)' }}
          />
          <span
            className="ml-3 text-sm"
            style={{ color: 'var(--color-sentinel-text-secondary)' }}
          >
            Loading workflow data...
          </span>
        </div>
      )}

      </div>
      )}
    </div>
  );
}

const BASELINE_STATE_LABELS: Record<string, string> = {
  none: 'No baseline — capture baseline readings to enable predictions',
  seed_only: 'Seed baseline only — first PPM readings activate the rolling baseline',
  rolling_active: 'Rolling baseline active',
  locked: 'Baseline locked',
};

function PPMSettingsPanel({ metadata }: { metadata: EquipmentMetadata }) {
  const [intervalInput, setIntervalInput] = useState<string>(
    metadata.service_interval_days != null ? String(metadata.service_interval_days) : ''
  );
  const [saving, setSaving] = useState(false);
  const [saveMessage, setSaveMessage] = useState<string | null>(null);
  const [saveError, setSaveError] = useState<string | null>(null);

  useEffect(() => {
    setIntervalInput(metadata.service_interval_days != null ? String(metadata.service_interval_days) : '');
    setSaveMessage(null);
    setSaveError(null);
  }, [metadata.id, metadata.service_interval_days]);

  const handleSave = async () => {
    const trimmed = intervalInput.trim();
    const parsed = trimmed === '' ? null : Number(trimmed);
    if (parsed !== null && (!Number.isInteger(parsed) || parsed < 1 || parsed > 365)) {
      setSaveError('Interval must be a whole number of days between 1 and 365');
      return;
    }
    setSaving(true);
    setSaveError(null);
    setSaveMessage(null);
    try {
      const result = await api.setEquipmentServiceInterval(metadata.id, parsed);
      setSaveMessage(result.message);
    } catch (err) {
      setSaveError(err instanceof Error ? err.message : 'Failed to save PPM interval');
    } finally {
      setSaving(false);
    }
  };

  const baselineState = metadata.baseline_state ?? 'none';
  const baselineActive = baselineState === 'rolling_active' || baselineState === 'locked';

  return (
    <div
      className="rounded-lg overflow-hidden"
      style={{
        background: 'var(--color-sentinel-bg-panel)',
        border: '1px solid var(--color-sentinel-border)',
      }}
    >
      <div className="p-4" style={{ borderBottom: '1px solid var(--color-sentinel-border)' }}>
        <h3 className="font-medium text-sm" style={{ color: 'var(--color-sentinel-text-primary)' }}>
          Preventive Maintenance
        </h3>
      </div>
      <div className="p-4 grid grid-cols-1 md:grid-cols-2 gap-4 text-xs">
        <div>
          <span style={{ color: 'var(--color-sentinel-text-secondary)' }}>Baseline State</span>
          <p
            className="font-medium mt-0.5"
            style={{ color: baselineActive ? 'var(--color-sentinel-green)' : 'var(--color-sentinel-amber)' }}
          >
            {BASELINE_STATE_LABELS[baselineState] ?? baselineState}
          </p>
          {metadata.last_rollup_at && (
            <p className="mt-0.5" style={{ color: 'var(--color-sentinel-text-secondary)' }}>
              Last rollup: {new Date(metadata.last_rollup_at).toLocaleDateString('en-ZA')}
            </p>
          )}
        </div>
        <div>
          <label style={{ color: 'var(--color-sentinel-text-secondary)' }}>
            PPM Interval (days) — drives the automated preventive work order
          </label>
          <div className="flex items-center gap-2 mt-1">
            <input
              value={intervalInput}
              onChange={(e) => setIntervalInput(e.target.value)}
              type="number"
              min={1}
              max={365}
              placeholder="Type default"
              className="w-28 rounded-lg px-3 py-2 text-sm"
              style={{
                background: 'var(--color-sentinel-bg-secondary)',
                border: '1px solid var(--color-sentinel-border)',
                color: 'var(--color-sentinel-text-primary)',
              }}
            />
            <button
              onClick={() => void handleSave()}
              disabled={saving}
              className="px-3 py-2 text-xs rounded-lg transition-colors disabled:opacity-60"
              style={{
                background: 'rgba(16, 185, 129, 0.2)',
                border: '1px solid rgba(16, 185, 129, 0.45)',
                color: 'var(--color-sentinel-green)',
              }}
            >
              {saving ? 'Saving...' : 'Save'}
            </button>
          </div>
          <p className="mt-1" style={{ color: 'var(--color-sentinel-text-disabled)' }}>
            Leave blank to use the equipment-type default.
          </p>
          {saveMessage && (
            <p className="mt-1" style={{ color: 'var(--color-sentinel-green)' }}>{saveMessage}</p>
          )}
          {saveError && (
            <p className="mt-1" style={{ color: 'var(--color-sentinel-red)' }}>{saveError}</p>
          )}
        </div>
      </div>
    </div>
  );
}

function EquipmentWorkflowDetail({
  workflowState,
  metadata,
  serviceRecords,
  onBack,
  maintenanceActive,
}: {
  workflowState: WorkflowState;
  metadata: EquipmentMetadata | null;
  serviceRecords: ServiceRecord[];
  onBack: () => void;
  maintenanceActive: boolean;
}) {
  // Use createElement to avoid react-hooks/static-components lint error
  const stateIconElement = createElement(getStateIcon(workflowState.current_state), { className: "h-3.5 w-3.5" });

  return (
    <div className="space-y-4">
      {/* Header Panel */}
      <div
        className="rounded-lg overflow-hidden"
        style={{
          background: 'var(--color-sentinel-bg-panel)',
          border: '1px solid var(--color-sentinel-border)',
        }}
      >
        <div className="p-4 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <button
              onClick={onBack}
              className="p-1.5 rounded transition-colors"
              style={{ color: 'var(--color-sentinel-text-secondary)' }}
              onMouseEnter={(e) => e.currentTarget.style.background = 'var(--color-sentinel-bg-secondary)'}
              onMouseLeave={(e) => e.currentTarget.style.background = ''}
            >
              <ArrowLeft className="h-4 w-4" />
            </button>
            <div>
              <h3
                className="font-medium text-sm"
                style={{ color: 'var(--color-sentinel-text-primary)' }}
              >
                {workflowState.equipment_id}
              </h3>
              <span
                className="text-xs"
                style={{ color: 'var(--color-sentinel-text-secondary)' }}
              >
                Workflow Status
              </span>
            </div>
          </div>
          <span
            className="text-xs px-2.5 py-1 rounded-full font-medium flex items-center gap-1.5"
            style={{
              background: getStateBgColor(workflowState.current_state),
              color: getStateColor(workflowState.current_state),
            }}
          >
            {stateIconElement}
            {workflowState.current_state.replace(/_/g, ' ')}
          </span>
        </div>
      </div>

      {/* Summary Stats */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard
          label="Baselines"
          value={String(workflowState.baseline_summary.total_baselines)}
          icon={<TrendingUp className="h-5 w-5" />}
          accentColor="var(--color-sentinel-blue)"
        />
        {maintenanceActive && (
          <StatCard
            label="Last Inspection"
            value={workflowState.inspection_status.status}
            icon={<Calendar className="h-5 w-5" />}
            accentColor="var(--color-sentinel-green)"
          />
        )}
        {workflowState.ml_prediction && (
          <StatCard
            label="Failure Risk"
            value={`${Math.round(workflowState.ml_prediction.failure_probability * 100)}%`}
            icon={<Activity className="h-5 w-5" />}
            accentColor={
              workflowState.ml_prediction.failure_probability > 0.5
                ? 'var(--color-sentinel-red)'
                : workflowState.ml_prediction.failure_probability > 0.2
                ? 'var(--color-sentinel-amber)'
                : 'var(--color-sentinel-green)'
            }
          />
        )}
        {maintenanceActive && (
          <StatCard
            label="Active Repairs"
            value={String(workflowState.active_repairs.length)}
            icon={<Wrench className="h-5 w-5" />}
            accentColor="var(--color-sentinel-amber)"
          />
        )}
      </div>

      {/* Equipment Details */}
      {metadata && (
        <div
          className="rounded-lg overflow-hidden"
          style={{
            background: 'var(--color-sentinel-bg-panel)',
            border: '1px solid var(--color-sentinel-border)',
          }}
        >
          <div
            className="p-4"
            style={{ borderBottom: '1px solid var(--color-sentinel-border)' }}
          >
            <h3
              className="font-medium text-sm"
              style={{ color: 'var(--color-sentinel-text-primary)' }}
            >
              Equipment Details
            </h3>
          </div>
          <div className="p-4 grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-4 text-xs">
            <div>
              <span style={{ color: 'var(--color-sentinel-text-secondary)' }}>Type</span>
              <p style={{ color: 'var(--color-sentinel-text-primary)' }} className="font-medium mt-0.5">{metadata.type}</p>
            </div>
            {metadata.manufacturer && (
              <div>
                <span style={{ color: 'var(--color-sentinel-text-secondary)' }}>Manufacturer</span>
                <p style={{ color: 'var(--color-sentinel-text-primary)' }} className="font-medium mt-0.5">{metadata.manufacturer}</p>
              </div>
            )}
            {metadata.model && (
              <div>
                <span style={{ color: 'var(--color-sentinel-text-secondary)' }}>Model</span>
                <p style={{ color: 'var(--color-sentinel-text-primary)' }} className="font-medium mt-0.5">{metadata.model}</p>
              </div>
            )}
            {metadata.serial_number && (
              <div>
                <span style={{ color: 'var(--color-sentinel-text-secondary)' }}>Serial</span>
                <p style={{ color: 'var(--color-sentinel-text-primary)' }} className="font-medium mt-0.5">{metadata.serial_number}</p>
              </div>
            )}
            {metadata.location && (
              <div>
                <span style={{ color: 'var(--color-sentinel-text-secondary)' }}>Location</span>
                <p style={{ color: 'var(--color-sentinel-text-primary)' }} className="font-medium mt-0.5">{metadata.location}</p>
              </div>
            )}
            {metadata.status && (
              <div>
                <span style={{ color: 'var(--color-sentinel-text-secondary)' }}>Status</span>
                <p style={{ color: 'var(--color-sentinel-text-primary)' }} className="font-medium mt-0.5">{metadata.status}</p>
              </div>
            )}
            {metadata.health_score !== undefined && (
              <div>
                <span style={{ color: 'var(--color-sentinel-text-secondary)' }}>Health</span>
                <p style={{ color: 'var(--color-sentinel-text-primary)' }} className="font-medium mt-0.5">{metadata.health_score}%</p>
              </div>
            )}
            {metadata.install_date && (
              <div>
                <span style={{ color: 'var(--color-sentinel-text-secondary)' }}>Installed</span>
                <p style={{ color: 'var(--color-sentinel-text-primary)' }} className="font-medium mt-0.5">{new Date(metadata.install_date).toLocaleDateString('en-ZA')}</p>
              </div>
            )}
            {metadata.last_service && (
              <div>
                <span style={{ color: 'var(--color-sentinel-text-secondary)' }}>Last Service</span>
                <p style={{ color: 'var(--color-sentinel-text-primary)' }} className="font-medium mt-0.5">{new Date(metadata.last_service).toLocaleDateString('en-ZA')}</p>
              </div>
            )}
          </div>
        </div>
      )}

      {/* Preventive Maintenance — per-asset PPM cadence + baseline lifecycle */}
      {maintenanceActive && metadata && <PPMSettingsPanel metadata={metadata} />}

      {/* Service Records */}
      {serviceRecords.length > 0 && (
        <div
          className="rounded-lg overflow-hidden"
          style={{
            background: 'var(--color-sentinel-bg-panel)',
            border: '1px solid var(--color-sentinel-border)',
          }}
        >
          <div
            className="p-4"
            style={{ borderBottom: '1px solid var(--color-sentinel-border)' }}
          >
            <h3
              className="font-medium text-sm"
              style={{ color: 'var(--color-sentinel-text-primary)' }}
            >
              Service Records ({serviceRecords.length})
            </h3>
          </div>
          <div className="divide-y" style={{ borderColor: 'var(--color-sentinel-border)' }}>
            {serviceRecords.map((rec) => (
              <div key={rec.code} className="p-4 flex items-start justify-between gap-4">
                <div className="min-w-0 flex-1">
                  <p className="text-xs font-medium" style={{ color: 'var(--color-sentinel-text-primary)' }}>
                    {rec.code} — {rec.service_type.replace(/_/g, ' ')}
                  </p>
                  {rec.confirmed_fault && (
                    <p className="text-xs mt-0.5" style={{ color: 'var(--color-sentinel-text-secondary)' }}>
                      Fault: {rec.confirmed_fault}
                    </p>
                  )}
                  {rec.actual_repair && (
                    <p className="text-xs" style={{ color: 'var(--color-sentinel-text-secondary)' }}>
                      Repair: {rec.actual_repair}
                    </p>
                  )}
                </div>
                <div className="flex items-center gap-3 shrink-0">
                  <span className="text-xs" style={{ color: 'var(--color-sentinel-text-secondary)' }}>
                    {rec.technician_name}
                  </span>
                  <span
                    className="text-xs px-2 py-0.5 rounded"
                    style={{
                      background: rec.status === 'completed' ? 'rgba(16, 185, 129, 0.15)' : 'rgba(245, 158, 11, 0.15)',
                      color: rec.status === 'completed' ? 'var(--color-sentinel-green)' : 'var(--color-sentinel-amber)',
                    }}
                  >
                    {rec.status}
                  </span>
                  {rec.completed_at && (
                    <span className="text-xs" style={{ color: 'var(--color-sentinel-text-secondary)' }}>
                      {new Date(rec.completed_at).toLocaleDateString('en-ZA')}
                    </span>
                  )}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Workflow Timeline — maintenance only */}
      {maintenanceActive && (
      <div
        className="rounded-lg overflow-hidden"
        style={{
          background: 'var(--color-sentinel-bg-panel)',
          border: '1px solid var(--color-sentinel-border)',
        }}
      >
        <div
          className="p-4"
          style={{ borderBottom: '1px solid var(--color-sentinel-border)' }}
        >
          <h3
            className="font-medium text-sm"
            style={{ color: 'var(--color-sentinel-text-primary)' }}
          >
            Workflow Timeline
          </h3>
        </div>
        <div className="p-4 space-y-0">
          {workflowState.state_history.map((transition, index) => {
            const isLast = index === workflowState.state_history.length - 1;
            return (
              <div key={index} className="flex gap-3">
                {/* Timeline line + dot */}
                <div className="flex flex-col items-center">
                  <div
                    className="w-2.5 h-2.5 rounded-full shrink-0 mt-1.5"
                    style={{
                      background: isLast
                        ? getStateColor(transition.to)
                        : 'var(--color-sentinel-text-disabled)',
                      boxShadow: isLast ? `0 0 8px ${getStateColor(transition.to)}` : 'none',
                    }}
                  />
                  {!isLast && (
                    <div
                      className="w-px flex-1 my-1"
                      style={{ background: 'var(--color-sentinel-border)' }}
                    />
                  )}
                </div>
                {/* Content */}
                <div className={`pb-4 ${isLast ? '' : ''}`}>
                  <div className="flex items-center gap-2">
                    <span
                      className="text-sm font-medium capitalize"
                      style={{ color: 'var(--color-sentinel-text-primary)' }}
                    >
                      {transition.to.replace(/_/g, ' ')}
                    </span>
                    <span
                      className="text-xs px-1.5 py-0.5 rounded"
                      style={{
                        background: 'var(--color-sentinel-bg-secondary)',
                        color: 'var(--color-sentinel-text-disabled)',
                      }}
                    >
                      from {transition.from.replace(/_/g, ' ')}
                    </span>
                  </div>
                  <span
                    className="text-xs"
                    style={{ color: 'var(--color-sentinel-text-secondary)' }}
                  >
                    {transition.timestamp} &middot; {transition.trigger.replace(/_/g, ' ')}
                  </span>
                </div>
              </div>
            );
          })}
        </div>
      </div>
      )}

      {/* ML Prediction */}
      {workflowState.ml_prediction && workflowState.ml_prediction.failure_probability > 0.1 && (
        <div
          className="rounded-lg overflow-hidden"
          style={{
            background: workflowState.ml_prediction.failure_probability > 0.5
              ? 'linear-gradient(135deg, rgba(220, 38, 38, 0.12) 0%, var(--color-sentinel-bg-panel) 100%)'
              : 'var(--color-sentinel-bg-panel)',
            border: workflowState.ml_prediction.failure_probability > 0.5
              ? '1px solid rgba(220, 38, 38, 0.3)'
              : '1px solid var(--color-sentinel-border)',
          }}
        >
          <div
            className="p-4 flex items-center gap-3"
            style={{ borderBottom: '1px solid var(--color-sentinel-border)' }}
          >
            <div
              className="p-2 rounded"
              style={{ background: 'rgba(245, 158, 11, 0.15)' }}
            >
              <Activity className="h-4 w-4" style={{ color: 'var(--color-sentinel-amber)' }} />
            </div>
            <h3
              className="font-medium text-sm"
              style={{ color: 'var(--color-sentinel-text-primary)' }}
            >
              ML Prediction
            </h3>
          </div>
          <div className="p-4">
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              <div>
                <span
                  className="text-xs uppercase tracking-wider"
                  style={{ color: 'var(--color-sentinel-text-secondary)' }}
                >
                  Failure Probability
                </span>
                <div
                  className="text-2xl font-bold mt-1"
                  style={{
                    color: workflowState.ml_prediction.failure_probability > 0.5
                      ? 'var(--color-sentinel-red)'
                      : 'var(--color-sentinel-amber)',
                  }}
                >
                  {Math.round(workflowState.ml_prediction.failure_probability * 100)}%
                </div>
                <span
                  className="text-xs"
                  style={{ color: 'var(--color-sentinel-text-secondary)' }}
                >
                  within {workflowState.ml_prediction.timeframe}
                </span>
              </div>
              <div>
                <span
                  className="text-xs uppercase tracking-wider"
                  style={{ color: 'var(--color-sentinel-text-secondary)' }}
                >
                  Confidence
                </span>
                <div
                  className="text-sm font-medium mt-1 capitalize"
                  style={{ color: 'var(--color-sentinel-text-primary)' }}
                >
                  {workflowState.ml_prediction.confidence}
                </div>
              </div>
              <div>
                <span
                  className="text-xs uppercase tracking-wider"
                  style={{ color: 'var(--color-sentinel-text-secondary)' }}
                >
                  Explanation
                </span>
                <p
                  className="text-sm mt-1"
                  style={{ color: 'var(--color-sentinel-text-primary)' }}
                >
                  {workflowState.ml_prediction.explanation}
                </p>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Recent Inspection — maintenance only */}
      {maintenanceActive && workflowState.inspection_status && (
        <div
          className="rounded-lg overflow-hidden"
          style={{
            background: 'var(--color-sentinel-bg-panel)',
            border: '1px solid var(--color-sentinel-border)',
          }}
        >
          <div
            className="p-4 flex items-center gap-3"
            style={{ borderBottom: '1px solid var(--color-sentinel-border)' }}
          >
            <div
              className="p-2 rounded"
              style={{ background: 'rgba(16, 185, 129, 0.15)' }}
            >
              <Calendar className="h-4 w-4" style={{ color: 'var(--color-sentinel-green)' }} />
            </div>
            <h3
              className="font-medium text-sm"
              style={{ color: 'var(--color-sentinel-text-primary)' }}
            >
              Recent Inspection
            </h3>
          </div>
          <div className="p-4">
            <div className="space-y-3">
              <div className="flex items-center justify-between">
                <span
                  className="text-sm"
                  style={{ color: 'var(--color-sentinel-text-secondary)' }}
                >
                  Date
                </span>
                <span
                  className="text-sm font-medium"
                  style={{ color: 'var(--color-sentinel-text-primary)' }}
                >
                  {workflowState.inspection_status.last_inspection}
                </span>
              </div>
              <div
                className="h-px"
                style={{ background: 'var(--color-sentinel-border)' }}
              />
              <div className="flex items-center justify-between">
                <span
                  className="text-sm"
                  style={{ color: 'var(--color-sentinel-text-secondary)' }}
                >
                  Status
                </span>
                <span
                  className="text-xs px-2 py-0.5 rounded-full font-medium uppercase"
                  style={{
                    background: workflowState.inspection_status.status === 'pass'
                      ? 'rgba(16, 185, 129, 0.15)'
                      : 'rgba(245, 158, 11, 0.15)',
                    color: workflowState.inspection_status.status === 'pass'
                      ? 'var(--color-sentinel-green)'
                      : 'var(--color-sentinel-amber)',
                  }}
                >
                  {workflowState.inspection_status.status}
                </span>
              </div>
              <div
                className="h-px"
                style={{ background: 'var(--color-sentinel-border)' }}
              />
              <div>
                <span
                  className="text-xs uppercase tracking-wider"
                  style={{ color: 'var(--color-sentinel-text-secondary)' }}
                >
                  Findings
                </span>
                <p
                  className="text-sm mt-1"
                  style={{ color: 'var(--color-sentinel-text-primary)' }}
                >
                  {workflowState.inspection_status.findings}
                </p>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Active Repairs - Service Feedback — maintenance only */}
      {maintenanceActive && workflowState.active_repairs && workflowState.active_repairs.length > 0 && (
        <div
          className="rounded-lg overflow-hidden"
          style={{
            background: 'var(--color-sentinel-bg-panel)',
            border: '1px solid var(--color-sentinel-border)',
          }}
        >
          <div
            className="p-4 flex items-center gap-3"
            style={{ borderBottom: '1px solid var(--color-sentinel-border)' }}
          >
            <div
              className="p-2 rounded"
              style={{ background: 'rgba(59, 130, 246, 0.15)' }}
            >
              <Wrench className="h-4 w-4" style={{ color: 'var(--color-sentinel-blue)' }} />
            </div>
            <h3
              className="font-medium text-sm"
              style={{ color: 'var(--color-sentinel-text-primary)' }}
            >
              Active Repairs
            </h3>
          </div>
          <div className="p-4 space-y-3">
            {workflowState.active_repairs.map((repair) => (
              <div
                key={repair.id}
                className="p-3 rounded-lg flex items-center justify-between"
                style={{
                  background: 'var(--color-sentinel-bg-secondary)',
                  border: '1px solid var(--color-sentinel-border)',
                }}
              >
                <div>
                  <div className="flex items-center gap-2">
                    <span
                      className="text-sm font-medium"
                      style={{ color: 'var(--color-sentinel-text-primary)' }}
                    >
                      {repair.title}
                    </span>
                    <span
                      className="text-xs px-2 py-0.5 rounded-full uppercase"
                      style={{
                        background: repair.priority === 'urgent' || repair.priority === 'high'
                          ? 'rgba(220, 38, 38, 0.15)'
                          : 'rgba(245, 158, 11, 0.15)',
                        color: repair.priority === 'urgent' || repair.priority === 'high'
                          ? 'var(--color-sentinel-red)'
                          : 'var(--color-sentinel-amber)',
                      }}
                    >
                      {repair.priority}
                    </span>
                  </div>
                  <span
                    className="text-xs"
                    style={{ color: 'var(--color-sentinel-text-secondary)' }}
                  >
                    {repair.id} &middot; {repair.status}
                  </span>
                </div>
                <div
                  className="text-xs px-3 py-1.5 rounded flex items-center gap-1.5"
                  style={{
                    background: 'rgba(59, 130, 246, 0.15)',
                    color: 'var(--color-sentinel-blue)',
                  }}
                >
                  <Clock className="h-3.5 w-3.5" />
                  Awaiting Service Feedback
                </div>
              </div>
            ))}
            <p
              className="text-xs mt-2"
              style={{ color: 'var(--color-sentinel-text-secondary)' }}
            >
              Technicians submit service feedback via SENTRY bot after completing repairs.
              Feedback includes readings, photos, and observations that update equipment health.
            </p>
          </div>
        </div>
      )}

      {/* Deviation Warning */}
      {workflowState.baseline_summary.deviation_detected && (
        <div
          className="rounded-lg overflow-hidden p-4 flex items-start gap-3"
          style={{
            background: 'rgba(245, 158, 11, 0.1)',
            border: '1px solid rgba(245, 158, 11, 0.3)',
          }}
        >
          <AlertTriangle
            className="h-5 w-5 shrink-0 mt-0.5"
            style={{ color: 'var(--color-sentinel-amber)' }}
          />
          <div>
            <h4
              className="text-sm font-medium"
              style={{ color: 'var(--color-sentinel-amber)' }}
            >
              Baseline Deviation Detected
            </h4>
            <p
              className="text-sm mt-1"
              style={{ color: 'var(--color-sentinel-text-secondary)' }}
            >
              Significant deviation from baseline detected. Automated inspection task has been created.
            </p>
          </div>
        </div>
      )}
    </div>
  );
}

function StatCard({
  label,
  value,
  icon,
  accentColor,
}: {
  label: string;
  value: string;
  icon: React.ReactNode;
  accentColor: string;
}) {
  return (
    <div
      className="rounded-lg p-4"
      style={{
        background: 'var(--color-sentinel-bg-panel)',
        border: '1px solid var(--color-sentinel-border)',
      }}
    >
      <div className="flex items-start justify-between">
        <div>
          <span
            className="text-xs uppercase tracking-wider"
            style={{ color: 'var(--color-sentinel-text-secondary)' }}
          >
            {label}
          </span>
          <div
            className="text-xl font-bold mt-1 capitalize"
            style={{ color: 'var(--color-sentinel-text-primary)' }}
          >
            {value}
          </div>
        </div>
        <div
          className="p-2 rounded"
          style={{ background: `${accentColor}20`, color: accentColor }}
        >
          {icon}
        </div>
      </div>
    </div>
  );
}

export default AssetWorkflowDashboard;
