import React, { useState, useEffect } from 'react';
import {
  Card,
  Title,
  Text,
  Button,
  Grid,
  Col,
  Badge,
  Flex,
  ListItem,
  List,
  Bold,
  Callout
} from '@tremor/react';
import {
  CheckCircle2,
  AlertTriangle,
  XCircle,
  Clock,
  TrendingUp,
  Activity,
  Calendar,
  FileText,
  Wrench
} from 'lucide-react';

// Types
interface WorkflowState {
  equipment_id: string;
  current_state: string;
  state_history: StateTransition[];
  baseline_summary: BaselineSummary;
  inspection_status: InspectionStatus;
  ml_prediction: MLPrediction | null;
  active_repairs: WorkOrder[];
}

interface StateTransition {
  from: string;
  to: string;
  timestamp: string;
  trigger: string;
}

interface BaselineSummary {
  total_baselines: number;
  latest_baseline: string;
  deviation_detected: boolean;
}

interface InspectionStatus {
  last_inspection: string;
  status: string;
  findings: string;
}

interface MLPrediction {
  failure_probability: number;
  timeframe: string;
  confidence: string;
  explanation: string;
}

interface WorkOrder {
  id: string;
  title: string;
  priority: string;
  status: string;
}

interface Equipment {
  equipment_id: string;
  name: string;
  type: string;
  current_state: string;
}

// Mock data (will be replaced with API calls)
const mockEquipment: Equipment[] = [
  {
    equipment_id: 'chiller-001',
    name: 'Main Chiller',
    type: 'chiller',
    current_state: 'healthy'
  },
  {
    equipment_id: 'generator-002',
    name: 'Standby Generator #2',
    type: 'generator',
    current_state: 'healthy'
  },
  {
    equipment_id: 'ahu-003',
    name: 'Level 3 AHU',
    type: 'ahu',
    current_state: 'anomaly_detected'
  }
];

const mockWorkflowState: Record<string, WorkflowState> = {
  'chiller-001': {
    equipment_id: 'chiller-001',
    current_state: 'healthy',
    state_history: [
      { from: 'onboarding', to: 'monitoring', timestamp: '2025-08-01', trigger: 'baseline_captured' },
      { from: 'monitoring', to: 'anomaly_detected', timestamp: '2026-01-01', trigger: 'ml_prediction' },
      { from: 'anomaly_detected', to: 'inspection_pending', timestamp: '2026-01-01', trigger: 'automated_task' },
      { from: 'inspection_pending', to: 'deficiency_found', timestamp: '2026-01-15', trigger: 'inspection_complete' },
      { from: 'deficiency_found', to: 'repair_in_progress', timestamp: '2026-01-16', trigger: 'work_order_created' },
      { from: 'repair_in_progress', to: 'validation_pending', timestamp: '2026-01-20', trigger: 'repair_complete' },
      { from: 'validation_pending', to: 'healthy', timestamp: '2026-01-20', trigger: 'effectiveness_validated' }
    ],
    baseline_summary: {
      total_baselines: 4,
      latest_baseline: '2026-01-20',
      deviation_detected: false
    },
    inspection_status: {
      last_inspection: '2026-01-22',
      status: 'pass',
      findings: 'Post-repair verification. Vibration back to normal (1.9 mm/s).'
    },
    ml_prediction: {
      failure_probability: 0.05,
      timeframe: '90 days',
      confidence: 'high',
      explanation: 'All parameters within normal range. No anomalies detected.'
    },
    active_repairs: []
  },
  'generator-002': {
    equipment_id: 'generator-002',
    current_state: 'healthy',
    state_history: [
      { from: 'onboarding', to: 'monitoring', timestamp: '2018-03-15', trigger: 'baseline_captured' }
    ],
    baseline_summary: {
      total_baselines: 2,
      latest_baseline: '2026-01-10',
      deviation_detected: false
    },
    inspection_status: {
      last_inspection: '2026-01-10',
      status: 'pass',
      findings: 'All values within normal range. No issues detected.'
    },
    ml_prediction: {
      failure_probability: 0.05,
      timeframe: '90 days',
      confidence: 'high',
      explanation: 'All parameters within normal range. No anomalies detected.'
    },
    active_repairs: []
  },
  'ahu-003': {
    equipment_id: 'ahu-003',
    current_state: 'anomaly_detected',
    state_history: [
      { from: 'onboarding', to: 'monitoring', timestamp: '2019-06-10', trigger: 'baseline_captured' },
      { from: 'monitoring', to: 'anomaly_detected', timestamp: '2026-01-28', trigger: 'ml_prediction' },
      { from: 'anomaly_detected', to: 'inspection_pending', timestamp: '2026-01-28', trigger: 'automated_task' }
    ],
    baseline_summary: {
      total_baselines: 2,
      latest_baseline: '2026-01-28',
      deviation_detected: true
    },
    inspection_status: {
      last_inspection: '2026-01-28',
      status: 'scheduled',
      findings: 'ML detected fan motor bearing degradation. Verify and inspect.'
    },
    ml_prediction: {
      failure_probability: 0.72,
      timeframe: '14 days',
      confidence: 'medium',
      explanation: 'Fan motor showing early signs of bearing degradation. Vibration up 73% with elevated current draw.'
    },
    active_repairs: []
  }
};

