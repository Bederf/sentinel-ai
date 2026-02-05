import { useState, useEffect, useCallback, useMemo } from 'react';
import {
  CheckCircle2,
  AlertTriangle,
  XCircle,
  Clock,
  TrendingUp,
  Activity,
  Calendar,
  Wrench,
  Shield,
  ChevronRight,
  ArrowLeft,
  RefreshCw,
} from 'lucide-react';
import {
  workflowApi,
  type WorkflowEquipmentItem,
  type WorkflowState,
} from '../lib/api';

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

export function AssetWorkflowDashboard() {
  const [equipment, setEquipment] = useState<Equipment[]>([]);
  const [workflowStates, setWorkflowStates] = useState<Record<string, WorkflowState>>({});
  const [selectedEquipment, setSelectedEquipment] = useState<string | null>(null);
  const [workflowState, setWorkflowState] = useState<WorkflowState | null>(null);
  const [loading, setLoading] = useState(false);
  const [initialLoading, setInitialLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Fetch equipment list and workflow states from API
  const fetchDashboardData = useCallback(async () => {
    try {
      setError(null);
      const data = await workflowApi.getDashboardEquipment();
      setEquipment(data.equipment);
      setWorkflowStates(data.workflow_states);
    } catch (err) {
      console.error('Failed to fetch workflow dashboard data:', err);
      setError('Failed to load equipment data');
    } finally {
      setInitialLoading(false);
    }
  }, []);

  // Initial fetch
  useEffect(() => {
    fetchDashboardData();
  }, [fetchDashboardData]);

  // When equipment is selected, get its workflow state from the cached data
  useEffect(() => {
    if (selectedEquipment) {
      setLoading(true);
      // Use cached workflow state from initial fetch
      const state = workflowStates[selectedEquipment];
      if (state) {
        setWorkflowState(state);
      } else {
        setWorkflowState(null);
      }
      setLoading(false);
    }
  }, [selectedEquipment, workflowStates]);

  // Show initial loading state
  if (initialLoading) {
    return (
      <div
        className="h-full overflow-y-auto p-4 md:p-6 flex items-center justify-center"
        style={{ background: 'var(--color-sentinel-bg-canvas)' }}
      >
        <div className="flex items-center gap-3">
          <Activity
            className="h-6 w-6 animate-spin"
            style={{ color: 'var(--color-sentinel-blue)' }}
          />
          <span style={{ color: 'var(--color-sentinel-text-secondary)' }}>
            Loading equipment workflow data...
          </span>
        </div>
      </div>
    );
  }

  return (
    <div
      className="h-full overflow-y-auto p-4 md:p-6"
      style={{ background: 'var(--color-sentinel-bg-canvas)' }}
    >
      {/* Page Header */}
      <div className="mb-6">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3 mb-1">
            <div
              className="p-2 rounded"
              style={{ background: 'rgba(59, 130, 246, 0.15)' }}
            >
              <Shield className="h-5 w-5" style={{ color: 'var(--color-sentinel-blue)' }} />
            </div>
            <div>
              <h1
                className="text-lg font-semibold"
                style={{ color: 'var(--color-sentinel-text-primary)' }}
              >
                Asset Management Workflow
              </h1>
              <p
                className="text-sm"
                style={{ color: 'var(--color-sentinel-text-secondary)' }}
              >
                Complete visibility from onboarding through repair validation
              </p>
            </div>
          </div>
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
        </div>
      </div>

      {/* Error State */}
      {error && (
        <div
          className="rounded-md p-4 mb-6 flex items-center gap-3"
          style={{
            background: 'rgba(220, 38, 38, 0.1)',
            border: '1px solid rgba(220, 38, 38, 0.3)',
          }}
        >
          <XCircle className="h-5 w-5" style={{ color: 'var(--color-sentinel-red)' }} />
          <span style={{ color: 'var(--color-sentinel-text-primary)' }}>{error}</span>
        </div>
      )}

      {/* Equipment Fleet Panel */}
      <div
        className="rounded-md overflow-hidden mb-6"
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
              {equipment.length} total
            </span>
          </div>
          <span
            className="text-xs px-2 py-1 rounded"
            style={{
              background: 'rgba(16, 185, 129, 0.15)',
              color: 'var(--color-sentinel-green)',
            }}
          >
            {equipment.filter(e => e.current_state === 'healthy').length} healthy
          </span>
        </div>

        {/* Equipment Grid */}
        <div className="p-4">
          {equipment.length === 0 ? (
            <div className="text-center py-8">
              <Activity
                className="h-8 w-8 mx-auto mb-3"
                style={{ color: 'var(--color-sentinel-text-disabled)' }}
              />
              <p style={{ color: 'var(--color-sentinel-text-secondary)' }}>
                No equipment found. Equipment will appear here once added to the system.
              </p>
            </div>
          ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {equipment.map((eq) => {
              const StateIcon = getStateIcon(eq.current_state);
              const isSelected = selectedEquipment === eq.equipment_id;
              return (
                <div
                  key={eq.equipment_id}
                  className="p-4 rounded-md cursor-pointer transition-all"
                  style={{
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
                  onClick={() => setSelectedEquipment(eq.equipment_id)}
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
                </div>
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

      {/* Selected Equipment Detail */}
      {selectedEquipment && !loading && workflowState && (
        <EquipmentWorkflowDetail
          workflowState={workflowState}
          onBack={() => setSelectedEquipment(null)}
        />
      )}
    </div>
  );
}

function EquipmentWorkflowDetail({
  workflowState,
  onBack,
}: {
  workflowState: WorkflowState;
  onBack: () => void;
}) {
  // Get icon component and render it - must use useMemo to avoid creating component during render
  const stateIconElement = useMemo(() => {
    const IconComponent = getStateIcon(workflowState.current_state);
    return <IconComponent className="h-3.5 w-3.5" />;
  }, [workflowState.current_state]);

  return (
    <div className="space-y-4">
      {/* Header Panel */}
      <div
        className="rounded-md overflow-hidden"
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
        <StatCard
          label="Last Inspection"
          value={workflowState.inspection_status.status}
          icon={<Calendar className="h-5 w-5" />}
          accentColor="var(--color-sentinel-green)"
        />
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
        <StatCard
          label="Active Repairs"
          value={String(workflowState.active_repairs.length)}
          icon={<Wrench className="h-5 w-5" />}
          accentColor="var(--color-sentinel-amber)"
        />
      </div>

      {/* Workflow Timeline */}
      <div
        className="rounded-md overflow-hidden"
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

      {/* ML Prediction */}
      {workflowState.ml_prediction && workflowState.ml_prediction.failure_probability > 0.1 && (
        <div
          className="rounded-md overflow-hidden"
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

      {/* Recent Inspection */}
      {workflowState.inspection_status && (
        <div
          className="rounded-md overflow-hidden"
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

      {/* Active Repairs - Service Feedback */}
      {workflowState.active_repairs && workflowState.active_repairs.length > 0 && (
        <div
          className="rounded-md overflow-hidden"
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
                className="p-3 rounded-md flex items-center justify-between"
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
              Technicians submit service feedback via Clawd bot after completing repairs.
              Feedback includes readings, photos, and observations that update equipment health.
            </p>
          </div>
        </div>
      )}

      {/* Deviation Warning */}
      {workflowState.baseline_summary.deviation_detected && (
        <div
          className="rounded-md overflow-hidden p-4 flex items-start gap-3"
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
      className="rounded-md p-4"
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