export function AssetWorkflowDashboard() {
  const [equipment] = useState<Equipment[]>(mockEquipment);
  const [selectedEquipment, setSelectedEquipment] = useState<string | null>(null);
  const [workflowState, setWorkflowState] = useState<WorkflowState | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (selectedEquipment) {
      setLoading(true);
      // Simulate API call
      setTimeout(() => {
        setWorkflowState(mockWorkflowState[selectedEquipment] || null);
        setLoading(false);
      }, 500);
    }
  }, [selectedEquipment]);

  const getStateColor = (state: string) => {
    switch (state) {
      case 'healthy': return 'emerald';
      case 'anomaly_detected': return 'amber';
      case 'inspection_pending': return 'amber';
      case 'deficiency_found': return 'rose';
      case 'repair_in_progress': return 'blue';
      case 'validation_pending': return 'blue';
      default: return 'gray';
    }
  };

  const getStateIcon = (state: string) => {
    switch (state) {
      case 'healthy': return CheckCircle2;
      case 'anomaly_detected': return AlertTriangle;
      case 'inspection_pending': return Clock;
      case 'deficiency_found': return XCircle;
      case 'repair_in_progress': return Wrench;
      case 'validation_pending': return Activity;
      default: return Activity;
    }
  };

  return (
    <div className="p-6 bg-gray-50 min-h-screen">
      <div className="max-w-7xl mx-auto">
        <div className="mb-6">
          <Title>Asset Management Workflow</Title>
          <Text className="mt-2">
            Complete visibility from onboarding through repair validation
          </Text>
        </div>

        {/* Equipment Grid */}
        <div className="mb-8">
          <h3 className="text-lg font-semibold mb-4">Equipment Fleet</h3>
          <Grid numCols={1} numColsMd={2} numColsLg={3} className="gap-4">
            {equipment.map((eq) => {
              const StateIcon = getStateIcon(eq.current_state);
              return (
                <Card
                  key={eq.equipment_id}
                  className="cursor-pointer hover:shadow-lg transition-shadow"
                  onClick={() => setSelectedEquipment(eq.equipment_id)}
                >
                  <Flex justifyContent="space-between" alignItems="center">
                    <div>
                      <Text>{eq.type}</Text>
                      <Title className="mt-1">{eq.name}</Title>
                      <Text className="text-sm text-gray-500">{eq.equipment_id}</Text>
                    </div>
                    <Badge
                      color={getStateColor(eq.current_state)}
                      icon={StateIcon}
                      size="lg"
                    >
                      {eq.current_state.replace(/_/g, ' ')}
                    </Badge>
                  </Flex>
                </Card>
              );
            })}
          </Grid>
        </div>

        {/* Selected Equipment Detail */}
        {selectedEquipment && !loading && workflowState && (
          <EquipmentWorkflowDetail workflowState={workflowState} />
        )}
      </div>
    </div>
  );
}

function EquipmentWorkflowDetail({ workflowState }: { workflowState: WorkflowState }) {
  const StateIcon = getStateIcon(workflowState.current_state);
  
  return (
    <div className="space-y-6">
      {/* Header */}
      <Card>
        <Flex justifyContent="space-between" alignItems="center">
          <div>
            <Title>{workflowState.equipment_id}</Title>
            <Text className="text-sm text-gray-500">Workflow Status</Text>
          </div>
          <Badge
            color={getStateColor(workflowState.current_state)}
            icon={StateIcon}
            size="lg"
          >
            {workflowState.current_state.replace(/_/g, ' ')}
          </Badge>
        </Flex>
      </Card>

      {/* Summary Stats */}
      <Grid numCols={1} numColsMd={2} numColsLg={4} className="gap-4">
        <Card>
          <Flex justifyContent="space-between" alignItems="start">
            <div>
              <Text>Baselines</Text>
              <Title className="mt-2">{workflowState.baseline_summary.total_baselines}</Title>
            </div>
            <TrendingUp className="text-gray-400" />
          </Flex>
        </Card>

        <Card>
          <Flex justifyContent="space-between" alignItems="start">
            <div>
              <Text>Last Inspection</Text>
              <Title className="mt-2">{workflowState.inspection_status.status}</Title>
            </div>
            <Calendar className="text-gray-400" />
          </Flex>
        </Card>

        {workflowState.ml_prediction && (
          <Card>
            <Flex justifyContent="space-between" alignItems="start">
              <div>
                <Text>Failure Risk</Text>
                <Title className="mt-2">
                  {Math.round(workflowState.ml_prediction.failure_probability * 100)}%
                </Title>
              </div>
              <Activity className="text-gray-400" />
            </Flex>
          </Card>
        )}

        <Card>
          <Flex justifyContent="space-between" alignItems="start">
            <div>
              <Text>Active Repairs</Text>
              <Title className="mt-2">{workflowState.active_repairs.length}</Title>
            </div>
            <Wrench className="text-gray-400" />
          </Flex>
        </Card>
      </Grid>

      {/* State History Timeline */}
      <Card>
        <Title className="mb-4">Workflow Timeline</Title>
        <List>
          {workflowState.state_history.map((transition, index) => (
            <ListItem key={index}>
              <div>
                <Text>{transition.to.replace(/_/g, ' ')}</Text>
                <Text className="text-sm text-gray-500">
                  {transition.timestamp} - Triggered by {transition.trigger.replace(/_/g, ' ')}
                </Text>
              </div>
              <Badge color="gray" size="sm">
                {transition.from.replace(/_/g, ' ')}
              </Badge>
            </ListItem>
          ))}
        </List>
      </Card>

      {/* ML Prediction */}
      {workflowState.ml_prediction && workflowState.ml_prediction.failure_probability > 0.1 && (
        <Card>
          <Title className="mb-4">ML Prediction</Title>
          <div className="space-y-4">
            <div>
              <Text className="text-sm text-gray-500">Failure Probability</Text>
              <Title className="mt-1">
                {Math.round(workflowState.ml_prediction.failure_probability * 100)}%
              </Title>
              <Text className="text-sm">
                within {workflowState.ml_prediction.timeframe}
              </Text>
              <Badge color="blue" size="sm" className="ml-2">
                {workflowState.ml_prediction.confidence} confidence
              </Badge>
            </div>
            <div>
              <Text className="text-sm text-gray-500">Explanation</Text>
              <Text className="mt-1">{workflowState.ml_prediction.explanation}</Text>
            </div>
          </div>
        </Card>
      )}

      {/* Recent Inspection */}
      {workflowState.inspection_status && (
        <Card>
          <Title className="mb-4">Recent Inspection</Title>
          <div className="space-y-2">
            <Flex justifyContent="space-between">
              <Text>Date</Text>
              <Bold>{workflowState.inspection_status.last_inspection}</Bold>
            </Flex>
            <Flex justifyContent="space-between">
              <Text>Status</Text>
              <Badge
                color={workflowState.inspection_status.status === 'pass' ? 'emerald' : 'rose'}
              >
                {workflowState.inspection_status.status}
              </Badge>
            </Flex>
            <div>
              <Text className="text-sm text-gray-500">Findings</Text>
              <Text className="mt-1">{workflowState.inspection_status.findings}</Text>
            </div>
          </div>
        </Card>
      )}

      {/* Deviation Warning */}
      {workflowState.baseline_summary.deviation_detected && (
        <Callout
          title="Baseline Deviation Detected"
          icon={AlertTriangle}
          color="amber"
        >
          Significant deviation from baseline detected. Automated inspection task has been created.
        </Callout>
      )}
    </div>
  );
}

function getStateColor(state: string): any {
  switch (state) {
    case 'healthy': return 'emerald';
    case 'anomaly_detected': return 'amber';
    case 'inspection_pending': return 'amber';
    case 'deficiency_found': return 'rose';
    case 'repair_in_progress': return 'blue';
    case 'validation_pending': return 'blue';
    default: return 'gray';
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
